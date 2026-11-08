"""Isolated cross-window memory acceptance: save, recall, model-input evidence.

Runs the real FastAPI app over TestClient with a synthetic in-memory DB so no
real user data is touched. No Memos/network: publication is monkeypatched.
"""
import base64
import hashlib
import hmac
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/life-core"))

from fastapi.testclient import TestClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

HEADERS = {"X-Internal-Token": "test-internal"}
NOW = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()


def token_for(user_id):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"id": user_id, "exp": int(time.time()) + 3600}
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")
    parts = [encode(header), encode(payload)]
    signature = hmac.new(b"test-jwt", b".".join(parts), hashlib.sha256).digest()
    parts.append(base64.urlsafe_b64encode(signature).rstrip(b"="))
    return b".".join(parts).decode()


def ingest(client, text, message, conversation):
    return client.post("/internal/v1/events/ingest", headers=HEADERS, json={
        "source_user_id": "e2e-user", "source_message_id": message,
        "conversation_id": conversation, "text": text, "occurred_at": NOW,
    })


def recall(client, query, conversation="query-chat", message="q1", recent=None):
    return client.post("/internal/v1/knowledge/recall", headers=HEADERS, json={
        "source_user_id": "e2e-user", "query": query, "conversation_id": conversation,
        "source_message_id": message, "recent_messages": recent or [],
    }).json()


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            database_path=Path(tmp) / "e2e.sqlite",
            internal_token="test-internal",
            jwt_secret="test-jwt",
            jwt_refresh_secret="test-refresh",
            memos_base_url="http://memos.invalid",
            memos_api_token="test-memos",
            timezone="Asia/Hong_Kong",
            allowed_origins=("http://localhost:3001",),
        )
        app = create_app(settings)
        client = TestClient(app)
        with client:
            # Bootstrap and grant consent.
            assert client.post("/internal/v1/users/bootstrap", headers=HEADERS, json={
                "librechat_user_id": "e2e-user", "memos_user_id": "users/e2e",
                "display_name": "E2E Synthetic", "memory_consent": True,
            }).status_code == 200
            client.patch("/api/v1/me/settings",
                         headers={"Authorization": f"Bearer {token_for('e2e-user')}"},
                         json={"recall_consent": True, "sensitive_consent": True})
            app.state.memos.create_private_memo = lambda event: "memos/" + event["event_id"]

            # Save a stable preference in window A.
            r = ingest(client, "我最喜欢喝龙井茶", "m-a", "chat-a").json()
            if not r["accepted"]:
                failures.append("save preference in chat-a rejected: %r" % r)

            # Save an occurred event in window B.
            r = ingest(client, "今天下午在公园散步，看见银杏树，感觉放松", "m-b", "chat-b").json()
            if not r["accepted"]:
                failures.append("save event in chat-b rejected: %r" % r)

            # Cross-window recall of the event by entity, from a different window.
            got = recall(client, "公园散步", conversation="chat-c")
            if not any("公园" in i["text"] for i in got["items"]):
                failures.append("cross-window event recall failed: %r" % got)

            # Cross-window recall of the preference by paraphrase (background profile).
            got = recall(client, "我以前说过我喜欢喝什么？", conversation="chat-c")
            if not any("龙井" in i["text"] for i in got["profile"]):
                failures.append("paraphrased preference profile missing: %r" % got)

            # Anaphora to a nonexistent project must not invent an event.
            got = recall(client, "那个项目后来怎么样", conversation="chat-d",
                         recent=[{"text": "星河项目组", "conversation_id": "chat-d"}])
            if got["items"]:
                failures.append("anaphora invented a project event: %r" % got["items"])
            if got["retrieval"].get("context_source") != "recent_users":
                failures.append("anaphora did not resolve via recent users: %r" % got["retrieval"])

            # Telemetry records a delivery stage for injected evidence (model input).
            client.post("/internal/v1/memory/telemetry", headers=HEADERS, json={
                "source_user_id": "e2e-user", "source_message_id": "q1",
                "conversation_id": "chat-b", "stage": "delivery", "status": "injected",
                "item_count": 1, "elapsed_ms": 12})
            status = client.get("/api/v1/memory-status",
                                headers={"Authorization": f"Bearer {token_for('e2e-user')}"}).json()
            stages = {(t["stage"], t["status"]) for t in status["traces"]}
            if ("delivery", "injected") not in stages:
                failures.append("delivery telemetry missing: %r" % stages)

    if failures:
        print("E2E_FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("E2E_PASS cross-window save, paraphrase recall, anaphora, and delivery telemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
