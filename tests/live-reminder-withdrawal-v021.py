"""Only a newly created synthetic reminder is cancelled by this acceptance check."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
accounts = json.loads((root / "infra/runtime/v02-memory-reminders/accounts.json").read_text(encoding="utf-8"))
internal = next(line.split("=", 1)[1] for line in (root / "infra/.env").read_text(encoding="utf-8-sig").splitlines() if line.startswith("LIFE_INTERNAL_TOKEN="))
report = {"started_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "FAIL"}
client = httpx.Client(base_url="http://127.0.0.1:3001", timeout=35)
created = None
try:
    login = client.post("/api/auth/login", json={"email": accounts["a"]["email"], "password": accounts["a"]["password"]})
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["token"]
    permission = client.get("/life-api/api/v1/me")
    permission.raise_for_status()
    original = permission.json()["notification_consent"]
    client.patch("/life-api/api/v1/me/settings", json={"notification_consent": True}).raise_for_status()
    response = client.post("/life-api/api/v1/reminders", json={"title": "Synthetic withdrawal cancellation test", "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    response.raise_for_status()
    created = response.json()["reminder"]
    client.patch("/life-api/api/v1/me/settings", json={"notification_consent": False}).raise_for_status()
    action = httpx.post("http://127.0.0.1:8010/internal/v1/reminders/execute", headers={"X-Internal-Token": internal}, json={"source_user_id": accounts["a"]["librechat_user_id"], "source_message_id": created["reminder_id"] + ":cancel", "text": "请取消名称为「Synthetic withdrawal cancellation test」的提醒。"}, timeout=35)
    action.raise_for_status()
    assert action.json()["status"] == "succeeded"
    read = client.get("/life-api/api/v1/reminders/" + created["reminder_id"])
    read.raise_for_status()
    assert read.json()["reminder"]["status"] == "cancelled"
    report["status"] = "PASS"
    report["real_llm_cancel_with_notifications_disabled"] = "PASS"
finally:
    if created:
        client.delete("/life-api/api/v1/reminders/" + created["reminder_id"])
    if "original" in locals():
        client.patch("/life-api/api/v1/me/settings", json={"notification_consent": original})
    report["ended_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    (root / "evidence/v02-memory-reminders/reminder-withdrawal-live.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
