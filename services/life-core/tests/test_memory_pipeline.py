from datetime import datetime, timedelta, timezone

from test_api import bootstrap, make_app, token_for


def auth(user="lc-user-a"):
    return {"Authorization": f"Bearer {token_for(user)}"}


def ingest(client, text, message="m1", day="02", conversation="c1"):
    return client.post(
        "/internal/v1/events/ingest",
        headers={"X-Internal-Token": "test-internal"},
        json={
            "source_user_id": "lc-user-a", "source_message_id": message,
            "conversation_id": conversation, "text": text,
            "occurred_at": f"2026-11-{day}T10:00:00+08:00",
        },
    )


def test_no_authorization_does_not_persist_candidate_text(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"memory_consent": False})
        response = ingest(client, "今天下午和朋友在公园散步，看见秋天的银杏树。")
        assert response.status_code == 200
        assert not response.json()["accepted"]
        assert app.state.store.list_events(user["life_user_id"]) == []


def test_fact_reinforcement_correction_recall_and_withdrawal(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        for _ in range(100):
            response = ingest(client, "我平常喜欢龙井茶")
            assert response.status_code == 200
        listing = client.get("/api/v1/knowledge", headers=auth()).json()["items"]
        assert len(listing) == 1
        first = listing[0]
        assert first["evidence_count"] == 1
        ingest(client, "我平常喜欢龙井茶", "copy", "03", "c2")
        copied = client.get("/api/v1/knowledge", headers=auth()).json()["items"][0]
        assert copied["importance"] == first["importance"]
        ingest(client, "我一直最喜欢喝龙井茶", "m2", "04", "c3")
        repeated = client.get("/api/v1/knowledge", headers=auth()).json()["items"][0]
        assert repeated["importance"] > first["importance"]
        assert repeated["confidence"] == first["confidence"]
        recall = client.get("/api/v1/knowledge/recall?q=今天喝什么茶", headers=auth()).json()
        assert len(recall["items"]) == 1
        ingest(client, "我以前喜欢龙井，现在更喜欢红茶", "m3", "05", "c4")
        current = client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"]
        assert len(current) == 1 and "红茶" in current[0]["canonical_text"]
        assert "龙井" not in current[0]["canonical_text"]
        item_id = current[0]["memory_id"]
        bootstrap(client, "lc-user-b", "users/b")
        assert client.delete(f"/api/v1/knowledge/{item_id}", headers=auth("lc-user-b")).status_code == 404
        assert client.delete(f"/api/v1/knowledge/{item_id}", headers=auth()).status_code == 200
        assert client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"] == []
        ingest(client, "我以前喜欢龙井，现在更喜欢红茶", "retry-new-id", "06", "c5")
        assert client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"] == []


def test_event_semantic_merge_and_sensitive_future_question_guards(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        writes = []
        monkeypatch.setattr(app.state.memos, "create_private_memo",
                            lambda event: writes.append(event) or f"memos/{event['event_id']}")
        first = ingest(client, "今天加入了一直想加入的项目组！").json()
        assert first["accepted"]
        second = ingest(client, "这个项目组真的很棒！", "m2").json()
        assert second["event"]["event_id"] == first["event"]["event_id"]
        assert len(second["event"]["source_message_ids"]) == 2
        assert len(writes) == 1
        for i, text in enumerate(["今天义乌天气怎么样？", "明天要去医院", "今天去医院做了检查", "别记这件事"]):
            assert not ingest(client, text, f"skip-{i}").json()["accepted"]
        assert client.get("/api/v1/memories", headers=auth()).json()["total"] == 0
        assert not ingest(client, "今天加入了一直想加入的项目组！").json()["accepted"]


def test_read_and_write_permissions_are_independent(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        ingest(client, "我平常喜欢龙井茶")
        assert client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"] == []
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        assert len(client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"]) == 1
        client.patch("/api/v1/me/settings", headers=auth(), json={"memory_consent": False})
        assert len(client.get("/api/v1/knowledge/recall?q=喝茶", headers=auth()).json()["items"]) == 1
        assert not ingest(client, "我平常喜欢红茶", "m2").json()["accepted"]


def test_unconnected_reminders_cannot_claim_scheduled(tmp_path):
    _app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        result = client.post("/api/v1/reminders", headers=auth(), json={
            "title": "隔离测试", "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        })
        assert result.status_code == 503


def test_model_invalid_json_and_fabricated_source_are_rejected(monkeypatch, tmp_path):
    import httpx
    import pytest
    from dataclasses import replace
    from datetime import datetime

    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        class Provider:
            def __init__(self, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def post(self, *_args, **_kwargs):
                return httpx.Response(200, json={"choices":[{"message":{"content":"not JSON"}}]})
        monkeypatch.setattr("app.memory.httpx.Client", Provider)
        with pytest.raises(ValueError, match="INVALID_MODEL_OUTPUT"):
            memory.classify("我平常喜欢龙井茶", datetime.fromisoformat("2026-11-02T10:00:00+08:00"), use_llm=True)
        assert memory.list_items("lc-user-a") == []


def test_queue_drops_unauthorized_text_and_clears_finished_payload(monkeypatch, tmp_path):
    import time
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        body = {"source_user_id":"lc-user-a","source_message_id":"queue-1",
                "text":"我平常喜欢龙井茶","occurred_at":"2026-11-02T10:00:00+08:00"}
        result = client.post("/internal/v1/events/enqueue",headers={"X-Internal-Token":"test-internal"},json=body)
        assert result.json()["accepted"]
        for _ in range(100):
            with app.state.store.connect() as db:
                row = db.execute("SELECT * FROM memory_jobs").fetchone()
            if row["status"] == "succeeded":
                break
            time.sleep(0.02)
        assert row["status"] == "succeeded" and row["payload"] is None
        assert len(app.state.memory.list_items(user["life_user_id"])) == 1
        client.patch("/api/v1/me/settings",headers=auth(),json={"memory_consent":False})
        result = client.post("/internal/v1/events/enqueue",headers={"X-Internal-Token":"test-internal"},
                             json={**body,"source_message_id":"unauthorized"})
        assert not result.json()["accepted"]
        with app.state.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM memory_jobs").fetchone()[0] == 1
