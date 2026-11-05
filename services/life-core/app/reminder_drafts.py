from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .reminders import ReminderPermissionError, ReminderUpstreamError
from .store import utc_now
from .reminder_parser import parse, choices

REFERENCE = re.compile(r"刚才(?:那个|的)(?:提醒)?|那条提醒")


class DraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None
    event_time: time | None = None
    timezone: str | None = Field(default=None, max_length=100)
    lead_minutes: int | None = Field(default=None, ge=0, le=10080, strict=True)
    place: str | None = Field(default=None, max_length=100)
    reminder_date: date | None = None
    reminder_time: time | None = None

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("INVALID_TIMEZONE") from exc
        return value


def preview(fields: dict, now: datetime | None = None):
    missing = [k for k in ("title", "event_date", "event_time", "timezone", "lead_minutes")
               if fields.get(k) is None or fields.get(k) == ""]
    if missing:
        return missing, None
    try:
        zone = ZoneInfo(fields["timezone"])
        clock = time.fromisoformat(fields["event_time"])
        if clock.tzinfo or clock.second or clock.microsecond:
            raise ValueError("INVALID_EVENT_TIME")
        local = datetime.combine(date.fromisoformat(fields["event_date"]), clock)
        offsets = set()
        for fold in (0, 1):
            value = local.replace(tzinfo=zone, fold=fold)
            if value.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == local:
                offsets.add(value.utcoffset())
        if not offsets:
            raise ValueError("NONEXISTENT_LOCAL_TIME")
        if len(offsets) > 1:
            raise ValueError("AMBIGUOUS_LOCAL_TIME")
        event = local.replace(tzinfo=zone)
        scheduled = event.astimezone(timezone.utc) - timedelta(minutes=fields["lead_minutes"])
        if fields.get("reminder_time"):
            # Validate the second local time with the same DST and future checks.
            _, notification = preview({**fields, "event_date": fields.get("reminder_date") or fields["event_date"],
                                       "event_time": fields["reminder_time"], "lead_minutes": 0,
                                       "reminder_time": None}, now)
            scheduled = datetime.fromisoformat(notification["scheduled_at"])
        if scheduled <= (now or datetime.now(timezone.utc)):
            raise ValueError("REMINDER_TIME_IN_PAST")
        return [], {"event_at": event.isoformat(),
                    "scheduled_at": scheduled.astimezone(zone).isoformat(),
                    "timezone": fields["timezone"]}
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise ValueError("INVALID_TIMEZONE") from exc


class ReminderDrafts:
    def __init__(self, store, settings, reminders):
        self.store, self.settings, self.reminders = store, settings, reminders
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reminder_drafts (
                    draft_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, source_message_id TEXT NOT NULL,
                    source_text TEXT NOT NULL, fields TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL,
                    expires_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(owner_id,conversation_id,source_message_id)
                );
                CREATE TABLE IF NOT EXISTS reminder_submissions (
                    owner_id TEXT NOT NULL, draft_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL, state TEXT NOT NULL,
                    task_json TEXT, reminder_id TEXT, updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner_id,draft_id), UNIQUE(owner_id,idempotency_key)
                );
            """)
            # A process restart may follow a successful upstream write. Reconcile, never resend.
            db.execute("UPDATE reminder_submissions SET state='unknown' WHERE state='creating'")
            db.execute("UPDATE reminder_drafts SET state='unknown' WHERE state='creating'")
            columns = {r["name"] for r in db.execute("PRAGMA table_info(reminder_submissions)")}
            if "last_error" not in columns:
                db.execute("ALTER TABLE reminder_submissions ADD COLUMN last_error TEXT")

    def _row(self, owner, draft_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM reminder_drafts WHERE owner_id=? AND draft_id=?",
                             (owner, draft_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "DRAFT_NOT_FOUND"})
        row = dict(row)
        if row["expires_at"] <= utc_now() and row["state"] not in ("scheduled", "cancelled", "unknown", "creating"):
            row["state"] = "expired"
        return row

    def public(self, row):
        fields = json.loads(row["fields"])
        missing, value = [], None
        error = None
        try:
            missing, value = preview(fields)
        except ValueError as exc:
            error = str(exc)
        state = row["state"]
        if state in ("needs_input", "ready_to_confirm", "unavailable"):
            state = "needs_input" if missing or error else "ready_to_confirm"
        with self.store.connect() as db:
            submission = db.execute("SELECT * FROM reminder_submissions WHERE owner_id=? AND draft_id=?",
                                    (row["owner_id"], row["draft_id"])).fetchone()
        reminder = self.store.get_reminder(submission["reminder_id"], row["owner_id"]) if submission and submission["reminder_id"] else None
        if reminder:
            reminder = {k: v for k, v in reminder.items() if k != "owner_user_id"}
            if reminder["status"] in ("cancelled", "completed"):
                state = reminder["status"]
        result = {"draft_id": row["draft_id"], "conversation_id": row["conversation_id"],
                "source_message_id": row["source_message_id"], "source_text": row["source_text"],
                **fields, "status": state, "revision": row["revision"],
                "expires_at": row["expires_at"], "missing_fields": missing, "preview": value,
                "error_code": error or (submission["last_error"] if submission else None), "reminder": reminder,
                "availability": self.reminders.provisioning.status(row["owner_id"])}
        result["quick_choice"] = choices(fields, missing, row["source_text"])
        result["parsed_at"] = row["created_at"]
        result["parse_source"] = "server_calendar_and_user_text"
        if REFERENCE.search(row["source_text"]):
            with self.store.connect() as db:
                candidates = db.execute("""SELECT * FROM reminder_drafts WHERE owner_id=?
                    AND conversation_id=? AND draft_id<>? AND expires_at>?
                    AND state IN ('needs_input','ready_to_confirm','unavailable','scheduled')
                    AND (state<>'scheduled' OR EXISTS (
                        SELECT 1 FROM reminder_submissions s JOIN reminders r
                        ON r.reminder_id=s.reminder_id AND r.owner_user_id=s.owner_id
                        WHERE s.draft_id=reminder_drafts.draft_id
                        AND s.owner_id=reminder_drafts.owner_id
                        AND r.status IN ('scheduled','due')))
                    ORDER BY created_at""",
                    (row["owner_id"], row["conversation_id"], row["draft_id"], utc_now())).fetchall()
            result["reference_options"] = [
                {"draft_id": item["draft_id"], "source_message_id": item["source_message_id"],
                 **{key: json.loads(item["fields"]).get(key)
                    for key in ("title", "event_date", "event_time")}}
                for item in candidates if not REFERENCE.search(item["source_text"])
            ]
        return result

    def get(self, owner, draft_id):
        return self.public(self._row(owner, draft_id))

    def list(self, owner, conversation):
        with self.store.connect() as db:
            rows = db.execute("""SELECT draft_id FROM reminder_drafts WHERE owner_id=?
                AND conversation_id=? ORDER BY created_at""", (owner, conversation)).fetchall()
        return [self.get(owner, row["draft_id"]) for row in rows]

    def extract(self, text, now=None, timezone_name=None):
        return DraftFields.model_validate(parse(
            text, timezone_name or self.settings.timezone, now)).model_dump(mode="json")

    def create(self, owner, conversation, source, text, fields=None):
        if not conversation:
            raise HTTPException(422, detail={"code": "CONVERSATION_REQUIRED"})
        with self.store.connect() as db:
            old = db.execute("""SELECT draft_id FROM reminder_drafts WHERE owner_id=?
                AND conversation_id=? AND source_message_id=?""", (owner, conversation, source)).fetchone()
        if old:
            return self.get(owner, old["draft_id"])
        if fields is None:
            try:
                with self.store.connect() as db:
                    preferences = db.execute("SELECT timezone FROM user_preferences WHERE user_id=?", (owner,)).fetchone()
                fields = DraftFields().model_dump(mode="json") if REFERENCE.search(text) else self.extract(
                    text,timezone_name=preferences[0] if preferences else self.settings.timezone)
            except (ValueError, KeyError) as exc:
                raise HTTPException(422, detail={"code":"INVALID_REMINDER_DATE_TIME"}) from exc
        else:
            fields = DraftFields.model_validate(fields).model_dump(mode="json")
        identifier = "rd_" + uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("""INSERT OR IGNORE INTO reminder_drafts VALUES (?,?,?,?,?,?,1,'needs_input',?,?,?)""",
                       (identifier, owner, conversation, source, text, json.dumps(fields, ensure_ascii=False),
                        (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(), utc_now(), utc_now()))
            row = db.execute("""SELECT draft_id FROM reminder_drafts WHERE owner_id=?
                AND conversation_id=? AND source_message_id=?""", (owner, conversation, source)).fetchone()
        return self.get(owner, row["draft_id"])

    def patch(self, owner, draft_id, revision, changes):
        row = self._row(owner, draft_id)
        if REFERENCE.search(row["source_text"]):
            raise HTTPException(409, detail={"code": "REFERENCE_SELECTION_ONLY"})
        if row["state"] in ("scheduled", "creating", "unknown", "cancelled", "expired"):
            raise HTTPException(409, detail={"code": "DRAFT_LOCKED"})
        fields = {**json.loads(row["fields"]), **changes}
        if fields.get("timezone") and not fields.get("event_date"):
            try:
                today = datetime.fromisoformat(row["created_at"]).astimezone(ZoneInfo(fields["timezone"])).date()
                for word, offset in (("明天", 1), ("后天", 2), ("今天", 0)):
                    if word in row["source_text"]:
                        fields["event_date"] = (today + timedelta(days=offset)).isoformat()
                        break
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise HTTPException(422, detail={"code": "INVALID_TIMEZONE"}) from exc
        fields = DraftFields.model_validate(fields).model_dump(mode="json")
        try:
            preview(fields)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": str(exc)}) from exc
        with self.store.connect() as db:
            result = db.execute("""UPDATE reminder_drafts SET fields=?,revision=revision+1,
                state='needs_input',updated_at=? WHERE owner_id=? AND draft_id=? AND revision=?
                AND state IN ('needs_input','ready_to_confirm','unavailable')""",
                                (json.dumps(fields, ensure_ascii=False), utc_now(), owner, draft_id, revision))
            if result.rowcount != 1:
                raise HTTPException(409, detail={"code": "DRAFT_REVISION_CONFLICT"})
        return self.get(owner, draft_id)

    def cancel(self, owner, draft_id):
        row = self._row(owner, draft_id)
        if row["state"] in ("creating", "unknown"):
            raise HTTPException(409, detail={"code": "CHECK_REMINDER_LIST"})
        value = self.get(owner, draft_id)
        if value["reminder"] and value["reminder"]["status"] not in ("cancelled", "completed"):
            self.reminders.cancel(owner, value["reminder"]["reminder_id"])
        with self.store.connect() as db:
            db.execute("UPDATE reminder_drafts SET state='cancelled',updated_at=? WHERE owner_id=? AND draft_id=?",
                       (utc_now(), owner, draft_id))
        return self.get(owner, draft_id)

    def confirm(self, owner, draft_id, revision, idempotency_key):
        row = self._row(owner, draft_id)
        if REFERENCE.search(row["source_text"]):
            raise HTTPException(409, detail={"code": "REFERENCE_SELECTION_ONLY"})
        with self.store.connect() as db:
            old = db.execute("SELECT * FROM reminder_submissions WHERE owner_id=? AND draft_id=?",
                             (owner, draft_id)).fetchone()
        if old:
            return self.get(owner, draft_id)
        if row["revision"] != revision:
            raise HTTPException(409, detail={"code": "DRAFT_REVISION_CONFLICT"})
        if row["state"] not in ("needs_input", "ready_to_confirm", "unavailable"):
            raise HTTPException(409, detail={"code": "DRAFT_LOCKED"})
        fields = json.loads(row["fields"])
        try:
            missing, value = preview(fields)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": str(exc)}) from exc
        if missing:
            raise HTTPException(422, detail={"code": "MISSING_FIELDS", "fields": missing})
        if not self.reminders.notifications_allowed(owner):
            raise ReminderPermissionError("NOTIFICATION_CONSENT_REQUIRED")
        if not self.reminders.configured(owner):
            status = self.reminders.provisioning.provision(owner)
            if status["status"] != "ready":
                raise HTTPException(409, detail={"code": "PROVISIONING_IN_PROGRESS"})
        marker = "LifeCompanion draft " + hashlib.sha256(f"{owner}:{draft_id}:{revision}".encode()).hexdigest()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM reminder_drafts WHERE owner_id=? AND draft_id=?", (owner, draft_id)).fetchone()
            if current["revision"] != revision or current["state"] not in ("needs_input", "ready_to_confirm", "unavailable"):
                return self.get(owner, draft_id)
            inserted = db.execute("""INSERT OR IGNORE INTO reminder_submissions (
                owner_id,draft_id,revision,idempotency_key,state,task_json,reminder_id,updated_at
                ) VALUES (?,?,?,?,'creating',NULL,NULL,?)""",
                                  (owner, draft_id, revision, idempotency_key, utc_now()))
            if not inserted.rowcount:
                return self.get(owner, draft_id)
            db.execute("UPDATE reminder_drafts SET state='creating',updated_at=? WHERE draft_id=?", (utc_now(), draft_id))
        try:
            reminder = self.reminders.create(
                owner, title=fields["title"], scheduled_at=datetime.fromisoformat(value["scheduled_at"]),
                timezone_name=fields["timezone"], delivery_channel="push", submission_marker=marker,
                on_remote=lambda task: self._remember_remote(owner, draft_id, task))
            with self.store.connect() as db:
                db.execute("UPDATE reminder_submissions SET state='scheduled',reminder_id=?,updated_at=? WHERE owner_id=? AND draft_id=?",
                           (reminder["reminder_id"], utc_now(), owner, draft_id))
                db.execute("UPDATE reminder_drafts SET state='scheduled',updated_at=? WHERE draft_id=?", (utc_now(), draft_id))
        except Exception as exc:
            # An HTTP timeout or failed local write may follow an upstream success.
            # Keep the operation claimed and expose reconciliation, never auto-POST.
            with self.store.connect() as db:
                code = str(exc) if isinstance(exc, ReminderUpstreamError) else "LOCAL_SAVE_OR_UPSTREAM_RESULT_UNKNOWN"
                db.execute("UPDATE reminder_submissions SET state='unknown',last_error=?,updated_at=? WHERE owner_id=? AND draft_id=?",
                           (code, utc_now(), owner, draft_id))
                db.execute("UPDATE reminder_drafts SET state='unknown',updated_at=? WHERE draft_id=?", (utc_now(), draft_id))
        return self.get(owner, draft_id)

    def _remember_remote(self, owner, draft_id, task):
        with self.store.connect() as db:
            db.execute("UPDATE reminder_submissions SET task_json=?,updated_at=? WHERE owner_id=? AND draft_id=?",
                       (json.dumps(task), utc_now(), owner, draft_id))

    def reconcile(self, owner, draft_id):
        row = self._row(owner, draft_id)
        if row["state"] != "unknown":
            return self.get(owner, draft_id)
        fields = json.loads(row["fields"])
        with self.store.connect() as db:
            submission = db.execute("SELECT * FROM reminder_submissions WHERE owner_id=? AND draft_id=?",
                                    (owner, draft_id)).fetchone()
        if not submission:
            return self.get(owner, draft_id)
        marker = "LifeCompanion draft " + hashlib.sha256(f"{owner}:{draft_id}:{submission['revision']}".encode()).hexdigest()
        config = self.reminders._user_config(owner)
        matches = []
        page = 1
        while True:
            response = self.reminders._request(config, "GET", f"/projects/{config['project_id']}/tasks",
                                              params={"page": page, "per_page": 100}).json()
            items = response.get("items", [])
            matches.extend(t for t in items if t.get("description") == marker)
            if len(items) < 100:
                break
            page += 1
        if len(matches) == 1:
            task = matches[0]
            remote_at = task["reminders"][0]["reminder"]
            reminder = self.store.get_reminder_by_task(task["id"], owner)
            if not reminder:
                reminder = self.store.create_reminder(
                    owner_user_id=owner, upstream_task_id=task["id"], title=task["title"],
                    scheduled_at=remote_at, timezone=fields["timezone"], delivery_channel="push")
            with self.store.connect() as db:
                db.execute("UPDATE reminder_submissions SET state='scheduled',reminder_id=?,updated_at=?,last_error=NULL WHERE owner_id=? AND draft_id=?",
                           (reminder["reminder_id"], utc_now(), owner, draft_id))
                db.execute("UPDATE reminder_drafts SET state='scheduled',updated_at=? WHERE draft_id=?", (utc_now(), draft_id))
        return self.get(owner, draft_id)
