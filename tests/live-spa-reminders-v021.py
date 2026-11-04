"""Verify two configured synthetic SPA accounts through the actual gateway."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3001"


def main():
    accounts = json.loads(
        (ROOT / "infra/runtime/v02-memory-reminders/accounts.json").read_text(encoding="utf-8")
    )
    mappings = json.loads(
        (ROOT / "infra/runtime/reminders/users.json").read_text(encoding="utf-8")
    )
    report = {"started_at": datetime.now(timezone.utc).astimezone().isoformat(),
              "status": "FAIL", "checks": {}}
    clients = {}
    created = None
    try:
        for label in ("a", "b"):
            client = httpx.Client(base_url=BASE, timeout=15)
            login = client.post("/api/auth/login", json={
                "email": accounts[label]["email"], "password": accounts[label]["password"],
            })
            login.raise_for_status()
            client.headers["Authorization"] = f"Bearer {login.json()['token']}"
            clients[label] = client
            listed = client.get("/life-api/api/v1/reminders")
            listed.raise_for_status()
            assert listed.json()["configured"] is True
        report["checks"]["both_synthetic_accounts_authenticated_and_configured"] = "PASS"
        a, b = clients["a"], clients["b"]
        consent = b.patch("/life-api/api/v1/me/settings", json={"notification_consent": True})
        consent.raise_for_status()
        response = b.post("/life-api/api/v1/reminders", json={
            "title": "Synthetic B isolated delivery verification",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(seconds=75)).isoformat(),
            "timezone": "Asia/Hong_Kong",
        })
        response.raise_for_status()
        created = response.json()["reminder"]
        report["b_reminder_id"] = created["reminder_id"]
        b_list = b.get("/life-api/api/v1/reminders").json()["reminders"]
        a_list = a.get("/life-api/api/v1/reminders").json()["reminders"]
        assert any(item["reminder_id"] == created["reminder_id"] for item in b_list)
        assert not any(item["reminder_id"] == created["reminder_id"] for item in a_list)
        assert a.get(f"/life-api/api/v1/reminders/{created['reminder_id']}").status_code == 404
        for row in a_list:
            assert b.get(f"/life-api/api/v1/reminders/{row['reminder_id']}").status_code == 404
        report["checks"]["both_users_see_own_records_and_cannot_read_other_details"] = "PASS"
        a_config = mappings[a.get("/life-api/api/v1/me").json()["life_user_id"]]
        b_config = mappings[b.get("/life-api/api/v1/me").json()["life_user_id"]]
        assert a_config["vikunja_user_id"] != b_config["vikunja_user_id"]
        denied = httpx.get(
            f"{b_config['ntfy_base_url']}/{b_config['ntfy_topic']}/json?poll=1",
            auth=(a_config["ntfy_user"], a_config["ntfy_password"]), timeout=8,
        )
        assert denied.status_code == 403
        report["checks"]["ntfy_acl_denies_other_user_topic"] = "PASS"
        deadline = time.monotonic() + 185
        while time.monotonic() < deadline:
            inbox = b.get("/life-api/api/v1/reminder-notifications")
            inbox.raise_for_status()
            if any(item["message"] == created["title"] for item in inbox.json()["messages"]):
                break
            time.sleep(2)
        else:
            raise AssertionError("B notification not received from ntfy")
        a_inbox = a.get("/life-api/api/v1/reminder-notifications")
        a_inbox.raise_for_status()
        assert not any(item["message"] == created["title"]
                       for item in a_inbox.json()["messages"])
        report["checks"]["b_receives_real_notification_a_does_not_receive_it"] = "PASS"
        complete = b.patch(f"/life-api/api/v1/reminders/{created['reminder_id']}",
                           json={"done": True})
        complete.raise_for_status()
        assert complete.json()["reminder"]["status"] == "completed"
        report["checks"]["real_upstream_completion"] = "PASS"
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    finally:
        if created and "b" in clients:
            response = clients["b"].delete(
                f"/life-api/api/v1/reminders/{created['reminder_id']}"
            )
            report["synthetic_b_task_cancelled"] = response.is_success
        report["ended_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        out = ROOT / "evidence/v02-memory-reminders/spa-two-user-live.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
