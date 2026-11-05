"""Real local acceptance using new synthetic accounts and an isolated life-core DB."""

import json
import os
import secrets
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v022-reminder-dialog"
EVIDENCE = ROOT / "evidence/v022-reminder-dialog"


def settings():
    for file in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value
    sys.path.insert(0, str(ROOT / "services/life-core"))
    from app.config import load_settings
    return load_settings()


def serve():
    import uvicorn
    from app.main import create_app
    config = replace(settings(), database_path=RUNTIME / "life-core.sqlite3",
                     reminder_webhook_url="http://host.docker.internal:8012/api/v1/webhooks/vikunja")
    uvicorn.run(create_app(config), host="127.0.0.1", port=8012)


def accounts():
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / "accounts.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for label in ("c", "d"):
        if label not in saved:
            suffix = secrets.token_hex(6)
            saved[label] = {"email": f"v022-{label}-{suffix}@example.invalid",
                            "password": secrets.token_urlsafe(24),
                            "name": f"V022 Synthetic {label.upper()}"}
            path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
            response = httpx.post("http://127.0.0.1:3080/api/auth/register",
                                  json={**saved[label], "confirm_password": saved[label]["password"],
                                        "username": f"v022{label}{suffix}"}, timeout=15)
            if response.status_code != 200:
                raise RuntimeError(f"REGISTER_HTTP_{response.status_code}")
    return saved


def create_source(client, text):
    source = str(uuid.uuid4())
    response = client.post(
        "http://127.0.0.1:3080/api/agents/chat/DeepSeek",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36"},
        json={"text": text, "messageId": source,
              "parentMessageId": "00000000-0000-0000-0000-000000000000",
              "conversationId": "new", "endpoint": "DeepSeek", "endpointType": "custom",
              "model": "deepseek-flash", "isCreatedByUser": True, "sender": "User",
              "timezone": "Asia/Shanghai"})
    response.raise_for_status()
    conversation = response.json()["conversationId"]
    with client.stream("GET", f"http://127.0.0.1:3080/api/agents/chat/stream/{conversation}") as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("final") or payload.get("event") == "done":
                    break
    for _ in range(120):
        saved = client.get(f"http://127.0.0.1:3080/api/messages/{conversation}")
        if saved.status_code == 200:
            matches = [m for m in saved.json() if m.get("isCreatedByUser") and m.get("text") == text]
            assistant_saved = any(
                not m.get("isCreatedByUser") and not m.get("error") and (
                    m.get("text") or any(p.get("type") == "text" and p.get("text")
                                         for p in m.get("content", []))
                ) for m in saved.json()
            )
            if len(matches) == 1 and assistant_saved:
                return {"conversation_id": conversation, "source_message_id": matches[0]["messageId"], "text": text}
        time.sleep(0.5)
    raise RuntimeError("SOURCE_MESSAGE_NOT_PERSISTED")


def provision():
    report = {"stage": "P0-2", "checks": {}, "status": "FAIL"}
    configs = accounts()
    clients = {}
    try:
        for label, account in configs.items():
            login = httpx.post("http://127.0.0.1:3080/api/auth/login",
                               json={"email": account["email"], "password": account["password"]}, timeout=15)
            login.raise_for_status()
            client = httpx.Client(base_url="http://127.0.0.1:8012", timeout=90,
                                  headers={"Authorization": "Bearer " + login.json()["token"]})
            clients[label] = client
        client = clients["c"]
        initial = client.get("/api/v1/reminders")
        assert initial.status_code == 200 and initial.json()["status"] == "consent_required"
        assert client.post("/api/v1/reminder-provisioning").status_code == 403
        report["checks"]["ordinary_account_maps_without_manual_bootstrap_and_requires_consent"] = "PASS"
        assert client.patch("/api/v1/me/settings", json={"notification_consent": True}).status_code == 200
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: client.post("/api/v1/reminder-provisioning"), range(2)))
        report["provisioning_http"] = [r.status_code for r in responses]
        report["provisioning_responses"] = [r.json() for r in responses]
        assert all(r.status_code == 200 for r in responses)
        ready = client.get("/api/v1/reminders")
        assert ready.json()["configured"] is True and ready.json()["status"] == "ready"
        assert clients["d"].get("/api/v1/reminders").json()["configured"] is False
        assert client.post("/api/v1/reminder-provisioning").json()["status"] == "ready"
        report["checks"]["real_concurrent_provisioning_ready_idempotent_other_account_unconfigured"] = "PASS"
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, RuntimeError):
            report["error_code"] = str(exc)
        if isinstance(exc, httpx.HTTPStatusError):
            report["http_status"] = exc.response.status_code
    finally:
        EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE / "p0-2-live-provisioning.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


def drafts():
    report = {"stage": "P0-3", "checks": {}, "status": "FAIL"}
    saved = accounts()
    clients = {}
    try:
        for label, account in saved.items():
            response = httpx.post("http://127.0.0.1:3080/api/auth/login",
                                  json={"email": account["email"], "password": account["password"]}, timeout=15)
            response.raise_for_status()
            clients[label] = httpx.Client(base_url="http://127.0.0.1:8012", timeout=90,
                                          headers={"Authorization": "Bearer " + response.json()["token"]})
        c, d = clients["c"], clients["d"]
        text = "我明天从义乌坐高铁，早上的高铁，能不能提前1小时提醒我赶车？"
        body = create_source(c, text)
        first = c.post("/api/v1/reminder-drafts", json=body)
        first.raise_for_status()
        draft = first.json()
        path = "/api/v1/reminder-drafts/" + draft["draft_id"]
        assert draft["missing_fields"] == ["event_time"]
        assert draft["timezone"] == "Asia/Shanghai"
        original = c.get("/api/v1/reminders").json()["reminders"]
        for revision, clock, expected in [(1, "09:30", "08:30:00+08:00"), (2, "10:15", "09:15:00+08:00")]:
            response = c.patch(path, headers={"If-Match": str(revision)}, json={"event_time": clock})
            response.raise_for_status()
            draft = response.json()
            assert draft["preview"]["scheduled_at"].endswith(expected)
        assert len(c.get("/api/v1/reminders").json()["reminders"]) == len(original)
        report["checks"]["exact_chinese_only_time_missing_two_previews_no_task_before_confirmation"] = "PASS"
        assert d.patch(path, headers={"If-Match": "3"}, json={"event_time": "09:30"}).status_code == 404
        assert d.get("/api/v1/reminder-drafts", params={"conversation_id": body["conversation_id"]}).json()["drafts"] == []
        report["checks"]["ordinary_account_d_cannot_read_or_mutate_c_draft"] = "PASS"
        command = {"revision": 3, "idempotency_key": "live-" + draft["draft_id"]}
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: c.post(path + "/confirm", json=command), range(2)))
        assert all(r.status_code == 200 for r in responses)
        confirmed = c.post(path + "/confirm", json=command).json()
        report["confirmation_state"] = confirmed["status"]
        assert confirmed["status"] == "scheduled", confirmed
        reminder = confirmed["reminder"]
        assert reminder["upstream_task_id"] > 0
        report["real_task_id"] = reminder["upstream_task_id"]
        assert len(c.get("/api/v1/reminders").json()["reminders"]) == len(original) + 1
        assert len(c.get("/api/v1/reminder-drafts", params={"conversation_id": body["conversation_id"]}).json()["drafts"]) == 1
        report["checks"]["real_upstream_task_id_concurrent_confirm_one_task_and_reload_recovery"] = "PASS"
        assert c.delete("/api/v1/reminders/" + reminder["reminder_id"]).status_code == 200
        report["checks"]["synthetic_task_cancelled_through_real_upstream"] = "PASS"
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            report["http_status"] = exc.response.status_code
    (EVIDENCE / "p0-3-live-drafts.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        settings()
        serve()
    elif len(sys.argv) > 1 and sys.argv[1] == "drafts":
        drafts()
    else:
        provision()
