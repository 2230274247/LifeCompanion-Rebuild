from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .occurrence import initialize_occurrence


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    life_user_id TEXT PRIMARY KEY,
                    librechat_user_id TEXT NOT NULL UNIQUE,
                    memos_user_id TEXT NOT NULL,
                    memos_username TEXT,
                    display_name TEXT,
                    memory_consent INTEGER NOT NULL DEFAULT 1,
                    image_consent INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(life_user_id),
                    source_type TEXT NOT NULL,
                    source_message_ids TEXT NOT NULL,
                    conversation_id TEXT,
                    occurred_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    consent_state TEXT NOT NULL,
                    memo_ref TEXT,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    error_message TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_user_time
                    ON events(user_id, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS ingest_attempts (
                    user_id TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    event_id TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, source_message_id)
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    owner_user_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    scheduled_for TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    upstream_reference TEXT
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    upstream_task_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    delivery_channel TEXT NOT NULL,
                    last_attempt_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminder_notifications (
                    event_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            initialize_occurrence(db, "events")
            reminder_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(reminders)").fetchall()
            }
            if "upstream_task_id" not in reminder_columns:
                db.execute("ALTER TABLE reminders ADD COLUMN upstream_task_id INTEGER")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_reminder_owner_task
                ON reminders(owner_user_id,upstream_task_id)""")
            db.execute(
                """
                UPDATE reminder_notifications SET status = 'pending', updated_at = ?
                WHERE status = 'sending'
                """,
                (utc_now(),),
            )

    def bootstrap_user(
        self,
        *,
        librechat_user_id: str,
        memos_user_id: str,
        memos_username: str | None,
        display_name: str | None,
        memory_consent: bool = True,
        image_consent: bool = True,
    ) -> dict[str, Any]:
        life_user_id = "life_" + hashlib.sha256(librechat_user_id.encode()).hexdigest()[:20]
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO users (
                    life_user_id, librechat_user_id, memos_user_id, memos_username,
                    display_name, memory_consent, image_consent, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(librechat_user_id) DO UPDATE SET
                    memos_user_id = excluded.memos_user_id,
                    memos_username = excluded.memos_username,
                    display_name = excluded.display_name,
                    memory_consent = excluded.memory_consent,
                    image_consent = excluded.image_consent,
                    updated_at = excluded.updated_at
                """,
                (
                    life_user_id,
                    librechat_user_id,
                    memos_user_id,
                    memos_username,
                    display_name,
                    int(memory_consent),
                    int(image_consent),
                    now,
                    now,
                ),
            )
        return self.get_user_by_librechat_id(librechat_user_id)

    def get_user_by_librechat_id(self, librechat_user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE librechat_user_id = ?", (librechat_user_id,)
            ).fetchone()
        return dict(row) if row else None

    def ensure_reminder_user(self, librechat_user_id: str) -> dict[str, Any]:
        life_id = "life_" + hashlib.sha256(librechat_user_id.encode()).hexdigest()[:20]
        with self.connect() as db:
            db.execute("""INSERT OR IGNORE INTO users (
                life_user_id,librechat_user_id,memos_user_id,memory_consent,image_consent,created_at,updated_at
                ) VALUES (?,?,'',1,1,?,?)""", (life_id, librechat_user_id, utc_now(), utc_now()))
        return self.get_user_by_librechat_id(librechat_user_id)

    def get_user(self, life_user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE life_user_id = ?", (life_user_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_consent(
        self, life_user_id: str, *, memory_consent: bool | None = None, image_consent: bool | None = None
    ) -> dict[str, Any]:
        current = self.get_user(life_user_id)
        if current is None:
            raise KeyError(life_user_id)
        memory_value = int(memory_consent) if memory_consent is not None else current["memory_consent"]
        image_value = int(image_consent) if image_consent is not None else current["image_consent"]
        with self.connect() as db:
            db.execute(
                """
                UPDATE users
                SET memory_consent = ?, image_consent = ?, updated_at = ?
                WHERE life_user_id = ?
                """,
                (memory_value, image_value, utc_now(), life_user_id),
            )
        return self.get_user(life_user_id)

    def get_ingest_attempt(self, user_id: str, source_message_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM ingest_attempts WHERE user_id = ? AND source_message_id = ?",
                (user_id, source_message_id),
            ).fetchone()
        return dict(row) if row else None

    def record_ingest_attempt(
        self,
        *,
        user_id: str,
        source_message_id: str,
        status: str,
        reason: str,
        event_id: str | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO ingest_attempts (
                    user_id, source_message_id, status, reason, event_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, source_message_id) DO UPDATE SET
                    status = excluded.status,
                    reason = excluded.reason,
                    event_id = excluded.event_id
                """,
                (user_id, source_message_id, status, reason, event_id, utc_now()),
            )

    def create_event(
        self,
        *,
        user_id: str,
        source_type: str,
        source_message_ids: list[str],
        conversation_id: str | None,
        occurred_at: str,
        title: str,
        summary: str,
        confidence: float,
        consent_state: str,
        status: str,
        idempotency_key: str,
        occurrence_start: str | None = None,
        occurrence_end: str | None = None,
        occurrence_precision: str = "unknown",
    ) -> dict[str, Any]:
        event_id = "evt_" + hashlib.sha256(
            f"{user_id}:{idempotency_key}".encode()
        ).hexdigest()[:24]
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO events (
                    event_id, user_id, source_type, source_message_ids, conversation_id,
                    occurred_at, title, summary, confidence, consent_state, status,
                    idempotency_key, created_at, updated_at, occurrence_start, occurrence_end, occurrence_precision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    event_id,
                    user_id,
                    source_type,
                    json.dumps(source_message_ids, ensure_ascii=False),
                    conversation_id,
                    occurred_at,
                    title,
                    summary,
                    confidence,
                    consent_state,
                    status,
                    idempotency_key,
                    now,
                    now,
                    occurrence_start, occurrence_end, occurrence_precision,
                ),
            )
            row = db.execute(
                "SELECT * FROM events WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return self._event_dict(row)

    def get_event(self, event_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM events WHERE event_id = ?"
        args: list[Any] = [event_id]
        if user_id is not None:
            query += " AND user_id = ?"
            args.append(user_id)
        with self.connect() as db:
            row = db.execute(query, args).fetchone()
        return self._event_dict(row) if row else None

    def list_events(self, user_id: str, *, published_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM events WHERE user_id = ?"
        if published_only:
            query += " AND status = 'published'"
        query += " ORDER BY occurred_at DESC, created_at DESC"
        with self.connect() as db:
            rows = db.execute(query, (user_id,)).fetchall()
        return [self._event_dict(row) for row in rows]

    def set_event_status(
        self,
        event_id: str,
        *,
        status: str,
        memo_ref: str | None = None,
        error_message: str | None = None,
        increment_attempts: bool = False,
    ) -> dict[str, Any]:
        attempts_fragment = ", attempts = attempts + 1" if increment_attempts else ""
        with self.connect() as db:
            db.execute(
                f"""
                UPDATE events
                SET status = ?, memo_ref = COALESCE(?, memo_ref),
                    error_message = ?, updated_at = ?{attempts_fragment}
                WHERE event_id = ?
                """,
                (status, memo_ref, error_message, utc_now(), event_id),
            )
            row = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        return self._event_dict(row)

    def upsert_task_run(
        self,
        *,
        job_type: str,
        idempotency_key: str,
        owner_user_id: str,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        last_error: str | None = None,
        upstream_reference: str | None = None,
        increment_attempts: bool = False,
    ) -> dict[str, Any]:
        job_id = "job_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO task_runs (
                    job_id, idempotency_key, owner_user_id, job_type, created_at,
                    started_at, completed_at, status, attempts, last_error,
                    upstream_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    started_at = COALESCE(excluded.started_at, task_runs.started_at),
                    completed_at = COALESCE(excluded.completed_at, task_runs.completed_at),
                    status = excluded.status,
                    attempts = task_runs.attempts + ?,
                    last_error = excluded.last_error,
                    upstream_reference = COALESCE(
                        excluded.upstream_reference, task_runs.upstream_reference
                    )
                """,
                (
                    job_id,
                    idempotency_key,
                    owner_user_id,
                    job_type,
                    now,
                    started_at,
                    completed_at,
                    status,
                    1 if increment_attempts else 0,
                    last_error,
                    upstream_reference,
                    1 if increment_attempts else 0,
                ),
            )
            row = db.execute(
                "SELECT * FROM task_runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return dict(row)

    def create_reminder(
        self,
        *,
        owner_user_id: str,
        title: str,
        scheduled_at: str,
        timezone: str,
        upstream_task_id: int,
        delivery_channel: str = "in_app",
    ) -> dict[str, Any]:
        reminder_id = "rem_" + uuid.uuid4().hex
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO reminders (
                    reminder_id, owner_user_id, upstream_task_id, title, scheduled_at, timezone,
                    status, delivery_channel, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
                """,
                (
                    reminder_id,
                    owner_user_id,
                    upstream_task_id,
                    title,
                    scheduled_at,
                    timezone,
                    delivery_channel,
                    now,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM reminders WHERE owner_user_id=? AND upstream_task_id=?",
                (owner_user_id, upstream_task_id),
            ).fetchone()
        return dict(row)

    def list_reminders(self, owner_user_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT r.*, COALESCE((
                    SELECT n.status FROM reminder_notifications n
                    WHERE n.owner_user_id = r.owner_user_id
                        AND json_extract(n.payload, '$.data.task.id') = r.upstream_task_id
                    ORDER BY n.created_at DESC LIMIT 1
                ), 'waiting') AS notification_status
                FROM reminders r
                WHERE r.owner_user_id = ?
                ORDER BY r.scheduled_at ASC
                """,
                (owner_user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_reminder(self, reminder_id: str, owner_user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM reminders WHERE reminder_id = ? AND owner_user_id = ?",
                (reminder_id, owner_user_id),
            ).fetchone()
        return dict(row) if row else None

    def update_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        *,
        title: str,
        scheduled_at: str | None,
        timezone: str | None,
        done: bool | None = None,
    ) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                UPDATE reminders
                SET title = ?, scheduled_at = COALESCE(?, scheduled_at),
                    timezone = COALESCE(?, timezone), updated_at = ?,
                    status = CASE WHEN ? = 1 THEN 'completed'
                        WHEN ? = 0 OR ? IS NOT NULL THEN 'scheduled' ELSE status END
                WHERE reminder_id = ? AND owner_user_id = ? AND status != 'cancelled'
                """,
                (title, scheduled_at, timezone, now,
                 int(done) if done is not None else None,
                 int(done) if done is not None else None,
                 scheduled_at, reminder_id, owner_user_id),
            )
            row = db.execute(
                "SELECT * FROM reminders WHERE reminder_id = ? AND owner_user_id = ?",
                (reminder_id, owner_user_id),
            ).fetchone()
        return dict(row) if row else None

    def cancel_reminder(self, reminder_id: str, owner_user_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                UPDATE reminders SET status = 'cancelled', updated_at = ?
                WHERE reminder_id = ? AND owner_user_id = ?
                """,
                (now, reminder_id, owner_user_id),
            )
            row = db.execute(
                "SELECT * FROM reminders WHERE reminder_id = ? AND owner_user_id = ?",
                (reminder_id, owner_user_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_reminder_fired(self, upstream_task_id: int, owner_user_id: str) -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                UPDATE reminders SET status = 'due', updated_at = ?
                WHERE upstream_task_id = ? AND owner_user_id = ? AND status = 'scheduled'
                """,
                (now, upstream_task_id, owner_user_id),
            )

    def get_reminder_by_task(self, task_id: int, owner_user_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM reminders WHERE upstream_task_id = ? AND owner_user_id = ?",
                (task_id, owner_user_id),
            ).fetchone()
        return dict(row) if row else None

    def queue_reminder_notification(
        self, *, event_id: str, owner_user_id: str, payload: dict[str, Any]
    ) -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO reminder_notifications (
                    event_id, owner_user_id, payload, status, next_attempt_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                """,
                (event_id, owner_user_id, json.dumps(payload), now, now, now),
            )

    def next_reminder_notification(self) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT * FROM reminder_notifications
                WHERE status = 'pending' AND next_attempt_at <= ?
                ORDER BY created_at LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                """
                UPDATE reminder_notifications SET status = 'sending', attempts = attempts + 1,
                    updated_at = ? WHERE event_id = ? AND status = 'pending'
                """,
                (now, row["event_id"]),
            )
            claimed = db.execute(
                "SELECT * FROM reminder_notifications WHERE event_id = ?", (row["event_id"],)
            ).fetchone()
        event = dict(claimed)
        event["payload"] = json.loads(event["payload"])
        return event

    def fail_reminder_notification(self, event_id: str) -> None:
        now = utc_now()
        with self.connect() as db:
            row = db.execute(
                "SELECT attempts FROM reminder_notifications WHERE event_id = ?", (event_id,)
            ).fetchone()
            attempts = row["attempts"] if row else 1
            retry_seconds = min(3600, 2 ** min(attempts, 10))
            retry_at = datetime.now(UTC).timestamp() + retry_seconds
            retry_iso = datetime.fromtimestamp(retry_at, UTC).isoformat()
            db.execute(
                """
                UPDATE reminder_notifications SET status = 'pending', next_attempt_at = ?,
                    last_error = 'NTFY_DELIVERY_FAILED', updated_at = ?
                WHERE event_id = ?
                """,
                (retry_iso, now, event_id),
            )

    def complete_reminder_notification(self, event_id: str) -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                UPDATE reminder_notifications SET status = 'accepted', last_error = NULL,
                    updated_at = ? WHERE event_id = ?
                """,
                (now, event_id),
            )

    def suppress_reminder_notification(self, event_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE reminder_notifications SET status = 'suppressed', updated_at = ? WHERE event_id = ?",
                (utc_now(), event_id),
            )

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        event = dict(row)
        event["source_message_ids"] = json.loads(event["source_message_ids"])
        return event

