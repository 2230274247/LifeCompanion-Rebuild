"""Exercise isolated Vikunja task CRUD and reminder delivery to isolated ntfy."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CREDS = json.loads(
    (ROOT / "infra/runtime/v02-memory-reminders/upstream-accounts.json").read_text(
        encoding="utf-8"
    )
)
BASE = "http://127.0.0.1:3456/api/v1"
NTFY = "http://127.0.0.1:8087"
TIMEOUT = 10


def main() -> None:
    result: dict = {
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "isolation": "local-only Vikunja account and ACL-protected ntfy topic",
        "checks": {},
        "status": "FAIL",
    }
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"
    task_id = None
    webhook_id = None
    try:
        auth = session.post(
            f"{BASE}/login",
            json={
                "username": CREDS["username"],
                "password": CREDS["password"],
                "long_token": True,
            },
            timeout=TIMEOUT,
        )
        auth.raise_for_status()
        session.headers["Authorization"] = f"Bearer {auth.json()['token']}"
        result["checks"]["isolated_account_login"] = "PASS"

        events = session.get(f"{BASE}/user/settings/webhooks/events", timeout=TIMEOUT)
        events.raise_for_status()
        event_names = events.json()
        assert "task.reminder.fired" in event_names
        created = session.put(
            f"{BASE}/user/settings/webhooks",
            json={
                "target_url": f"http://ntfy:80/{CREDS['topic']}",
                "events": ["task.reminder.fired"],
                "secret": CREDS["webhook_secret"],
                "basic_auth_user": CREDS["ntfy_user"],
                "basic_auth_password": CREDS["ntfy_password"],
            },
            timeout=TIMEOUT,
        )
        created.raise_for_status()
        webhook_id = created.json()["id"]
        result["checks"]["official_user_webhook_registered"] = "PASS"

        projects = session.get(f"{BASE}/projects", timeout=TIMEOUT)
        projects.raise_for_status()
        project_rows = projects.json()
        project = next((p for p in project_rows if not p.get("is_archived")), None)
        assert project, "isolated test account has no writable project"
        fire_at = datetime.now(timezone.utc) + timedelta(seconds=55)
        task_response = session.put(
            f"{BASE}/projects/{project['id']}/tasks",
            json={
                "title": "Codex isolated reminder API verification",
                "reminders": [
                    {
                        "reminder": fire_at.replace(microsecond=0).isoformat(),
                        "relative_period": 0,
                    }
                ],
            },
            timeout=TIMEOUT,
        )
        task_response.raise_for_status()
        task = task_response.json()
        task_id = task["id"]
        result["checks"]["task_created_with_absolute_reminder"] = "PASS"

        read = session.get(f"{BASE}/tasks/{task_id}", timeout=TIMEOUT)
        read.raise_for_status()
        assert read.json()["title"] == task["title"]
        assert read.json()["reminders"], "Vikunja did not persist reminder"
        patch = session.post(
            f"{BASE}/tasks/{task_id}",
            json={**read.json(), "title": "Codex isolated reminder API verification updated"},
            timeout=TIMEOUT,
        )
        patch.raise_for_status()
        task = patch.json()
        assert task["title"].endswith("updated")
        result["checks"]["task_read_and_updated"] = "PASS"
        result["task"] = {
            "id": task_id,
            "project_id": project["id"],
            "reminder": read.json()["reminders"][0]["reminder"],
            "updated_title": task["title"],
        }

        deadline = time.monotonic() + 110
        received = None
        while time.monotonic() < deadline:
            poll = requests.get(
                f"{NTFY}/{CREDS['topic']}/json",
                params={"poll": "1"},
                auth=(CREDS["ntfy_user"], CREDS["ntfy_password"]),
                timeout=TIMEOUT,
            )
            poll.raise_for_status()
            for line in poll.text.splitlines():
                if not line:
                    continue
                message = json.loads(line)
                payload = message.get("message", "")
                try:
                    webhook = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                event_task = webhook.get("data", {}).get("task", {})
                if (
                    webhook.get("event_name") == "task.reminder.fired"
                    and event_task.get("id") == task_id
                ):
                    received = webhook
                    break
            if received:
                break
            time.sleep(2)
        assert received, "no reminder webhook message appeared in isolated ntfy topic"
        result["checks"]["reminder_webhook_received_by_ntfy"] = "PASS"
        result["notification"] = {
            "topic": CREDS["topic"],
            "event_name": received.get("event_name"),
            "payload_fields": sorted(received.keys()),
            "task_id_matches": received.get("data", {}).get("task", {}).get("id") == task_id,
            "received": True,
        }
        assert result["notification"]["task_id_matches"]
        result["status"] = "PASS"
    except Exception as exc:  # Evidence captures a sanitized error only.
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        if task_id is not None:
            deleted = session.delete(f"{BASE}/tasks/{task_id}", timeout=TIMEOUT)
            result["cleanup_task"] = deleted.status_code in (200, 204, 404)
        if webhook_id is not None:
            deleted = session.delete(
                f"{BASE}/user/settings/webhooks/{webhook_id}", timeout=TIMEOUT
            )
            result["cleanup_webhook"] = deleted.status_code in (200, 204, 404)
        result["ended_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        out = ROOT / "evidence/v02-memory-reminders/upstream-live-api.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
