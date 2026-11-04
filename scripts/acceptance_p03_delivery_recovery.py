"""Real due clock, Core outage, independent scheduler restart and private ntfy."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, token, utc_now
from verify_rebuild_workspace import verify


def wait_for(check, timeout, code):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(1)
    raise AssertionError(code)


def launch_scheduler(settings, base_url, jobstore, log):
    env = os.environ.copy()
    env.update(LIFE_CORE_URL=base_url, LIFE_INTERNAL_TOKEN=settings.internal_token,
               PYTHONPATH=str(ROOT / "services/life-core"))
    code = (
        "import logging,sys; from pathlib import Path; "
        "from app.reminder_scheduler import create_scheduler; "
        "logging.basicConfig(level=logging.INFO); "
        "create_scheduler(Path(sys.argv[1]),interval_seconds=5).start()"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code, str(jobstore)], cwd=ROOT, env=env,
        stdout=log, stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def stop_scheduler(process):
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=15)


def main():
    verify(ROOT)
    run_id = uuid.uuid4().hex[:16]
    runtime = ROOT / "infra/runtime/p02" / f"p03-delivery-{run_id}"
    runtime.mkdir()
    settings = replace(
        load_settings(), database_path=runtime / "life.sqlite3",
        memory_llm_key="", memory_llm_request_budget=0, memos_api_token="",
        neo4j_uri="", vikunja_users={}, reminder_scheduler_external=True,
        reminder_webhook_url="http://host.docker.internal:9/unreachable-acceptance-callback")
    result = {
        "status": "FAIL", "run_id": run_id, "started_at": utc_now(),
        "database": str(settings.database_path.relative_to(ROOT)),
        "compose_project": "lcr-acceptance-20261103",
        "provider_calls": 0, "provider_key_configured": False,
        "device_delivery": "UNKNOWN",
        "scope": "synthetic HTTP API; real clock/Vikunja/ntfy; Core and scheduler process restarts",
        "checks": {},
    }
    owner = f"p03-due-{run_id}"
    headers = token(settings, owner)
    internal = {"X-Internal-Token": settings.internal_token}
    app, server, worker, client = start(settings)
    running = True
    scheduler = None
    log = (runtime / "scheduler.log").open("ab")
    try:
        boot = client.post("/internal/v1/users/bootstrap", headers=internal, json={
            "librechat_user_id": owner, "memos_user_id": "", "display_name": "Synthetic due test",
            "memory_consent": False, "image_consent": False})
        boot.raise_for_status()
        life_id = boot.json()["life_user_id"]
        client.patch("/api/v1/me/settings", headers=headers,
                     json={"notification_consent": True}).raise_for_status()
        provision = client.post("/api/v1/reminder-provisioning", headers=headers)
        provision.raise_for_status()
        assert provision.json()["status"] == "ready"
        config = dict(app.state.provisioning.config(life_id))
        due = datetime.now(UTC) + timedelta(seconds=65)

        def create(label):
            response = client.post("/api/v1/reminders", headers=headers, json={
                "title": f"P03 {label} {run_id}", "scheduled_at": due.isoformat(),
                "timezone": "Asia/Hong_Kong", "delivery_channel": "push"})
            response.raise_for_status()
            return response.json()["reminder"]

        actual, moved, cancelled = create("due"), create("moved"), create("cancelled")
        scheduled = datetime.fromisoformat(actual["scheduled_at"])
        changed = client.patch(f"/api/v1/reminders/{moved['reminder_id']}", headers=headers,
                               json={"scheduled_at": (scheduled + timedelta(days=1)).isoformat()})
        changed.raise_for_status()
        assert changed.json()["reminder"]["reminder_id"] == moved["reminder_id"]
        client.delete(f"/api/v1/reminders/{cancelled['reminder_id']}",
                      headers=headers).raise_for_status()
        task_id = app.state.store.get_reminder(actual["reminder_id"], life_id)["upstream_task_id"]
        result.update(reminder_id=actual["reminder_id"], task_id=task_id,
                      scheduled_at=scheduled.isoformat(),
                      core_stopped_at=utc_now(), embedded_reconciliation=False)
        service = app.state.reminders
        store = app.state.store
        stop(server, worker, client)
        running = False
        assert datetime.now(UTC) < scheduled
        print(json.dumps({"status": "WAITING_REAL_DUE", "run_id": run_id,
                          "scheduled_at": scheduled.isoformat(), "provider_calls": 0}), flush=True)

        def upstream_fired():
            items = service._request(config, "GET", "/notifications",
                                     params={"per_page": 100}).json()["items"]
            return next((item for item in items if item.get("name") == "task.reminder"
                         and item.get("notification", {}).get("task", {}).get("id") == task_id), None)

        notification = wait_for(upstream_fired, 180, "REAL_VIKUNJA_DUE_NOTIFICATION_MISSING")
        result["upstream_notification"] = {
            "name": notification["name"], "created": notification["created"], "task_id": task_id}
        result["checks"]["real_upstream_due_while_core_stopped"] = "PASS"
        # Vikunja may announce the minute's reminder early; the outbox must wait.
        wait_for(lambda: datetime.now(UTC) >= scheduled, 65, "PLANNED_TIME_NOT_REACHED")
        with store.connect() as db:
            assert db.execute("SELECT count(*) FROM reminder_notifications").fetchone()[0] == 0
        result["checks"]["no_callback_or_embedded_delivery"] = "PASS"

        app, server, worker, client = start(settings)
        running = True
        bad_config = {**config, "ntfy_base_url": "http://127.0.0.1:1"}
        app.state.provisioning._save(life_id, bad_config, "ready")
        scheduler = launch_scheduler(settings, str(client.base_url).rstrip("/"),
                                     runtime / "scheduler.sqlite3", log)

        def event():
            with app.state.store.connect() as db:
                row = db.execute("SELECT event_id,status,attempts,next_attempt_at,last_error,updated_at "
                                 "FROM reminder_notifications WHERE owner_user_id=?", (life_id,)).fetchone()
            return dict(row) if row else None

        def failed_attempt():
            value = event()
            return value if value and value["attempts"] >= 1 and value["last_error"] else None

        failed = wait_for(failed_attempt, 45, "REAL_NTFY_FAILURE_NOT_RECORDED")
        assert scheduler.poll() is None
        stop_scheduler(scheduler)
        result["retry_before_restart"] = failed
        result["checks"]["real_connection_failure_persists_backoff"] = "PASS"
        app.state.provisioning._save(life_id, config, "ready")
        stop(server, worker, client)
        running = False

        app, server, worker, client = start(settings)
        running = True
        scheduler = launch_scheduler(settings, str(client.base_url).rstrip("/"),
                                     runtime / "scheduler.sqlite3", log)
        accepted = wait_for(lambda: (value if (value := event()) and value["status"] == "accepted"
                                    else None), 60, "RESTARTED_SCHEDULER_DID_NOT_DELIVER")
        assert scheduler.poll() is None
        assert accepted["attempts"] >= 2
        assert datetime.fromisoformat(accepted["updated_at"]) >= scheduled
        result["accepted_outbox"] = accepted
        result["checks"]["independent_scheduler_restart_recovers_pending_retry"] = "PASS"
        stop_scheduler(scheduler)

        for _ in range(2):
            client.post("/internal/v1/reminders/reconcile", headers=internal).raise_for_status()
        for item in (moved, cancelled):
            response = client.get(f"/api/v1/reminders/{item['reminder_id']}", headers=headers)
            response.raise_for_status()
            assert response.json()["reminder"]["status"] == (
                "scheduled" if item is moved else "cancelled")
        messages = httpx.get(
            f"{config['ntfy_base_url']}/{config['ntfy_topic']}/json",
            params={"poll": "1", "since": "24h"},
            auth=(config["ntfy_user"], config["ntfy_password"]), timeout=15)
        messages.raise_for_status()
        cached = [json.loads(line) for line in messages.text.splitlines() if line]
        cached = [item for item in cached if item.get("event") == "message"]
        sequence_id = hashlib.sha256(f"{life_id}:{task_id}:{actual['scheduled_at']}".encode()).hexdigest()
        assert len(cached) == 1 and cached[0]["sequence_id"] == sequence_id
        assert cached[0]["message"] == actual["title"]
        anonymous = httpx.get(
            f"{config['ntfy_base_url']}/{config['ntfy_topic']}/json",
            params={"poll": "1"}, timeout=15)
        assert anonymous.status_code == 403
        other = client.get(f"/api/v1/reminders/{actual['reminder_id']}",
                           headers=token(settings, f"p03-other-{run_id}"))
        assert other.status_code == 404
        inbox = client.get("/api/v1/reminder-notifications", headers=headers)
        inbox.raise_for_status()
        assert len(inbox.json()["messages"]) == 1
        with app.state.store.connect() as db:
            runs = [dict(row) for row in db.execute(
                "SELECT status,users,notifications_accepted,error_code FROM reminder_scheduler_runs")]
            calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert calls == 0
        assert any(row["notifications_accepted"] == 1 for row in runs)
        result.update(
            status="PASS", model_call_rows=calls, scheduler_runs=runs,
            ntfy_message_count=len(cached), jobstore_bytes=(runtime / "scheduler.sqlite3").stat().st_size)
        result["checks"].update({
            "real_ntfy_accepted_and_authenticated_inbox": "PASS",
            "reconciliation_replay_does_not_duplicate_notification": "PASS",
            "rescheduled_and_cancelled_tasks_do_not_fire_at_old_time": "PASS",
            "anonymous_topic_read_denied": "PASS",
            "cross_account_reminder_read_denied": "PASS",
            "persistent_scheduler_audit": "PASS", "no_model_requests": "PASS"})
        # Remove only the synthetic future task created by this run.
        client.delete(f"/api/v1/reminders/{moved['reminder_id']}", headers=headers).raise_for_status()
    except Exception as exc:
        result.update(error_type=type(exc).__name__,
                      error=str(exc) if isinstance(exc, AssertionError) else "SEE_PRIVATE_RUNTIME_LOG")
        raise
    finally:
        stop_scheduler(scheduler)
        if running:
            stop(server, worker, client)
        log.close()
        result["ended_at"] = utc_now()
        evidence = ROOT / "evidence/p03" / f"delivery-recovery-{run_id}.json"
        evidence.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
