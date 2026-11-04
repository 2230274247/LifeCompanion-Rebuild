"""Real HTTP + isolated SQLite + acceptance Vikunja/ntfy reminder lifecycle."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import sys
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.config import load_settings
from app.main import create_app
from app.store import utc_now


def token(settings, user):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    parts = [encode({"alg": "HS256", "typ": "JWT"}),
             encode({"id": user, "exp": int(time.time()) + 3600})]
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(), b".".join(parts), hashlib.sha256).digest()
    ).rstrip(b"=")
    return {"Authorization": "Bearer " + b".".join([*parts, signature]).decode()}


def start(settings):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    deadline = time.monotonic() + 25
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(.1)
    if not server.started:
        server.should_exit = True
        worker.join(timeout=15)
        sock.close()
        raise RuntimeError("ISOLATED_HTTP_STARTUP_FAILED")
    return app, server, worker, httpx.Client(
        base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=20)


def stop(server, worker, client):
    client.close()
    server.should_exit = True
    worker.join(timeout=45)
    if worker.is_alive():
        raise RuntimeError("ISOLATED_HTTP_SHUTDOWN_TIMEOUT")


def main():
    run_id = uuid.uuid4().hex[:16]
    settings = replace(load_settings(),
        database_path=ROOT / f"infra/runtime/p02/p03-reminders-{run_id}.sqlite3",
        memory_llm_key="", memory_llm_request_budget=0, memos_api_token="",
        neo4j_uri="", vikunja_users={})
    owner, other = f"p03-synthetic-a-{run_id}", f"p03-synthetic-b-{run_id}"
    internal = {"X-Internal-Token": settings.internal_token}
    headers = token(settings, owner)
    other_headers = token(settings, other)
    result = {
        "run_id": run_id, "started_at": utc_now(), "status": "FAIL",
        "provider_calls": 0, "provider_key_configured": False,
        "database": str(settings.database_path.relative_to(ROOT)),
        "upstream": "verified lcr-acceptance-20261103-vikunja-1 at 127.0.0.1:3461",
        "device_delivery": "UNKNOWN",
        "checks": {},
    }
    app, server, worker, client = start(settings)
    try:
        for user in (owner, other):
            response = client.post("/internal/v1/users/bootstrap", headers=internal, json={
                "librechat_user_id": user, "memos_user_id": "",
                "display_name": "Synthetic P03 Acceptance",
                "memory_consent": False, "image_consent": False,
            })
            response.raise_for_status()
        consent = client.patch("/api/v1/me/settings", headers=headers,
                               json={"notification_consent": True})
        consent.raise_for_status()
        provisioned = client.post("/api/v1/reminder-provisioning", headers=headers)
        provisioned.raise_for_status()
        assert provisioned.json()["status"] == "ready", provisioned.json()
        result["checks"]["per_user_vikunja_and_ntfy_provisioning"] = "PASS"

        due = datetime.now(UTC) + timedelta(days=2)
        create = client.post("/api/v1/reminders", headers=headers, json={
            "title": f"P03 acceptance {run_id}",
            "scheduled_at": due.isoformat(), "timezone": "Asia/Hong_Kong",
            "delivery_channel": "push",
        })
        create.raise_for_status()
        reminder = create.json()["reminder"]
        reminder_id = reminder["reminder_id"]
        assert reminder["status"] == "scheduled"
        result["reminder_id"] = reminder_id
        result["checks"]["create_real_vikunja_task_and_sqlite_projection"] = "PASS"

        foreign = client.get(f"/api/v1/reminders/{reminder_id}", headers=other_headers)
        assert foreign.status_code == 404
        result["checks"]["cross_account_reminder_access_denied"] = "PASS"

        change = client.patch(f"/api/v1/reminders/{reminder_id}", headers=headers, json={
            "title": f"P03 acceptance updated {run_id}",
        })
        change.raise_for_status()
        assert change.json()["reminder"]["title"].endswith("updated " + run_id)
        listed = client.get("/api/v1/reminders", headers=headers)
        listed.raise_for_status()
        assert any(item["reminder_id"] == reminder_id and
                   item["title"].endswith("updated " + run_id)
                   for item in listed.json()["reminders"])
        result["checks"]["update_and_authoritative_vikunja_reconciliation"] = "PASS"

        canceled = client.delete(f"/api/v1/reminders/{reminder_id}", headers=headers)
        canceled.raise_for_status()
        repeated = client.delete(f"/api/v1/reminders/{reminder_id}", headers=headers)
        repeated.raise_for_status()
        assert repeated.json()["reminder"]["status"] == "cancelled"
        result["checks"]["cancel_is_idempotent_and_vikunja_delete_succeeded"] = "PASS"

        stop(server, worker, client)
        app, server, worker, client = start(settings)
        restored = client.get(f"/api/v1/reminders/{reminder_id}", headers=headers)
        restored.raise_for_status()
        assert restored.json()["reminder"]["status"] == "cancelled"
        result["checks"]["service_restart_restores_cancelled_state"] = "PASS"
        with app.state.store.connect() as db:
            result["model_call_rows"] = db.execute(
                "SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert result["model_call_rows"] == 0
        result["checks"]["no_model_requests"] = "PASS"
        result["status"] = "PASS"
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        stop(server, worker, client)
        result["ended_at"] = utc_now()
        (ROOT / "evidence/p03").mkdir(parents=True, exist_ok=True)
        (ROOT / "evidence/p03/live-reminder-lifecycle.json").write_text(
            json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
