"""Real LibreChat ownership + persistent LangGraph + Vikunja; zero generation."""
from __future__ import annotations

import argparse
import json
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, utc_now
from verify_rebuild_workspace import verify


def insert_sources(account, run_id):
    baseline = json.loads((ROOT / "infra/runtime/p00/baseline-state.json").read_text(encoding="utf-8"))
    sources = [
        {"kind": "missing_time", "text": "明天提醒我带绿色 U 盘，不是银色的。"},
        {"kind": "two_clocks", "text": "明天下午15:00开会，早上09:00提醒我。"},
        {"kind": "missing_day", "text": "到杭州后17:00在学校开会，提前2小时提醒。"},
        {"kind": "lost_projection", "text": "明天提醒我带合成验收文件。"},
    ]
    for item in sources:
        item.update(conversation_id=str(uuid.uuid4()), message_id=f"p03-business-{run_id}-{item['kind']}")
    script = """
const template = db.conversations.findOne({conversationId: TEMPLATE_ID});
if (!template || String(template.user) !== OWNER_ID) throw new Error('SYNTHETIC_TEMPLATE_OWNER_MISMATCH');
const sources = SOURCES;
for (const source of sources) {
  const now = new Date();
  const user = db.messages.insertOne({
    messageId: source.message_id, user: template.user, __v: 0, _meiliIndex: false,
    conversationId: source.conversation_id, createdAt: now, endpoint: 'DeepSeek',
    error: false, isCreatedByUser: true, isTemporary: false, model: 'deepseek-flash',
    parentMessageId: '00000000-0000-0000-0000-000000000000', sender: 'User',
    text: source.text, tokenCount: 0, unfinished: false, updatedAt: now, expiredAt: null
  });
  const assistant = db.messages.insertOne({
    messageId: source.message_id + '-assistant', user: template.user, __v: 0, _meiliIndex: false,
    conversationId: source.conversation_id, createdAt: now, endpoint: 'DeepSeek',
    error: false, isCreatedByUser: false, isTemporary: false, model: 'deepseek-flash',
    parentMessageId: source.message_id, sender: 'Synthetic acceptance',
    content: [{type:'text', text:'Synthetic fixture: no model generation.'}], text:'',
    tokenCount:0, unfinished:false, updatedAt:now, expiredAt:null, attachments:[]
  });
  const conversation = {...template};
  delete conversation._id;
  Object.assign(conversation, {
    conversationId: source.conversation_id, title: 'P03 business ' + source.kind,
    messages:[user.insertedId, assistant.insertedId], createdAt:now, updatedAt:now,
    endpoint:'DeepSeek', model:'deepseek-flash', chatGptLabel:'DeepSeek'
  });
  db.conversations.insertOne(conversation);
}
print(JSON.stringify({inserted_sources:sources.length}));
""".replace("TEMPLATE_ID", json.dumps(baseline["d"]["conversation_id"])).replace(
        "OWNER_ID", json.dumps(account["librechat_user_id"])).replace("SOURCES", json.dumps(sources))
    subprocess.run(["docker", "exec", "lcr-acceptance-20261103-mongo-1", "mongosh",
                    "LibreChatAcceptance", "--quiet", "--eval", script],
                   capture_output=True, text=True, check=True)
    return {item["kind"]: item for item in sources}


def main(reuse_database=None):
    verify(ROOT)
    run_id = uuid.uuid4().hex[:16]
    settings = replace(
        load_settings(), database_path=ROOT / f"infra/runtime/p02/business-workflow-{run_id}.sqlite3",
        memory_llm_key="", memory_llm_request_budget=0, memos_api_token="",
        neo4j_uri="", vikunja_users={}, reminder_scheduler_external=True,
        reminder_webhook_url="http://host.docker.internal:9/unused-business-acceptance")
    if reuse_database:
        path = Path(reuse_database).resolve()
        assert (path.is_relative_to((ROOT / "infra/runtime/p02").resolve())
                and path.name.startswith("business-workflow-") and path.suffix == ".sqlite3"
                and path.is_file()), "NOT_AN_ISOLATED_WORKFLOW_DATABASE"
        settings = replace(settings, database_path=path)
    assert settings.vikunja_base_url == "http://127.0.0.1:3461/api/v2"
    accounts = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))
    sources = insert_sources(accounts["a"], run_id)
    result = {
        "status": "FAIL", "run_id": run_id, "started_at": utc_now(), "checks": {},
        "scope": "real HTTP + SQLite + LangGraph + Vikunja; synthetic Mongo source, no chat generation",
        "database": str(settings.database_path.relative_to(ROOT)),
        "provider_calls": 0, "provider_key_configured": False, "states": [],
    }
    def login(account):
        response = httpx.post("http://127.0.0.1:3091/api/auth/login",
                              json={"email": account["email"], "password": account["password"]},
                              timeout=20)
        response.raise_for_status()
        return {"Authorization": "Bearer " + response.json()["token"]}
    headers, other = login(accounts["a"]), login(accounts["b"])
    app, server, worker, client = start(settings)
    owner = None
    drafts = []

    def request(method, path, body=None, auth=None, extra=None, timeout=20):
        response = client.request(method, path, headers={**(auth or headers), **(extra or {})},
                                  timeout=timeout,
                                  **({"json": body} if body is not None else {}))
        response.raise_for_status()
        return response.json()

    def create(kind):
        source = sources[kind]
        value = request("POST", "/api/v1/reminder-drafts", {
            "conversation_id": source["conversation_id"],
            "source_message_id": source["message_id"], "text": source["text"]})
        drafts.append(value["draft_id"])
        return value

    def snapshot(draft_id, label):
        value = app.state.reminder_drafts.workflow.snapshot(owner, draft_id)
        result["states"].append({"label": label, "draft_id": draft_id, "next": value["next"],
                                 "interrupted": value["interrupted"],
                                 "revision": value["values"].get("revision"),
                                 "status": value["values"].get("status")})
        return value

    def remote_tasks():
        config = app.state.provisioning.config(owner)
        if not config:
            return []
        return app.state.reminders._request(config, "GET",
            f"/projects/{config['project_id']}/tasks", params={"per_page": 100}).json()["items"]

    try:
        owner = request("GET", "/api/v1/me")["life_user_id"]
        request("GET", "/api/v1/me", auth=other)
        assert remote_tasks() == [], "REUSED_DATABASE_HAS_ACTIVE_TASKS"
        request("PATCH", "/api/v1/me/settings", {"notification_consent": False})
        with app.state.store.connect() as db:
            initial_submissions = db.execute("SELECT count(*) FROM reminder_submissions").fetchone()[0]
        draft = create("missing_time")
        identifier = draft["draft_id"]
        path = "/api/v1/reminder-drafts/" + identifier
        assert draft["missing_fields"] == ["event_time"] and "不是银色" in draft["title"]
        assert snapshot(identifier, "before_restart_collect_missing")["next"] == ["collect_missing"]
        stop(server, worker, client)
        app, server, worker, client = start(settings)
        assert snapshot(identifier, "after_restart_collect_missing")["interrupted"]
        ready = request("PATCH", path, {"event_time": "09:00"}, extra={"If-Match": "1"})
        assert ready["revision"] == 2
        assert snapshot(identifier, "ready_waiting_confirmation")["next"] == ["await_confirmation"]
        denied = client.post(path + "/confirm", headers=headers,
                             json={"revision": 2, "idempotency_key": "business-one"})
        assert denied.status_code == 403 and not remote_tasks()
        result["checks"]["persistent_missing_input_and_authorization_gate"] = "PASS"
        request("PATCH", "/api/v1/me/settings", {"notification_consent": True})
        assert request("POST", "/api/v1/reminder-provisioning", timeout=45)["status"] == "ready"
        with ThreadPoolExecutor(3) as pool:
            confirmations = list(pool.map(
                lambda _: request("POST", path + "/confirm",
                                  {"revision": 2, "idempotency_key": "business-one"}), range(3)))
        assert all(value["status"] == "scheduled" for value in confirmations)
        assert len(remote_tasks()) == 1
        reminder = confirmations[0]["reminder"]
        reminder_path = "/api/v1/reminders/" + reminder["reminder_id"]
        assert snapshot(identifier, "active_after_concurrent_confirmation")["next"] == ["active"]
        result["checks"]["three_real_concurrent_confirmations_one_vikunja_task"] = "PASS"

        moved = (datetime.now(UTC) + timedelta(days=3)).replace(second=0, microsecond=0)
        update = {"scheduled_at": moved.isoformat()}
        changed = request("PATCH", reminder_path, update)["reminder"]
        assert changed["reminder_id"] == reminder["reminder_id"] and changed["revision"] == 2
        draft_version = app.state.reminder_drafts.get(owner, identifier)["revision"]
        repeated = request("PATCH", reminder_path, update)["reminder"]
        assert repeated["revision"] == 2
        assert app.state.reminder_drafts.get(owner, identifier)["revision"] == draft_version
        assert len(remote_tasks()) == 1
        assert snapshot(identifier, "active_after_reschedule")["next"] == ["active"]
        denied = client.patch(reminder_path, headers=other, json={"title": "must not change"})
        assert denied.status_code == 404
        result["checks"]["reschedule_original_id_version_and_retry_idempotence"] = "PASS"
        request("DELETE", reminder_path)
        again = request("DELETE", reminder_path)["reminder"]
        assert again["status"] == "cancelled" and again["revision"] == 3
        assert remote_tasks() == []
        stop(server, worker, client)
        app, server, worker, client = start(settings)
        assert request("GET", reminder_path)["reminder"]["status"] == "cancelled"
        assert snapshot(identifier, "cancelled_after_restart")["next"] == []
        result["checks"]["formal_cancel_and_restart_match_graph_terminal_state"] = "PASS"

        complete = create("two_clocks")
        assert complete["missing_fields"] == []
        assert complete["preview"]["event_at"].endswith("15:00:00+08:00")
        assert complete["preview"]["scheduled_at"].endswith("09:00:00+08:00")
        request("POST", f"/api/v1/reminder-drafts/{complete['draft_id']}/confirm",
                {"revision": 1, "idempotency_key": "business-two"})
        result["checks"]["real_event_and_reminder_clocks_remain_distinct"] = "PASS"
        missing = create("missing_day")
        assert missing["missing_fields"] == ["event_date"]
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).astimezone(
            __import__("zoneinfo").ZoneInfo("Asia/Hong_Kong")).date().isoformat()
        selected = request("POST", f"/api/v1/reminder-drafts/{missing['draft_id']}/select",
                           {"revision": 1, "fields": {"event_date": tomorrow}})
        assert selected["status"] == "scheduled"
        assert selected["preview"]["event_at"].endswith("17:00:00+08:00")
        assert selected["preview"]["scheduled_at"].endswith("15:00:00+08:00")
        result["checks"]["date_choice_resumes_graph_and_computes_120_minute_lead"] = "PASS"

        uncertain = create("lost_projection")
        before_tasks = len(remote_tasks())
        with app.state.store.connect() as db:
            db.execute("""CREATE TRIGGER p03_projection_fault BEFORE INSERT ON reminders
                BEGIN SELECT RAISE(FAIL, 'SYNTHETIC_PROJECTION_FAILURE'); END""")
        unknown = request("POST", f"/api/v1/reminder-drafts/{uncertain['draft_id']}/select",
                          {"revision": 1, "fields": {"event_time": "10:00"}})
        assert unknown["status"] == "unknown" and len(remote_tasks()) == before_tasks + 1
        assert snapshot(uncertain["draft_id"], "unknown_after_real_sqlite_fault")["next"] == ["unknown"]
        with app.state.store.connect() as db:
            db.execute("DROP TRIGGER p03_projection_fault")
        stop(server, worker, client)
        app, server, worker, client = start(settings)
        before_ids = {item["id"] for item in remote_tasks()}
        reconciled = request("POST", f"/api/v1/reminder-drafts/{uncertain['draft_id']}/reconcile")
        assert reconciled["status"] == "scheduled"
        assert before_ids == {item["id"] for item in remote_tasks()}
        assert snapshot(uncertain["draft_id"], "active_after_real_reconciliation")["next"] == ["active"]
        result["checks"]["remote_success_sqlite_failure_restart_reconciles_without_new_task"] = "PASS"

        with app.state.store.connect() as db:
            result["model_call_rows"] = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
            result["submission_rows"] = db.execute("SELECT count(*) FROM reminder_submissions").fetchone()[0]
        assert result["model_call_rows"] == 0 and result["submission_rows"] == initial_submissions + 4
        result["checks"]["no_model_requests"] = "PASS"
        result["status"] = "PASS"
    except Exception as exc:
        result.update(error_type=type(exc).__name__,
                      error=str(exc) if isinstance(exc, AssertionError) else "SEE_PRIVATE_RUNTIME_LOG")
        raise
    finally:
        with app.state.store.connect() as db:
            db.execute("DROP TRIGGER IF EXISTS p03_projection_fault")
        cleanup_errors = []
        for draft_id in drafts:
            try:
                if app.state.reminder_drafts.get(owner, draft_id)["status"] == "unknown":
                    app.state.reminder_drafts.reconcile(owner, draft_id)
                app.state.reminder_drafts.cancel(owner, draft_id)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        result["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            result["status"] = "FAIL"
        stop(server, worker, client)
        result["ended_at"] = utc_now()
        (ROOT / f"evidence/p03/business-workflow-{run_id}.json").write_text(
            json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if cleanup_errors and not result.get("error_type"):
            raise RuntimeError("ISOLATED_ACCEPTANCE_CLEANUP_FAILED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-database")
    main(parser.parse_args().reuse_database)
