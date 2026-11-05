"""Verify real C-account chat confirmation, signed webhook and private ntfy inbox."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3
import sys
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("dialog", ROOT / "tests/live-reminder-dialog-v022.py")
dialog = module_from_spec(spec)
spec.loader.exec_module(dialog)
STATE = ROOT / "infra/runtime/v022-reminder-dialog/delivery-state.json"
EVIDENCE = ROOT / "evidence/v022-reminder-dialog"


def client_for(label):
    dialog.settings()
    from app.provisioning import protect, unprotect
    cache = ROOT / f"infra/runtime/v022-reminder-dialog/session-{label}.dpapi"
    saved = unprotect(cache.read_text(encoding="ascii")) if cache.exists() else None
    if saved and saved["expires_at"] > time.time() + 60:
        token = saved["token"]
    else:
        import base64
        account = (dialog.accounts()[label] if label in ("c", "d") else json.loads(
            (ROOT / "infra/runtime/v02-memory-reminders/accounts.json").read_text(encoding="utf-8")
        )[label])
        response = httpx.post("http://127.0.0.1:3080/api/auth/login",
                              json={"email": account["email"], "password": account["password"]},
                              timeout=15)
        response.raise_for_status()
        token = response.json()["token"]
        encoded = token.split(".")[1]
        expires = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["exp"]
        cache.write_text(protect({"token": token, "expires_at": expires}), encoding="ascii")
    return httpx.Client(base_url="http://127.0.0.1:8010", timeout=90, headers={
        "Authorization": "Bearer " + token,
    })


def start():
    with client_for("c") as client:
        when = (datetime.now(timezone.utc) + timedelta(minutes=3)).replace(second=0, microsecond=0)
        local = when.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Shanghai"))
        text = f"今天在义乌{local:%H:%M}提醒我检查合成通知测试"
        source = dialog.create_source(client, text)
        created = client.post("/api/v1/reminder-drafts", json=source)
        created.raise_for_status()
        draft = created.json()
        path = "/api/v1/reminder-drafts/" + draft["draft_id"]
        ready = client.patch(path, headers={"If-Match": str(draft["revision"])}, json={
            "title": "V022 合成通知测试", "event_date": local.date().isoformat(),
            "event_time": local.strftime("%H:%M"), "timezone": "Asia/Shanghai",
            "lead_minutes": 0,
        })
        ready.raise_for_status()
        result = client.post(path + "/confirm", json={
            "revision": ready.json()["revision"],
            "idempotency_key": "delivery-" + draft["draft_id"],
        })
        result.raise_for_status()
        assert result.json()["status"] == "scheduled"
        value = result.json()["reminder"]
        owner = client.get("/api/v1/me").json()["life_user_id"]
        state = {"owner_id": owner, "draft_id": draft["draft_id"],
                 "reminder_id": value["reminder_id"], "task_id": value["upstream_task_id"],
                 "scheduled_at": value["scheduled_at"],
                 "conversation_id": source["conversation_id"]}
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        public = {k: v for k, v in state.items() if k != "owner_id"}
        (EVIDENCE / "p0-5-delivery-start.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
        print(json.dumps({"status": "SCHEDULED", **public}))


def check():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    dialog.settings()
    from app.provisioning import unprotect

    database = ROOT / "services/life-core/data/life-core.sqlite3"
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        config = unprotect(db.execute("SELECT credentials FROM reminder_accounts WHERE owner_id=?",
                                      (state["owner_id"],)).fetchone()[0])
        event_id = hashlib.sha256(
            f"{state['owner_id']}:{state['task_id']}:{state['scheduled_at']}".encode()
        ).hexdigest()
        row = db.execute("SELECT * FROM reminder_notifications WHERE event_id=?",
                         (event_id,)).fetchone()
    if not row:
        print(json.dumps({"status": "WAITING", "scheduled_at": state["scheduled_at"]}))
        return
    if row["status"] != "accepted":
        print(json.dumps({"status": "WAITING", "outbox_status": row["status"],
                          "attempts": row["attempts"]}))
        return
    payload = json.loads(row["payload"])
    with client_for("c") as client, client_for("d") as other:
        inbox = client.get("/api/v1/reminder-notifications")
        inbox.raise_for_status()
        messages = inbox.json()["messages"]
        assert any("合成通知测试" in m["message"] for m in messages)
        assert other.get("/api/v1/reminders/" + state["reminder_id"]).status_code == 404
        drafts = other.get("/api/v1/reminder-drafts", params={"conversation_id": state["conversation_id"]})
        assert drafts.status_code == 200 and drafts.json()["drafts"] == []
        denied = httpx.get(f"{config['ntfy_base_url']}/{config['ntfy_topic']}/json",
                           params={"poll": "1"}, timeout=10)
        assert denied.status_code == 403
        assert row["status"] == "accepted"
        assert payload.get("event_name") == "task.reminder.fired"
        complete = client.patch("/api/v1/reminders/" + state["reminder_id"], json={"done": True})
        complete.raise_for_status()
        assert complete.json()["reminder"]["status"] == "completed"
        report = {
            "status": "PASS", "task_id": state["task_id"], "scheduled_at": state["scheduled_at"],
            "checks": {
                "real_chat_source_and_explicit_confirm": "PASS",
                "real_signed_vikunja_webhook_event": "PASS",
                "real_ntfy_accepted": "PASS",
                "authenticated_in_app_inbox_read": "PASS",
                "anonymous_private_topic_denied": "PASS",
                "account_d_cannot_read_c_draft_or_reminder": "PASS",
                "real_upstream_completed": "PASS",
            },
            "notification_count": len(messages), "device_delivery": "UNKNOWN",
        }
    (EVIDENCE / "p0-5-live-delivery.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def boundaries():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    settings = dialog.settings()
    from app.provisioning import unprotect
    with sqlite3.connect(ROOT / "services/life-core/data/life-core.sqlite3") as db:
        config = unprotect(db.execute("SELECT credentials FROM reminder_accounts WHERE owner_id=?",
                                      (state["owner_id"],)).fetchone()[0])
    report = {"status": "FAIL", "checks": {}}
    with client_for("c") as client:
        for label in ("a", "b", "d"):
            with client_for(label) as other:
                assert other.get("/api/v1/reminders/" + state["reminder_id"]).status_code == 404, "CROSS_REMINDER"
                drafts = other.get("/api/v1/reminder-drafts", params={"conversation_id": state["conversation_id"]})
                assert drafts.status_code == 200 and drafts.json()["drafts"] == [], "CROSS_DRAFT"
                inbox = other.get("/api/v1/reminder-notifications")
                assert inbox.status_code == 200, "CROSS_INBOX_HTTP"
                assert not any("V022 合成通知测试" in m["message"] for m in inbox.json()["messages"]), "CROSS_INBOX_CONTENT"
                if label in ("a", "b"):
                    owner = other.get("/api/v1/me").json()["life_user_id"]
                    cfg = settings.vikunja_users[owner]
                    denied = httpx.get(f"{config['ntfy_base_url']}/{config['ntfy_topic']}/json",
                                       params={"poll": "1"}, auth=(cfg["ntfy_user"], cfg["ntfy_password"]),
                                       timeout=10)
                    assert denied.status_code == 403, "CROSS_TOPIC"
                report["checks"][f"account_{label}_cannot_read_c_draft_reminder_or_inbox"] = "PASS"
        previous = client.get("/api/v1/me").json()["notification_consent"]
        try:
            assert client.patch("/api/v1/me/settings", json={"notification_consent": False}).status_code == 200
            rejected = client.post("/api/v1/reminders", json={
                "title": "must not create", "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "timezone": "Asia/Shanghai", "delivery_channel": "push",
            })
            assert rejected.status_code == 403, "REVOKED_CREATE_HTTP"
            assert rejected.json()["detail"]["code"] == "NOTIFICATION_CONSENT_REQUIRED", "REVOKED_CREATE_CODE"
            assert client.get("/api/v1/reminder-notifications").json()["messages"] == [], "REVOKED_INBOX"
            report["checks"]["revocation_rejects_create_and_suppresses_inbox"] = "PASS"
            source = dialog.create_source(client, "这是一条合成普通聊天测试，请只回复普通聊天正常。")
            for _ in range(120):
                saved = client.get("http://127.0.0.1:3080/api/messages/" + source["conversation_id"])
                saved.raise_for_status()
                if any(not m.get("isCreatedByUser") for m in saved.json()):
                    break
                time.sleep(0.5)
            assert any(not m.get("isCreatedByUser") and not m.get("error") for m in saved.json()), "ORDINARY_CHAT"
            report["checks"]["ordinary_chat_after_revocation"] = "PASS"
            reminders = client.get("/api/v1/reminders").json()["reminders"]
            future = [r for r in reminders if r["status"] == "scheduled" and r["title"] == "赶高铁"]
            assert len(future) == 1, "SYNTHETIC_FUTURE_COUNT"
            cancelled = client.delete("/api/v1/reminders/" + future[0]["reminder_id"])
            cancelled.raise_for_status()
            assert cancelled.json()["reminder"]["status"] == "cancelled", "REVOKED_CANCEL"
            report["checks"]["revoked_user_can_cancel_existing_synthetic_reminder"] = "PASS"
        finally:
            client.patch("/api/v1/me/settings", json={"notification_consent": previous}).raise_for_status()
    report["status"] = "PASS"
    (EVIDENCE / "p0-5-live-boundaries.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else "check"
        {"start": start, "check": check, "boundaries": boundaries}[mode]()
    except Exception as exc:
        report = {"status": "FAIL", "error_type": type(exc).__name__}
        if isinstance(exc, AssertionError) and str(exc).replace("_", "").isupper():
            report["assertion_code"] = str(exc)
        if isinstance(exc, httpx.HTTPStatusError):
            report["http_status"] = exc.response.status_code
        path = EVIDENCE / ("p0-5-failure-" + datetime.now().strftime("%H%M%S") + ".json")
        path.write_text(json.dumps(report), encoding="utf-8")
        print(json.dumps(report))
        sys.exit(1)
