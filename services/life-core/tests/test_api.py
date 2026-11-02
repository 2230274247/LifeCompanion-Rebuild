import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def token_for(user_id: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "id": user_id,
        "exp": int(time.time()) + 3600,
    }
    encode = lambda value: base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).rstrip(b"=")
    parts = [encode(header), encode(payload)]
    signature = hmac.new(b"test-jwt", b".".join(parts), hashlib.sha256).digest()
    parts.append(base64.urlsafe_b64encode(signature).rstrip(b"="))
    return b".".join(parts).decode()


def make_app(tmp_path: Path, token: str = "test-memos") -> tuple:
    settings = Settings(
        database_path=tmp_path / "life.db",
        internal_token="test-internal",
        jwt_secret="test-jwt",
        jwt_refresh_secret="test-refresh",
        memos_base_url="http://memos.invalid",
        memos_api_token=token,
        timezone="Asia/Hong_Kong",
        allowed_origins=("http://localhost:3001",),
    )
    app = create_app(settings)
    client = TestClient(app)
    return app, client


def bootstrap(client: TestClient, user_id: str = "lc-user-a", memos_user: str = "users/a"):
    response = client.post(
        "/internal/v1/users/bootstrap",
        headers={"X-Internal-Token": "test-internal"},
        json={
            "librechat_user_id": user_id,
            "memos_user_id": memos_user,
            "memos_username": memos_user.split("/")[-1],
            "display_name": "Synthetic Tester",
            "memory_consent": True,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_ingest_is_idempotent(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)

        def fake_create(event):
            return f"memos/{event['event_id']}"

        monkeypatch.setattr(app.state.memos, "create_private_memo", fake_create)
        body = {
            "source_user_id": "lc-user-a",
            "source_message_id": "message-1",
            "conversation_id": "conversation-1",
            "text": "今天下午和朋友在公园散步，看见秋天的银杏树，感觉特别放松。",
            "occurred_at": "2026-11-02T15:00:00+08:00",
        }
        first = client.post(
            "/internal/v1/events/ingest",
            headers={"X-Internal-Token": "test-internal"},
            json=body,
        )
        second = client.post(
            "/internal/v1/events/ingest",
            headers={"X-Internal-Token": "test-internal"},
            json=body,
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["event"]["event_id"] == second.json()["event"]["event_id"]
        assert second.json()["event"]["memo_ref"].startswith("memos/")
        event = app.state.store.get_event(first.json()["event"]["event_id"])
        assert event["idempotency_key"] == "chat:message-1"


def test_user_isolation(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client, "lc-user-a", "users/a")
        bootstrap(client, "lc-user-b", "users/b")
        response = client.get(
            "/api/v1/events", headers={"Authorization": f"Bearer {token_for('lc-user-a')}"}
        )
        assert response.status_code == 200
        assert response.json() == {"events": []}
        forbidden = client.get(
            "/api/v1/events", headers={"Authorization": f"Bearer {token_for('lc-user-b')}"}
        )
        assert forbidden.status_code == 200
        assert forbidden.json() == {"events": []}


def test_internal_endpoint_rejects_bad_token(tmp_path):
    _app, client = make_app(tmp_path)
    with client:
        response = client.post(
            "/internal/v1/users/bootstrap",
            headers={"X-Internal-Token": "wrong"},
            json={"librechat_user_id": "x", "memos_user_id": "users/x"},
        )
        assert response.status_code == 401

