"""Content-free, user-scoped diagnostics for each memory stage."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .store import utc_now

STAGES = {"enqueue", "extraction", "recall", "delivery", "publication"}
STATUSES = {
    "queued", "saved", "rejected", "failed", "retrying", "expired", "matched",
    "no_match", "permission_denied", "user_not_mapped", "excluded", "injected",
    "unavailable", "disabled", "empty_input", "not_attempted", "published",
}


class MemoryTrace:
    def __init__(self, store):
        self.store = store

    def initialize(self):
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory_traces (
                    trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL, message_id TEXT, conversation_id TEXT,
                    stage TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                    item_count INTEGER NOT NULL DEFAULT 0, elapsed_ms INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memory_traces_owner
                    ON memory_traces(user_id, trace_id DESC);
            """)

    def record(self, user_id, message_id, conversation_id, stage, status,
               reason=None, item_count=0, elapsed_ms=None):
        if stage not in STAGES or status not in STATUSES:
            raise ValueError("INVALID_MEMORY_TRACE")
        # Reasons are machine codes only. Never store provider errors or user text.
        reason = str(reason or "")[:80]
        if not all(c.isascii() and (c.isalnum() or c in "_:-.") for c in reason):
            reason = "DETAIL_REDACTED"
        with self.store.connect() as db:
            db.execute("""INSERT INTO memory_traces
                (user_id,message_id,conversation_id,stage,status,reason,item_count,elapsed_ms,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (user_id, message_id, conversation_id,
                stage, status, reason, max(0, min(int(item_count), 100)), elapsed_ms, utc_now()))
            db.execute("DELETE FROM memory_traces WHERE created_at<?",
                       ((datetime.now(UTC)-timedelta(days=7)).isoformat(),))

    def recent(self, user_id, conversation_id=None):
        with self.store.connect() as db:
            where = "user_id=?"
            args = [user_id]
            if conversation_id:
                where += " AND conversation_id=?"
                args.append(conversation_id)
            rows = db.execute(f"SELECT * FROM memory_traces WHERE {where} ORDER BY trace_id DESC LIMIT 60",
                              args).fetchall()
            jobs = db.execute("""SELECT status,COUNT(*) AS count FROM memory_jobs
                WHERE user_id=? GROUP BY status""", (user_id,)).fetchall()
        return {"traces": [{k: v for k, v in dict(r).items() if k != "user_id"} for r in rows],
                "jobs": {r["status"]: r["count"] for r in jobs}}
