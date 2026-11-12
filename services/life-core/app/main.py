from __future__ import annotations

import os
import re
import threading
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel, Field, field_validator

from .auth import identity_from_request
from .collaboration import CollaborationService
from .collaboration_api import collaboration_router
from .config import Settings, load_settings
from .extraction import extract_event
from .occurrence import item_interval, overlaps
from .memos import MemosClient, MemosError
from .memory import Candidate, MemoryService, FORGET, SENSITIVE, digest
from .memory_forget import MemoryForget
from .retrieval import MemoryRetriever
from .assistant_plan import AssistantPlan, PlanUnavailable, SemanticPlanner
from .moments import Moments, MomentSettings
from .reminders import ReminderPermissionError, ReminderService, ReminderUpstreamError
from .reminder_chat import ReminderChat
from .provisioning import ReminderProvisioning
from .reminder_drafts import DraftFields, ReminderDrafts
from .store import Store


class IngestRequest(BaseModel):
    source_user_id: str = Field(min_length=1)
    source_message_id: str = Field(min_length=1)
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime


class BootstrapUserRequest(BaseModel):
    librechat_user_id: str
    memos_user_id: str
    memos_username: str | None = None
    display_name: str | None = None
    memory_consent: bool = True
    image_consent: bool = True


class ConsentRequest(BaseModel):
    memory_consent: bool | None = None
    image_consent: bool | None = None
    recall_consent: bool | None = None
    sensitive_consent: bool | None = None
    notification_consent: bool | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (KeyError,ValueError) as exc:
                raise ValueError("INVALID_TIMEZONE") from exc
        return value


class RecallContext(BaseModel):
    text: str = Field(max_length=500)
    role: Literal["user"] = "user"
    conversation_id: str | None = None


class UserRecallRequest(BaseModel):
    model_config = {"extra": "forbid"}
    query: str = Field(max_length=4000)
    conversation_id: str | None = None
    source_message_id: str | None = None
    recent_messages: list[RecallContext] = Field(default_factory=list, max_length=4)


class RecallRequest(UserRecallRequest):
    source_user_id: str


class PlanRequest(UserRecallRequest):
    model_config = {"extra": "forbid"}
    source_user_id: str


class PlanResponse(BaseModel):
    version: str = "1"
    tasks: list[dict[str, Any]]


class MemoryTelemetry(BaseModel):
    source_user_id: str
    source_message_id: str | None = None
    conversation_id: str | None = None
    stage: Literal["recall", "delivery"] = "recall"
    status: Literal["injected", "unavailable", "disabled", "empty_input", "not_attempted",
                    "matched", "no_match", "permission_denied", "user_not_mapped", "excluded"]
    reason: str | None = Field(default=None, max_length=80)
    item_count: int = Field(default=0, ge=0, le=100)
    elapsed_ms: int | None = Field(default=None, ge=0, le=300000)


class ReminderChatRequest(BaseModel):
    source_user_id: str = Field(min_length=1)
    source_message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200)


class DraftCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    conversation_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)


class DraftConfirmation(BaseModel):
    model_config = {"extra": "forbid"}
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=200)


class DraftSelection(BaseModel):
    model_config = {"extra": "forbid"}
    revision: int = Field(ge=1)
    fields: DraftFields


class KnowledgeUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class MemoryCommand(ReminderChatRequest):
    previous_user_message: IngestRequest | None = None


class ManualExtractRequest(BaseModel):
    source_message_id: str
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime | None = None


class PublishRequest(BaseModel):
    event_id: str


class DirectMomentTestRequest(BaseModel):
    model_config = {"extra": "forbid"}
    conversation_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    action: str = Field(default="image", pattern="^(memory|image)$")


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scheduled_at: AwareDatetime
    timezone: str = "Asia/Hong_Kong"
    delivery_channel: Literal["push"] = "push"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as exc:
            raise ValueError("Unknown time zone") from exc
        return value

    @field_validator("scheduled_at")
    @classmethod
    def future_time(cls, value):
        if value.timestamp() <= datetime.now().timestamp():
            raise ValueError("Reminder time must be in the future")
        return value


class ReminderUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scheduled_at: AwareDatetime | None = None
    timezone: str | None = None
    done: bool | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return ReminderRequest.valid_timezone(value) if value is not None else value

    @field_validator("scheduled_at")
    @classmethod
    def future_time(cls, value):
        return ReminderRequest.future_time(value) if value is not None else value


def current_identity(request: Request) -> tuple[str, str, dict[str, Any]]:
    librechat_user_id, _source = identity_from_request(request)
    user = request.app.state.store.get_user_by_librechat_id(librechat_user_id)
    if user is None:
        # Any authenticated LibreChat account gets a minimal life-core user row
        # (no Memos mapping, no consent) so read-only pages such as the memories
        # gallery degrade to an empty list instead of 403 USER_NOT_MAPPED.
        # Publishing still requires explicit bootstrap and consent downstream.
        user = request.app.state.store.ensure_reminder_user(librechat_user_id)
    return user["life_user_id"], librechat_user_id, user


def require_internal(request: Request, token: Annotated[str | None, Header(alias="X-Internal-Token")] = None) -> None:
    expected = request.app.state.settings.internal_token
    if not expected or not token or token != expected:
        raise HTTPException(status_code=401, detail={"code": "INVALID_INTERNAL_TOKEN"})


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "source_type": event["source_type"],
        "source_message_ids": event["source_message_ids"],
        "conversation_id": event["conversation_id"],
        "occurred_at": event["occurred_at"] if event.get("occurrence_precision") == "day" else "",
        "occurrence_start": event.get("occurrence_start"),
        "occurrence_end": event.get("occurrence_end"),
        "occurrence_precision": event.get("occurrence_precision") or "unknown",
        "title": event["title"],
        "summary": event["summary"],
        "confidence": event["confidence"],
        "consent_state": event["consent_state"],
        "memo_ref": event["memo_ref"],
        "status": event["status"],
        "error_message": event["error_message"],
        "attempts": event["attempts"],
        "created_at": event["created_at"],
        "updated_at": event["updated_at"],
    }


def public_reminder(reminder: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in reminder.items()
        if key not in {"owner_user_id", "upstream_task_id"}
    }


def verify_draft_source(request: Request, conversation: str, source: str, text: str):
    """Use LibreChat's authenticated ownership check and current persisted message."""
    url = (request.app.state.settings.librechat_base_url + "/api/messages/"
           + quote(conversation, safe="") + "/" + quote(source, safe=""))
    try:
        response = httpx.get(url, headers={"Authorization": request.headers.get("authorization", "")}, timeout=8)
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "SOURCE_VERIFICATION_UNAVAILABLE"}) from exc
    if response.status_code in (403, 404):
        raise HTTPException(409, detail={"code": "SOURCE_MESSAGE_UNAVAILABLE"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "SOURCE_VERIFICATION_UNAVAILABLE"})
    messages = response.json()
    if not isinstance(messages, list) or not any(
        item.get("messageId") == source and item.get("isCreatedByUser") is True and item.get("text") == text
        for item in messages
    ):
        raise HTTPException(409, detail={"code": "SOURCE_MESSAGE_CHANGED_OR_DELETED"})


def create_app(settings_override: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = settings_override or load_settings()
        store = Store(settings.database_path)
        store.initialize()
        app.state.settings = settings
        app.state.store = store
        app.state.memos = MemosClient(settings.memos_base_url, settings.memos_api_token)
        app.state.memory = MemoryService(store, settings)
        app.state.memory.initialize()
        app.state.forget_memory = MemoryForget(app.state.memory)
        app.state.memory.retriever = MemoryRetriever(app.state.memory)
        if settings.memory_embedding_model:
            threading.Thread(target=app.state.memory.retriever.warmup,
                             name="memory-embedding-warmup", daemon=True).start()
        app.state.moments = Moments(
            store, settings, app.state.memory, publish_event=publish_event
        )
        app.state.collaboration = CollaborationService(
            store, settings, app.state.moments
        )
        app.state.collaboration.initialize()
        app.state.reminders = ReminderService(store, settings)
        app.state.provisioning = ReminderProvisioning(store, settings, app.state.reminders)
        app.state.reminders.provisioning = app.state.provisioning
        app.state.reminder_drafts = ReminderDrafts(store, settings, app.state.reminders)
        app.state.reminder_chat = ReminderChat(store, settings, app.state.reminders)
        app.state.reminder_chat.drafts = app.state.reminder_drafts
        app.state.planner = SemanticPlanner(settings)
        stop = threading.Event()
        def work():
            next_cleanup = 0.0
            next_notification_retry = 0.0
            while not stop.is_set():
                import time
                if time.monotonic() >= next_cleanup:
                    try:
                        retry_memo_cleanup()
                        app.state.reminders.reconcile_notifications()
                        app.state.provisioning.maintain()
                    except Exception:
                        # A reminder/provisioning outage (e.g. missing credential
                        # master key) must never kill the memory extraction loop.
                        pass
                    next_cleanup = time.monotonic() + 30
                if time.monotonic() >= next_notification_retry:
                    try:
                        app.state.reminders.deliver_one_notification()
                    except Exception:
                        pass
                    next_notification_retry = time.monotonic() + 5
                if not app.state.memory.run_one(process_event):
                    stop.wait(0.5)
        worker = threading.Thread(target=work, name="memory-extraction", daemon=True)
        def moment_work():
            while not stop.is_set():
                app.state.moments.schedule()
                app.state.moments.run_one()
                app.state.moments.publish_generated_one()
                stop.wait(20)
        moment_worker = threading.Thread(target=moment_work, name="moment-generation", daemon=True)
        app.state.memory_worker = worker
        worker.start()
        moment_worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=40)
            moment_worker.join(timeout=5)

    app = FastAPI(title="Life Companion Core", version="0.1.0", lifespan=lifespan)
    app.include_router(collaboration_router)
    settings_for_cors = settings_override or load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings_for_cors.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Vikunja-Signature", "If-Match", "Idempotency-Key"],
    )

    @app.get("/health")
    def health(request: Request):
        settings = request.app.state.settings
        return {
            "status": "ok",
            "service": "life-core",
            "memos_configured": settings.memos_configured,
            "internal_auth_configured": bool(settings.internal_token),
            "jwt_auth_configured": bool(settings.jwt_secret and settings.jwt_refresh_secret),
            "memory_pipeline": {
                "version": "memory-v03",
                "database_id": digest(str(settings.database_path.resolve()))[:12],
                "worker_alive": request.app.state.memory_worker.is_alive(),
                "extractor": settings.memory_llm_provider if settings.memory_llm_key else "rules",
            },
        }

    @app.get("/api/v1/me")
    def me(request: Request, identity=Depends(current_identity)):
        _life_id, _source_id, user = identity
        return {
            "life_user_id": user["life_user_id"],
            "librechat_user_id": user["librechat_user_id"],
            "memos_user_id": user["memos_user_id"],
            "memos_username": user["memos_username"],
            "display_name": user["display_name"],
            "memory_consent": bool(user["memory_consent"]),
            "image_consent": bool(user["image_consent"]),
            "timezone": request.app.state.memory.timezone(user["life_user_id"]),
            **request.app.state.memory.permissions(user["life_user_id"]),
        }

    @app.patch("/api/v1/me/settings")
    def update_settings(body: ConsentRequest, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        with request.app.state.memory.lock:
            if body.timezone is not None:
                with request.app.state.store.connect() as db:
                    db.execute("""INSERT INTO user_preferences VALUES (?,?,?) ON CONFLICT(user_id)
                        DO UPDATE SET timezone=excluded.timezone,updated_at=excluded.updated_at""",
                        (life_id,body.timezone,datetime.now().astimezone().isoformat()))
            before = {k: bool(_user[k]) for k in ("memory_consent", "image_consent")}
            updated = request.app.state.store.update_consent(
                life_id,
                memory_consent=body.memory_consent,
                image_consent=body.image_consent,
            )
            after = {k: bool(updated[k]) for k in before}
            if before != after:
                with request.app.state.store.connect() as db:
                    db.execute("""INSERT INTO permission_audit(user_id,actor,old_values,new_values,created_at)
                        VALUES (?,'authenticated_settings',?,?,?)""",
                        (life_id,json.dumps(before),json.dumps(after),datetime.now().astimezone().isoformat()))
            scopes = request.app.state.memory.set_permissions(life_id, {
                "recall_consent": body.recall_consent, "sensitive_consent": body.sensitive_consent,
                "notification_consent": body.notification_consent,
            })
            if body.memory_consent is False or body.sensitive_consent is False:
                with request.app.state.store.connect() as db:
                    db.execute("""UPDATE memory_jobs SET payload=NULL,status='revoked'
                        WHERE user_id=? AND status IN ('queued','running')""", (life_id,))
            return {
                "memory_consent": bool(updated["memory_consent"]),
                "image_consent": bool(updated["image_consent"]),
                "timezone": request.app.state.memory.timezone(life_id),
                "updated_at": updated["updated_at"],
                **scopes,
            }

    @app.post("/internal/v1/users/bootstrap", dependencies=[Depends(require_internal)])
    def bootstrap_user(body: BootstrapUserRequest, request: Request):
        user = request.app.state.store.bootstrap_user(
            librechat_user_id=body.librechat_user_id,
            memos_user_id=body.memos_user_id,
            memos_username=body.memos_username,
            display_name=body.display_name,
            memory_consent=body.memory_consent,
            image_consent=body.image_consent,
        )
        user["memory_consent"] = bool(user["memory_consent"])
        user["image_consent"] = bool(user["image_consent"])
        return user

    def process_event(**kwargs):
        import time
        start = time.monotonic()
        owner = kwargs["user"]["life_user_id"]
        message_id = kwargs["source_message_ids"][0]
        try:
            memory = app.state.memory
            source = memory.sources.record(kwargs["user"], {
                "source_message_id": message_id, "text": kwargs["text"],
                "conversation_id": kwargs.get("conversation_id"),
                "occurred_at": kwargs["occurred_at"].isoformat(),
            })
            if source.get("status") == "revoked":
                return {"accepted": False, "reason": "source_revoked"}
            with app.state.store.connect() as db:
                batch_row = db.execute("SELECT status FROM memory_batches WHERE user_id=? AND message_id=?",
                                       (owner, message_id)).fetchone()
            previous = app.state.store.get_ingest_attempt(owner, message_id)
            context = memory.contextual_event(owner, kwargs.get("conversation_id"), kwargs["text"], kwargs["occurred_at"])
            if batch_row and batch_row["status"] == "completed":
                with app.state.store.connect() as db:
                    saved = [dict(r) for r in db.execute("""SELECT m.* FROM memory_items m
                        JOIN memory_evidence e ON m.memory_id=e.memory_id
                        WHERE e.user_id=? AND e.message_id=? AND m.state='active'""", (owner, message_id))]
                result = {"accepted": bool(saved), "reason": "batch_duplicate",
                          "results": [{"accepted": True, "memory": item} for item in saved]}
            elif FORGET.search(kwargs["text"]) or context or not memory.allowed(kwargs["user"], kwargs["text"]) or (previous and not batch_row):
                result = process_single_event(**kwargs)
            else:
                candidates, reason = memory.classify_many(kwargs["text"],
                    kwargs["occurred_at"].astimezone(ZoneInfo(memory.timezone(owner))),
                    use_llm=kwargs.get("use_llm", False))
                if not candidates:
                    result = {"accepted": False, "reason": reason}
                else:
                    is_batch = len(candidates) > 1 or bool(batch_row)
                    if is_batch:
                        with app.state.store.connect() as db:
                            db.execute("INSERT OR IGNORE INTO memory_batches VALUES (?,?,'running')", (owner,message_id))
                    results = []
                    for candidate in candidates:
                        args = {**kwargs, "text": candidate.evidence_quote,
                                "candidate_override": candidate, "reason_override": reason, "batch": is_batch}
                        results.append(process_single_event(**args))
                    result = {**results[0], "accepted": any(r["accepted"] for r in results), "results": results}
                    if is_batch:
                        with app.state.store.connect() as db:
                            db.execute("UPDATE memory_batches SET status='completed' WHERE user_id=? AND message_id=?", (owner,message_id))
        except Exception as exc:
            if str(exc) != "SOURCE_MESSAGE_CONFLICT":
                app.state.memory.sources.set_status(owner, message_id, "failed")
            app.state.memory.trace.record(owner, message_id, kwargs.get("conversation_id"),
                "extraction", "failed", type(exc).__name__.upper(),
                elapsed_ms=int((time.monotonic()-start)*1000))
            raise
        with app.state.store.connect() as db:
            count = db.execute("""SELECT COUNT(*) FROM memory_evidence e JOIN memory_items m
                ON e.memory_id=m.memory_id WHERE e.user_id=? AND e.message_id=? AND m.state='active'""",
                (owner, message_id)).fetchone()[0]
        app.state.memory.sources.set_status(owner, message_id, "extracted" if count else "no_memory")
        app.state.memory.trace.record(owner, message_id, kwargs.get("conversation_id"),
            "extraction", "saved" if count else "rejected", result.get("reason"), count,
            int((time.monotonic()-start)*1000))
        return result

    def process_single_event(
        *,
        user: dict[str, Any],
        text: str,
        source_type: str,
        source_message_ids: list[str],
        conversation_id: str | None,
        occurred_at: datetime,
        use_llm: bool = False,
        candidate_override: Candidate | None = None,
        reason_override: str | None = None,
        batch: bool = False,
    ) -> dict[str, Any]:
        settings = app.state.settings
        memory = app.state.memory
        user = app.state.store.get_user(user["life_user_id"])
        previous = app.state.store.get_ingest_attempt(user["life_user_id"], source_message_ids[0])
        if previous and not batch:
            if previous["event_id"]:
                event = app.state.store.get_event(previous["event_id"], user["life_user_id"])
                if event and event["status"] == "failed":
                    return publish_event(event)
                return {"accepted": bool(event and event["status"] != "withdrawn"),
                        "event": public_event(event) if event else None}
            return {"accepted": previous["status"] == "fact", "reason": previous["reason"]}
        context = memory.contextual_event(user["life_user_id"], conversation_id, text, occurred_at)
        if FORGET.search(text):
            if context:
                revoke_item(user["life_user_id"], context["memory_id"])
            else:
                # An unspecified plural deletion needs clarification, never a bulk erase.
                return {"accepted": False, "reason": "FORGET_TARGET_REQUIRED"}
            return {"accepted": False, "reason": "MEMORY_WITHDRAWN"}
        if not memory.allowed(user, text):
            return {"accepted": False, "reason": "MEMORY_CONSENT_REQUIRED"}
        if context:
            event = app.state.store.get_event(context["event_id"], user["life_user_id"])
            candidate = Candidate(candidate_type="life_event",canonical_text=context["canonical_text"],
                evidence_quote=text,occurred_state="occurred",confidence=context["confidence"],
                sensitivity=context["sensitivity"],image_candidate=bool(context["image_candidate"]))
            memory.save(user["life_user_id"],candidate,context["semantic_key"],source_message_ids[0],
                conversation_id,text,occurred_at,event["event_id"])
            app.state.store.record_ingest_attempt(user_id=user["life_user_id"],
                source_message_id=source_message_ids[0],status="accepted",reason="context_merged",event_id=event["event_id"])
            return {"accepted":True,"event":public_event(app.state.store.get_event(event["event_id"]))}
        if candidate_override is not None:
            candidate, reason = candidate_override, reason_override or "validated_candidate"
        else:
            candidate, reason = memory.classify(text,
                occurred_at.astimezone(ZoneInfo(memory.timezone(user["life_user_id"]))), use_llm=use_llm)
        if candidate is None:
            return {"accepted": False, "reason": reason}
        if candidate.sensitivity != "ordinary" and not memory.permissions(user["life_user_id"])["sensitive_consent"]:
            return {"accepted":False,"reason":"SENSITIVE_CONSENT_REQUIRED"}
        key = memory.key_for(candidate, text, occurred_at, memory.timezone(user["life_user_id"]))
        existing = memory.find(user["life_user_id"], key)
        if existing and existing["state"] == "withdrawn":
            return {"accepted":False,"reason":"MEMORY_WITHDRAWN"}
        if existing and existing["state"] == "superseded":
            existing = None
        if candidate.candidate_type in ("stable_fact", "future_plan"):
            item = memory.save(user["life_user_id"],candidate,key,source_message_ids[0],
                               conversation_id,text,occurred_at)
            app.state.store.record_ingest_attempt(user_id=user["life_user_id"],
                source_message_id=source_message_ids[0],status="fact",reason=candidate.candidate_type)
            return {"accepted":not item.get("conflict",False),"memory":item,
                    "reason":"FACT_CONFLICT" if item.get("conflict") else candidate.candidate_type}
        if existing and existing["event_id"]:
            event = app.state.store.get_event(existing["event_id"], user["life_user_id"])
            memory.save(user["life_user_id"],candidate,key,source_message_ids[0],
                        conversation_id,text,occurred_at,event["event_id"])
            app.state.store.record_ingest_attempt(user_id=user["life_user_id"],
                source_message_id=source_message_ids[0],status="accepted",reason="event_merged",event_id=event["event_id"])
            return publish_event(app.state.store.get_event(event["event_id"]))
        result = extract_event(
            text,
            now=occurred_at,
            timezone=memory.timezone(user["life_user_id"]),
        )
        if not result.accepted and candidate.candidate_type != "life_event":
            app.state.store.record_ingest_attempt(
                user_id=user["life_user_id"],
                source_message_id=source_message_ids[0],
                status="skipped",
                reason=result.reason,
            )
            return {
                "accepted": False,
                "reason": result.reason,
                "source_message_ids": source_message_ids,
            }

        consent = bool(user["memory_consent"])
        start_day, end_day, precision = candidate.occurrence.bounds(
            occurred_at.astimezone(ZoneInfo(memory.timezone(user["life_user_id"]))))
        event = app.state.store.create_event(
            user_id=user["life_user_id"],
            source_type=source_type,
            source_message_ids=source_message_ids,
            conversation_id=conversation_id,
            occurred_at=datetime.fromisoformat(start_day).replace(
                tzinfo=ZoneInfo(memory.timezone(user["life_user_id"]))).isoformat() if precision == "day" else "",
            occurrence_start=start_day, occurrence_end=end_day, occurrence_precision=precision,
            title=result.title or candidate.canonical_text[:28],
            summary=candidate.canonical_text,
            confidence=candidate.confidence,
            consent_state="granted" if consent else "pending",
            status="pending_consent" if not consent else "pending",
            idempotency_key=f"{user['life_user_id']}:{source_type}:{source_message_ids[0]}" + (f":{digest(key)[:16]}" if batch else ""),
        )
        memory.save(user["life_user_id"],candidate,key,source_message_ids[0],
                    conversation_id,text,occurred_at,event["event_id"])
        app.state.store.record_ingest_attempt(
            user_id=user["life_user_id"],
            source_message_id=source_message_ids[0],
            status="accepted",
            reason=result.reason,
            event_id=event["event_id"],
        )
        if not consent:
            return {"accepted": True, "event": public_event(event)}
        return publish_event(event)

    def publish_event(event: dict[str, Any]) -> dict[str, Any]:
        if event["status"] == "withdrawn":
            raise HTTPException(status_code=409, detail={"code":"MEMORY_WITHDRAWN"})
        if event["memo_ref"]:
            return {"accepted": True, "event": public_event(event)}
        user = app.state.store.get_user(event["user_id"])
        if user is None or not user["memory_consent"]:
            raise HTTPException(status_code=403, detail={"code": "MEMORY_CONSENT_REQUIRED"})

        job_key = f"memo_publish:{event['event_id']}"
        started = datetime.now(ZoneInfo(app.state.settings.timezone)).isoformat()
        app.state.store.upsert_task_run(
            job_type="memo_publish",
            idempotency_key=job_key,
            owner_user_id=event["user_id"],
            status="running",
            started_at=started,
            increment_attempts=True,
        )
        try:
            memo_ref = memos_for(user).create_private_memo({**event, "memos_user_id": user["memos_user_id"]})
        except (MemosError, httpx.HTTPError) as exc:
            reason = str(exc)[:500] if isinstance(exc, MemosError) else "MEMOS_NETWORK_ERROR"
            app.state.store.set_event_status(
                event["event_id"],
                status="failed",
                error_message=reason,
                increment_attempts=True,
            )
            app.state.store.upsert_task_run(
                job_type="memo_publish",
                idempotency_key=job_key,
                owner_user_id=event["user_id"],
                status="failed",
                completed_at=datetime.now(ZoneInfo(app.state.settings.timezone)).isoformat(),
                last_error=reason,
            )
            app.state.memory.trace.record(event["user_id"], event["source_message_ids"][0],
                event.get("conversation_id"), "publication", "failed", "MEMOS_PUBLISH_FAILED")
            raise HTTPException(status_code=502, detail={"code": "MEMOS_PUBLISH_FAILED"}) from exc

        updated = app.state.store.set_event_status(
            event["event_id"],
            status="published",
            memo_ref=memo_ref,
            error_message=None,
            increment_attempts=True,
        )
        app.state.store.upsert_task_run(
            job_type="memo_publish",
            idempotency_key=job_key,
            owner_user_id=event["user_id"],
            status="succeeded",
            completed_at=datetime.now(ZoneInfo(app.state.settings.timezone)).isoformat(),
            upstream_reference=memo_ref,
        )
        app.state.memory.trace.record(event["user_id"], event["source_message_ids"][0],
            event.get("conversation_id"), "publication", "published", item_count=1)
        return {"accepted": True, "event": public_event(updated)}

    @app.post("/internal/v1/events/ingest")
    def ingest(
        body: IngestRequest,
        request: Request,
        _internal: None = Depends(require_internal),
    ):
        store = request.app.state.store
        user = store.get_user_by_librechat_id(body.source_user_id)
        if user is None:
            raise HTTPException(status_code=403, detail={"code": "USER_NOT_MAPPED"})

        with request.app.state.memory.lock:
            try:
                return process_event(
                    user=user, text=body.text, source_type="chat",
                    source_message_ids=[body.source_message_id],
                    conversation_id=body.conversation_id, occurred_at=body.occurred_at,
                )
            except ValueError as exc:
                if str(exc) == "SOURCE_MESSAGE_CONFLICT":
                    raise HTTPException(409, detail={"code": "SOURCE_MESSAGE_CONFLICT"}) from exc
                raise

    @app.post("/internal/v1/events/enqueue", dependencies=[Depends(require_internal)])
    def enqueue(body: IngestRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            raise HTTPException(status_code=403, detail={"code":"USER_NOT_MAPPED"})
        try:
            return request.app.state.memory.enqueue(user, body.model_dump(mode="json"))
        except ValueError as exc:
            if str(exc) == "SOURCE_MESSAGE_CONFLICT":
                raise HTTPException(409, detail={"code": "SOURCE_MESSAGE_CONFLICT"}) from exc
            raise

    def perform_memory_command(body: MemoryCommand, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user or not request.app.state.memory.allowed(user, body.text):
            return {"status":"permission_required","code":"MEMORY_CONSENT_REQUIRED"}
        if not re.search(r"加入(?:到)?回忆|记下来|记录下来|记住这件事|记住刚才", body.text):
            return {"status":"not_saved","code":"EXPLICIT_MEMORY_REQUEST_REQUIRED"}
        if re.search(r"不要|别|不想", body.text):
            return {"status":"not_saved","code":"MEMORY_NOT_REQUESTED"}
        source = body.previous_user_message
        if source is None or source.source_user_id != body.source_user_id or source.conversation_id != body.conversation_id:
            return {"status":"needs_input","code":"MEMORY_TARGET_REQUIRED"}
        if not request.app.state.memory.allowed(user, source.text):
            return {"status":"permission_required","code":"SOURCE_CONSENT_REQUIRED"}
        with request.app.state.memory.lock:
            result = process_event(user=user,text=source.text,source_type="chat",
                source_message_ids=[source.source_message_id],conversation_id=source.conversation_id,
                occurred_at=source.occurred_at)
            with request.app.state.store.connect() as db:
                row = db.execute("""SELECT m.* FROM memory_items m JOIN memory_evidence e
                    ON m.memory_id=e.memory_id AND m.user_id=e.user_id
                    WHERE m.user_id=? AND e.message_id=? AND m.state='active' LIMIT 1""",
                    (user["life_user_id"],source.source_message_id)).fetchone()
                if row:
                    db.execute("""INSERT OR IGNORE INTO memory_recall_hits VALUES (?,?,?,?,?)""",
                        (user["life_user_id"],body.conversation_id,body.source_message_id,row["memory_id"],
                         datetime.now().astimezone().isoformat()))
                    if row["kind"] == "life_event":
                        db.execute("UPDATE memory_items SET importance=MAX(importance,.9) WHERE memory_id=?", (row["memory_id"],))
            if row and result["accepted"]:
                return {"status":"succeeded","kind":row["kind"],"url":f"/knowledge/{row['memory_id']}",
                        "image_status":"not_generated","message":"记忆已持久化，可点击查看；没有声称图片已经生成。"}
            return {"status":"not_saved","code":result.get("reason","MEMORY_SAVE_NOT_CONFIRMED")}

    @app.post("/internal/v1/memory/execute", dependencies=[Depends(require_internal)])
    def execute_memory(body: MemoryCommand, request: Request):
        result = perform_memory_command(body,request)
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if user and body.conversation_id:
            with request.app.state.store.connect() as db:
                db.execute("""INSERT OR REPLACE INTO memory_actions VALUES (?,?,?,?,?,?,?)""",
                    (user["life_user_id"],body.conversation_id,body.source_message_id,result["status"],
                     result.get("code"),result.get("url","").removeprefix("/knowledge/") or None,
                     datetime.now().astimezone().isoformat()))
        return result

    @app.post("/internal/v1/memory/forget", dependencies=[Depends(require_internal)])
    def forget_memory(body: ReminderChatRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"status": "user_not_mapped"}
        result = request.app.state.forget_memory.execute(
            user, body.source_message_id, body.conversation_id, body.text)
        if result["status"] == "forgotten":
            with app.state.store.connect() as db:
                rows = db.execute("""SELECT DISTINCT m.memory_id FROM memory_items m
                    JOIN memory_revisions r ON r.memory_id=m.memory_id
                    WHERE m.user_id=? AND r.action='withdrawn' AND r.source_message_id=?""",
                    (user["life_user_id"], body.source_message_id)).fetchall()
            cleanup = [revoke_item(user["life_user_id"], r["memory_id"])["cleanup"] for r in rows]
            result = {**result, "cleanup": "pending" if "pending" in cleanup else "complete"}
        return result

    @app.post("/internal/v1/knowledge/recall", dependencies=[Depends(require_internal)])
    def internal_recall(body: RecallRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"status": "user_not_mapped", "reason": "USER_NOT_MAPPED", "items": [], "profile": []}
        memory = request.app.state.memory
        recalled = memory.retriever.retrieve(user["life_user_id"], body.query,
            recent_messages=[m.model_dump() for m in body.recent_messages
                             if m.conversation_id in (None, body.conversation_id)], conversation_id=body.conversation_id)
        items = recalled["items"]
        profile = recalled["profile"]
        status = recalled["status"]
        memory.trace.record(user["life_user_id"], body.source_message_id, body.conversation_id,
                            "recall", status, item_count=len(items)+len(profile))
        if body.conversation_id and body.source_message_id:
            with request.app.state.store.connect() as db:
                for item in [*profile, *items]:
                    db.execute("INSERT OR IGNORE INTO memory_recall_hits VALUES (?,?,?,?,?)",
                        (user["life_user_id"],body.conversation_id,body.source_message_id,item["memory_id"],
                         datetime.now().astimezone().isoformat()))
        def evidence(i):
            return _overview_evidence(i, ZoneInfo(memory.timezone(user["life_user_id"])))
        result = [evidence(i) for i in items]
        profile_result = [evidence(i) for i in profile]
        return {"status": "matched" if result or profile_result else status, "items": result,
                "profile": profile_result, "retrieval": recalled["retrieval"]}

    @app.post("/internal/v1/assistant/plan", dependencies=[Depends(require_internal)])
    def internal_plan(body: PlanRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"status": "user_not_mapped", "tasks": []}
        life_id = user["life_user_id"]
        memory = request.app.state.memory
        try:
            plan = request.app.state.planner.plan(
                body.query,
                now=datetime.now(ZoneInfo(memory.timezone(life_id))),
                timezone=memory.timezone(life_id),
                recent_messages=[m.model_dump() for m in body.recent_messages
                                 if m.conversation_id in (None, body.conversation_id)],
            )
        except PlanUnavailable:
            return {"status": "planner_unavailable", "tasks": []}
        if not memory.permissions(life_id).get("recall_consent") and plan.tasks[0].action != "forget_memory":
            return {"status": "permission_denied", "tasks": []}
        return {"status": "planned",
                "tasks": [task.model_dump(mode="json") for task in plan.tasks]}

    def _overview_evidence(item, zone):
        evidence = {"memory_id": item["memory_id"], "text": item["canonical_text"],
                    "valid_from": item.get("valid_from") or item.get("recorded_at"),
                    "kind": item["kind"], "url": f"/knowledge/{item['memory_id']}"}
        if item["kind"] == "life_event":
            start, end, precision = item_interval(item)
            evidence.update(occurrence_start=start, occurrence_end=end, occurrence_precision=precision,
                            occurrence_day=start if precision == "day" else None)
        return evidence

    @app.post("/internal/v1/assistant/execute", dependencies=[Depends(require_internal)])
    def internal_execute(body: PlanRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"status": "user_not_mapped", "results": []}
        life_id = user["life_user_id"]
        memory = request.app.state.memory
        zone = ZoneInfo(memory.timezone(life_id))
        recent = [m.model_dump() for m in body.recent_messages
                  if m.conversation_id in (None, body.conversation_id)]
        try:
            plan = request.app.state.planner.plan(
                body.query, now=datetime.now(zone), timezone=memory.timezone(life_id),
                recent_messages=recent)
        except PlanUnavailable:
            return {"status": "planner_unavailable", "results": []}
        results = []
        for task in plan.tasks:
            entry = {"action": task.action, "status": "skipped"}
            if task.action in ("search_memory", "answer"):
                query = task.query or body.query
                recalled = memory.retriever.retrieve(life_id, query,
                    recent_messages=recent, conversation_id=body.conversation_id)
                matched_profile_ids = set(recalled["retrieval"].get("profile_match_ids", []))
                # Retrieval labels profile facts separately; pass only semantic matches,
                # not unrelated background facts, into the task's evidence items.
                evidence_items = recalled["items"] + [
                    item for item in recalled.get("profile", [])
                    if item["memory_id"] in matched_profile_ids]
                entry.update(status=recalled["status"],
                             items=[_overview_evidence(i, zone) for i in evidence_items],
                             retrieval=recalled["retrieval"])
            elif task.action == "overview":
                today = datetime.now(zone).date()
                window = task.window.resolve(today) if task.window else None
                found = memory.retriever.overview(life_id, window=window, today=today,
                                                  limit=task.limit, offset=task.offset, zone=zone)
                entry.update(status=found["status"],
                             items=[_overview_evidence(i, zone) for i in found["items"]],
                             retrieval=found["retrieval"])
            elif task.action == "forget_memory":
                # Planning is read-only; the chat caller must persist the current
                # user message before invoking the separate mutation endpoint.
                entry.update(status="needs_execution")
            elif task.action == "query_reminders":
                records = app.state.reminders.list(life_id)
                entry.update(status="ready", reminders=[
                    {k: item[k] for k in ("reminder_id", "title", "scheduled_at", "status")
                     if k in item} for item in records[:40]])
            elif task.action == "prepare_reminder" and task.reminder is not None:
                entry.update(status="needs_draft", fields=task.reminder.model_dump(mode="json"))
            elif task.action in ("web_search", "clarify"):
                entry.update(status="unavailable" if task.action == "web_search" else "clarify",
                             clarification=task.clarification)
            results.append(entry)
        return {"status": "executed", "results": results}

    @app.post("/internal/v1/memory/telemetry", dependencies=[Depends(require_internal)])
    def memory_telemetry(body: MemoryTelemetry, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"status": "user_not_mapped"}
        request.app.state.memory.trace.record(user["life_user_id"], body.source_message_id,
            body.conversation_id, body.stage, body.status, body.reason, body.item_count, body.elapsed_ms)
        return {"status": "recorded"}

    @app.get("/api/v1/memory-status")
    def memory_status(request: Request, conversation_id: str | None = None, identity=Depends(current_identity)):
        memory = request.app.state.memory
        return {**memory.trace.recent(identity[0], conversation_id),
                "permissions": memory.permissions(identity[0]),
                "memory_consent": bool(identity[2]["memory_consent"]),
                "database_id": digest(str(request.app.state.settings.database_path.resolve()))[:12],
                "extractor_configured": bool(request.app.state.settings.memory_llm_key),
                "source_coverage": memory.sources.coverage(identity[0])}

    @app.get("/api/v1/memory-sources/coverage")
    def source_coverage(request: Request, identity=Depends(current_identity)):
        return request.app.state.memory.sources.coverage(identity[0])

    @app.get("/api/v1/memory-sources/{source_id}")
    def source_detail(source_id: str, request: Request, identity=Depends(current_identity)):
        item = request.app.state.memory.sources.detail(identity[0], source_id)
        if item is None:
            raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND"})
        return {"item": item}

    @app.delete("/api/v1/memory-sources/{source_id}")
    def source_withdraw(source_id: str, request: Request, identity=Depends(current_identity)):
        memory = request.app.state.memory
        with memory.lock:
            item = memory.sources.detail(identity[0], source_id)
            if item is None:
                raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND"})
            with memory.store.connect() as db:
                derived = db.execute("""SELECT DISTINCT memory_id FROM memory_evidence
                    WHERE user_id=? AND message_id=?""",
                    (identity[0], item["source_message_id"])).fetchall()
            for row in derived:
                revoke_item(identity[0], row["memory_id"])
            memory.sources.withdraw(identity[0], source_id)
            return {"state": "withdrawn"}

    @app.get("/api/v1/knowledge")
    def knowledge(request: Request, identity=Depends(current_identity)):
        return {"items":request.app.state.memory.list_items(identity[0])}

    @app.post("/api/v1/knowledge/recall")
    def user_recall(body: UserRecallRequest, request: Request, identity=Depends(current_identity)):
        # Same retrieval contract, but the owner comes exclusively from the JWT.
        return internal_recall(RecallRequest(source_user_id=identity[1], **body.model_dump()), request)

    @app.get("/api/v1/knowledge/recall")
    def recall(request: Request, q: str = Query(max_length=4000), identity=Depends(current_identity)):
        return {"items":request.app.state.memory.recall(identity[0], q)}

    @app.get("/api/v1/knowledge/{memory_id}")
    def knowledge_detail(memory_id: str, request: Request, identity=Depends(current_identity)):
        memory = request.app.state.memory
        item = (memory.sources.detail(identity[0], memory_id) if memory_id.startswith("source_")
                else memory.detail(identity[0], memory_id))
        if item is None:
            raise HTTPException(404, detail={"code":"MEMORY_NOT_FOUND"})
        return {"item":item}

    @app.get("/api/v1/chat-links")
    def chat_links(conversation_id: str, request: Request, identity=Depends(current_identity)):
        owner = identity[0]
        scopes = request.app.state.memory.permissions(owner)
        with request.app.state.store.connect() as db:
            sources = db.execute("""SELECT e.message_id,m.memory_id,m.kind,m.event_id,m.canonical_text
                FROM memory_evidence e JOIN memory_items m ON m.memory_id=e.memory_id AND m.user_id=e.user_id
                WHERE e.user_id=? AND e.conversation_id=? AND m.state='active'
                UNION SELECT h.message_id,m.memory_id,m.kind,m.event_id,m.canonical_text
                FROM memory_recall_hits h JOIN memory_items m ON m.memory_id=h.memory_id AND m.user_id=h.user_id
                WHERE h.user_id=? AND h.conversation_id=? AND m.state='active'
                AND ?=1 AND (m.sensitivity='ordinary' OR ?=1)""",
                (owner,conversation_id,owner,conversation_id,
                 int(scopes["recall_consent"]),int(scopes["sensitive_consent"]))).fetchall()
            actions = db.execute("""SELECT a.message_id,a.status,a.code,a.memory_id,m.state
                FROM memory_actions a LEFT JOIN memory_items m ON m.memory_id=a.memory_id AND m.user_id=a.user_id
                WHERE a.user_id=? AND a.conversation_id=?""", (owner,conversation_id)).fetchall()
        moments = request.app.state.moments.list(owner)
        return {"actions":[{**dict(a),"status":a["status"] if a["state"] in (None,"active") else "withdrawn"}
                           for a in actions],
                "links":[{**dict(row), "url":f"/knowledge/{row['memory_id']}",
                         "moments":[{"moment_id":m["moment_id"],"status":m["status"]}
                                    for m in moments if row["memory_id"] in m["source_memory_ids"] and m["status"]!="cancelled"]}
                        for row in sources]}

    def revoke_item(user_id, memory_id):
        item = app.state.memory.invalidate(user_id, memory_id)
        if item is None:
            raise HTTPException(status_code=404, detail={"code":"MEMORY_NOT_FOUND"})
        app.state.moments.withdraw_source(user_id, memory_id)
        cleanup = "not_required"
        if item["event_id"]:
            event = app.state.store.get_event(item["event_id"], user_id)
            if event and event["memo_ref"]:
                try:
                    user = app.state.store.get_user(user_id)
                    memos_for(user).delete_private_memo(event["memo_ref"], user["memos_user_id"])
                    cleanup = "succeeded"
                except (MemosError, httpx.HTTPError):
                    cleanup = "pending"
                    app.state.store.upsert_task_run(job_type="memo_delete",
                        idempotency_key=f"memo_delete:{item['event_id']}",owner_user_id=user_id,
                        status="failed",last_error="MEMOS_DELETE_PENDING",upstream_reference=event["memo_ref"])
        return {"state":"withdrawn","cleanup":cleanup}

    def retry_memo_cleanup():
        with app.state.memory.lock:
            with app.state.store.connect() as db:
                jobs = db.execute("""SELECT * FROM task_runs WHERE job_type='memo_delete'
                    AND status='failed' AND attempts<10 LIMIT 10""").fetchall()
            for job in jobs:
                user = app.state.store.get_user(job["owner_user_id"])
                if not user:
                    continue
                try:
                    memos_for(user).delete_private_memo(job["upstream_reference"], user["memos_user_id"])
                    status, error = "succeeded", None
                except (MemosError, httpx.HTTPError):
                    status, error = "failed", "MEMOS_DELETE_PENDING"
                app.state.store.upsert_task_run(job_type="memo_delete",
                    idempotency_key=job["idempotency_key"],owner_user_id=job["owner_user_id"],
                    status=status,last_error=error,increment_attempts=True,
                    completed_at=datetime.now(ZoneInfo(app.state.settings.timezone)).isoformat()
                        if status=="succeeded" else None)

    @app.delete("/api/v1/knowledge/{memory_id}")
    def delete_knowledge(memory_id: str, request: Request, identity=Depends(current_identity)):
        with request.app.state.memory.lock:
            return revoke_item(identity[0], memory_id)

    @app.patch("/api/v1/knowledge/{memory_id}")
    def update_knowledge(memory_id: str, body: KnowledgeUpdate, request: Request,
                         identity=Depends(current_identity)):
        life_id, _source_id, user = identity
        with request.app.state.memory.lock:
            with request.app.state.store.connect() as db:
                row = db.execute("SELECT * FROM memory_items WHERE memory_id=? AND user_id=? AND state='active'",
                                 (memory_id,life_id)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail={"code":"MEMORY_NOT_FOUND"})
            now = datetime.now(ZoneInfo(request.app.state.settings.timezone))
            candidate, _reason = request.app.state.memory.classify(body.text, now)
            if row["kind"] == "life_event":
                if candidate is None or candidate.candidate_type != "life_event" or not request.app.state.memory.allowed(user,body.text):
                    raise HTTPException(422,detail={"code":"EVENT_CORRECTION_REQUIRED"})
                request.app.state.memory.invalidate(life_id,memory_id,"superseded")
                request.app.state.moments.withdraw_source(life_id,memory_id)
                return process_event(user=user,text=body.text,source_type="manual",
                    source_message_ids=[f"edit:{memory_id}:{row['revision']}:{digest(body.text)[:16]}"],
                    conversation_id=None,occurred_at=now)
            if row["kind"] == "future_plan":
                if candidate is None or candidate.candidate_type != "future_plan" or not request.app.state.memory.allowed(user, body.text):
                    raise HTTPException(422, detail={"code":"PLAN_CORRECTION_REQUIRED"})
                request.app.state.memory.invalidate(life_id, memory_id, "superseded")
                return process_event(user=user,text=body.text,source_type="manual",
                    source_message_ids=[f"edit:{memory_id}:{row['revision']}:{digest(body.text)[:16]}"],
                    conversation_id=None,occurred_at=now)
            if candidate is None or candidate.candidate_type != "stable_fact" or row["kind"] != "stable_fact":
                raise HTTPException(status_code=422, detail={"code":"FACT_CORRECTION_REQUIRED"})
            key = request.app.state.memory.key_for(candidate, body.text, now)
            if key != row["semantic_key"]:
                raise HTTPException(status_code=422, detail={"code":"FACT_KIND_MISMATCH"})
            return process_event(user=user,text="现在"+body.text,source_type="manual",
                source_message_ids=[f"edit:{memory_id}:{row['revision']}:{digest(candidate.value)[:16]}"],
                conversation_id=None,occurred_at=now)

    @app.post("/api/v1/events/extract")
    def manual_extract(body: ManualExtractRequest, identity=Depends(current_identity), request: Request = None):
        _life_id, _source_id, user = identity
        previous = request.app.state.store.get_ingest_attempt(
            user["life_user_id"], body.source_message_id
        )
        if previous and previous["event_id"]:
            event = request.app.state.store.get_event(previous["event_id"], user["life_user_id"])
            return {"accepted": True, "event": public_event(event)}
        occurred_at = body.occurred_at or datetime.now(ZoneInfo(request.app.state.settings.timezone))
        with request.app.state.memory.lock:
            return process_event(
                user=user, text=body.text, source_type="manual",
                source_message_ids=[body.source_message_id],
                conversation_id=body.conversation_id, occurred_at=occurred_at,
            )

    @app.post("/api/v1/memories/publish")
    def publish(body: PublishRequest, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        event = request.app.state.store.get_event(body.event_id, life_id)
        if event is None:
            raise HTTPException(status_code=404, detail={"code": "EVENT_NOT_FOUND"})
        return publish_event(event)

    @app.get("/api/v1/events")
    def list_events(identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        events = request.app.state.store.list_events(life_id)
        return {"events": [public_event(event) for event in events]}

    def memos_for(user):
        if not user["memos_user_id"]:
            raise HTTPException(403, detail={"code": "MEMOS_USER_NOT_CONFIGURED"})
        token = app.state.settings.memos_user_tokens.get(user["memos_user_id"])
        return MemosClient(app.state.settings.memos_base_url, token) if token else app.state.memos

    def read_memory(
        event: dict[str, Any],
        user: dict[str, Any],
        request: Request,
        *,
        include_image: bool = False,
    ) -> dict[str, Any]:
        try:
            memo = memos_for(user).get_private_memo(event["memo_ref"], user["memos_user_id"])
        except MemosError as exc:
            raise HTTPException(status_code=502, detail={"code": "MEMOS_READ_FAILED"}) from exc
        media = request.app.state.moments.media_for_event(
            event["user_id"], event["event_id"], include_image=include_image
        )
        return {
            **public_event(event),
            "content": memo["content"],
            "tags": memo.get("tags", []),
            "event_type": "life_event",
            "has_image": media is not None,
            "media": media,
        }

    @app.get("/api/v1/memories")
    def list_memories(
        identity=Depends(current_identity),
        request: Request = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=50),
        q: str = Query(default="", max_length=200),
        on_date: date | None = None,
        order: str = Query(default="desc", pattern="^(asc|desc)$"),
    ):
        life_id, _source_id, user = identity
        events = request.app.state.store.list_events(life_id, published_only=True)
        needle = q.strip().casefold()
        events = [
            event for event in events
            if (not needle or needle in f"{event['title']} {event['summary']}".casefold())
            and (
                on_date is None
                or overlaps(event, on_date, on_date)
            )
        ]
        dated = [e for e in events if e.get("occurrence_start")]
        undated = [e for e in events if not e.get("occurrence_start")]
        dated.sort(key=lambda e: (e["occurrence_start"], e.get("occurrence_end") or ""), reverse=order == "desc")
        undated.sort(key=lambda e: e["created_at"], reverse=order == "desc")
        events = dated + undated
        start = (page - 1) * page_size
        with ThreadPoolExecutor(max_workers=6) as executor:
            memories = list(
                executor.map(
                    lambda event: read_memory(event, user, request),
                    events[start:start + page_size],
                )
            )
        return {
            "memories": memories,
            "total": len(events),
            "page": page,
            "page_size": page_size,
            "has_more": start + page_size < len(events),
        }

    @app.get("/api/v1/memories/{memory_id}")
    def memory_detail(memory_id: str, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, user = identity
        if not re.fullmatch(r"evt_[a-f0-9]{24}", memory_id):
            raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND"})
        event = request.app.state.store.get_event(memory_id, life_id)
        if event is None or event["status"] != "published" or not event["memo_ref"]:
            raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND"})
        return {"memory": read_memory(event, user, request, include_image=True)}

    @app.post("/api/v1/reminders")
    def create_reminder(body: ReminderRequest, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        try:
            reminder = request.app.state.reminders.create(
                life_id,
                title=body.title,
                scheduled_at=body.scheduled_at,
                timezone_name=body.timezone,
                delivery_channel=body.delivery_channel,
            )
        except ReminderUpstreamError as exc:
            raise HTTPException(
                status_code=403 if isinstance(exc, ReminderPermissionError) else 503,
                detail={"code": str(exc)},
            ) from exc
        return {"reminder": public_reminder(reminder)}

    @app.patch("/api/v1/reminders/{reminder_id}")
    def update_reminder(
        reminder_id: str,
        body: ReminderUpdateRequest,
        identity=Depends(current_identity),
        request: Request = None,
    ):
        life_id, _source_id, _user = identity
        try:
            reminder = request.app.state.reminders.update(
                life_id,
                reminder_id,
                title=body.title,
                scheduled_at=body.scheduled_at,
                timezone_name=body.timezone,
                done=body.done,
            )
        except ReminderUpstreamError as exc:
            raise HTTPException(
                status_code=403 if isinstance(exc, ReminderPermissionError) else 503,
                detail={"code": str(exc)},
            ) from exc
        if reminder is None:
            raise HTTPException(status_code=404, detail={"code": "REMINDER_NOT_FOUND"})
        return {"reminder": public_reminder(reminder)}

    @app.delete("/api/v1/reminders/{reminder_id}")
    def cancel_reminder(
        reminder_id: str,
        identity=Depends(current_identity),
        request: Request = None,
    ):
        life_id, _source_id, _user = identity
        try:
            reminder = request.app.state.reminders.cancel(life_id, reminder_id)
        except ReminderUpstreamError as exc:
            raise HTTPException(status_code=503, detail={"code": str(exc)}) from exc
        if reminder is None:
            raise HTTPException(status_code=404, detail={"code": "REMINDER_NOT_FOUND"})
        return {"reminder": public_reminder(reminder)}

    @app.get("/api/v1/reminders/{reminder_id}")
    def reminder_detail(reminder_id: str, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        reminder = request.app.state.store.get_reminder(reminder_id, life_id)
        if reminder is None:
            raise HTTPException(status_code=404, detail={"code": "REMINDER_NOT_FOUND"})
        try:
            request.app.state.reminders.list(life_id)
        except ReminderUpstreamError as exc:
            raise HTTPException(status_code=503, detail={"code": str(exc)}) from exc
        reminder = request.app.state.store.get_reminder(reminder_id, life_id)
        with request.app.state.store.connect() as db:
            source = db.execute("""SELECT d.conversation_id,d.source_message_id,d.fields
                FROM reminder_drafts d JOIN reminder_submissions s ON s.draft_id=d.draft_id
                AND s.owner_id=d.owner_id WHERE s.owner_id=? AND s.reminder_id=?""",
                (life_id, reminder_id)).fetchone()
        return {"reminder": {**public_reminder(reminder),
                             "source": {**dict(source), "fields": json.loads(source["fields"])} if source else None}}

    @app.get("/api/v1/reminders")
    def list_reminders(identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        try:
            reminders = request.app.state.reminders.list(life_id)
        except ReminderUpstreamError as exc:
            raise HTTPException(status_code=503, detail={"code": str(exc)}) from exc
        return {
            **request.app.state.provisioning.status(life_id),
            "reminders": [
                public_reminder(item) for item in reminders
            ]
        }

    @app.get("/api/v1/reminder-notifications")
    def reminder_notifications(identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        if not request.app.state.reminders.configured(life_id):
            return {"messages": []}
        try:
            return {"messages": request.app.state.reminders.notifications(life_id)}
        except ReminderUpstreamError as exc:
            raise HTTPException(status_code=503, detail={"code": str(exc)}) from exc

    @app.get("/api/v1/moment-settings")
    def moment_settings(request: Request, identity=Depends(current_identity)):
        return request.app.state.moments.config(identity[0])

    @app.put("/api/v1/moment-settings")
    def configure_moments(body: MomentSettings, request: Request, identity=Depends(current_identity)):
        try:
            with request.app.state.memory.lock:
                return request.app.state.moments.configure(identity[2],body)
        except ValueError as exc:
            raise HTTPException(403,detail={"code":"MEMORY_AND_IMAGE_CONSENT_REQUIRED"}) from exc

    @app.get("/api/v1/moments")
    def list_moments(request: Request, identity=Depends(current_identity)):
        return {"moments":request.app.state.moments.list(identity[0])}

    @app.get("/api/v1/moments/{moment_id}")
    def moment_detail(moment_id: str, request: Request, identity=Depends(current_identity)):
        item = request.app.state.moments.detail(identity[0],moment_id)
        if item is None:
            raise HTTPException(404,detail={"code":"MOMENT_NOT_FOUND"})
        return {"moment":item}

    @app.post("/api/v1/moments/{moment_id}/retry")
    def retry_moment(moment_id: str, request: Request, identity=Depends(current_identity)):
        try:
            return {"moment":request.app.state.moments.retry(identity[0],moment_id)}
        except LookupError as exc:
            raise HTTPException(404,detail={"code":"MOMENT_NOT_FOUND"}) from exc
        except ValueError as exc:
            raise HTTPException(403,detail={"code":"CONSENT_OR_SOURCE_REVOKED"}) from exc

    @app.get("/api/v1/test/direct-moment")
    def direct_moment_test_status(request: Request, identity=Depends(current_identity)):
        return request.app.state.moments.direct_test_status(identity[2])

    @app.post("/api/v1/test/direct-moment")
    def direct_moment_test_create(
        body: DirectMomentTestRequest, request: Request, identity=Depends(current_identity)
    ):
        if not request.app.state.moments.direct_test_status(identity[2])["enabled"]:
            raise HTTPException(403, detail={"code": "ADMIN_DIRECT_TEST_REQUIRED"})
        verify_draft_source(
            request, body.conversation_id, body.source_message_id, body.text
        )
        try:
            moment = request.app.state.moments.create_direct_test(
                identity[2], body.source_message_id, body.conversation_id, body.text,
                datetime.now(timezone.utc), action=body.action,
            )
        except ValueError as exc:
            code = str(exc)
            status = 503 if "PROVIDER" in code or "TIMEOUT" in code else 403
            raise HTTPException(status, detail={"code": code}) from exc
        if body.action == "image":
            return {"moment": moment, "test_mode": "DIRECT_TEST_BYPASS"}
        event = request.app.state.store.get_event(moment["memory"]["event_id"], identity[0])
        if event is None:
            raise HTTPException(404, detail={"code": "EVENT_NOT_FOUND"})
        published = publish_event(event)["event"]
        moment["memory"].update(
            event_id=published["event_id"],
            memo_ref=published["memo_ref"],
            status=published["status"],
        )
        return {**moment, "test_mode": "DIRECT_TEST_BYPASS"}

    @app.post("/api/v1/moments/{moment_id}/publish")
    def publish_moment_to_memories(
        moment_id: str, request: Request, identity=Depends(current_identity)
    ):
        if not request.app.state.moments.direct_test_status(identity[2])["enabled"]:
            raise HTTPException(403, detail={"code": "ADMIN_DIRECT_TEST_REQUIRED"})
        try:
            event = request.app.state.moments.memory_source_event(identity[0], moment_id)
        except LookupError as exc:
            raise HTTPException(404, detail={"code": "MOMENT_NOT_FOUND"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": str(exc)}) from exc
        published = publish_event(event)["event"]
        return {
            "memory": published,
            "moment_id": moment_id,
            "test_mode": "DIRECT_TEST_BYPASS",
        }

    @app.delete("/api/v1/moments/{moment_id}")
    def delete_moment(moment_id: str, request: Request, identity=Depends(current_identity)):
        if not request.app.state.moments.delete(identity[0],moment_id):
            raise HTTPException(404,detail={"code":"MOMENT_NOT_FOUND"})
        return {"status":"cancelled"}

    @app.post("/api/v1/knowledge/{memory_id}/exclude-moments")
    def exclude_moment_source(memory_id: str, request: Request, identity=Depends(current_identity)):
        try:
            request.app.state.moments.exclude(identity[0],memory_id)
        except LookupError as exc:
            raise HTTPException(404,detail={"code":"MEMORY_NOT_FOUND"}) from exc
        return {"excluded":True}

    @app.post("/api/v1/reminder-provisioning")
    def provision_reminders(identity=Depends(current_identity), request: Request = None):
        try:
            return request.app.state.provisioning.provision(identity[0])
        except ReminderUpstreamError as exc:
            raise HTTPException(
                status_code=403 if isinstance(exc, ReminderPermissionError) else 503,
                detail={"code": str(exc)},
            ) from exc

    @app.post("/api/v1/reminder-drafts")
    def create_draft(body: DraftCreateRequest, identity=Depends(current_identity), request: Request = None):
        verify_draft_source(request, body.conversation_id, body.source_message_id, body.text)
        return request.app.state.reminder_drafts.create(
            identity[0], body.conversation_id, body.source_message_id, body.text)

    @app.get("/api/v1/reminder-drafts")
    def list_drafts(conversation_id: str = Query(min_length=1, max_length=200),
                    identity=Depends(current_identity), request: Request = None):
        return {"drafts": request.app.state.reminder_drafts.list(identity[0], conversation_id)}

    @app.patch("/api/v1/reminder-drafts/{draft_id}")
    def patch_draft(draft_id: str, body: DraftFields,
                    if_match: Annotated[int, Header(alias="If-Match")],
                    identity=Depends(current_identity), request: Request = None):
        return request.app.state.reminder_drafts.patch(
            identity[0], draft_id, if_match, body.model_dump(mode="json", exclude_unset=True))

    @app.delete("/api/v1/reminder-drafts/{draft_id}")
    def cancel_draft(draft_id: str, identity=Depends(current_identity), request: Request = None):
        return request.app.state.reminder_drafts.cancel(identity[0], draft_id)

    @app.post("/api/v1/reminder-drafts/{draft_id}/confirm")
    def confirm_draft(draft_id: str, body: DraftConfirmation,
                      identity=Depends(current_identity), request: Request = None):
        try:
            draft = request.app.state.reminder_drafts.get(identity[0], draft_id)
            if draft["status"] in ("needs_input", "ready_to_confirm", "unavailable"):
                verify_draft_source(request, draft["conversation_id"], draft["source_message_id"], draft["source_text"])
            return request.app.state.reminder_drafts.confirm(
                identity[0], draft_id, body.revision, body.idempotency_key)
        except ReminderUpstreamError as exc:
            raise HTTPException(
                status_code=403 if isinstance(exc, ReminderPermissionError) else 503,
                detail={"code": str(exc)},
            ) from exc

    @app.post("/api/v1/reminder-drafts/{draft_id}/reconcile")
    def reconcile_draft(draft_id: str, identity=Depends(current_identity), request: Request = None):
        try:
            return request.app.state.reminder_drafts.reconcile(identity[0], draft_id)
        except ReminderUpstreamError as exc:
            raise HTTPException(503, detail={"code": str(exc)}) from exc

    @app.post("/api/v1/reminder-drafts/{draft_id}/select")
    def select_draft(draft_id: str, body: DraftSelection, request: Request, identity=Depends(current_identity)):
        drafts = request.app.state.reminder_drafts
        draft = drafts.get(identity[0], draft_id)
        if draft["status"] in ("scheduled", "unknown", "creating", "cancelled"):
            return draft
        verify_draft_source(request, draft["conversation_id"], draft["source_message_id"], draft["source_text"])
        try:
            value = drafts.patch(identity[0], draft_id, body.revision,
                                 body.fields.model_dump(mode="json", exclude_unset=True))
            if value["missing_fields"] or value["error_code"]:
                return value
            return drafts.confirm(identity[0], draft_id, value["revision"],
                                  f"{draft_id}:{value['revision']}")
        except ReminderUpstreamError as exc:
            raise HTTPException(403 if isinstance(exc, ReminderPermissionError) else 503,
                                detail={"code": str(exc)}) from exc

    @app.post("/api/v1/webhooks/vikunja")
    async def vikunja_webhook(request: Request):
        raw_body = await request.body()
        signature = request.headers.get("X-Vikunja-Signature", "")
        if not request.app.state.reminders.handle_webhook(raw_body, signature):
            raise HTTPException(status_code=401, detail={"code": "INVALID_VIKUNJA_WEBHOOK"})
        return {"accepted": True}

    @app.post("/internal/v1/reminders/execute", dependencies=[Depends(require_internal)])
    def chat_reminder(body: ReminderChatRequest, request: Request, background_tasks: BackgroundTasks):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if user is None:
            user = request.app.state.store.ensure_reminder_user(body.source_user_id)
        result = request.app.state.reminder_chat.execute(
            user, body.source_message_id, body.text, body.conversation_id)
        owner = user["life_user_id"]
        if result.get("draft_id") and request.app.state.reminders.notifications_allowed(owner) and not request.app.state.reminders.configured(owner):
            def provision_after_response():
                try:
                    request.app.state.provisioning.provision(owner)
                except ReminderUpstreamError:
                    pass  # The persisted Saga exposes a safe retryable error to the card.
            background_tasks.add_task(provision_after_response)
        return result

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("LIFE_HOST", "127.0.0.1"),
        port=int(os.getenv("LIFE_PORT", "8010")),
    )

