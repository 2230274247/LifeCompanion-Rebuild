"""Durable weather clarification; all network work uses the shared tool ledger."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .store import utc_now
from .tools import ToolRequest


# Deliberately narrow: other weather wording is handled by the ordinary chat.
WEATHER = re.compile(
    r"^(?:请帮我|帮我|请)?(?:查一下|查询|查查|看看)?\s*"
    r"(?P<before>[\w\u4e00-\u9fff ·.-]{0,60}?)"
    r"(?:天气|气温)(?:怎么样|如何|预报|情况|是多少)?[？?。！!\s]*$"
)


class ToolChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    place_index: int | None = Field(default=None, ge=0, le=4)
    place_query: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def one_choice(self):
        if (self.place_index is None) == (self.place_query is None):
            raise ValueError("ONE_TOOL_CHOICE_REQUIRED")
        if self.place_query is not None and not self.place_query.strip():
            raise ValueError("EMPTY_PLACE")
        return self


class ToolChat:
    def __init__(self, store, tools, memory):
        self.store, self.tools, self.memory = store, tools, memory
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tool_chats (
                interaction_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,
                conversation_id TEXT,source_message_id TEXT,request_hash TEXT NOT NULL,
                state TEXT NOT NULL,revision INTEGER NOT NULL,
                data TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL
            )""")
            # Recovery is explicit; uncertain network outcomes are never replayed.
            db.execute("UPDATE tool_chats SET state='unknown' WHERE state='running'")

    def cleanup(self):
        with self.store.connect() as db:
            expired = db.execute("SELECT user_id,data FROM tool_chats WHERE expires_at<=? AND state<>'expired'",
                                 (utc_now(),)).fetchall()
            db.execute("""UPDATE tool_chats SET state='expired',data='{}',
                conversation_id=NULL,source_message_id=NULL
                WHERE expires_at<=? AND state<>'expired'""", (utc_now(),))
        for row in expired:
            for execution in json.loads(row["data"]).get("execution_ids", []):
                self.tools.delete(row["user_id"], execution)

    def row(self, owner, identifier):
        self.cleanup()
        with self.store.connect() as db:
            return db.execute("SELECT * FROM tool_chats WHERE user_id=? AND interaction_id=?",
                              (owner, identifier)).fetchone()

    def public(self, row):
        if row is None:
            return None
        data = json.loads(row["data"])
        return {"handled": True, "interaction_id": row["interaction_id"],
                "conversation_id": row["conversation_id"], "source_message_id": row["source_message_id"],
                "status": row["state"], "revision": row["revision"],
                **{key: data.get(key) for key in ("forecast_date", "timezone", "places")},
                "execution": self.tools.detail(row["user_id"], data["execution_id"])
                if data.get("execution_id") else None}

    def list(self, owner, conversation):
        self.cleanup()
        with self.store.connect() as db:
            rows = db.execute("""SELECT * FROM tool_chats WHERE user_id=? AND conversation_id=?
                AND state NOT IN ('expired','cancelled') ORDER BY created_at DESC LIMIT 30""",
                              (owner, conversation)).fetchall()
        return [self.public(row) for row in rows]

    def execute(self, owner, message, text, conversation):
        match = WEATHER.fullmatch(text.strip())
        if not match:
            return {"handled": False}
        prefix = match["before"].strip()
        if re.search(r"我|你|他说|她说|什么|喜欢|系统|昨天|前天|下周|后周|星期|周[一二三四五六日天]|\d", prefix):
            return {"handled": False}
        zone = self.memory.timezone(owner)
        offset = 2 if "后天" in prefix else 1 if "明天" in prefix else 0
        forecast = (datetime.now(ZoneInfo(zone)).date() + timedelta(days=offset)).isoformat() if offset else None
        place = re.sub(r"今天|现在|明天|后天|的", "", prefix).strip()
        request_hash = hashlib.sha256(f"{conversation}:{text}".encode()).hexdigest()
        identifier = "tc_" + hashlib.sha256(f"{owner}:{message}".encode()).hexdigest()[:28]
        data = {"forecast_date": forecast, "timezone": zone, "places": []}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM tool_chats WHERE interaction_id=?", (identifier,)).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("TOOL_CHAT_CONFLICT")
            else:
                db.execute("INSERT INTO tool_chats VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (identifier, owner, conversation, message, request_hash, "needs_place", 1,
                            json.dumps(data), utc_now(),
                            (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
        if existing or not place:
            return self.public(self.row(owner, identifier))
        return self.select(owner, identifier, ToolChoice(revision=1, place_query=place))

    def select(self, owner, identifier, choice):
        self.cleanup()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tool_chats WHERE user_id=? AND interaction_id=?",
                             (owner, identifier)).fetchone()
            if row is None:
                raise LookupError("TOOL_CHAT_NOT_FOUND")
            data = json.loads(row["data"])
            selected = choice.model_dump(exclude={"revision"}, exclude_none=True)
            if data.get("last_choice") == selected and data.get("last_revision") == choice.revision:
                replay = True
            else:
                replay = False
                if row["revision"] != choice.revision or row["state"] not in ("needs_place", "choose_place"):
                    raise ValueError("TOOL_CHAT_CONFLICT")
                if row["state"] == "needs_place" and choice.place_query is not None:
                    name, parameters = "place_search", {"query": choice.place_query.strip()}
                elif row["state"] == "choose_place" and choice.place_index is not None:
                    places = data.get("places", [])
                    if choice.place_index >= len(places):
                        raise ValueError("INVALID_TOOL_CHOICE")
                    place = places[choice.place_index]
                    name = "weather"
                    parameters = {key: place[key] for key in ("latitude", "longitude")}
                    parameters.update(place_label=" · ".join(filter(None, (
                        place["name"], place["admin1"], place["country"])))[:80],
                        forecast_date=data["forecast_date"], timezone=data["timezone"])
                else:
                    raise ValueError("INVALID_TOOL_CHOICE")
                data.update(last_choice=selected, last_revision=choice.revision)
                db.execute("UPDATE tool_chats SET state='running',revision=revision+1,data=? WHERE interaction_id=?",
                           (json.dumps(data), identifier))
        if replay:
            return self.public(self.row(owner, identifier))
        execution = self.tools.execute(owner, ToolRequest(
            name=name, parameters=parameters, idempotency_key=f"{identifier}:{choice.revision}",
            source_message_id=row["source_message_id"], conversation_id=row["conversation_id"]))
        state = execution["status"]
        data["execution_id"] = execution["execution_id"]
        data.setdefault("execution_ids", []).append(execution["execution_id"])
        if name == "place_search" and state == "succeeded":
            data["places"] = execution["result"]["places"]
            state = "choose_place" if data["places"] else "no_places"
        with self.store.connect() as db:
            # A cancelled or expired interaction cannot regain data after HTTP.
            db.execute("""UPDATE tool_chats SET state=?,data=? WHERE user_id=?
                AND interaction_id=? AND state='running' AND revision=?""",
                       (state, json.dumps(data), owner, identifier, choice.revision+1))
        current = self.row(owner, identifier)
        if current["state"] in ("cancelled", "expired"):
            self.tools.delete(owner, execution["execution_id"])
        return self.public(current)

    def delete(self, owner, identifier):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tool_chats WHERE user_id=? AND interaction_id=?",
                             (owner, identifier)).fetchone()
            if row is None:
                return False
            executions = json.loads(row["data"]).get("execution_ids", [])
            db.execute("""UPDATE tool_chats SET state='cancelled',data='{}',
                source_message_id=NULL,conversation_id=NULL WHERE interaction_id=?""", (identifier,))
        for execution in executions:
            self.tools.delete(owner, execution)
        return True
