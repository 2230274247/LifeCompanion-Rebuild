from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import identity_from_request
from .config import Settings, load_settings
from .extraction import extract_event
from .memos import MemosClient, MemosError
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
    memory_consent: bool = False
    image_consent: bool = False


class ConsentRequest(BaseModel):
    memory_consent: bool | None = None
    image_consent: bool | None = None


class ManualExtractRequest(BaseModel):
    source_message_id: str
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime | None = None


class PublishRequest(BaseModel):
    event_id: str


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scheduled_at: datetime
    timezone: str = "Asia/Hong_Kong"
    delivery_channel: str = "in_app"


def current_identity(request: Request) -> tuple[str, str, dict[str, Any]]:
    librechat_user_id, _source = identity_from_request(request)
    user = request.app.state.store.get_user_by_librechat_id(librechat_user_id)
    if user is None:
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


def create_app(settings_override: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = settings_override or load_settings()
        store = Store(settings.database_path)
        store.initialize()
        app.state.settings = settings
        app.state.store = store
        app.state.memos = MemosClient(settings.memos_base_url, settings.memos_api_token)
        yield

    app = FastAPI(title="Life Companion Core", version="0.1.0", lifespan=lifespan)
    settings_for_cors = settings_override or load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings_for_cors.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
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
    def me(identity=Depends(current_identity)):
        _life_id, _source_id, user = identity
        return {
            "life_user_id": user["life_user_id"],
            "librechat_user_id": user["librechat_user_id"],
            "memos_user_id": user["memos_user_id"],
            "memos_username": user["memos_username"],
            "display_name": user["display_name"],
            "memory_consent": bool(user["memory_consent"]),
            "image_consent": bool(user["image_consent"]),
        }

    @app.patch("/api/v1/me/settings")
    def update_settings(body: ConsentRequest, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        updated = request.app.state.store.update_consent(
            life_id,
            memory_consent=body.memory_consent,
            image_consent=body.image_consent,
        )
        return {
            "memory_consent": bool(updated["memory_consent"]),
            "image_consent": bool(updated["image_consent"]),
            "updated_at": updated["updated_at"],
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

    def process_event(
        *,
        user: dict[str, Any],
        text: str,
        source_type: str,
        source_message_ids: list[str],
        conversation_id: str | None,
        occurred_at: datetime,
    ) -> dict[str, Any]:
        settings = app.state.settings
        result = extract_event(
            text,
            now=occurred_at,
            timezone=settings.timezone,
        )
        if not result.accepted:
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
            occurred_at=result.occurred_at.isoformat(),
            title=result.title or "生活片段",
            summary=result.summary or text[:500],
            confidence=result.confidence,
            consent_state="granted" if consent else "pending",
            status="pending_consent" if not consent else "pending",
            idempotency_key=f"{source_type}:{source_message_ids[0]}",
        )
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
            memo_ref = app.state.memos.create_private_memo(event)
        except MemosError as exc:
            app.state.store.set_event_status(
                event["event_id"],
                status="failed",
                error_message=str(exc)[:500],
                increment_attempts=True,
            )
            app.state.store.upsert_task_run(
                job_type="memo_publish",
                idempotency_key=job_key,
                owner_user_id=event["user_id"],
                status="failed",
                completed_at=datetime.now(ZoneInfo(app.state.settings.timezone)).isoformat(),
                last_error=str(exc)[:500],
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
                return {"accepted": True, "event": public_event(event)}
            return {
                "accepted": False,
                "reason": previous["reason"],
                "source_message_ids": [body.source_message_id],
            }
        return process_event(
            user=user,
            text=body.text,
            source_type="chat",
            source_message_ids=[body.source_message_id],
            conversation_id=body.conversation_id,
            occurred_at=body.occurred_at,
        )

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
        return process_event(
            user=user,
            text=body.text,
            source_type="manual",
            source_message_ids=[body.source_message_id],
            conversation_id=body.conversation_id,
            occurred_at=occurred_at,
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

    @app.get("/api/v1/memories")
    def list_memories(identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        events = request.app.state.store.list_events(life_id, published_only=True)
        return {"memories": [public_event(event) for event in events]}

    @app.post("/api/v1/reminders")
    def create_reminder(body: ReminderRequest, identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        reminder = request.app.state.store.create_reminder(
            owner_user_id=life_id,
            title=body.title,
            scheduled_at=body.scheduled_at.isoformat(),
            timezone=body.timezone,
            delivery_channel=body.delivery_channel,
        )
        return reminder

    @app.get("/api/v1/reminders")
    def list_reminders(identity=Depends(current_identity), request: Request = None):
        life_id, _source_id, _user = identity
        return {"reminders": request.app.state.store.list_reminders(life_id)}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("LIFE_HOST", "127.0.0.1"),
        port=int(os.getenv("LIFE_PORT", "8010")),
    )

