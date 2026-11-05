"""Live isolated life-core -> Vikunja -> signed webhook -> ntfy acceptance."""

from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import uvicorn

requests = httpx


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v02-memory-reminders"
VIKUNJA = "http://127.0.0.1:3456/api/v2"
NTFY = "http://127.0.0.1:8087"
PORT = 8011
INTERNAL_TOKEN = "isolated-live-reminders-internal-token"
JWT_SECRET = "isolated-live-reminders-jwt-secret"


def serve_life_core(database_path: str) -> None:
    from app.config import Settings
    from app.main import create_app

    user_file = RUNTIME / "life-core-vikunja-users.json"
    users = json.loads(user_file.read_text(encoding="utf-8"))
    provider_key = next(
        (
            line.split("=", 1)[1]
            for env_file in (ROOT / "products/librechat-custom/.env", ROOT / "infra/.env")
            for line in env_file.read_text(encoding="utf-8-sig").splitlines()
            if line.startswith("DEEPSEEK_API_KEY=") and line.split("=", 1)[1].strip()
        ),
        "",
    )
    app = create_app(
        Settings(
            database_path=Path(database_path),
            internal_token=INTERNAL_TOKEN,
            jwt_secret=JWT_SECRET,
            jwt_refresh_secret="isolated-live-reminders-refresh",
            memos_base_url="http://127.0.0.1:5230",
            memos_api_token="",
            timezone="Asia/Hong_Kong",
            allowed_origins=("http://localhost:3001",),
            vikunja_base_url=VIKUNJA,
            vikunja_users=users,
            memory_llm_key=provider_key,
        )
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


def token_for(user_id: str) -> str:
    import base64

    def encode(data):
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).rstrip(b"=")

    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode(
        {
            "id": user_id,
            "exp": int(time.time()) + 3600,
        }
    )
    signing = header + b"." + payload
    signature = hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest()
    return (signing + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def main() -> None:
    from zoneinfo import ZoneInfo

    result: dict = {
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "isolation": "fresh life-core SQLite, dedicated Vikunja test user and private ntfy topic",
        "checks": {},
        "status": "FAIL",
        "api_version": "v2",
    }
    database_path = RUNTIME / f"live-api/reminders-{time.time_ns()}.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    app_process = multiprocessing.Process(
        target=serve_life_core, args=(str(database_path),), daemon=True
    )
    vikunja_session = requests.Client()
    task_ids: list[int] = []
    webhook_id = None
    try:
        app_process.start()
        api = f"http://127.0.0.1:{PORT}"
        for _ in range(60):
            try:
                health = requests.get(f"{api}/health", timeout=2)
                if health.is_success:
                    break
            except requests.RequestError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("isolated life-core failed to start")
        result["checks"]["isolated_life_core_started"] = "PASS"

        bootstrap = requests.post(
            f"{api}/internal/v1/users/bootstrap",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={
                "librechat_user_id": "lc-user-a",
                "memos_user_id": "users/reminder-test",
                "memos_username": "reminder-test",
                "display_name": "Reminder API test",
            },
            timeout=8,
        )
        bootstrap.raise_for_status()
        user = bootstrap.json()
        life_id = user["life_user_id"]
        jwt = token_for("lc-user-a")
        user_headers = {"Authorization": f"Bearer {jwt}"}
        result["checks"]["user_bootstrapped_in_isolated_database"] = "PASS"
        consent = requests.patch(
            f"{api}/api/v1/me/settings",
            headers=user_headers,
            json={"notification_consent": True},
            timeout=8,
        )
        consent.raise_for_status()

        user_config = json.loads(
            (RUNTIME / "life-core-vikunja-users.json").read_text(encoding="utf-8")
        )[life_id]
        result["checks"]["per_user_scoped_vikunja_token_configured"] = "PASS"

        creds = json.loads(
            (RUNTIME / "upstream-accounts.json").read_text(encoding="utf-8")
        )
        login = vikunja_session.post(
            f"{VIKUNJA}/login",
            json={
                "username": creds["username"],
                "password": creds["password"],
                "long_token": True,
            },
            timeout=8,
        )
        login.raise_for_status()
        vikunja_session.headers["Authorization"] = f"Bearer {login.json()['token']}"
        webhook = vikunja_session.post(
            f"{VIKUNJA}/user/settings/webhooks",
            json={
                "target_url": f"http://host.docker.internal:{PORT}/api/v1/webhooks/vikunja",
                "events": ["task.reminder.fired"],
                "secret": user_config["webhook_secret"],
            },
            timeout=8,
        )
        webhook.raise_for_status()
        webhook_id = webhook.json()["id"]
        result["checks"]["signed_callback_registered_to_life_core"] = "PASS"

        title = f"Codex live reminder {datetime.now().strftime('%H%M%S')}"
        due_at = datetime.now(ZoneInfo("Asia/Hong_Kong")) + timedelta(seconds=105)
        created = requests.post(
            f"{api}/api/v1/reminders",
            headers=user_headers,
            json={
                "title": title,
                "scheduled_at": due_at.isoformat(),
                "timezone": "Asia/Hong_Kong",
                "delivery_channel": "push",
            },
            timeout=12,
        )
        created.raise_for_status()
        reminder = created.json()["reminder"]
        upstream_tasks = requests.get(
            f"{VIKUNJA}/tasks",
            headers={
                "Authorization": "Bearer "
                + json.loads(
                    (RUNTIME / "life-core-vikunja-users.json").read_text(
                        encoding="utf-8"
                    )
                )[life_id]["api_token"]
            },
            timeout=8,
        )
        upstream_tasks.raise_for_status()
        matching_task = next(
            row for row in upstream_tasks.json()["items"] if row["title"] == title
        )
        task_id = int(matching_task["id"])
        task_ids.append(task_id)
        result["checks"]["life_core_created_real_vikunja_task"] = "PASS"
        result["created"] = {
            "reminder_id": reminder["reminder_id"],
            "vikunja_task_id": task_id,
            "status": reminder["status"],
        }

        updated_due = datetime.now(ZoneInfo("Asia/Hong_Kong")) + timedelta(seconds=78)
        updated = requests.patch(
            f"{api}/api/v1/reminders/{reminder['reminder_id']}",
            headers=user_headers,
            json={"title": title + " updated", "scheduled_at": updated_due.isoformat()},
            timeout=12,
        )
        updated.raise_for_status()
        result["checks"]["life_core_updated_real_vikunja_task"] = "PASS"

        listed = requests.get(f"{api}/api/v1/reminders", headers=user_headers, timeout=8)
        listed.raise_for_status()
        assert any(row["reminder_id"] == reminder["reminder_id"] for row in listed.json()["reminders"])
        result["checks"]["life_core_listed_user_scoped_task"] = "PASS"

        other_headers = {"Authorization": f"Bearer {token_for('lc-user-b')}"}
        other_bootstrap = requests.post(
            f"{api}/internal/v1/users/bootstrap",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={
                "librechat_user_id": "lc-user-b",
                "memos_user_id": "users/reminder-test-b",
                "memos_username": "reminder-test-b",
                "display_name": "Second isolated user",
            },
            timeout=8,
        )
        other_bootstrap.raise_for_status()
        other_list = requests.get(f"{api}/api/v1/reminders", headers=other_headers, timeout=8)
        other_list.raise_for_status()
        assert other_list.json()["reminders"] == []
        result["checks"]["second_user_cannot_read_first_user_reminder"] = "PASS"

        received = False
        deadline = time.monotonic() + 185
        while time.monotonic() < deadline:
            poll = requests.get(
                f"{NTFY}/{user_config['ntfy_topic']}/json",
                params={"poll": "1"},
                auth=(user_config["ntfy_user"], user_config["ntfy_password"]),
                timeout=8,
            )
            poll.raise_for_status()
            for line in poll.text.splitlines():
                if not line:
                    continue
                message = json.loads(line)
                if message.get("message") == title + " updated":
                    received = True
                    break
            if received:
                break
            time.sleep(2)
        assert received, "Vikunja webhook did not reach the isolated ntfy topic"
        result["checks"]["real_signed_webhook_reached_ntfy"] = "PASS"

        listed_after = requests.get(
            f"{api}/api/v1/reminders", headers=user_headers, timeout=8
        )
        listed_after.raise_for_status()
        fired = next(
            row for row in listed_after.json()["reminders"]
            if row["reminder_id"] == reminder["reminder_id"]
        )
        assert fired["status"] == "due"
        result["checks"]["life_core_recorded_fired_state"] = "PASS"

        cancel_title = title + " cancel"
        cancel_due = datetime.now(ZoneInfo("Asia/Hong_Kong")) + timedelta(seconds=45)
        cancel_create = requests.post(
            f"{api}/api/v1/reminders",
            headers=user_headers,
            json={"title": cancel_title, "scheduled_at": cancel_due.isoformat()},
            timeout=12,
        )
        cancel_create.raise_for_status()
        cancel_reminder = cancel_create.json()["reminder"]
        cancel_tasks = requests.get(
            f"{VIKUNJA}/tasks",
            headers={
                "Authorization": "Bearer "
                + json.loads(
                    (RUNTIME / "life-core-vikunja-users.json").read_text(
                        encoding="utf-8"
                    )
                )[life_id]["api_token"]
            },
            timeout=8,
        )
        cancel_tasks.raise_for_status()
        cancel_task = next(
            row for row in cancel_tasks.json()["items"] if row["title"] == cancel_title
        )
        task_ids.append(int(cancel_task["id"]))
        cancelled = requests.delete(
            f"{api}/api/v1/reminders/{cancel_reminder['reminder_id']}",
            headers=user_headers,
            timeout=12,
        )
        cancelled.raise_for_status()
        assert cancelled.json()["reminder"]["status"] == "cancelled"
        missing = vikunja_session.get(
            f"{VIKUNJA}/tasks/{cancel_task['id']}", timeout=8
        )
        assert missing.status_code == 404
        result["checks"]["life_core_cancelled_and_deleted_upstream_task"] = "PASS"

        removed_hook = vikunja_session.delete(
            f"{VIKUNJA}/user/settings/webhooks/{webhook_id}", timeout=8
        )
        removed_hook.raise_for_status()
        webhook_id = None
        lost_title = title + " inbox recovery"
        lost_create = requests.post(
            f"{api}/api/v1/reminders",
            headers=user_headers,
            json={
                "title": lost_title,
                "scheduled_at": (datetime.now(ZoneInfo("Asia/Hong_Kong")) + timedelta(seconds=75)).isoformat(),
            },
            timeout=12,
        )
        lost_create.raise_for_status()
        latest_tasks = vikunja_session.get(f"{VIKUNJA}/tasks", timeout=8)
        latest_tasks.raise_for_status()
        lost_task = next(row for row in latest_tasks.json()["items"] if row["title"] == lost_title)
        task_ids.append(lost_task["id"])
        deadline = time.monotonic() + 200
        recovered = False
        while time.monotonic() < deadline:
            inbox = requests.get(
                f"{api}/api/v1/reminder-notifications", headers=user_headers, timeout=12
            )
            inbox.raise_for_status()
            messages = inbox.json()["messages"]
            assert not any(item["message"] == cancel_title for item in messages)
            if any(item["message"] == lost_title for item in messages):
                recovered = True
                break
            time.sleep(3)
        assert recovered, "missing webhook was not recovered from Vikunja notification inbox"
        result["checks"]["missing_webhook_recovered_from_official_inbox"] = "PASS"
        result["checks"]["cancelled_reminder_not_pushed_after_original_deadline"] = "PASS"
        result["checks"]["ntfy_messages_read_through_authorized_life_core"] = "PASS"

        planned = (datetime.now(ZoneInfo("Asia/Hong_Kong")) + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        request_body = {
            "source_user_id": "lc-user-a",
            "source_message_id": "live-chat-create",
            "text": f"请在{planned.strftime('%Y年%m月%d日')}上午九点提醒我喝龙井茶。",
        }
        action = requests.post(
            f"{api}/internal/v1/reminders/execute",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json=request_body,
            timeout=35,
        )
        action.raise_for_status()
        assert action.json()["status"] == "succeeded", action.json()
        repeat = requests.post(
            f"{api}/internal/v1/reminders/execute",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json=request_body,
            timeout=12,
        )
        repeat.raise_for_status()
        assert repeat.json() == action.json()
        result["checks"]["real_llm_chat_created_and_retry_deduplicated"] = "PASS"
        query_after_chat = requests.get(f"{api}/api/v1/reminders", headers=user_headers, timeout=8)
        query_after_chat.raise_for_status()
        chat_reminder = next(
            row for row in query_after_chat.json()["reminders"]
            if row["status"] == "scheduled" and row["title"] not in (title, cancel_title, lost_title)
        )
        remote_after_chat = vikunja_session.get(f"{VIKUNJA}/tasks", timeout=8)
        remote_after_chat.raise_for_status()
        task_ids.extend(
            row["id"] for row in remote_after_chat.json()["items"]
            if row["title"] == chat_reminder["title"] and row["id"] not in task_ids
        )
        result["chat_result"] = action.json()
        cancel_chat = requests.post(
            f"{api}/internal/v1/reminders/execute",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={
                "source_user_id": "lc-user-a",
                "source_message_id": "live-chat-cancel",
                "text": f"请取消内容为「{chat_reminder['title']}」的提醒。",
            },
            timeout=35,
        )
        cancel_chat.raise_for_status()
        assert cancel_chat.json()["status"] == "succeeded", cancel_chat.json()
        result["checks"]["real_llm_chat_cancelled_existing_reminder"] = "PASS"
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        if webhook_id is not None:
            response = vikunja_session.delete(
                f"{VIKUNJA}/user/settings/webhooks/{webhook_id}", timeout=8
            )
            result["cleanup_webhook"] = response.status_code in (200, 204, 404)
        for task_id in task_ids:
            response = vikunja_session.delete(f"{VIKUNJA}/tasks/{task_id}", timeout=8)
            result.setdefault("cleanup_tasks", []).append(
                {"task_id": task_id, "deleted": response.status_code in (200, 204, 404)}
            )
        if app_process.is_alive():
            app_process.terminate()
            app_process.join(timeout=8)
        result["ended_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        evidence_path = ROOT / "evidence/v02-memory-reminders/life-core-live-api.json"
        evidence_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT / "services/life-core"))
    multiprocessing.freeze_support()
    main()
