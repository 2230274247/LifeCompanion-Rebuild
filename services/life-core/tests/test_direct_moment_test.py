from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from app.recollection_policy import CONSENT_VERSION
from test_api import bootstrap, make_app
from test_memory_pipeline import auth
from test_v023_moments import FakeImageProvider


def enable_direct_test(app, *, unlimited=False):
    app.state.moments.settings = replace(
        app.state.moments.settings,
        direct_moment_test_enabled=True,
        direct_moment_test_username="a",
        direct_moment_test_unlimited=unlimited,
        moment_image_provider="kolors",
        moment_image_model="Kwai-Kolors/Kolors",
        moment_image_request_budget=1,
    )
    app.state.moments.provider = FakeImageProvider()


def authorize(client):
    response = client.patch(
        "/api/v1/me/settings",
        headers=auth(),
        json={"memory_consent": True, "image_consent": True},
    )
    assert response.status_code == 200
    response = client.put(
        "/api/v1/moment-egress-consents/image_generation",
        headers=auth(),
        json={
            "provider": "kolors",
            "granted": True,
            "consent_version": CONSENT_VERSION,
        },
    )
    assert response.status_code == 200


def test_direct_test_bypasses_pipeline_but_keeps_source_and_budget(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app)
        calls = []

        def verify_source(request, conversation, source, text):
            calls.append((conversation, source, text))

        monkeypatch.setattr("app.main.verify_draft_source", verify_source)
        body = {
            "conversation_id": "conversation-direct",
            "source_message_id": "message-direct",
            "text": "今天下午给阳台上的多肉换土，手指沾满泥，阳光很暖。",
        }
        first = client.post(
            "/api/v1/test/direct-moment", headers=auth(), json=body
        )
        assert first.status_code == 200
        moment = first.json()["moment"]
        assert first.json()["test_mode"] == "DIRECT_TEST_BYPASS"
        assert moment["status"] == "generated"
        assert moment["display_kind"] == "IMAGE"
        assert moment["media"]["width"] == 64
        assert moment["selection"][0]["reason_code"] == "DIRECT_TEST_BYPASS"
        assert calls == [(
            body["conversation_id"],
            body["source_message_id"],
            body["text"],
        )]
        with app.state.store.connect() as db:
            event = db.execute(
                "SELECT status FROM events WHERE source_type='chat_direct_test'"
            ).fetchone()
        assert event["status"] == "direct_test"
        with app.state.store.connect() as db:
            db.execute(
                "UPDATE events SET status='published' "
                "WHERE source_type='chat_direct_test'"
            )
        memories = client.get("/api/v1/memories", headers=auth())
        assert memories.status_code == 200
        assert memories.json()["memories"] == []

        second = client.post(
            "/api/v1/test/direct-moment", headers=auth(), json=body
        )
        assert second.status_code == 200
        assert second.json()["moment"]["moment_id"] == moment["moment_id"]
        with app.state.store.connect() as db:
            assert db.execute(
                "SELECT count(*) FROM recollection_image_calls"
            ).fetchone()[0] == 1

        different = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(),
            json={**body, "source_message_id": "message-direct-2"},
        )
        assert different.status_code == 409
        assert different.json()["detail"]["code"] == "DIRECT_TEST_IMAGE_BUDGET"


def test_direct_test_unlimited_skips_budget_for_fixed_account_only(
    tmp_path, monkeypatch
):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app, unlimited=True)
        calls = []
        app.state.moments.provider.callback = lambda: calls.append(1)
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)

        status = client.get("/api/v1/test/direct-moment", headers=auth())
        assert status.status_code == 200
        assert status.json()["unlimited"] is True

        body = {
            "conversation_id": "conversation-unlimited",
            "source_message_id": "message-unlimited-1",
            "text": "今天在阳台给薄荷浇水，水珠落在叶子上。",
        }
        first = client.post(
            "/api/v1/test/direct-moment", headers=auth(), json=body
        )
        assert first.status_code == 200
        retry = client.post(
            "/api/v1/test/direct-moment", headers=auth(), json=body
        )
        assert retry.status_code == 200
        assert retry.json()["moment"]["moment_id"] == first.json()["moment"]["moment_id"]
        assert calls == [1]

        second = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(),
            json={**body, "source_message_id": "message-unlimited-2"},
        )
        assert second.status_code == 200
        assert calls == [1, 1]

        status = client.get("/api/v1/test/direct-moment", headers=auth())
        assert status.status_code == 200
        assert status.json() == {
            "enabled": True,
            "provider_ready": True,
            "budget": 1,
            "used": 2,
            "remaining": 0,
            "unlimited": True,
            "mode": "DIRECT_TEST_BYPASS",
        }


def test_direct_test_verifies_source_through_configured_librechat(
    tmp_path, monkeypatch
):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app, unlimited=True)
        provider_calls = []
        app.state.moments.provider.callback = lambda: provider_calls.append(1)
        requests = []
        body = {
            "conversation_id": "conversation-source",
            "source_message_id": "message-source",
            "text": "今天在窗边给薄荷浇水。",
        }

        def get_source(url, **kwargs):
            requests.append((url, kwargs))
            return httpx.Response(
                200,
                json={
                    "messages": [{
                        "messageId": body["source_message_id"],
                        "isCreatedByUser": True,
                        "text": body["text"],
                    }]
                },
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr("app.main.httpx.get", get_source)
        response = client.post(
            "/api/v1/test/direct-moment", headers=auth(), json=body
        )
        assert response.status_code == 200
        assert requests[0][0] == (
            app.state.settings.librechat_base_url + "/api/messages"
        )
        assert requests[0][1]["params"] == {
            "conversationId": body["conversation_id"],
            "messageId": body["source_message_id"],
        }
        assert provider_calls == [1]


def test_direct_test_stops_before_provider_when_source_upstream_fails(
    tmp_path, monkeypatch
):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app, unlimited=True)
        provider_calls = []
        app.state.moments.provider.callback = lambda: provider_calls.append(1)
        monkeypatch.setattr(
            "app.main.httpx.get",
            lambda url, **_kwargs: httpx.Response(
                401, request=httpx.Request("GET", url)
            ),
        )
        response = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(),
            json={
                "conversation_id": "conversation-source",
                "source_message_id": "message-source",
                "text": "今天在窗边给薄荷浇水。",
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "SOURCE_VERIFICATION_UNAVAILABLE"
        assert provider_calls == []


def test_direct_test_is_limited_to_configured_account(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client, "lc-user-b", "users/b")
        authorize(client)
        enable_direct_test(app)
        monkeypatch.setattr(
            "app.main.verify_draft_source",
            lambda *_args: pytest.fail("source verification must not run"),
        )
        response = client.get(
            "/api/v1/test/direct-moment",
            headers=auth("lc-user-b"),
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        post = client.post(
            "/api/v1/test/direct-moment",
            headers=auth("lc-user-b"),
            json={
                "conversation_id": "conversation-b",
                "source_message_id": "message-b",
                "text": "今天在窗边整理书架。",
            },
        )
        assert post.status_code == 403
        assert post.json()["detail"]["code"] == "DIRECT_TEST_ACCOUNT_REQUIRED"


def test_direct_test_unlimited_still_requires_egress_authorization(
    tmp_path, monkeypatch
):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch(
            "/api/v1/me/settings",
            headers=auth(),
            json={"memory_consent": True, "image_consent": True},
        )
        enable_direct_test(app, unlimited=True)
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)
        response = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(),
            json={
                "conversation_id": "conversation-no-egress",
                "source_message_id": "message-no-egress",
                "text": "今天傍晚在公园散步。",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "DIRECT_TEST_EGRESS_NOT_AUTHORIZED"


def test_direct_test_keeps_privacy_gate(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app)
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)
        response = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(),
            json={
                "conversation_id": "conversation-private",
                "source_message_id": "message-private",
                "text": "今天收到诊断报告，医生说结果稳定。",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "DIRECT_TEST_PRIVATE_SOURCE"
        with app.state.store.connect() as db:
            assert db.execute(
                "SELECT count(*) FROM recollection_image_calls"
            ).fetchone()[0] == 0


def test_direct_test_separates_event_chat_and_display_times(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app, unlimited=True)
        user = app.state.store.get_user_by_librechat_id("lc-user-a")
        moment = app.state.moments.create_direct_test(
            user,
            "message-time-separation",
            "conversation-time-separation",
            "今天早上六点起床去公园跑步，跑完后觉得精神很好。",
            datetime(2026, 11, 4, 11, 45, tzinfo=timezone.utc),
        )
        assert moment["event_at"] == "2026-11-04T06:00:00+08:00"
        assert moment["message_at"] == "2026-11-04T19:45:00+08:00"
        assert moment["display_slot"] == "晚间"
