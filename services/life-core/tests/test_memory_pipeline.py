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


def test_graphiti_embedding_gate_is_explicit_and_fail_closed(tmp_path):
    import pytest
    from app.graphiti_provider import GraphitiUnavailable

    app, client = make_app(tmp_path)
    with client:
        provider = app.state.memory.graphiti
        assert provider.status.state == "BLOCKED_EMBEDDING"
        with pytest.raises(GraphitiUnavailable, match="BLOCKED_EMBEDDING"):
            provider.search(query="synthetic")


def test_langmem_fabricated_source_is_rejected(monkeypatch, tmp_path):
    import pytest
    from dataclasses import replace
    from datetime import datetime
    from types import SimpleNamespace
    from app.memory import Candidate

    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        class Model:
            def __init__(self, **_kwargs): pass
        class Manager:
            def invoke(self, _state, config=None):
                candidate = Candidate(
                    candidate_type="stable_fact", canonical_text="喜欢喝龙井茶",
                    evidence_quote="我喜欢喝咖啡", occurred_state="occurred",
                    experience_owner="self",
                    fact_key="drink_preference", value="咖啡", confidence=.9,
                    sensitivity="ordinary",
                )
                return [SimpleNamespace(content=candidate)]
        monkeypatch.setattr("langchain_openai.ChatOpenAI", Model)
        monkeypatch.setattr("langmem.create_memory_manager", lambda *_a, **_kw: Manager())
        with pytest.raises(ValueError, match="UNGROUNDED"):
            memory.classify("我平常喜欢龙井茶", datetime.fromisoformat("2026-11-02T10:00:00+08:00"), use_llm=True)
        assert memory.list_items("lc-user-a") == []


def test_langmem_context_excludes_other_owner_and_revoked_sensitive_memory(monkeypatch, tmp_path):
    from dataclasses import replace
    from datetime import UTC
    from app.memory import Candidate

    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        other = bootstrap(client, "lc-user-b", "users/b")["life_user_id"]
        memory = app.state.memory
        now = datetime.now(UTC)
        ordinary = Candidate(
            candidate_type="stable_fact", canonical_text="likes tea",
            evidence_quote="likes tea", occurred_state="occurred",
            experience_owner="self",
            fact_key="drink_preference", value="tea", confidence=.9, sensitivity="ordinary",
        )
        sensitive = Candidate(
            candidate_type="stable_fact", canonical_text="lives in City A",
            evidence_quote="lives in City A", occurred_state="occurred",
            experience_owner="self",
            fact_key="residence", value="City A", confidence=.9, sensitivity="sensitive",
        )
        allowed = memory.save(owner, ordinary, "fact:drink_preference", "a", "c", "likes tea", now)
        memory.save(owner, sensitive, "fact:residence", "s", "c", "lives in City A", now)
        memory.save(other, ordinary, "fact:drink_preference", "b", "c", "likes tea", now)
        memory.set_permissions(owner, {"sensitive_consent": True})
        memory.set_permissions(owner, {"sensitive_consent": False})
        seen = []

        class Model:
            def __init__(self, **_kwargs):
                pass

        class Manager:
            def invoke(self, state, config=None):
                seen.extend(identifier for identifier, _candidate in state["existing"])
                return []

        monkeypatch.setattr("langchain_openai.ChatOpenAI", Model)
        monkeypatch.setattr("langmem.create_memory_manager", lambda *_a, **_kw: Manager())
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        memory.classify("I enjoy tea", now, use_llm=True, user_id=owner)
        assert seen == [allowed["memory_id"]]


def test_provider_quota_stops_requests_and_survives_restart(monkeypatch, tmp_path):
    from dataclasses import replace
    import pytest
    from app.memory import MemoryProviderQuotaError, MemoryService

    attempts = []

    class QuotaError(Exception):
        status_code = 429

    class Model:
        def __init__(self, **_kwargs):
            attempts.append(1)
            raise QuotaError("insufficient_quota")

    monkeypatch.setattr("langchain_openai.ChatOpenAI", Model)
    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic")
        for _ in range(2):
            with pytest.raises(MemoryProviderQuotaError):
                memory._llm("synthetic")
        assert len(attempts) == 1
        restarted = MemoryService(memory.store, memory.settings)
        restarted.initialize()
        with pytest.raises(MemoryProviderQuotaError):
            restarted._llm("synthetic")
        assert len(attempts) == 1
        restarted.graph.close()


def test_model_call_audit_records_tokens_and_enforces_cap(tmp_path):
    import pytest
    from types import SimpleNamespace
    from app.memory_model_audit import MemoryModelAudit

    app, client = make_app(tmp_path)
    with client:
        audit = MemoryModelAudit(app.state.store, "synthetic", "synthetic")
        for number in range(3):
            audit.on_chat_model_start({}, [], run_id=f"call-{number}")
        with pytest.raises(ValueError, match="CALL_LIMIT"):
            audit.on_chat_model_start({}, [], run_id="over-limit")
        audit.on_llm_end(SimpleNamespace(llm_output={"token_usage":{
            "prompt_tokens":12,"completion_tokens":3}}, generations=[[
                SimpleNamespace(text='{"candidate_type":"life_event"}', message=None)
            ]]),run_id="call-0")
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM memory_model_calls WHERE call_id='call-0'").fetchone()
            count = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert row["input_tokens"] == 12 and row["output_tokens"] == 3
        assert row["raw_output"] == '{"candidate_type":"life_event"}'
        assert count == 3


def test_model_call_audit_records_structured_tool_call_output(tmp_path):
    from types import SimpleNamespace
    from app.memory_model_audit import MemoryModelAudit

    app, client = make_app(tmp_path)
    with client:
        audit = MemoryModelAudit(app.state.store, "synthetic", "synthetic")
        audit.on_chat_model_start({}, [], run_id="tool-call")
        audit.on_llm_end(SimpleNamespace(
            llm_output={},
            generations=[[SimpleNamespace(
                text="",
                message=SimpleNamespace(
                    content="",
                    tool_calls=[{
                        "name": "Candidate",
                        "args": {"candidate_type": "life_event"},
                    }],
                    usage_metadata=None,
                ),
            )]],
        ), run_id="tool-call")
        with app.state.store.connect() as db:
            row = db.execute(
                "SELECT raw_output FROM memory_model_calls WHERE call_id='tool-call'"
            ).fetchone()
    recorded = __import__("json").loads(row["raw_output"])
    assert recorded["tool_calls"][0]["args"]["candidate_type"] == "life_event"


def test_database_request_budget_survives_new_callback_and_counts_failures(tmp_path):
    import pytest
    from app.memory_model_audit import MemoryModelAudit, MemoryModelBudgetError

    app, client = make_app(tmp_path)
    with client:
        for number in range(2):
            audit = MemoryModelAudit(app.state.store, "synthetic", "synthetic", request_budget=2)
            audit.on_chat_model_start({}, [], run_id=f"budget-{number}")
            audit.on_llm_error(ValueError("private input must not be logged"), run_id=f"budget-{number}")
        restarted = MemoryModelAudit(app.state.store, "synthetic", "synthetic", request_budget=2)
        with pytest.raises(MemoryModelBudgetError, match="REQUEST_BUDGET"):
            restarted.on_chat_model_start({}, [], run_id="must-not-send")
        with app.state.store.connect() as db:
            rows = db.execute("SELECT status,error_code FROM memory_model_calls").fetchall()
        assert len(rows) == 2
        assert all(row["status"] == "failed" and row["error_code"] == "ValueError:no_status" for row in rows)


def test_request_budget_reservation_is_atomic_for_concurrent_callbacks(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.memory_model_audit import MemoryModelAudit, MemoryModelBudgetError

    app, client = make_app(tmp_path)
    with client:
        def reserve(number):
            callback = MemoryModelAudit(app.state.store, "synthetic", "synthetic", request_budget=2)
            try:
                callback.on_chat_model_start({}, [], run_id=f"concurrent-{number}")
                return True
            except MemoryModelBudgetError:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(8)))
        assert sum(results) == 2
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0] == 2


def test_worker_preserves_budget_blocked_job_without_automatic_retry(tmp_path):
    from app.memory import MemoryProviderQuotaError

    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        def blocked(**kwargs):
            raise MemoryProviderQuotaError("MEMORY_MODEL_REQUEST_BUDGET")

        with app.state.memory.lock:
            app.state.memory.enqueue(user, {
                "text": "synthetic", "source_message_id": "budget-job",
                "occurred_at": "2026-11-04T00:00:00+08:00",
            })
            app.state.memory.run_one(blocked)
            with app.state.store.connect() as db:
                row = db.execute("SELECT * FROM memory_jobs WHERE job_id LIKE 'extract_%'").fetchone()
            assert row["status"] == "blocked_provider"
            assert row["last_error"] == "MEMORY_MODEL_REQUEST_BUDGET"
            assert row["payload"] is not None
            assert not app.state.memory.run_one(blocked)


def test_deepseek_insufficient_balance_402_blocks_without_retry(monkeypatch, tmp_path):
    from dataclasses import replace
    import pytest
    from app.memory import MemoryProviderQuotaError

    options = []

    class BalanceError(Exception):
        status_code = 402

    class Model:
        def __init__(self, **kwargs):
            options.append(kwargs)
            raise BalanceError("private upstream detail")

    monkeypatch.setattr("langchain_openai.ChatOpenAI", Model)
    app, client = make_app(tmp_path)
    with client:
        memory = app.state.memory
        memory.settings = replace(memory.settings, memory_llm_key="synthetic",
                                  memory_llm_provider="deepseek", memory_llm_max_tokens=1024)
        for _ in range(2):
            with pytest.raises(MemoryProviderQuotaError, match="QUOTA_EXHAUSTED"):
                memory._llm("synthetic")
        assert len(options) == 1
        assert options[0]["max_tokens"] == 1024
        assert options[0]["max_retries"] == 0
        assert options[0]["extra_body"] == {"thinking": {"type": "disabled"}}


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
