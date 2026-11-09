from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, UTC
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from .extraction import extract_event
from .store import Store, utc_now
from .reminder_parser import calendar_day
from .memory_trace import MemoryTrace
from .memory_sources import MemorySources


VERSION = "memory-v02.1"
SENSITIVE = re.compile(r"医院|医疗|病|药|诊断|身份证|银行卡|住址|住在|居住|门牌|定位|经纬度")
FORGET = re.compile(r"别记|不要记|忘记|删除.*记忆|别再记")
MANUAL = re.compile(r"记下来|记录下来|记住这件事|记住刚才|加入(?:到)?回忆")
FUTURE = re.compile(r"明天|后天|下周|下月|明年|准备|打算|可能|也许|如果|计划")


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_type: Literal["life_event", "stable_fact", "future_plan", "no_memory"]
    canonical_text: str = Field(max_length=500)
    evidence_quote: str = Field(min_length=1, max_length=4000)
    occurred_state: Literal["occurred", "planned", "uncertain"]
    fact_key: str = Field(default="other", min_length=1, max_length=100)
    value: str = Field(default="", max_length=100)
    confidence: float = Field(ge=0, le=1)
    sensitivity: Literal["ordinary", "sensitive", "unknown"]
    image_candidate: bool = False
    _classifier: str = PrivateAttr(default=f"rules:{VERSION}")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).casefold()


class MemoryService:
    def __init__(self, store: Store, settings):
        self.store, self.settings = store, settings
        self.lock = threading.RLock()
        self.trace = MemoryTrace(store)
        self.sources = MemorySources(self)

    def initialize(self):
        self.trace.initialize()
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory_permissions (
                    user_id TEXT PRIMARY KEY, recall_consent INTEGER NOT NULL DEFAULT 0,
                    sensitive_consent INTEGER NOT NULL DEFAULT 0,
                    notification_consent INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_items (
                    memory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    kind TEXT NOT NULL, semantic_key TEXT NOT NULL,
                    canonical_text TEXT NOT NULL, value TEXT NOT NULL DEFAULT '',
                    event_id TEXT, state TEXT NOT NULL DEFAULT 'active',
                    importance REAL NOT NULL, confidence REAL NOT NULL,
                    sensitivity TEXT NOT NULL, image_candidate INTEGER NOT NULL,
                    valid_from TEXT NOT NULL, valid_until TEXT, revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_owner ON memory_items(user_id, state, semantic_key);
                CREATE TABLE IF NOT EXISTS memory_evidence (
                    memory_id TEXT NOT NULL, user_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    conversation_id TEXT, evidence_date TEXT NOT NULL,
                    content_hash TEXT NOT NULL, independent INTEGER NOT NULL,
                    classifier_version TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(memory_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS memory_revisions (
                    memory_id TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL,
                    source_message_id TEXT, created_at TEXT NOT NULL,
                    PRIMARY KEY(memory_id, revision)
                );
                CREATE TABLE IF NOT EXISTS memory_jobs (
                    job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    payload TEXT, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT, available_at TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_recall_hits (
                    user_id TEXT NOT NULL, conversation_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id,conversation_id,message_id,memory_id)
                );
                CREATE TABLE IF NOT EXISTS permission_audit (
                    audit_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, actor TEXT NOT NULL,
                    old_values TEXT NOT NULL, new_values TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_actions (
                    user_id TEXT NOT NULL, conversation_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    status TEXT NOT NULL, code TEXT, memory_id TEXT, created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id,conversation_id,message_id)
                );
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY, timezone TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_batches (
                    user_id TEXT NOT NULL, message_id TEXT NOT NULL, status TEXT NOT NULL,
                    PRIMARY KEY(user_id,message_id)
                );
            """)
            # In-flight extraction is replayable after a process restart.
            columns = {r["name"] for r in db.execute("PRAGMA table_info(memory_evidence)")}
            if "message_at" not in columns:
                db.execute("ALTER TABLE memory_evidence ADD COLUMN message_at TEXT")
            db.execute("UPDATE memory_jobs SET status='queued' WHERE status='running'")
        self.sources.initialize()

    def permissions(self, user_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM memory_permissions WHERE user_id=?", (user_id,)).fetchone()
        return {key: bool(row[key]) if row else False
                for key in ("recall_consent", "sensitive_consent", "notification_consent")}

    def timezone(self, user_id):
        with self.store.connect() as db:
            row = db.execute("SELECT timezone FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else self.settings.timezone

    def set_permissions(self, user_id, changes):
        old = self.permissions(user_id)
        values = {**old, **{k: v for k, v in changes.items() if v is not None}}
        with self.store.connect() as db:
            db.execute("""INSERT INTO memory_permissions VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET recall_consent=excluded.recall_consent,
                sensitive_consent=excluded.sensitive_consent,
                notification_consent=excluded.notification_consent, updated_at=excluded.updated_at""",
                (user_id, int(values["recall_consent"]), int(values["sensitive_consent"]),
                 int(values["notification_consent"]), utc_now()))
            if old != values:
                db.execute("""INSERT INTO permission_audit(user_id,actor,old_values,new_values,created_at)
                    VALUES (?,'authenticated_settings',?,?,?)""",
                    (user_id,json.dumps(old),json.dumps(values),utc_now()))
        return values

    def allowed(self, user, text):
        return bool(user["memory_consent"]) and (
            not SENSITIVE.search(text) or self.permissions(user["life_user_id"])["sensitive_consent"]
        )

    def classify_many(self, text, now, *, use_llm=False):
        from .extraction_candidates import extract_candidates
        return extract_candidates(self, text, now, use_llm=use_llm)

    def classify(self, text, now, *, use_llm=False):
        candidates, reason = self.classify_many(text, now, use_llm=use_llm)
        return (candidates[0] if candidates else None), reason

    def key_for(self, candidate, text, now, timezone_name=None):
        zone = ZoneInfo(timezone_name or self.settings.timezone)
        if candidate.candidate_type == "stable_fact":
            if candidate.fact_key in ("interest", "drink_avoidance"):
                return f"fact:{candidate.fact_key}:{digest(normalized(candidate.value))[:16]}"
            return f"fact:{candidate.fact_key}"
        day = now.astimezone(zone).date().isoformat()
        if candidate.candidate_type == "future_plan":
            planned_day = calendar_day(text, now.astimezone(zone).date()) or "unspecified"
            topic = "usb" if re.search(r"u\s*盘", text, re.I) else "umbrella" if "雨伞" in text else digest(normalized(text))
            return f"plan:{planned_day}:{topic}"
        if "加入" in text and "项目组" in text:
            entity = re.search(r"加入(?:了)?(.{1,40}?项目组)", text)
            project = normalized(entity.group(1)) if entity else "unknown"
            return f"event:{day}:joined-project:{digest(project)[:16]}"
        return f"event:{day}:{digest(normalized(candidate.canonical_text))}"

    def find(self, user_id, key):
        with self.store.connect() as db:
            row = db.execute("""SELECT * FROM memory_items WHERE user_id=? AND semantic_key=?
                ORDER BY created_at DESC, rowid DESC LIMIT 1""", (user_id, key)).fetchone()
        return dict(row) if row else None

    def contextual_event(self, user_id, conversation_id, text, now):
        if "这个项目组" not in text and not MANUAL.search(text) and not FORGET.search(text):
            return None
        with self.store.connect() as db:
            rows = db.execute("""SELECT DISTINCT m.* FROM memory_items m JOIN memory_evidence e
                ON m.memory_id=e.memory_id WHERE m.user_id=? AND e.conversation_id=?
                AND m.kind='life_event' AND m.state='active' ORDER BY m.created_at DESC LIMIT 2""",
                (user_id, conversation_id)).fetchall()
        if len(rows) != 1:
            return None
        item = dict(rows[0])
        if ("这个项目组" in text and "项目组" not in item["canonical_text"]):
            return None
        return item

    def save(self, user_id, candidate, key, message_id, conversation_id, text, now, event_id=None):
        existing = self.find(user_id, key)
        if candidate.candidate_type == "stable_fact" and candidate.fact_key == "drink_avoidance":
            positive = self.find(user_id, "fact:drink_preference")
            if positive and positive["state"] == "active" and normalized(positive["value"]) == normalized(candidate.value):
                self.invalidate(user_id, positive["memory_id"], "superseded", message_id)
        if existing and existing["state"] == "withdrawn":
            return existing
        if existing and existing["state"] == "superseded":
            existing = None
        value = candidate.value
        if existing and existing["kind"] == "future_plan" and existing["canonical_text"] != candidate.canonical_text:
            if re.search(r"改为|改成|更正|不是.*是|现在", text):
                self.invalidate(user_id, existing["memory_id"], "superseded", message_id)
                existing = None
            else:
                return {**existing, "conflict": True}
        if existing and existing["kind"] == "stable_fact" and existing["value"] != value:
            if not re.search(r"现在|目前|更喜欢|不再|改为", text):
                return {**existing, "conflict": True}
            self.invalidate(user_id, existing["memory_id"], "superseded", message_id)
            existing = None
        item_id = existing["memory_id"] if existing else "mem_" + digest(
            f"{user_id}:{key}:{message_id}")[:24]
        stamp = utc_now()
        day = now.astimezone(ZoneInfo(self.settings.timezone)).date().isoformat()
        content_hash = digest(normalized(text))
        with self.store.connect() as db:
            if not existing:
                db.execute("""INSERT INTO memory_items (
                    memory_id,user_id,kind,semantic_key,canonical_text,value,event_id,importance,
                    confidence,sensitivity,image_candidate,valid_from,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item_id,user_id,candidate.candidate_type,key,candidate.canonical_text,value,event_id,
                     0.7 if "加入" in text else 0.5,candidate.confidence,candidate.sensitivity,
                     int(candidate.image_candidate and candidate.candidate_type=="life_event"),
                     now.isoformat(),stamp,stamp))
                db.execute("INSERT INTO memory_revisions VALUES (?,1,'created',?,?)",
                           (item_id,message_id,stamp))
            copied = db.execute("""SELECT 1 FROM memory_evidence WHERE memory_id=? AND (
                content_hash=? OR evidence_date=? OR conversation_id=?)""",
                (item_id,content_hash,day,conversation_id)).fetchone()
            independent = int(not copied)
            inserted = db.execute("""INSERT OR IGNORE INTO memory_evidence
                (memory_id,user_id,message_id,conversation_id,evidence_date,content_hash,independent,
                 classifier_version,created_at,message_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (item_id,user_id,message_id,conversation_id,day,content_hash,independent,candidate._classifier,stamp,now.isoformat())).rowcount
            if inserted and existing and independent:
                db.execute("""UPDATE memory_items SET importance=MIN(0.95,importance+0.08),
                    updated_at=? WHERE memory_id=?""", (stamp,item_id))
            if event_id:
                event = db.execute("SELECT source_message_ids FROM events WHERE event_id=?", (event_id,)).fetchone()
                sources = json.loads(event[0])
                if message_id not in sources:
                    db.execute("UPDATE events SET source_message_ids=?,updated_at=? WHERE event_id=?",
                               (json.dumps(sources+[message_id]),stamp,event_id))
            row = db.execute("SELECT * FROM memory_items WHERE memory_id=?", (item_id,)).fetchone()
        if hasattr(self, "retriever"):
            self.retriever._schedule(user_id)
        return dict(row)

    def invalidate(self, user_id, item_id, state="withdrawn", source_message_id=None):
        with self.lock, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._invalidate(db, user_id, item_id, state, source_message_id)

    def _invalidate(self, db, user_id, item_id, state, source_message_id=None):
        if state not in {"withdrawn", "superseded"}:
            raise ValueError("INVALID_MEMORY_STATE")
        row = db.execute("SELECT * FROM memory_items WHERE memory_id=? AND user_id=?",
                         (item_id,user_id)).fetchone()
        if row is None:
            return None
        # Read source links before removing evidence, within the same transaction.
        self.sources.withdraw_for_item(db, user_id, item_id, state)
        if row["state"] == "withdrawn":
            return dict(row)
        db.execute("""UPDATE memory_items SET state=?,valid_until=?,updated_at=?,revision=revision+1
            WHERE memory_id=?""", (state,utc_now(),utc_now(),item_id))
        db.execute("INSERT INTO memory_revisions VALUES (?,?,?,?,?)",
                   (item_id,row["revision"]+1,state,source_message_id,utc_now()))
        if row["event_id"]:
            db.execute("UPDATE events SET status='withdrawn',updated_at=? WHERE event_id=?",
                       (utc_now(),row["event_id"]))
        if state == "withdrawn":
            # Keep only a non-content tombstone to prevent replay resurrection.
            db.execute("UPDATE memory_items SET canonical_text='',value='' WHERE memory_id=?", (item_id,))
            db.execute("DELETE FROM memory_evidence WHERE memory_id=?", (item_id,))
            if row["event_id"]:
                db.execute("UPDATE events SET title='已撤回',summary='' WHERE event_id=?", (row["event_id"],))
        return dict(row)

    def list_items(self, user_id):
        with self.store.connect() as db:
            rows = db.execute("""SELECT m.*,(SELECT COUNT(*) FROM memory_evidence e
                WHERE e.memory_id=m.memory_id) AS evidence_count FROM memory_items m
                WHERE user_id=? AND state='active' ORDER BY importance DESC,updated_at DESC""",
                (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def detail(self, user_id, memory_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM memory_items WHERE user_id=? AND memory_id=?", (user_id,memory_id)).fetchone()
            if row is None:
                return None
            item = dict(row)
            if item["event_id"]:
                event = db.execute("SELECT status FROM events WHERE event_id=? AND user_id=?",
                                   (item["event_id"],user_id)).fetchone()
                item["event_status"] = event[0] if event else None
            item["sources"] = [dict(r) for r in db.execute("""SELECT message_id,conversation_id,evidence_date
                FROM memory_evidence WHERE user_id=? AND memory_id=?""", (user_id,memory_id))]
        return item

    def recall(self, user_id, query):
        if hasattr(self, "retriever"):
            found = self.retriever.retrieve(user_id, query)
            matching = set(found["retrieval"].get("profile_match_ids", []))
            return [i for i in found["profile"] if i["memory_id"] in matching] + found["items"]
        # No lexical fallback: unavailable vectors must not change the retrieval contract.
        return []

    def enqueue(self, user, body):
        with self.lock:
            return self._enqueue(user, body)

    def _enqueue(self, user, body):
        source = self.sources.record(user, body)
        if source["status"] == "revoked":
            return {"accepted": False, "status": "revoked", "reason": "SOURCE_REVOKED"}
        if not self.allowed(user, body["text"]) and not FORGET.search(body["text"]):
            self.trace.record(user["life_user_id"], body["source_message_id"], body.get("conversation_id"),
                              "enqueue", "permission_denied", "MEMORY_CONSENT_REQUIRED")
            return {"accepted":False,"status":"permission_denied","reason":"MEMORY_CONSENT_REQUIRED"}
        job_id = "extract_" + digest(f"{user['life_user_id']}:{body['source_message_id']}")[:24]
        with self.store.connect() as db:
            db.execute("""INSERT OR IGNORE INTO memory_jobs
                (job_id,user_id,payload,status,available_at,created_at,updated_at)
                VALUES (?,?,?,'queued',?,?,?)""",
                (job_id,user["life_user_id"],json.dumps(body),utc_now(),utc_now(),utc_now()))
            row = db.execute("SELECT status FROM memory_jobs WHERE job_id=?", (job_id,)).fetchone()
        self.trace.record(user["life_user_id"], body["source_message_id"], body.get("conversation_id"),
                          "enqueue", "queued", "TASK_" + row[0].upper())
        return {"accepted":True,"status":row[0],"job_id":job_id}

    def run_one(self, processor):
        with self.lock:
            with self.store.connect() as db:
                cutoff = (datetime.now(UTC)-timedelta(hours=24)).isoformat()
                expired = db.execute("""SELECT user_id,payload FROM memory_jobs
                    WHERE payload IS NOT NULL AND created_at<?""", (cutoff,)).fetchall()
                for job in expired:
                    try:
                        message_id = json.loads(job["payload"])["source_message_id"]
                    except (ValueError, TypeError, KeyError):
                        continue
                    self.sources._set_status(db, job["user_id"], message_id, "expired",
                                             only_if={"queued", "running", "failed"})
                db.execute("""UPDATE memory_jobs SET payload=NULL,status='expired'
                    WHERE payload IS NOT NULL AND created_at<?""", (cutoff,))
                row = db.execute("""SELECT * FROM memory_jobs WHERE status='queued' AND available_at<=?
                    ORDER BY created_at LIMIT 1""", (utc_now(),)).fetchone()
                if row is None:
                    return False
                db.execute("UPDATE memory_jobs SET status='running',attempts=attempts+1 WHERE job_id=?",
                           (row["job_id"],))
            try:
                payload = json.loads(row["payload"])
                self.sources.set_status(row["user_id"], payload["source_message_id"], "running")
                user = self.store.get_user(row["user_id"])
                processor(user=user,text=payload["text"],source_type="chat",
                    source_message_ids=[payload["source_message_id"]],
                    conversation_id=payload.get("conversation_id"),
                    occurred_at=datetime.fromisoformat(payload["occurred_at"]),use_llm=True)
            except Exception as exc:
                retry = row["attempts"] < 2
                self.trace.record(row["user_id"], payload.get("source_message_id") if 'payload' in locals() else None,
                    payload.get("conversation_id") if 'payload' in locals() else None,
                    "extraction", "retrying" if retry else "failed", type(exc).__name__.upper())
                with self.store.connect() as db:
                    db.execute("""UPDATE memory_jobs SET status=?,last_error='EXTRACTION_OR_PUBLISH_FAILED',
                        payload=CASE WHEN ? THEN payload ELSE NULL END,available_at=?,updated_at=?
                        WHERE job_id=? AND status='running'""", ("queued" if retry else "failed",int(retry),
                        (datetime.now(UTC)+timedelta(seconds=10)).isoformat(),utc_now(),row["job_id"]))
                    if 'payload' in locals() and isinstance(payload, dict):
                        self.sources._set_status(db, row["user_id"], payload.get("source_message_id"), "failed")
            else:
                with self.store.connect() as db:
                    db.execute("""UPDATE memory_jobs SET status='succeeded',payload=NULL,updated_at=?
                        WHERE job_id=? AND status='running'""", (utc_now(),row["job_id"]))
                    count = db.execute("""SELECT COUNT(*) FROM memory_evidence e JOIN memory_items m
                        ON e.user_id=m.user_id AND e.memory_id=m.memory_id WHERE e.user_id=?
                        AND e.message_id=? AND m.state='active'""",
                        (row["user_id"],payload["source_message_id"])).fetchone()[0]
                    # process_event may already have recorded a more precise terminal status.
                    self.sources._set_status(db, row["user_id"], payload["source_message_id"],
                        "extracted" if count else "no_memory", only_if={"queued", "running"})
        return True
