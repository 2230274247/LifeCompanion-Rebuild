from datetime import UTC, datetime, timedelta
import hashlib
from types import SimpleNamespace

import httpx
import pytest

from app.reminders import ReminderService
from app.store import Store


@pytest.fixture
def service(tmp_path):
    store = Store(tmp_path / "reminders.sqlite3")
    store.initialize()
    with store.connect() as db:
        db.execute("CREATE TABLE memory_permissions (user_id TEXT PRIMARY KEY, notification_consent INTEGER)")
        db.executemany("INSERT INTO memory_permissions VALUES (?, 1)", [("a",), ("b",)])
    return ReminderService(store, SimpleNamespace(vikunja_users={
        owner: {"api_token": "synthetic", "project_id": index,
                "ntfy_base_url": "http://ntfy.invalid", "ntfy_topic": owner,
                "ntfy_user": owner, "ntfy_password": "synthetic"}
        for index, owner in enumerate(("a", "b"), 1)
    }))


def reminder(service, when):
    return service.store.create_reminder(
        owner_user_id="a", title="synthetic", scheduled_at=when.isoformat(),
        timezone="UTC", upstream_task_id=42)


def queue(service, when):
    event_id = hashlib.sha256(f"a:42:{when.isoformat()}".encode()).hexdigest()
    service.store.queue_reminder_notification(
        event_id=event_id, owner_user_id="a",
        payload={"data": {"task": {"id": 42, "title": "synthetic"}}})
    return event_id


def test_rescheduled_notification_is_suppressed_before_http(service, monkeypatch):
    old = datetime.now(UTC) - timedelta(minutes=1)
    row = reminder(service, old)
    event_id = queue(service, old)
    service.store.update_reminder(row["reminder_id"], "a", title="synthetic",
                                  scheduled_at=(old + timedelta(days=1)).isoformat(),
                                  timezone="UTC")
    sent = []
    monkeypatch.setattr("app.reminders.httpx.post", lambda *args, **kwargs: sent.append(args))
    assert service.deliver_one_notification() is False
    assert sent == []
    with service.store.connect() as db:
        assert db.execute("SELECT status FROM reminder_notifications WHERE event_id=?",
                          (event_id,)).fetchone()[0] == "suppressed"


def test_reconcile_reads_each_owner_once(service, monkeypatch):
    owners = []
    def request(config, *args, **kwargs):
        owners.append(config["ntfy_user"])
        return httpx.Response(200, json={"items": []})
    monkeypatch.setattr(service, "_request", request)
    assert service.reconcile_all() == (2, 0)
    assert owners == ["a", "b"]


def test_delayed_upstream_notification_recovers_after_restart(service, monkeypatch):
    when = datetime.now(UTC) - timedelta(minutes=5)
    reminder(service, when)
    notification = {"name": "task.reminder", "created": (when + timedelta(seconds=7)).isoformat(),
                    "notification": {"task": {"id": 42, "title": "synthetic"}}}
    monkeypatch.setattr(service, "_request",
                        lambda *args, **kwargs: httpx.Response(200, json={"items": [notification]}))
    service.reconcile_notifications()
    with service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM reminder_notifications").fetchone()[0] == 1


def test_early_notification_waits_until_planned_time(service, monkeypatch):
    when = datetime.now(UTC) + timedelta(seconds=25)
    reminder(service, when)
    notification = {"name": "task.reminder", "created": datetime.now(UTC).isoformat(),
                    "notification": {"task": {"id": 42, "title": "synthetic"}}}
    monkeypatch.setattr(service, "_request",
                        lambda *args, **kwargs: httpx.Response(200, json={"items": [notification]}))
    service.reconcile_notifications()
    assert service.store.next_reminder_notification() is None
