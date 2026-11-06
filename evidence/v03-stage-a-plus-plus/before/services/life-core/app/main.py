from __future__ import annotations

import os
import re
import threading
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel, Field, ValidationError, field_validator

from .auth import identity_from_request
from .config import Settings, load_settings
from .extraction import extract_event
from .memos import MemosClient, MemosError
from .memory import Candidate, MemoryService, FORGET, SENSITIVE, digest
from .moments import Moments, MomentSettings
from .reminders import ReminderPermissionError, ReminderService, ReminderUpstreamError
from .reminder_chat import ReminderChat
from .provisioning import ReminderProvisioning
from .reminder_drafts import DraftFields, ReminderDrafts
from .store import Store
from .tools import ToolExecution, ToolRequest
from .tool_chat import ToolChat, ToolChoice

logger = logging.getLogger(__name__)


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
    memory_consent: bool = False
    image_consent: bool = False


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


class RecallRequest(BaseModel):
    source_user_id: str
    query: str = Field(max_length=4000)
    conversation_id: str | None = None
    source_message_id: str | None = None


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
        if request.url.path.startswith("/api/v1/reminder") or request.url.path in ("/api/v1/me", "/api/v1/me/settings"):
            user = request.app.state.store.ensure_reminder_user(librechat_user_id)
        else:
            raise HTTPException(status_code=403, detail={"code": "USER_NOT_MAPPED"})
    return user["life_user_id"], librechat_user_id, user


def require_internal(token: Annotated[str | None, Header(alias="X-Internal-Token")], request: Request) -> None:
    expected = request.app.state.settings.internal_token
    if not expected or not token or token != expected:
        raise HTTPException(status_code=401, detail={"code": "INVALID_INTERNAL_TOKEN"})


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "source_type": event["source_type"],
        "source_message_ids": event["source_message_ids"],
        "conversation_id": event["conversation_id"],
        "occurred_at": event["occurred_at"],
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
    url = request.app.state.settings.librechat_base_url + "/api/messages"
    try:
        response = httpx.get(
            url,
            params={"conversationId": conversation, "messageId": source},
            headers={"Authorization": request.headers.get("authorization", "")},
            timeout=8,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "SOURCE_VERIFICATION_UNAVAILABLE"}) from exc
    if response.status_code in (403, 404):
        raise HTTPException(409, detail={"code": "SOURCE_MESSAGE_UNAVAILABLE"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "SOURCE_VERIFICATION_UNAVAILABLE"})
    payload = response.json()
    messages = payload.get("messages") if isinstance(payload, dict) else payload
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
        app.state.moments = Moments(store, settings, app.state.memory)
        app.state.tools = ToolExecution(store,settings)
        app.state.tool_chat = ToolChat(store, app.state.tools, app.state.memory)
        app.state.reminders = ReminderService(store, settings)
        app.state.provisioning = ReminderProvisioning(store, settings, app.state.reminders)
        app.state.reminders.provisioning = app.state.provisioning
        app.state.reminder_drafts = ReminderDrafts(store, settings, app.state.reminders)
        app.state.reminders.drafts = app.state.reminder_drafts
        app.state.reminder_chat = ReminderChat(store, settings, app.state.reminders)
        app.state.reminder_chat.drafts = app.state.reminder_drafts
        stop = threading.Event()
        def work():
            next_cleanup = 0.0
            next_notification_retry = 0.0
            while not stop.is_set():
                import time
                if time.monotonic() >= next_cleanup:
                    app.state.tools.cleanup()
                    app.state.tool_chat.cleanup()
                    retry_memo_cleanup()
                    if not settings.reminder_scheduler_external:
                        app.state.reminders.reconcile_notifications()
                    app.state.provisioning.maintain()
                    next_cleanup = time.monotonic() + 30
                if not settings.reminder_scheduler_external and time.monotonic() >= next_notification_retry:
                    app.state.reminders.deliver_one_notification()
                    next_notification_retry = time.monotonic() + 5
                app.state.memory.project_one()
                if not app.state.memory.run_one(process_event):
                    stop.wait(0.5)
        worker = threading.Thread(target=work, name="memory-extraction", daemon=True)
        def moment_work():
            while not stop.is_set():
                try:
                    if not getattr(settings,"moment_scheduler_external",False):
                        app.state.moments.schedule()
                    app.state.moments.score_one()
                    if (not getattr(settings,"moment_windows_v03",False)
                            or getattr(settings,"moment_image_generation_enabled",False)):
                        app.state.moments.run_one()
                except Exception:
                    logger.exception("Moment worker tick failed")
                stop.wait(20)
        moment_worker = (
            threading.Thread(target=moment_work, name="moment-generation", daemon=True)
            if getattr(settings,"moment_workers_enabled",True) else None
        )
        worker.start()
        if moment_worker:
            moment_worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=40)
            if moment_worker:
                moment_worker.join(timeout=5)
            app.state.memory.graph.close()

    app = FastAPI(title="Life Companion Core", version="0.1.0", lifespan=lifespan)
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
            if (body.timezone is not None
                    and getattr(request.app.state.settings,"moment_windows_v03",False)
                    and updated["memory_consent"]):
                moment_config = request.app.state.moments.config(life_id)
                if moment_config["enabled"] and moment_config["timezone"] != body.timezone:
                    values = {
                        key:value for key,value in moment_config.items()
                        if key in MomentSettings.model_fields
                    }
                    request.app.state.moments.configure(
                        updated, MomentSettings(**{**values,"timezone":body.timezone})
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
            if body.memory_consent is False or (
                    body.image_consent is False
                    and not getattr(request.app.state.settings,"moment_windows_v03",False)):
                request.app.state.moments.revoke_owner(life_id)
            if (body.image_consent is False
                    and getattr(request.app.state.settings,"moment_windows_v03",False)):
                request.app.state.moments.clear_images(life_id)
            return {
                "memory_consent": bool(updated["memory_consent"]),
                "image_consent": bool(updated["image_consent"]),
                "timezone": request.app.state.memory.timezone(life_id),
                "updated_at": updated["updated_at"],
                **scopes,
            }

    @app.post("/internal/v1/users/bootstrap", dependencies=[Depends(require_internal)])
    def bootstrap_user(body: BootstrapUserRequest, request: Request):
        return request.app.state.store.bootstrap_user(
            librechat_user_id=body.librechat_user_id,
            memos_user_id=body.memos_user_id,
            memos_username=body.memos_username,
            display_name=body.display_name,
            memory_consent=body.memory_consent,
            image_consent=body.image_consent,
        )

    @app.post("/internal/v1/reminders/reconcile", dependencies=[Depends(require_internal)])
    def reconcile_reminders(request: Request):
        users, delivered = request.app.state.reminders.reconcile_all()
        return {"status": "reconciled", "users": users,
                "notifications_accepted": delivered}

    @app.post("/internal/v1/moments/settle", dependencies=[Depends(require_internal)])
    def settle_moment_intents(request: Request):
        request.app.state.moments.schedule()
        return {"status": "settlement_intents_recorded", "mode": "PERSISTENT_ONLY"}

    def process_event(
        *,
        user: dict[str, Any],
        text: str,
        source_type: str,
        source_message_ids: list[str],
        conversation_id: str | None,
        occurred_at: datetime,
        use_llm: bool = False,
    ) -> dict[str, Any]:
        settings = app.state.settings
        memory = app.state.memory
        user = app.state.store.get_user(user["life_user_id"])
        previous = app.state.store.get_ingest_attempt(user["life_user_id"], source_message_ids[0])
        if previous:
            if previous["event_id"]:
                event = app.state.store.get_event(previous["event_id"], user["life_user_id"])
                if event and event["status"] == "failed":
                    return publish_event(event)
                return {"accepted": bool(event and event["status"] != "withdrawn"),
                        "event": public_event(event) if event else None}
            item = memory.from_source(user["life_user_id"], source_message_ids[0])
            return {"accepted": bool(item and item["state"] == "active"), "memory": item,
                    "reason": previous["reason"] if item else "MEMORY_SOURCE_UNAVAILABLE"}
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
        candidate, reason = memory.classify(
            text, occurred_at, use_llm=use_llm, user_id=user["life_user_id"]
        )
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
                source_message_id=source_message_ids[0],
                status="conflict" if item.get("conflict") else "fact",
                reason="FACT_CONFLICT" if item.get("conflict") else candidate.candidate_type)
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
        event = app.state.store.create_event(
            user_id=user["life_user_id"],
            source_type=source_type,
            source_message_ids=source_message_ids,
            conversation_id=conversation_id,
            occurred_at=(result.occurred_at or occurred_at).isoformat(),
            title=result.title or candidate.canonical_text[:28],
            summary=candidate.canonical_text,
            confidence=candidate.confidence,
            consent_state="granted" if consent else "pending",
            status="pending_consent" if not consent else "pending",
            idempotency_key=f"{user['life_user_id']}:{source_type}:{source_message_ids[0]}",
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

        previous = store.get_ingest_attempt(user["life_user_id"], body.source_message_id)
        if previous:
            if previous["event_id"]:
                event = store.get_event(previous["event_id"], user["life_user_id"])
                if event is None or event["status"] == "withdrawn":
                    return {"accepted":False,"reason":"MEMORY_WITHDRAWN"}
                if event["status"] == "failed":
                    return publish_event(event)
                return {"accepted": True, "event": public_event(event)}
            item = request.app.state.memory.from_source(user["life_user_id"], body.source_message_id)
            return {"accepted": bool(item and item["state"] == "active"),
                    "memory": item, "reason": previous["reason"] if item else "MEMORY_SOURCE_UNAVAILABLE",
                    "source_message_ids": [body.source_message_id]}
        with request.app.state.memory.lock:
            return process_event(
                user=user, text=body.text, source_type="chat",
                source_message_ids=[body.source_message_id],
                conversation_id=body.conversation_id, occurred_at=body.occurred_at,
            )

    @app.post("/internal/v1/events/enqueue", dependencies=[Depends(require_internal)])
    def enqueue(body: IngestRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            raise HTTPException(status_code=403, detail={"code":"USER_NOT_MAPPED"})
        return request.app.state.memory.enqueue(user, body.model_dump(mode="json"))

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

    @app.post("/internal/v1/knowledge/recall", dependencies=[Depends(require_internal)])
    def internal_recall(body: RecallRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if not user:
            return {"items": []}
        items = request.app.state.memory.recall(user["life_user_id"], body.query)
        if body.conversation_id and body.source_message_id:
            with request.app.state.store.connect() as db:
                for item in items:
                    db.execute("INSERT OR IGNORE INTO memory_recall_hits VALUES (?,?,?,?,?)",
                        (user["life_user_id"],body.conversation_id,body.source_message_id,item["memory_id"],
                         datetime.now().astimezone().isoformat()))
        result = [{"text": i["canonical_text"], "valid_from": i["valid_from"],
                   "kind": i["kind"], "url": f"/knowledge/{i['memory_id']}"} for i in items]
        if request.app.state.memory.permissions(user["life_user_id"])["recall_consent"] and re.search(r"提醒|带什么|带哪些", body.query):
            for reminder in request.app.state.store.list_reminders(user["life_user_id"])[:40]:
                if SENSITIVE.search(reminder["title"]) and not request.app.state.memory.permissions(user["life_user_id"])["sensitive_consent"]:
                    continue
                if not re.search(r"带|提醒", body.query) or not re.search(r"带|盘|伞", reminder["title"]):
                    continue
                result.append({"text": reminder["title"], "status": reminder["status"],
                               "kind": "reminder", "url": f"/reminders/{reminder['reminder_id']}"})
        return {"items": result}

    @app.get("/api/v1/knowledge")
    def knowledge(request: Request, identity=Depends(current_identity)):
        return {"items":request.app.state.memory.list_items(identity[0])}

    @app.get("/api/v1/knowledge/recall")
    def recall(request: Request, q: str = Query(max_length=4000), identity=Depends(current_identity)):
        return {"items":request.app.state.memory.recall(identity[0], q)}

    @app.get("/api/v1/knowledge/{memory_id}")
    def knowledge_detail(memory_id: str, request: Request, identity=Depends(current_identity)):
        item = request.app.state.memory.detail(identity[0], memory_id)
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

    def read_memory(event: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        try:
            memo = memos_for(user).get_private_memo(event["memo_ref"], user["memos_user_id"])
        except MemosError as exc:
            raise HTTPException(status_code=502, detail={"code": "MEMOS_READ_FAILED"}) from exc
        return {
            **public_event(event),
            "content": memo["content"],
            "tags": memo.get("tags", []),
            "event_type": "life_event",
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
        timezone = ZoneInfo(request.app.state.settings.timezone)
        events = [
            event for event in events
            if (not needle or needle in f"{event['title']} {event['summary']}".casefold())
            and (
                on_date is None
                or datetime.fromisoformat(event["occurred_at"]).astimezone(timezone).date() == on_date
            )
        ]
        events.sort(key=lambda event: datetime.fromisoformat(event["occurred_at"]), reverse=order == "desc")
        start = (page - 1) * page_size
        with ThreadPoolExecutor(max_workers=6) as executor:
            memories = list(executor.map(lambda event: read_memory(event, user), events[start:start + page_size]))
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
        return {"memory": read_memory(event, user)}

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
            if str(exc) in (
                "MEMORY_CONSENT_REQUIRED", "MEMORY_AND_IMAGE_CONSENT_REQUIRED"
            ):
                raise HTTPException(
                    403,detail={"code":str(exc)}
                ) from exc
            raise HTTPException(422,detail={"code":str(exc)}) from exc

    @app.get("/api/v1/tools")
    def tool_catalog(request: Request, identity=Depends(current_identity)):
        return {"tools":request.app.state.tools.catalog()}

    @app.post("/internal/v1/tools/chat", dependencies=[Depends(require_internal)])
    def chat_tool(body: ReminderChatRequest, request: Request):
        user = request.app.state.store.get_user_by_librechat_id(body.source_user_id)
        if user is None:
            user = request.app.state.store.ensure_reminder_user(body.source_user_id)
        try:
            return request.app.state.tool_chat.execute(
                user["life_user_id"], body.source_message_id, body.text, body.conversation_id)
        except ValueError:
            raise HTTPException(409, detail={"code": "TOOL_CHAT_CONFLICT"}) from None

    @app.get("/api/v1/tool-chats")
    def list_tool_chats(request: Request, conversation_id: str = Query(min_length=1, max_length=200),
                        identity=Depends(current_identity)):
        return {"interactions": request.app.state.tool_chat.list(identity[0], conversation_id)}

    @app.post("/api/v1/tool-chats/{interaction_id}/select")
    def select_tool_chat(interaction_id: str, body: ToolChoice, request: Request,
                         identity=Depends(current_identity)):
        try:
            return request.app.state.tool_chat.select(identity[0], interaction_id, body)
        except LookupError:
            raise HTTPException(404, detail={"code": "TOOL_CHAT_NOT_FOUND"}) from None
        except ValueError as exc:
            code = "INVALID_TOOL_CHOICE" if str(exc) == "INVALID_TOOL_CHOICE" else "TOOL_CHAT_CONFLICT"
            raise HTTPException(422 if code == "INVALID_TOOL_CHOICE" else 409, detail={"code": code}) from None

    @app.delete("/api/v1/tool-chats/{interaction_id}")
    def delete_tool_chat(interaction_id: str, request: Request, identity=Depends(current_identity)):
        if not request.app.state.tool_chat.delete(identity[0], interaction_id):
            raise HTTPException(404, detail={"code": "TOOL_CHAT_NOT_FOUND"})
        return {"status": "cancelled"}

    @app.post("/api/v1/tools/execute")
    def execute_tool(body: ToolRequest, request: Request, identity=Depends(current_identity)):
        try:
            return request.app.state.tools.execute(identity[0],body)
        except ValidationError:
            raise HTTPException(422,detail={"code":"INVALID_TOOL_PARAMETERS"}) from None
        except ValueError as exc:
            code = str(exc)
            allowed = {"TOOL_IDEMPOTENCY_CONFLICT","TOOL_FORECAST_DATE_OUTSIDE_HORIZON","TOOL_ARRIVAL_MUST_BE_FUTURE"}
            raise HTTPException(409 if code == "TOOL_IDEMPOTENCY_CONFLICT" else 422,
                                detail={"code":code if code in allowed else "INVALID_TOOL_PARAMETERS"}) from None

    @app.get("/api/v1/tool-executions")
    def list_tool_executions(request: Request, identity=Depends(current_identity),
                             conversation_id: str | None = None, source_message_id: str | None = None):
        return {"executions":request.app.state.tools.list(identity[0],conversation_id,source_message_id)}

    @app.get("/api/v1/tool-executions/{execution_id}")
    def tool_execution_detail(execution_id: str, request: Request, identity=Depends(current_identity)):
        result = request.app.state.tools.detail(identity[0],execution_id)
        if result is None:
            raise HTTPException(404,detail={"code":"TOOL_EXECUTION_NOT_FOUND"})
        return result

    @app.delete("/api/v1/tool-executions/{execution_id}")
    def delete_tool_execution(execution_id: str, request: Request, identity=Depends(current_identity)):
        if not request.app.state.tools.delete(identity[0],execution_id):
            raise HTTPException(404,detail={"code":"TOOL_EXECUTION_NOT_FOUND"})
        return {"status":"deleted"}

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
            code = str(exc)
            if code in {"IMAGE_RESULT_RECONCILIATION_REQUIRED", "IMAGE_RETRY_UNSAFE"}:
                raise HTTPException(409,detail={"code":code}) from exc
            raise HTTPException(403,detail={"code":"CONSENT_OR_SOURCE_REVOKED"}) from exc

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
            return drafts.select(identity[0], draft_id, body.revision,
                                 body.fields.model_dump(mode="json", exclude_unset=True))
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

