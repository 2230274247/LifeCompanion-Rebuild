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


def token_for(user_id: str, **claims) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "id": user_id,
        "exp": int(time.time()) + 3600,
        **claims,
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
        assert event["idempotency_key"] == f"{event['user_id']}:chat:message-1"


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


def publish_test_memory(app, client, monkeypatch, user_id="lc-user-a", message_id="memory-1"):
    bootstrap(client, user_id, f"users/{user_id}")
    monkeypatch.setattr(app.state.memos, "create_private_memo", lambda event: f"memos/{event['event_id']}")
    response = client.post(
        "/internal/v1/events/ingest",
        headers={"X-Internal-Token": "test-internal"},
        json={
            "source_user_id": user_id,
            "source_message_id": message_id,
            "conversation_id": "owned-conversation",
            "text": "今天下午和朋友在公园散步，看见秋天的银杏树，感觉特别放松。",
            "occurred_at": "2026-11-02T15:00:00+08:00",
        },
    )
    assert response.status_code == 200
    return response.json()["event"]


def test_memories_read_real_memo_and_enforce_owner(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        event = publish_test_memory(app, client, monkeypatch)
        bootstrap(client, "lc-user-b", "users/b")
        reads = []

        def read_memo(ref, creator):
            reads.append((ref, creator))
            return {"content": "Memos 中修改后的真实内容", "tags": ["散步"]}

        monkeypatch.setattr(app.state.memos, "get_private_memo", read_memo)
        headers = {"Authorization": f"Bearer {token_for('lc-user-a')}"}
        result = client.get("/api/v1/memories?page_size=1&on_date=2026-11-02&q=公园", headers=headers)
        assert result.status_code == 200
        assert result.json()["memories"][0]["content"] == "Memos 中修改后的真实内容"
        assert result.json()["total"] == 1
        assert reads == [(event["memo_ref"], "users/lc-user-a")]
        assert client.get(f"/api/v1/memories/{event['event_id']}", headers=headers).status_code == 200
        other = {"Authorization": f"Bearer {token_for('lc-user-b')}"}
        assert client.get(f"/api/v1/memories/{event['event_id']}", headers=other).status_code == 404
        assert client.get("/api/v1/memories?user_id=lc-user-a", headers=other).json()["memories"] == []
        assert client.get("/api/v1/memories?on_date=2026-11-03", headers=headers).json()["total"] == 0
        assert client.get("/api/v1/memories?page=2&page_size=1", headers=headers).json()["memories"] == []
        assert client.get("/api/v1/memories?page_size=51", headers=headers).status_code == 422


def test_memories_upstream_failure_is_not_empty_success(monkeypatch, tmp_path):
    from app.memos import MemosError

    app, client = make_app(tmp_path)
    with client:
        publish_test_memory(app, client, monkeypatch)

        def fail_read(*_args):
            raise MemosError("sensitive upstream details")

        monkeypatch.setattr(app.state.memos, "get_private_memo", fail_read)
        response = client.get("/api/v1/memories", headers={"Authorization": f"Bearer {token_for('lc-user-a')}"})
        assert response.status_code == 502
        assert "sensitive" not in response.text


def test_memories_requires_access_token_not_cookie(tmp_path):
    _app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        assert client.get("/api/v1/memories").status_code == 401
        client.cookies.set("refreshToken", token_for("lc-user-a"))
        assert client.get("/api/v1/memories").status_code == 401
        for invalid in (
            "garbage",
            "W10.W10.AA",
            token_for("unmapped-user"),
            token_for("lc-user-a", exp=int(time.time()) - 1),
            token_for("lc-user-a", exp=None),
        ):
            result = client.get("/api/v1/memories", headers={"Authorization": f"Bearer {invalid}"})
            assert result.status_code in (401, 403)


def test_same_source_id_cannot_cross_user_boundary(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        first = publish_test_memory(app, client, monkeypatch, "lc-user-a", "shared-source-id")
        second = publish_test_memory(app, client, monkeypatch, "lc-user-b", "shared-source-id")
        assert first["event_id"] != second["event_id"]
        assert app.state.store.get_event(second["event_id"])["user_id"] == bootstrap(client, "lc-user-b", "users/lc-user-b")["life_user_id"]


def test_network_publish_failure_records_failed_status_and_can_retry(monkeypatch, tmp_path):
    import httpx

    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        body = {
            "source_user_id": "lc-user-a",
            "source_message_id": "network-failure",
            "text": "今天下午和朋友在公园散步，感觉特别放松。",
            "occurred_at": "2026-11-02T15:00:00+08:00",
        }
        def fail_create(_event):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(app.state.memos, "create_private_memo", fail_create)
        response = client.post("/internal/v1/events/ingest", headers={"X-Internal-Token": "test-internal"}, json=body)
        assert response.status_code == 502
        user = app.state.store.get_user_by_librechat_id("lc-user-a")
        event = app.state.store.list_events(user["life_user_id"])[0]
        assert event["status"] == "failed"
        monkeypatch.setattr(app.state.memos, "create_private_memo", lambda event: "memos/recovered")
        response = client.post("/internal/v1/events/ingest", headers={"X-Internal-Token": "test-internal"}, json=body)
        assert response.json()["event"]["status"] == "published"

