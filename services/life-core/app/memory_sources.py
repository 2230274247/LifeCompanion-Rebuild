"""Authorized user quotations, independent of short-lived extraction payloads.

recorded_at is the message timestamp, never evidence that an event occurred.
Tombstones retain only identity/hash metadata so replay cannot restore old text.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .store import utc_now


STATUSES = {"queued", "running", "extracted", "no_memory", "failed", "expired", "revoked"}


class MemorySources:
    def __init__(self, memory):
        self.memory = memory
        self.store = memory.store

    def initialize(self):
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory_sources (
                    source_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    message_id TEXT NOT NULL, conversation_id TEXT, text TEXT,
                    content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    captured_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'active'
                        CHECK(state IN ('active','withdrawn','superseded')),
                    extraction_status TEXT NOT NULL DEFAULT 'queued',
                    sensitivity TEXT NOT NULL,
                    UNIQUE(user_id,message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sources_owner_state
                    ON memory_sources(user_id,state,recorded_at);
                CREATE INDEX IF NOT EXISTS idx_sources_owner_hash
                    ON memory_sources(user_id,content_hash,state);
            """)

    def record(self, user, body):
        # Local import avoids a cycle with MemoryService's public constants.
        from .memory import FORGET, SENSITIVE

        text = body["text"]
        if FORGET.search(text):
            return {"accepted": False, "status": "excluded", "reason": "FORGET_REQUEST"}
        if not self.memory.allowed(user, text):
            return {"accepted": False, "status": "permission_denied",
                    "reason": "MEMORY_CONSENT_REQUIRED"}
        user_id, message_id = user["life_user_id"], body["source_message_id"]
        stamp = body["occurred_at"]
        recorded_at = (stamp if isinstance(stamp, datetime)
                       else datetime.fromisoformat(stamp.replace("Z", "+00:00"))).isoformat()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        source_id = "source_" + hashlib.sha256(json.dumps(
            [user_id, message_id], ensure_ascii=False).encode()).hexdigest()[:32]
        with self.memory.lock, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM memory_sources WHERE user_id=? AND message_id=?",
                                  (user_id, message_id)).fetchone()
            if existing:
                if existing["content_hash"] != content_hash:
                    raise ValueError("SOURCE_MESSAGE_CONFLICT")
                return {"accepted": existing["state"] == "active",
                        "status": "duplicate" if existing["state"] == "active" else "revoked",
                        "source_id": existing["source_id"]}
            # A different message ID must not resurrect an identical withdrawn quote.
            revoked = db.execute("""SELECT state FROM memory_sources WHERE user_id=?
                AND content_hash=? AND state!='active' LIMIT 1""", (user_id, content_hash)).fetchone()
            state = revoked["state"] if revoked else "active"
            captured_at = utc_now()
            db.execute("""INSERT INTO memory_sources
                (source_id,user_id,message_id,conversation_id,text,content_hash,recorded_at,
                 captured_at,updated_at,state,extraction_status,sensitivity)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id,user_id,message_id,body.get("conversation_id"),None if revoked else text,
                 content_hash,recorded_at,captured_at,captured_at,state,
                 "revoked" if revoked else "queued", "sensitive" if SENSITIVE.search(text) else "ordinary"))
        return {"accepted": not bool(revoked), "status": "revoked" if revoked else "recorded",
                "source_id": source_id}

    def _visible(self, user_id):
        permissions = self.memory.permissions(user_id)
        if not permissions["recall_consent"]:
            return None
        return permissions["sensitive_consent"]

    @staticmethod
    def _item(row):
        return {"memory_id": row["source_id"], "source_id": row["source_id"],
                "user_id": row["user_id"], "message_id": row["message_id"],
                "source_message_id": row["message_id"], "conversation_id": row["conversation_id"],
                "kind": "user_message", "canonical_text": row["text"], "value": "",
                "state": row["state"], "semantic_key": "source:" + row["source_id"],
                "valid_from": row["recorded_at"], "recorded_at": row["recorded_at"],
                "captured_at": row["captured_at"], "sensitivity": row["sensitivity"],
                "extraction_status": row["extraction_status"]}

    def items(self, user_id):
        sensitive = self._visible(user_id)
        if sensitive is None:
            return []
        with self.store.connect() as db:
            rows = db.execute("""SELECT * FROM memory_sources WHERE user_id=?
                AND state='active' AND text IS NOT NULL AND (? OR sensitivity='ordinary')
                ORDER BY recorded_at,source_id""", (user_id, int(sensitive))).fetchall()
        return [self._item(row) for row in rows]

    def detail(self, user_id, source_id):
        sensitive = self._visible(user_id)
        if sensitive is None:
            return None
        with self.store.connect() as db:
            row = db.execute("""SELECT * FROM memory_sources WHERE user_id=? AND source_id=?
                AND state='active' AND text IS NOT NULL AND (? OR sensitivity='ordinary')""",
                (user_id,source_id,int(sensitive))).fetchone()
        return self._item(row) if row else None

    def coverage(self, user_id):
        sensitive = self._visible(user_id)
        if sensitive is None:
            return {"status": "permission_denied"}
        with self.store.connect() as db:
            rows = db.execute("""SELECT state,extraction_status,COUNT(*) AS count
                FROM memory_sources WHERE user_id=? AND (? OR sensitivity='ordinary')
                GROUP BY state,extraction_status""", (user_id, int(sensitive))).fetchall()
        states, statuses = {}, {}
        for row in rows:
            states[row["state"]] = states.get(row["state"], 0) + row["count"]
            statuses[row["extraction_status"]] = statuses.get(row["extraction_status"], 0) + row["count"]
        return {"status": "available", "total": sum(states.values()), "states": states,
                "extraction_status": statuses, "historical_coverage": "not_verified"}

    def _set_status(self, db, user_id, message_id, status, only_if=None):
        if status not in STATUSES:
            raise ValueError("INVALID_SOURCE_STATUS")
        where, args = "", []
        if only_if is not None:
            where = " AND extraction_status IN (" + ",".join("?" for _ in only_if) + ")"
            args = list(only_if)
        return bool(db.execute("""UPDATE memory_sources SET extraction_status=?,updated_at=?
            WHERE user_id=? AND message_id=? AND state='active'""" + where,
            [status,utc_now(),user_id,message_id,*args]).rowcount)

    def set_status(self, user_id, message_id, status, *, only_if=None):
        with self.store.connect() as db:
            return self._set_status(db, user_id, message_id, status, only_if)

    @staticmethod
    def _delete_vectors(db, user_id, item_ids):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_vectors'").fetchone():
            return
        db.executemany("DELETE FROM memory_vectors WHERE user_id=? AND memory_id=?",
                       [(user_id,item_id) for item_id in item_ids])

    def _tombstone(self, db, user_id, rows, state):
        for row in rows:
            # Revocations are irreversible, including a later supersede operation.
            db.execute("""UPDATE memory_sources SET text=NULL,
                state=CASE WHEN state='withdrawn' THEN state ELSE ? END,
                extraction_status='revoked',updated_at=? WHERE user_id=? AND source_id=?""",
                (state,utc_now(),user_id,row["source_id"]))
            job_id = "extract_" + hashlib.sha256(f"{user_id}:{row['message_id']}".encode()).hexdigest()[:24]
            db.execute("""UPDATE memory_jobs SET payload=NULL,status='revoked',updated_at=?
                WHERE user_id=? AND job_id=?""", (utc_now(),user_id,job_id))
        self._delete_vectors(db, user_id, [row["source_id"] for row in rows])

    def withdraw_for_item(self, db, user_id, item_id, state):
        if state not in {"withdrawn", "superseded"}:
            raise ValueError("INVALID_SOURCE_STATE")
        rows = db.execute("""SELECT DISTINCT s.source_id,s.message_id FROM memory_sources s
            JOIN memory_evidence e ON s.user_id=e.user_id AND s.message_id=e.message_id
            WHERE e.user_id=? AND e.memory_id=?""", (user_id,item_id)).fetchall()
        self._tombstone(db, user_id, rows, state)
        self._delete_vectors(db, user_id, [item_id])

    def withdraw(self, user_id, source_id):
        with self.memory.lock, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT * FROM memory_sources WHERE user_id=? AND source_id=?",
                                (user_id,source_id)).fetchone()
            if source is None:
                return None
            linked = db.execute("""SELECT DISTINCT m.memory_id FROM memory_items m
                JOIN memory_evidence e ON m.user_id=e.user_id AND m.memory_id=e.memory_id
                WHERE e.user_id=? AND e.message_id=? AND m.state='active'""",
                (user_id,source["message_id"])).fetchall()
            self._tombstone(db, user_id, [source], "withdrawn")
            for row in linked:
                self.memory._invalidate(db, user_id, row["memory_id"], "withdrawn", source["message_id"])
        return {"source_id": source_id, "state": "withdrawn", "status": "revoked",
                "invalidated_count": len(linked)}
