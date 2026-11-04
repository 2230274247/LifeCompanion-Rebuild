from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest

from app.reminder_drafts import ReminderDrafts
from app.reminders import ReminderPermissionError
from test_api import make_app, token_for


@pytest.fixture
def business(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    tasks, calls = {}, []

    def remote(method, url, **kwargs):
        calls.append(method)
        if method == "POST":
            task = {"id": len(tasks) + 1, **kwargs["json"]}
            tasks[task["id"]] = task
            return httpx.Response(200, json=task)
        if method == "PUT":
            task = kwargs["json"]
            tasks[task["id"]] = task
            return httpx.Response(200, json=task)
        if method == "DELETE":
            tasks.pop(int(url.rsplit("/", 1)[1]), None)
            return httpx.Response(204)
        if url.rsplit("/", 1)[1].isdigit():
            return httpx.Response(200, json=tasks[int(url.rsplit("/", 1)[1])])
        return httpx.Response(200, json={"items": list(tasks.values())})

    monkeypatch.setattr("app.reminders.httpx.request", remote)
    with client:
        owner = client.get("/api/v1/me", headers={
            "Authorization": "Bearer " + token_for("business-owner"),
        }).json()["life_user_id"]
        app.state.settings.vikunja_users[owner] = {
            "api_token": "synthetic", "project_id": 1, "vikunja_user_id": 1}
        yield app, owner, tasks, calls


def draft_for(app, owner):
    return app.state.reminder_drafts.create(
        owner, "synthetic-conversation", "synthetic-source",
        "2099-11-04提醒我带绿色U盘，不是银色的",
        fields={"title": "green not silver", "event_date": "2099-11-04",
                "event_time": None, "timezone": "Asia/Hong_Kong", "lead_minutes": 0})


def test_missing_information_is_a_durable_interrupt_and_resumes_after_restart(business):
    app, owner, tasks, calls = business
    draft = draft_for(app, owner)
    snapshot = app.state.reminder_drafts.workflow.snapshot(owner, draft["draft_id"])
    assert snapshot["next"] == ["collect_missing"] and snapshot["interrupted"]
    assert tasks == {}
    restarted = ReminderDrafts(app.state.store, app.state.settings, app.state.reminders)
    ready = restarted.patch(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    snapshot = restarted.workflow.snapshot(owner, draft["draft_id"])
    assert snapshot["next"] == ["await_confirmation"] and snapshot["interrupted"]
    assert ready["revision"] == 2 and calls == []


def test_authorization_is_rechecked_in_graph_and_double_confirmation_creates_once(business):
    app, owner, tasks, calls = business
    draft = draft_for(app, owner)
    drafts = app.state.reminder_drafts
    drafts.patch(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    with pytest.raises(ReminderPermissionError):
        drafts.confirm(owner, draft["draft_id"], 2, "same-operation")
    assert calls == []
    app.state.memory.set_permissions(owner, {"notification_consent": True})
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(
            lambda _: drafts.confirm(owner, draft["draft_id"], 2, "same-operation"), range(2)))
    assert all(value["status"] == "scheduled" for value in results)
    assert calls.count("POST") == 1 and len(tasks) == 1
    snapshot = drafts.workflow.snapshot(owner, draft["draft_id"])
    assert snapshot["next"] == ["active"] and snapshot["interrupted"]


def test_unknown_remote_success_recovers_without_reposting(business, monkeypatch):
    app, owner, tasks, calls = business
    app.state.memory.set_permissions(owner, {"notification_consent": True})
    draft = draft_for(app, owner)
    drafts = app.state.reminder_drafts
    drafts.patch(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    create = app.state.store.create_reminder
    monkeypatch.setattr(app.state.store, "create_reminder",
                        lambda **_: (_ for _ in ()).throw(OSError("synthetic projection failure")))
    assert drafts.confirm(owner, draft["draft_id"], 2, "unknown-operation")["status"] == "unknown"
    assert drafts.workflow.snapshot(owner, draft["draft_id"])["next"] == ["unknown"]
    monkeypatch.setattr(app.state.store, "create_reminder", create)
    restarted = ReminderDrafts(app.state.store, app.state.settings, app.state.reminders)
    assert restarted.reconcile(owner, draft["draft_id"])["status"] == "scheduled"
    assert calls.count("POST") == 1 and len(tasks) == 1
    assert restarted.workflow.snapshot(owner, draft["draft_id"])["next"] == ["active"]


def test_update_and_cancel_keep_original_id_and_durable_versions(business):
    app, owner, tasks, calls = business
    app.state.memory.set_permissions(owner, {"notification_consent": True})
    draft = draft_for(app, owner)
    drafts = app.state.reminder_drafts
    scheduled = drafts.select(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    reminder_id = scheduled["reminder"]["reminder_id"]
    assert scheduled["reminder"]["revision"] == 1
    updated = app.state.reminders.update(
        owner, reminder_id, title="updated qualifier", scheduled_at=datetime(
            2099, 11, 5, 10, tzinfo=timezone.utc), timezone_name="UTC")
    assert updated["reminder_id"] == reminder_id and updated["revision"] == 2
    assert drafts.workflow.snapshot(owner, draft["draft_id"])["next"] == ["active"]
    assert drafts.get(owner, draft["draft_id"])["title"] == "updated qualifier"
    assert drafts.get(owner, draft["draft_id"])["preview"]["scheduled_at"] == updated["scheduled_at"]
    revision = drafts.get(owner, draft["draft_id"])["revision"]
    repeated = app.state.reminders.update(
        owner, reminder_id, title="updated qualifier", scheduled_at=datetime(
            2099, 11, 5, 10, tzinfo=timezone.utc), timezone_name="UTC")
    assert repeated["revision"] == 2 and calls.count("PUT") == 1
    assert drafts.get(owner, draft["draft_id"])["revision"] == revision
    cancelled = drafts.cancel(owner, draft["draft_id"])
    assert cancelled["status"] == "cancelled" and cancelled["reminder"]["revision"] == 3
    assert drafts.workflow.snapshot(owner, draft["draft_id"])["next"] == []
    assert drafts.cancel(owner, draft["draft_id"])["reminder"]["revision"] == 3
    assert calls.count("DELETE") == 1


def test_cross_owner_cannot_resume_another_workflow(business):
    app, owner, tasks, calls = business
    draft = draft_for(app, owner)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        app.state.reminder_drafts.patch("different-owner", draft["draft_id"], 1,
                                       {"event_time": "09:00"})
    assert exc.value.status_code == 404
    assert tasks == {} and calls == []


def test_legacy_checkpoint_upgrades_without_replaying_old_action(business):
    from typing import TypedDict
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    class LegacyState(TypedDict):
        owner_id: str
        draft_id: str
        action: str
        revision: int

    app, owner, tasks, calls = business
    draft = draft_for(app, owner)
    thread = f"reminder:{owner}:{draft['draft_id']}"
    legacy = StateGraph(LegacyState)
    legacy.add_node("record_transition", lambda state: {})
    legacy.add_edge(START, "record_transition")
    legacy.add_edge("record_transition", END)
    with SqliteSaver.from_conn_string(str(app.state.store.database_path)) as saver:
        saver.delete_thread(thread)
        legacy.compile(checkpointer=saver).invoke(
            {"owner_id": owner, "draft_id": draft["draft_id"], "action": "committing", "revision": 1},
            config={"configurable": {"thread_id": thread}})
    restarted = ReminderDrafts(app.state.store, app.state.settings, app.state.reminders)
    ready = restarted.patch(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    assert ready["status"] == "ready_to_confirm" and calls == []
    snapshot = restarted.workflow.snapshot(owner, draft["draft_id"])
    assert snapshot["values"]["workflow_version"] == 2
    assert snapshot["next"] == ["await_confirmation"]


def test_cancelled_workflow_rejects_further_field_changes(business):
    from fastapi import HTTPException
    app, owner, tasks, calls = business
    draft = draft_for(app, owner)
    app.state.reminder_drafts.cancel(owner, draft["draft_id"])
    with pytest.raises(HTTPException) as exc:
        app.state.reminder_drafts.patch(owner, draft["draft_id"], 1, {"event_time": "09:00"})
    assert exc.value.status_code == 409
    assert tasks == {} and calls == []


@pytest.mark.parametrize("text", [
    "明天9点不用提醒我喝水",
    "明天9点不再提醒我喝水",
    "明天9点不想再收到喝水提醒",
    "不要设置明天9点的闹钟",
    "别再提醒我明天9点开会",
    "朋友说：“明天9点提醒我开会。”",
    "她明天9点提醒我开会",
    "明天她9点提醒我开会",
    "昨天9点提醒我喝水",
    "如果明天9点下雨就提醒我",
    "明天9点提醒小王喝水",
])
def test_negation_reporting_past_and_conditional_text_never_auto_creates(business, text):
    app, owner, tasks, calls = business
    app.state.memory.set_permissions(owner, {"notification_consent": True})
    result = app.state.reminder_chat.execute(
        {"life_user_id": owner}, "synthetic-guard-source", text, "synthetic-guard-conversation")
    assert result["status"] in ("no_action", "clarify")
    assert tasks == {} and calls == []
    assert app.state.reminder_drafts.list(owner, "synthetic-guard-conversation") == []


@pytest.mark.parametrize("text", [
    "明天9点提醒我带绿色U盘，不是银色的",
    "不用提前，明天9点提醒我喝水",
    "明天9点别忘提醒我喝水",
    "明天我和朋友开会，9点提醒我",
])
def test_negated_qualifier_does_not_erase_an_explicit_authorized_command(business, text):
    app, owner, tasks, calls = business
    app.state.memory.set_permissions(owner, {"notification_consent": True})
    result = app.state.reminder_chat.execute(
        {"life_user_id": owner}, "synthetic-guard-source", text, "synthetic-guard-conversation")
    assert result["status"] == "scheduled"
    assert len(tasks) == 1 and calls.count("POST") == 1
