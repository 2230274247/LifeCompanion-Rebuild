from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest

from app.provisioning import protect, unprotect
from app.reminder_drafts import preview
from test_api import make_app, token_for

TEXT = "我明天从义乌坐高铁，早上的高铁，能不能提前1小时提醒我赶车？"
NOW = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)


def fields(**changes):
    return {"title": "赶高铁", "event_date": "2026-11-04", "event_time": "09:30",
            "timezone": "Asia/Shanghai", "lead_minutes": 60, **changes}


@pytest.mark.parametrize("changes,missing", [
    ({"event_time": None}, ["event_time"]),
    ({"event_date": None}, ["event_date"]),
    ({"timezone": None}, ["timezone"]),
    ({"lead_minutes": None}, ["lead_minutes"]),
])
def test_missing_fields_are_not_guessed(changes, missing):
    assert preview(fields(**changes), NOW) == (missing, None)


@pytest.mark.parametrize("changes,expected", [
    ({}, "2026-11-04T08:30:00+08:00"),
    ({"event_time": "10:15"}, "2026-11-04T09:15:00+08:00"),
    ({"event_time": "00:30"}, "2026-11-03T23:30:00+08:00"),
])
def test_deterministic_time_and_previous_day(changes, expected):
    assert preview(fields(**changes), NOW)[1]["scheduled_at"] == expected


@pytest.mark.parametrize("changes,error", [
    ({"event_date": "2026-11-03", "event_time": "09:20"}, "REMINDER_TIME_IN_PAST"),
    ({"timezone": "Wrong/Zone"}, "INVALID_TIMEZONE"),
    ({"timezone": "America/New_York", "event_date": "2027-03-14", "event_time": "02:30"},
     "NONEXISTENT_LOCAL_TIME"),
    ({"timezone": "America/New_York", "event_date": "2027-11-07", "event_time": "01:30"},
     "AMBIGUOUS_LOCAL_TIME"),
])
def test_invalid_times(changes, error):
    with pytest.raises(ValueError, match=error):
        preview(fields(**changes), NOW)


def test_windows_credential_vault_encrypts_and_roundtrips():
    secret = {"api_token": "synthetic-secret", "password": "synthetic-password"}
    value = protect(secret)
    assert "synthetic" not in value
    assert unprotect(value) == secret


def test_ambiguous_reference_returns_owner_conversation_choices_without_execution(tmp_path):
    app, client = make_app(tmp_path)
    headers = {"Authorization": f"Bearer {token_for('ordinary-c')}"}
    with client:
        owner = client.get("/api/v1/me", headers=headers).json()["life_user_id"]
        drafts = app.state.reminder_drafts
        first = drafts.create(owner, "conversation-c", "first", TEXT)
        second = drafts.create(owner, "conversation-c", "second", TEXT)
        drafts.create(owner, "other-conversation", "third", TEXT)
        result = app.state.reminder_chat.execute(
            {"life_user_id": owner}, "reference", "取消刚才那个提醒", "conversation-c")
        assert result["status"] == "needs_input"
        reference = drafts.get(owner, result["draft_id"])
        assert {item["draft_id"] for item in reference["reference_options"]} == {
            first["draft_id"], second["draft_id"]}
        response = client.patch("/api/v1/reminder-drafts/" + result["draft_id"],
                                headers={**headers, "If-Match": "1"}, json={"event_time": "09:30"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "REFERENCE_SELECTION_ONLY"
        assert app.state.store.list_reminders(owner) == []


def test_deleted_source_blocks_confirmation(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    headers = {"Authorization": f"Bearer {token_for('ordinary-c')}"}
    monkeypatch.setattr("app.main.httpx.get", lambda *args, **kwargs: httpx.Response(404))
    with client:
        owner = client.get("/api/v1/me", headers=headers).json()["life_user_id"]
        draft = app.state.reminder_drafts.create(
            owner, "conversation-c", "deleted-source", TEXT, fields=fields(event_date="2099-11-04"))
        result = client.post("/api/v1/reminder-drafts/" + draft["draft_id"] + "/confirm",
                             headers=headers, json={"revision": 1, "idempotency_key": "deleted-source"})
        assert result.status_code == 409
        assert result.json()["detail"]["code"] == "SOURCE_MESSAGE_UNAVAILABLE"
        assert app.state.store.list_reminders(owner) == []


def test_real_draft_lifecycle_owner_revision_concurrency_and_recovery(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    a = {"Authorization": f"Bearer {token_for('ordinary-c')}"}
    b = {"Authorization": f"Bearer {token_for('ordinary-d')}"}
    requests = []
    tasks = []

    def upstream(method, url, **kwargs):
        requests.append((method, url))
        if method == "POST":
            task = {"id": len(tasks) + 1, **kwargs["json"]}
            tasks.append(task)
            return httpx.Response(200, json=task)
        return httpx.Response(200, json={"items": tasks})

    monkeypatch.setattr("app.reminders.httpx.request", upstream)
    monkeypatch.setattr("app.main.httpx.get", lambda url, **kwargs: httpx.Response(
        200, json=[{"messageId": url.rsplit("/", 1)[-1], "isCreatedByUser": True, "text": TEXT}]))
    with client:
        owner = client.get("/api/v1/me", headers=a).json()["life_user_id"]
        client.get("/api/v1/me", headers=b)
        app.state.settings.vikunja_users[owner] = {
            "api_token": "synthetic", "project_id": 1, "vikunja_user_id": 1}
        body = {"conversation_id": "conversation-c", "source_message_id": "message-c", "text": TEXT}
        draft = client.post("/api/v1/reminder-drafts", headers=a, json=body).json()
        identifier = draft["draft_id"]
        path = "/api/v1/reminder-drafts/" + identifier
        assert draft["missing_fields"] == ["event_time"]
        assert draft["timezone"] == "Asia/Shanghai" and draft["lead_minutes"] == 60
        assert requests == []
        assert client.post("/api/v1/reminder-drafts", headers=a, json=body).json()["draft_id"] == identifier
        assert client.get("/api/v1/reminder-drafts?conversation_id=conversation-c", headers=b).json()["drafts"] == []
        assert client.patch(path, headers={**b, "If-Match": "1"}, json={"event_time": "09:30"}).status_code == 404
        ready = client.patch(path, headers={**a, "If-Match": "1"}, json={"event_time": "09:30"})
        assert ready.status_code == 200 and ready.json()["status"] == "ready_to_confirm"
        assert ready.json()["preview"]["scheduled_at"].endswith("08:30:00+08:00")
        assert client.patch(path, headers={**a, "If-Match": "1"}, json={"event_time": "10:15"}).status_code == 409
        assert client.patch(path, headers={**a, "If-Match": "2"}, json={"owner_id": "other"}).status_code == 422
        command = {"revision": 2, "idempotency_key": "test-key-one"}
        assert client.post(path + "/confirm", headers=a, json=command).status_code == 403
        client.patch("/api/v1/me/settings", headers=a, json={"notification_consent": True})
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: client.post(path + "/confirm", headers=a, json=command), range(2)))
        assert all(x.status_code == 200 for x in results)
        assert len(tasks) == 1
        assert client.post(path + "/confirm", headers=a, json=command).json()["status"] == "scheduled"
        assert len(tasks) == 1
        second = client.post("/api/v1/reminder-drafts", headers=a, json={**body, "source_message_id": "message-other"}).json()
        assert second["draft_id"] != identifier
        assert client.delete("/api/v1/reminder-drafts/" + second["draft_id"], headers=a).json()["status"] == "cancelled"

        third = client.post("/api/v1/reminder-drafts", headers=a, json={**body, "source_message_id": "message-crash"}).json()
        third_path = "/api/v1/reminder-drafts/" + third["draft_id"]
        client.patch(third_path, headers={**a, "If-Match": "1"}, json={"event_time": "09:30"})
        original = app.state.store.create_reminder
        monkeypatch.setattr(app.state.store, "create_reminder", lambda **_: (_ for _ in ()).throw(OSError("synthetic crash")))
        unknown = client.post(third_path + "/confirm", headers=a, json={"revision": 2, "idempotency_key": "crash-key"})
        assert unknown.json()["status"] == "unknown"
        assert len(tasks) == 2
        assert client.post(third_path + "/confirm", headers=a, json={"revision": 2, "idempotency_key": "crash-key"}).json()["status"] == "unknown"
        assert len(tasks) == 2
        monkeypatch.setattr(app.state.store, "create_reminder", original)
        reconciled = client.post(third_path + "/reconcile", headers=a)
        assert reconciled.json()["status"] == "scheduled"
        assert len(tasks) == 2
