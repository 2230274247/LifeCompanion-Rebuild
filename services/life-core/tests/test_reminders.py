from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx

from app.reminders import ReminderService
from app.reminder_chat import ReminderChat
from app.store import Store
from test_api import bootstrap, make_app, token_for


def user_mapping():
    life_id = "life_" + hashlib.sha256(b"lc-user-a").hexdigest()[:20]
    return life_id, {
        "api_token": "tk_scoped-user-token",
        "project_id": 7,
        "vikunja_user_id": 17,
        "webhook_secret": "test-webhook-secret",
        "ntfy_base_url": "http://ntfy.test",
        "ntfy_topic": "private-user-topic",
        "ntfy_user": "topic-writer",
        "ntfy_password": "topic-password",
    }


def test_reminder_crud_uses_scoped_vikunja_api(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    requests = []
    remote_task = {
        "id": 912, "title": "喝龙井",
        "reminders": [{"reminder": "2026-11-03T01:00:00Z"}],
    }

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs["headers"]["Authorization"], kwargs.get("json")))
        if method == "POST":
            remote_task.update(kwargs["json"])
            return httpx.Response(
                200,
                json={"id": 912, "title": kwargs["json"]["title"]},
                request=httpx.Request(method, url),
            )
        if method == "GET":
            return httpx.Response(
                200,
                json={"items": [remote_task]} if url.endswith("/tasks") else remote_task,
                request=httpx.Request(method, url),
            )
        if method == "PUT":
            remote_task.update(kwargs["json"])
            return httpx.Response(
                200,
                json={"id": 912, "title": kwargs["json"]["title"]},
                request=httpx.Request(method, url),
            )
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr("app.reminders.httpx.request", fake_request)
    with client:
        bootstrap(client)
        app.state.settings = replace(app.state.settings, vikunja_users={life_id: mapping})
        app.state.reminders = ReminderService(app.state.store, app.state.settings)
        headers = {"Authorization": f"Bearer {token_for('lc-user-a')}"}
        consent = client.patch(
            "/api/v1/me/settings", headers=headers, json={"notification_consent": True}
        )
        assert consent.status_code == 200
        created = client.post(
            "/api/v1/reminders",
            headers=headers,
            json={"title": "喝龙井", "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
        )
        assert created.status_code == 200
        reminder = created.json()["reminder"]
        assert reminder["status"] == "scheduled"
        assert "upstream_task_id" not in reminder

        updated = client.patch(
            f"/api/v1/reminders/{reminder['reminder_id']}",
            headers=headers,
            json={"title": "喝西湖龙井"},
        )
        assert updated.status_code == 200
        assert updated.json()["reminder"]["title"] == "喝西湖龙井"

        listed = client.get("/api/v1/reminders", headers=headers)
        assert len(listed.json()["reminders"]) == 1
        assert listed.json()["reminders"][0]["title"] == "喝西湖龙井"

        completed = client.patch(
            f"/api/v1/reminders/{reminder['reminder_id']}",
            headers=headers, json={"done": True},
        )
        assert completed.status_code == 200
        assert completed.json()["reminder"]["status"] == "completed"
        assert remote_task["done"] is True
        cancelled = client.delete(
            f"/api/v1/reminders/{reminder['reminder_id']}", headers=headers
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["reminder"]["status"] == "cancelled"
        assert {"POST", "GET", "PUT", "DELETE"} <= {item[0] for item in requests}
        assert all(item[2] == "Bearer tk_scoped-user-token" for item in requests)

        bootstrap(client, user_id="lc-user-b", memos_user="users/b")
        other = client.get(
            "/api/v1/reminders",
            headers={"Authorization": f"Bearer {token_for('lc-user-b')}"},
        )
        assert other.status_code == 200
        assert other.json()["reminders"] == []


def test_signed_reminder_webhook_is_deduplicated_and_delivered(monkeypatch, tmp_path):
    app, _client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    sent = []

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.reminders.httpx.post", fake_post)
    payload = {
        "event_name": "task.reminder.fired",
        "time": "2026-11-02T14:00:00Z",
        "data": {
            "task": {"id": 912, "title": "喝龙井"},
            "user": {"id": 17},
            "reminder": {"reminder": "2026-11-03T01:00:00Z"},
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(
        mapping["webhook_secret"].encode(), raw_body, hashlib.sha256
    ).hexdigest()

    with _client:
        settings = replace(app.state.settings, vikunja_users={life_id: mapping})
        service = ReminderService(app.state.store, settings)
        app.state.store.bootstrap_user(
            librechat_user_id="lc-user-a",
            memos_user_id="users/a",
            memos_username="a",
            display_name="A",
        )
        app.state.memory.set_permissions(life_id, {"notification_consent": True})
        app.state.store.create_reminder(
            owner_user_id=life_id,
            upstream_task_id=912,
            title="喝龙井",
            scheduled_at="2026-11-03T01:00:00+00:00",
            timezone="Asia/Hong_Kong",
        )
        assert service.handle_webhook(raw_body, "invalid-signature") is False
        assert service.handle_webhook(raw_body, signature) is True
        assert service.handle_webhook(raw_body, signature) is True
        assert len(sent) == 1
        assert sent[0][0] == "http://ntfy.test/private-user-topic"
        assert sent[0][1]["auth"] == ("topic-writer", "topic-password")
        with app.state.store.connect() as db:
            row = db.execute("SELECT status FROM reminder_notifications").fetchone()
        assert row["status"] == "accepted"


def test_future_timezone_validation_and_notification_permission(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    remote = monkeypatch.setattr(
        "app.reminders.httpx.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call upstream")),
    )
    with client:
        bootstrap(client)
        app.state.reminders = ReminderService(
            app.state.store, replace(app.state.settings, vikunja_users={life_id: mapping})
        )
        headers = {"Authorization": f"Bearer {token_for('lc-user-a')}"}
        valid = {"title": "synthetic", "scheduled_at": "2099-11-03T09:00:00+08:00"}
        assert client.post("/api/v1/reminders", headers=headers, json=valid).status_code == 403
        for changes in (
            {"scheduled_at": "2020-01-01T09:00:00Z"},
            {"scheduled_at": "2099-11-03T09:00:00"},
            {"timezone": "Unknown/Place"},
        ):
            assert client.post(
                "/api/v1/reminders", headers=headers, json={**valid, **changes}
            ).status_code == 422


def test_notification_claim_is_atomic_and_restart_recovers(tmp_path):
    store = Store(tmp_path / "claim.sqlite3")
    store.initialize()
    store.queue_reminder_notification(event_id="one", owner_user_id="isolated", payload={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.next_reminder_notification(), range(2)))
    assert sum(item is not None for item in claims) == 1
    store.initialize()
    recovered = store.next_reminder_notification()
    assert recovered["event_id"] == "one"
    store.fail_reminder_notification("one")
    assert store.next_reminder_notification() is None


def test_chat_action_is_idempotent_and_plan_without_reminder_is_not_executed(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    calls = []
    with client:
        user = bootstrap(client)
        app.state.memory.set_permissions(life_id, {"notification_consent": True})
        settings = replace(app.state.settings, vikunja_users={life_id: mapping})
        service = ReminderService(app.state.store, settings)
        chat = ReminderChat(app.state.store, settings, service)

        def run(owner, text):
            calls.append((owner, text))
            return {"handled": True, "status": "succeeded", "message": "confirmed"}

        monkeypatch.setattr(chat, "_run", run)
        assert chat.execute(user, "plan", "明天去公园") == {"handled": False}
        first = chat.execute(user, "source-1", "明天9点提醒我喝茶")
        assert chat.execute(user, "source-1", "明天9点提醒我喝茶") == first
        assert len(calls) == 1
        assert chat.execute(user, "source-1", "明天10点提醒我喝茶")["status"] == "clarify"
        assert len(calls) == 1


def test_chat_create_accepts_provider_null_clarification(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    with client:
        bootstrap(client)
        app.state.memory.set_permissions(life_id, {"notification_consent": True})
        settings = replace(
            app.state.settings, vikunja_users={life_id: mapping}, memory_llm_key="test"
        )
        service = ReminderService(app.state.store, settings)
        chat = ReminderChat(app.state.store, settings, service)
        monkeypatch.setattr(service, "list", lambda _: [])
        created = []

        def create(owner, **values):
            created.append((owner, values))
            return {
                "title": values["title"],
                "scheduled_at": values["scheduled_at"].isoformat(),
            }

        monkeypatch.setattr(service, "create", create)
        monkeypatch.setattr(
            "app.reminder_chat.httpx.post",
            lambda *args, **kwargs: httpx.Response(
                200, request=httpx.Request("POST", "https://provider.test"),
                json={"choices": [{"message": {"content": json.dumps({
                    "action": "create", "title": "喝茶",
                    "scheduled_at": "2099-11-03T09:00:00+08:00",
                    "reminder_id": None, "clarification": None,
                })}}]},
            ),
        )
        assert chat._run(life_id, "明天九点提醒我喝茶")["status"] == "succeeded"
        assert len(created) == 1


def test_chat_cancel_remains_available_after_notification_consent_is_withdrawn(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    life_id, mapping = user_mapping()
    with client:
        user = bootstrap(client)
        settings = replace(
            app.state.settings, vikunja_users={life_id: mapping}, memory_llm_key="test"
        )
        service = ReminderService(app.state.store, settings)
        reminder = {
            "reminder_id": "owned-reminder", "title": "喝茶", "status": "scheduled",
            "scheduled_at": "2099-11-03T09:00:00+08:00",
        }
        monkeypatch.setattr(service, "list", lambda _: [reminder])
        cancelled = []

        def cancel(owner, reminder_id):
            cancelled.append((owner, reminder_id))
            return {**reminder, "status": "cancelled"}

        monkeypatch.setattr(service, "cancel", cancel)
        monkeypatch.setattr(
            "app.reminder_chat.httpx.post",
            lambda *args, **kwargs: httpx.Response(
                200, request=httpx.Request("POST", "https://provider.test"),
                json={"choices": [{"message": {"content": json.dumps({
                    "action": "cancel", "title": "喝茶", "scheduled_at": None,
                    "reminder_id": "owned-reminder", "clarification": None,
                })}}]},
            ),
        )
        chat = ReminderChat(app.state.store, settings, service)
        assert chat.execute(user, "withdrawn-cancel", "取消喝茶提醒")["status"] == "succeeded"
        assert cancelled == [(life_id, "owned-reminder")]
