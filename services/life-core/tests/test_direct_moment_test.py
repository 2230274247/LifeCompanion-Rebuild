from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image

from test_api import bootstrap, make_app
from test_memory_pipeline import auth


class FakeImageProvider:
    def generate(self, request):
        from app.image_provider import GeneratedImage
        output = BytesIO()
        Image.new("RGB", (96, 96), (49, 90, 72)).save(output, format="PNG")
        return GeneratedImage(output.getvalue(), "image/png", 96, 96, "fake")


def enable_direct_test(app, username="shiguang_admin"):
    app.state.moments.settings = replace(
        app.state.moments.settings,
        direct_moment_test_enabled=True,
        direct_moment_test_username=username,
        direct_moment_test_unlimited=True,
    )
    app.state.moments.provider = FakeImageProvider()


def authorize(client, user="lc-user-a"):
    response = client.patch(
        "/api/v1/me/settings",
        headers=auth(user),
        json={
            "memory_consent": True, "image_consent": True, "recall_consent": True,
            "sensitive_consent": True, "notification_consent": True,
        },
    )
    assert response.status_code == 200


def test_direct_test_is_limited_to_configured_admin_account(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        authorize(client)
        enable_direct_test(app, username="shiguang-admin")
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)
        body = {
            "conversation_id": "conversation-admin",
            "source_message_id": "message-admin",
            "text": "今天在阳台给薄荷浇水，阳光很暖。",
        }
        status = client.get("/api/v1/test/direct-moment", headers=auth())
        assert status.status_code == 200
        assert status.json()["enabled"] is False
        post = client.post("/api/v1/test/direct-moment", headers=auth(), json=body)
        assert post.status_code == 403
        assert post.json()["detail"]["code"] == "ADMIN_DIRECT_TEST_REQUIRED"


def test_direct_test_memory_and_image_use_declared_response_shapes(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        admin_id = "6aebe2cbf985b8e48d7a4d08"
        bootstrap(
            client,
            user_id=admin_id,
            memos_user="users/shiguang-admin",
        )
        authorize(client, admin_id)
        enable_direct_test(app, username="shiguang-admin")
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)
        writes = []
        monkeypatch.setattr(
            app.state.memos,
            "create_private_memo",
            lambda event: writes.append(event["event_id"]) or f"memos/{event['event_id']}",
        )
        monkeypatch.setattr(
            app.state.memos,
            "get_private_memo",
            lambda memo_ref, creator: {
                "content": "# 测试回忆\n\n测试正文",
                "tags": ["生活回忆"],
            },
        )
        body = {
            "conversation_id": "conversation-admin",
            "source_message_id": "message-admin",
            "text": "今天在阳台给薄荷浇水，阳光很暖。",
            "action": "memory",
        }

        memory = client.post("/api/v1/test/direct-moment", headers=auth(admin_id), json=body)
        assert memory.status_code == 200
        assert set(memory.json()) >= {"memory", "test_mode"}
        assert memory.json()["memory"]["memory_id"].startswith("mem_")
        assert memory.json()["memory"]["status"] == "published"
        assert memory.json()["memory"]["memo_ref"].startswith("memos/")
        listed = client.get("/api/v1/memories", headers=auth(admin_id))
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["memories"][0]["event_id"] == memory.json()["memory"]["event_id"]

        body["action"] = "image"
        image = client.post("/api/v1/test/direct-moment", headers=auth(admin_id), json=body)
        assert image.status_code == 200
        assert set(image.json()) >= {"moment", "test_mode"}
        assert image.json()["moment"]["status"] == "generated"

        # A completed image must not make a later memory action return the moment.
        body["source_message_id"] = "message-admin-second"
        image = client.post("/api/v1/test/direct-moment", headers=auth(admin_id), json=body)
        assert image.status_code == 200
        assert image.json()["moment"]["status"] == "generated"

        body["action"] = "memory"
        memory = client.post("/api/v1/test/direct-moment", headers=auth(admin_id), json=body)
        assert memory.status_code == 200
        assert set(memory.json()) >= {"memory", "test_mode"}
        assert memory.json()["memory"]["memory_id"].startswith("mem_")
        assert memory.json()["memory"]["status"] == "published"
        assert len(writes) == 2


def test_admin_can_publish_a_moment_to_memories_but_normal_user_cannot(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        admin_id = "6aebe2cbf985b8e48d7a4d08"
        normal_id = "lc-user-normal"
        bootstrap(client, user_id=admin_id, memos_user="users/shiguang-admin")
        bootstrap(client, user_id=normal_id, memos_user="users/normal")
        authorize(client, admin_id)
        authorize(client, normal_id)
        enable_direct_test(app, username="shiguang-admin")
        monkeypatch.setattr("app.main.verify_draft_source", lambda *_args: None)
        writes = []
        monkeypatch.setattr(
            app.state.memos,
            "create_private_memo",
            lambda event: writes.append(event["event_id"]) or f"memos/{event['event_id']}",
        )
        monkeypatch.setattr(
            app.state.memos,
            "get_private_memo",
            lambda memo_ref, creator: {
                "content": "# 测试回忆\n\n测试正文",
                "tags": ["生活回忆"],
            },
        )
        image = client.post(
            "/api/v1/test/direct-moment",
            headers=auth(admin_id),
            json={
                "conversation_id": "conversation-admin",
                "source_message_id": "message-to-publish",
                "text": "傍晚给阳台的薄荷浇水，叶子被夕阳照得发亮。",
                "action": "image",
            },
        )
        assert image.status_code == 200
        moment_id = image.json()["moment"]["moment_id"]

        forbidden = client.post(
            f"/api/v1/moments/{moment_id}/publish", headers=auth(normal_id)
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"]["code"] == "ADMIN_DIRECT_TEST_REQUIRED"

        first = client.post(f"/api/v1/moments/{moment_id}/publish", headers=auth(admin_id))
        second = client.post(f"/api/v1/moments/{moment_id}/publish", headers=auth(admin_id))
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["memory"]["event_id"] == second.json()["memory"]["event_id"]
        assert first.json()["memory"]["status"] == "published"
        assert len(writes) == 1

        listed = client.get("/api/v1/memories", headers=auth(admin_id))
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["memories"][0]["event_id"] == first.json()["memory"]["event_id"]
        assert listed.json()["memories"][0]["has_image"] is True
        assert listed.json()["memories"][0]["media"]["ai_generated"] is True
        assert listed.json()["memories"][0]["media"]["thumbnail_data"].startswith("data:image/")

        detail = client.get(
            f"/api/v1/memories/{first.json()['memory']['event_id']}", headers=auth(admin_id)
        )
        assert detail.status_code == 200
        assert detail.json()["memory"]["media"]["image_data"].startswith("data:image/")
