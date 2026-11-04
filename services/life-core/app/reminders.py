from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from .store import utc_now
from .reminder_workflow import ReminderWorkflow


class ReminderUpstreamError(RuntimeError):
    pass


class ReminderPermissionError(ReminderUpstreamError):
    pass


class ReminderService:
    def __init__(self, store, settings):
        self.store = store
        self.settings = settings
        self.provisioning = None
        self.drafts = None
        self.workflow = ReminderWorkflow(store.database_path, self, task=True)

    def _draft_id(self, owner, reminder_id):
        if self.drafts is None:
            return None
        with self.store.connect() as db:
            row = db.execute(
                "SELECT draft_id FROM reminder_submissions WHERE owner_id=? AND reminder_id=?",
                (owner, reminder_id)).fetchone()
        return row["draft_id"] if row else None

    def _workflow_load(self, owner, reminder_id):
        value = self.store.get_reminder(reminder_id, owner)
        if value is None:
            raise HTTPException(404, detail={"code": "REMINDER_NOT_FOUND"})
        return {"status": value["status"], "revision": value["revision"],
                "missing_fields": [], "reminder_id": reminder_id}

    def _workflow_authorize(self, owner, reminder_id, command):
        value = self._workflow_load(owner, reminder_id)
        if value["revision"] != command["revision"]:
            raise HTTPException(409, detail={"code": "REMINDER_REVISION_CONFLICT"})
        if command.get("done") is not True and not self.notifications_allowed(owner):
            raise ReminderPermissionError("NOTIFICATION_CONSENT_REQUIRED")

    def _workflow_update(self, owner, reminder_id, command):
        return self._update(
            owner, reminder_id, title=command.get("title"),
            scheduled_at=datetime.fromisoformat(command["scheduled_at"]) if command.get("scheduled_at") else None,
            timezone_name=command.get("timezone_name"), done=command.get("done"))

    def _workflow_cancel(self, owner, reminder_id, command):
        return self._cancel(owner, reminder_id)

    def configured(self, life_user_id: str) -> bool:
        return bool(self._configs().get(life_user_id))

    def _configs(self):
        return self.provisioning.configs() if self.provisioning else self.settings.vikunja_users

    def _user_config(self, life_user_id: str) -> dict[str, Any]:
        config = self.provisioning.config(life_user_id) if self.provisioning else self.settings.vikunja_users.get(life_user_id)
        if not config or not config.get("api_token") or not config.get("project_id"):
            raise ReminderUpstreamError("REMINDER_USER_NOT_CONFIGURED")
        expires = config.get("token_expires_at")
        if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc) + timedelta(days=1):
            self.provisioning.provision(life_user_id, renew=True)
            config = self.provisioning.config(life_user_id)
            if not config:
                raise ReminderUpstreamError("TOKEN_RENEWAL_UNAVAILABLE")
        return config

    def notifications_allowed(self, life_user_id: str) -> bool:
        with self.store.connect() as db:
            row = db.execute(
                "SELECT notification_consent FROM memory_permissions WHERE user_id = ?",
                (life_user_id,),
            ).fetchone()
        return bool(row and row["notification_consent"])

    def _request(self, config: dict[str, Any], method: str, path: str, **kwargs):
        try:
            response = httpx.request(
                method,
                f"{self.settings.vikunja_base_url}{path}",
                headers={"Authorization": f"Bearer {config['api_token']}"},
                timeout=8,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ReminderUpstreamError("VIKUNJA_UNAVAILABLE") from exc
        if response.is_error:
            raise ReminderUpstreamError(f"VIKUNJA_HTTP_{response.status_code}")
        return response

    @staticmethod
    def _remote_reminder(scheduled_at: datetime) -> dict[str, Any]:
        instant = scheduled_at.astimezone(timezone.utc).replace(microsecond=0)
        return {
            "reminder": instant.isoformat().replace("+00:00", "Z"),
            "relative_period": 0,
        }

    @staticmethod
    def _minute_time(value: datetime) -> datetime:
        # Vikunja's scheduler operates per minute; round forward, never remind early.
        return value.replace(second=0, microsecond=0) + (
            timedelta(minutes=1) if value.second or value.microsecond else timedelta()
        )

    def create(
        self,
        life_user_id: str,
        *,
        title: str,
        scheduled_at: datetime,
        timezone_name: str,
        delivery_channel: str,
        submission_marker: str | None = None,
        on_remote=None,
    ):
        config = self._user_config(life_user_id)
        if not self.notifications_allowed(life_user_id):
            raise ReminderPermissionError("NOTIFICATION_CONSENT_REQUIRED")
        scheduled_at = self._minute_time(scheduled_at)
        response = self._request(
            config,
            "POST",
            f"/projects/{int(config['project_id'])}/tasks",
            json={
                "title": title,
                "reminders": [self._remote_reminder(scheduled_at)],
                **({"description": submission_marker} if submission_marker else {}),
            },
        )
        task = response.json()
        if on_remote:
            on_remote(task)
        return self.store.create_reminder(
            owner_user_id=life_user_id,
            title=task["title"],
            scheduled_at=scheduled_at.isoformat(),
            timezone=timezone_name,
            upstream_task_id=int(task["id"]),
            delivery_channel=delivery_channel,
        )

    def list(self, life_user_id: str):
        records = self.store.list_reminders(life_user_id)
        if not self.configured(life_user_id):
            return records
        config = self._user_config(life_user_id)
        response = self._request(config, "GET", "/tasks", params={"per_page": 100})
        tasks = {item["id"]: item for item in response.json().get("items", [])}
        for record in records:
            if record["status"] == "cancelled" or not record["upstream_task_id"]:
                continue
            task = tasks.get(record["upstream_task_id"])
            if task is None:
                try:
                    task = self._request(config, "GET", f"/tasks/{record['upstream_task_id']}").json()
                except ReminderUpstreamError as exc:
                    if str(exc) == "VIKUNJA_HTTP_404":
                        self.store.cancel_reminder(record["reminder_id"], life_user_id)
                        continue
                    raise
            remote_at = (task.get("reminders") or [{}])[0].get("reminder")
            changed_at = (
                remote_at if remote_at and
                datetime.fromisoformat(remote_at.replace("Z", "+00:00")).timestamp() !=
                datetime.fromisoformat(record["scheduled_at"]).timestamp() else None
            )
            if (not changed_at and task["title"] == record["title"]
                    and bool(task.get("done")) == (record["status"] == "completed")):
                continue
            self.store.update_reminder(
                record["reminder_id"], life_user_id, title=task["title"],
                scheduled_at=changed_at, timezone=None,
                done=True if task.get("done") else None,
            )
        return self.store.list_reminders(life_user_id)

    def notifications(self, life_user_id: str):
        config = self._user_config(life_user_id)
        if not self.notifications_allowed(life_user_id):
            return []
        try:
            response = httpx.get(
                f"{config['ntfy_base_url'].rstrip('/')}/{config['ntfy_topic']}/json",
                params={"poll": "1", "since": "24h"},
                auth=(config["ntfy_user"], config["ntfy_password"]),
                timeout=8,
            )
            response.raise_for_status()
            messages = [json.loads(line) for line in response.text.splitlines() if line]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ReminderUpstreamError("NTFY_READ_FAILED") from exc
        latest = {}
        for item in messages:
            latest[item.get("sequence_id") or item.get("id")] = item
        return [
            {
                "id": item["id"],
                "title": item.get("title", "Shiguang"),
                "message": item.get("message", ""),
                "time": item["time"],
            }
            for item in latest.values()
            if item.get("event") == "message" and item.get("title") == "Shiguang"
        ][-10:][::-1]

    def update(
        self,
        life_user_id: str,
        reminder_id: str,
        *,
        title: str | None,
        scheduled_at: datetime | None,
        timezone_name: str | None,
        done: bool | None = None,
    ):
        current = self.store.get_reminder(reminder_id, life_user_id)
        if current is None or current["status"] == "cancelled":
            return None
        values = dict(title=title, scheduled_at=scheduled_at,
                      timezone_name=timezone_name, done=done)
        draft_id = self._draft_id(life_user_id, reminder_id)
        if draft_id:
            return self.drafts.update_reminder(life_user_id, draft_id, **values)
        self.workflow.send(life_user_id, reminder_id, {
            "action": "update", "revision": current["revision"],
            **{key: value.isoformat() if isinstance(value, datetime) else value
               for key, value in values.items()}})
        return self.store.get_reminder(reminder_id, life_user_id)

    def _update(
        self,
        life_user_id: str,
        reminder_id: str,
        *,
        title: str | None,
        scheduled_at: datetime | None,
        timezone_name: str | None,
        done: bool | None = None,
    ):
        current = self.store.get_reminder(reminder_id, life_user_id)
        if current is None or current["status"] == "cancelled":
            return None
        config = self._user_config(life_user_id)
        if done is not True and not self.notifications_allowed(life_user_id):
            raise ReminderPermissionError("NOTIFICATION_CONSENT_REQUIRED")
        if scheduled_at is not None:
            scheduled_at = self._minute_time(scheduled_at)
        if (
            (title is None or title == current["title"])
            and (scheduled_at is None or scheduled_at.timestamp() == datetime.fromisoformat(current["scheduled_at"]).timestamp())
            and (timezone_name is None or timezone_name == current["timezone"])
            and (done is None or done == (current["status"] == "completed"))
        ):
            return current
        task_response = self._request(config, "GET", f"/tasks/{current['upstream_task_id']}")
        task = task_response.json()
        task.pop("max_permission", None)
        task.pop("$schema", None)
        if title is not None:
            task["title"] = title
        if done is not None:
            task["done"] = done
        if scheduled_at is not None:
            scheduled_at = self._minute_time(scheduled_at)
            task["reminders"] = [self._remote_reminder(scheduled_at)]
        response = self._request(
            config, "PUT", f"/tasks/{current['upstream_task_id']}", json=task
        )
        task = response.json()
        return self.store.update_reminder(
            reminder_id,
            life_user_id,
            title=task["title"],
            scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
            timezone=timezone_name,
            done=done,
        )

    def cancel(self, life_user_id: str, reminder_id: str):
        current = self.store.get_reminder(reminder_id, life_user_id)
        if current is None:
            return None
        draft_id = self._draft_id(life_user_id, reminder_id)
        if draft_id:
            self.drafts.cancel(life_user_id, draft_id)
        else:
            self.workflow.send(life_user_id, reminder_id, {"action": "cancel"})
        return self.store.get_reminder(reminder_id, life_user_id)

    def _cancel(self, life_user_id: str, reminder_id: str):
        current = self.store.get_reminder(reminder_id, life_user_id)
        if current is None:
            return None
        if current["status"] == "cancelled":
            return current
        config = self._user_config(life_user_id)
        try:
            self._request(config, "DELETE", f"/tasks/{current['upstream_task_id']}")
        except ReminderUpstreamError as exc:
            if str(exc) != "VIKUNJA_HTTP_404":
                raise
        return self.store.cancel_reminder(reminder_id, life_user_id)

    def handle_webhook(self, raw_body: bytes, signature: str) -> bool:
        try:
            payload = json.loads(raw_body)
            data = payload["data"]
            vikunja_user_id = str(data["user"]["id"])
        except (ValueError, KeyError, TypeError):
            return False
        matched = next(
            (
                (life_user_id, item)
                for life_user_id, item in self._configs().items()
                if str(item.get("vikunja_user_id")) == vikunja_user_id
            ),
            None,
        )
        if not matched or payload.get("event_name") != "task.reminder.fired":
            return False
        life_user_id, config = matched
        secret = config.get("webhook_secret", "")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, signature):
            return False
        task = data.get("task", {})
        try:
            task_id = int(task["id"])
        except (KeyError, TypeError, ValueError):
            return False
        reminder = self.store.get_reminder_by_task(task_id, life_user_id)
        if not reminder or reminder["status"] in ("cancelled", "completed"):
            return True
        callback_time = data.get("reminder", {}).get("reminder")
        try:
            if int(datetime.fromisoformat(callback_time.replace("Z", "+00:00")).timestamp()) != int(
                datetime.fromisoformat(reminder["scheduled_at"]).timestamp()
            ):
                return True
        except (ValueError, AttributeError, TypeError):
            return False
        if not self.notifications_allowed(life_user_id):
            return True
        event_id = hashlib.sha256(
            f"{life_user_id}:{task_id}:{reminder['scheduled_at']}".encode()
        ).hexdigest()
        self.store.queue_reminder_notification(
            event_id=event_id,
            owner_user_id=life_user_id,
            payload=payload,
            not_before=reminder["scheduled_at"],
        )
        self.deliver_one_notification()
        return True

    def reconcile_notifications(self) -> int:
        """Recover missed callbacks from Vikunja's own durable notification inbox."""
        users = 0
        for life_user_id, config in self._configs().items():
            if not self.notifications_allowed(life_user_id):
                continue
            users += 1
            try:
                response = self._request(
                    config, "GET", "/notifications", params={"per_page": 100}
                )
                for item in response.json().get("items", []):
                    if item.get("name") != "task.reminder":
                        continue
                    task = item.get("notification", {}).get("task", {})
                    reminder = self.store.get_reminder_by_task(task.get("id"), life_user_id)
                    if not reminder or reminder["status"] in ("cancelled", "completed"):
                        continue
                    scheduled = datetime.fromisoformat(reminder["scheduled_at"]).timestamp()
                    fired = datetime.fromisoformat(item["created"].replace("Z", "+00:00")).timestamp()
                    if not abs(scheduled - fired) < 61:
                        continue
                    event_id = hashlib.sha256(
                        f"{life_user_id}:{task['id']}:{reminder['scheduled_at']}".encode()
                    ).hexdigest()
                    self.store.queue_reminder_notification(
                        event_id=event_id,
                        owner_user_id=life_user_id,
                        payload={"data": {"task": task}},
                        not_before=reminder["scheduled_at"],
                    )
            except (ReminderUpstreamError, ValueError, KeyError, TypeError):
                continue
        return users

    def reconcile_all(self) -> tuple[int, int]:
        """Run one reconciliation pass over provisioned owners for the scheduler."""
        run_id = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("INSERT INTO reminder_scheduler_runs (run_id, started_at, status) VALUES (?, ?, 'running')",
                       (run_id, utc_now()))
        users, delivered = 0, 0
        try:
            users = self.reconcile_notifications()
            # Bound each pass; durable pending events remain for the next pass.
            for _ in range(100):
                if not self.deliver_one_notification():
                    break
                delivered += 1
        except Exception:
            with self.store.connect() as db:
                db.execute("""UPDATE reminder_scheduler_runs SET status='failed',
                    completed_at=?, error_code='RECONCILIATION_FAILED' WHERE run_id=?""",
                           (utc_now(), run_id))
            raise
        with self.store.connect() as db:
            db.execute("""UPDATE reminder_scheduler_runs SET status='completed', completed_at=?,
                users=?, notifications_accepted=? WHERE run_id=?""",
                       (utc_now(), users, delivered, run_id))
        return users, delivered

    def deliver_one_notification(self) -> bool:
        event = self.store.next_reminder_notification()
        if event is None:
            return False
        config = self._configs().get(event["owner_user_id"])
        if not config or not self.notifications_allowed(event["owner_user_id"]):
            self.store.suppress_reminder_notification(event["event_id"])
            return False
        task = event["payload"].get("data", {}).get("task", {})
        reminder = self.store.get_reminder_by_task(task.get("id"), event["owner_user_id"])
        if not reminder or reminder["status"] in ("cancelled", "completed"):
            self.store.suppress_reminder_notification(event["event_id"])
            return False
        current_event_id = hashlib.sha256(
            f"{event['owner_user_id']}:{task['id']}:{reminder['scheduled_at']}".encode()
        ).hexdigest()
        if event["event_id"] != current_event_id:
            self.store.suppress_reminder_notification(event["event_id"])
            return False
        self.store.mark_reminder_fired(int(task["id"]), event["owner_user_id"])
        try:
            if event["attempts"] > 1:
                cached = httpx.get(
                    f"{config['ntfy_base_url'].rstrip('/')}/{config['ntfy_topic']}/json",
                    params={"poll": "1", "since": "24h"},
                    auth=(config["ntfy_user"], config["ntfy_password"]),
                    timeout=8,
                )
                cached.raise_for_status()
                if any(
                    json.loads(line).get("sequence_id") == event["event_id"]
                    for line in cached.text.splitlines() if line
                ):
                    self.store.complete_reminder_notification(event["event_id"])
                    return True
            response = httpx.post(
                f"{config['ntfy_base_url'].rstrip('/')}/{config['ntfy_topic']}",
                content=reminder["title"].encode("utf-8"),
                headers={"Title": "Shiguang", "X-Sequence-ID": event["event_id"]},
                auth=(config["ntfy_user"], config["ntfy_password"]),
                timeout=8,
            )
            response.raise_for_status()
        except (httpx.HTTPError, KeyError, ValueError, UnicodeError):
            self.store.fail_reminder_notification(event["event_id"])
            return False
        self.store.complete_reminder_notification(event["event_id"])
        return True
