"""Source lifecycle tests use only synthetic users and pytest temporary databases."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.memory import Candidate, MemoryService
from app.store import Store


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "sources.sqlite")
    store.initialize()
    memory = MemoryService(store, SimpleNamespace(timezone="Asia/Shanghai"))
    memory.initialize()
    users = [store.bootstrap_user(librechat_user_id=name, memos_user_id="synthetic",
        memos_username=None, display_name=name, memory_consent=True) for name in ("alice", "bob")]
    for user in users:
        memory.set_permissions(user["life_user_id"], {"recall_consent": True})
    return memory, *users


def body(message="m1", text="我平常喜欢龙井茶", day="02"):
    return {"source_message_id": message, "text": text, "conversation_id": "synthetic-chat",
            "occurred_at": f"2020-11-{day}T10:00:00+08:00"}


def save(memory, user, source, key="fact:drink_preference", value="龙井茶"):
    candidate = Candidate(candidate_type="stable_fact", canonical_text=source["text"],
        evidence_quote=source["text"], occurred_state="uncertain", fact_key="drink_preference",
        value=value, confidence=0.9, sensitivity="ordinary")
    return memory.save(user["life_user_id"], candidate, key, source["source_message_id"],
        source["conversation_id"], source["text"], datetime.fromisoformat(source["occurred_at"]))


def vectors(memory, user, *ids):
    with memory.store.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS memory_vectors (
            user_id TEXT,memory_id TEXT,model TEXT,content_hash TEXT,dimension INTEGER,vector TEXT,
            PRIMARY KEY(user_id,memory_id,model))""")
        db.executemany("INSERT INTO memory_vectors VALUES (?,?,'synthetic','hash',2,'[1,0]')",
                       [(user["life_user_id"], item_id) for item_id in ids])


def test_record_is_idempotent_and_conflicting_identity_never_overwrites(setup):
    memory, alice, _ = setup
    owner = alice["life_user_id"]
    first = memory.sources.record(alice, body())
    again = memory.sources.record(alice, body(day="03"))
    assert first["accepted"] and first["source_id"].startswith("source_")
    assert again == {"accepted": True, "status": "duplicate", "source_id": first["source_id"]}
    with pytest.raises(ValueError, match="SOURCE_MESSAGE_CONFLICT"):
        memory.sources.record(alice, body(text="我平常喜欢红茶"))
    item, = memory.sources.items(owner)
    assert item["canonical_text"] == body()["text"]
    assert item["valid_from"] == body()["occurred_at"]
    assert item["recorded_at"] != item["captured_at"]
    assert item["kind"] == "user_message" and item["value"] == ""
    assert item["memory_id"] == item["source_id"]
    assert memory.sources.detail(owner, first["source_id"])["source_message_id"] == "m1"


def test_unauthorized_and_forget_requests_do_not_store_text_or_jobs(setup):
    memory, alice, _ = setup
    alice = {**alice, "memory_consent": False}
    assert memory.sources.record(alice, body())["status"] == "permission_denied"
    assert memory.enqueue(alice, body())["accepted"] is False
    assert memory.sources.record({**alice, "memory_consent": True},
        body(text="不要记这句话"))["status"] == "excluded"
    with memory.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM memory_jobs").fetchone()[0] == 0


def test_same_text_on_different_days_is_retained_without_age_cutoff(setup):
    memory, alice, _ = setup
    first = memory.sources.record(alice, body())
    second = memory.sources.record(alice, body("m2", day="03"))
    assert first["source_id"] != second["source_id"]
    items = memory.sources.items(alice["life_user_id"])
    assert len(items) == 2
    assert items[0]["canonical_text"] == items[1]["canonical_text"]
    assert items[0]["recorded_at"] != items[1]["recorded_at"]


def test_queue_success_clears_payload_and_preserves_source_with_no_candidates(setup):
    memory, alice, _ = setup
    source = body(text="你觉得秋天的树叶是什么颜色？")
    memory.enqueue(alice, source)
    assert memory.run_one(lambda **_kwargs: {"accepted": False})
    with memory.store.connect() as db:
        job = db.execute("SELECT * FROM memory_jobs").fetchone()
    assert job["status"] == "succeeded" and job["payload"] is None
    item, = memory.sources.items(alice["life_user_id"])
    assert item["canonical_text"] == source["text"]
    assert item["extraction_status"] == "no_memory"
    assert memory.list_items(alice["life_user_id"]) == []


def test_queue_success_records_extracted_and_preserves_precise_processor_status(setup):
    memory, alice, _ = setup
    source = body()
    memory.enqueue(alice, source)
    assert memory.run_one(lambda **_kwargs: save(memory, alice, source))
    assert memory.sources.items(alice["life_user_id"])[0]["extraction_status"] == "extracted"
    other = body("m2", "合成的普通问句")
    memory.enqueue(alice, other)
    assert memory.run_one(lambda **_kwargs: memory.sources.set_status(alice["life_user_id"], "m2", "no_memory"))
    assert memory.sources.items(alice["life_user_id"])[1]["extraction_status"] == "no_memory"


def test_queue_failure_is_visible_after_retries_clear_payload(setup):
    memory, alice, _ = setup
    memory.enqueue(alice, body())
    def fail(**_kwargs):
        raise RuntimeError("synthetic provider failure")
    for _ in range(3):
        with memory.store.connect() as db:
            db.execute("UPDATE memory_jobs SET available_at='2000-01-01T00:00:00+00:00'")
        assert memory.run_one(fail)
        assert memory.sources.coverage(alice["life_user_id"])["extraction_status"] == {"failed": 1}
    with memory.store.connect() as db:
        job = db.execute("SELECT * FROM memory_jobs").fetchone()
    assert job["status"] == "failed" and job["payload"] is None
    assert memory.sources.items(alice["life_user_id"])[0]["canonical_text"] == body()["text"]


def test_queue_expiry_does_not_expire_quotation(setup):
    memory, alice, _ = setup
    memory.enqueue(alice, body())
    with memory.store.connect() as db:
        db.execute("UPDATE memory_jobs SET created_at='2000-01-01T00:00:00+00:00'")
    assert not memory.run_one(lambda **_kwargs: pytest.fail("expired job was processed"))
    item, = memory.sources.items(alice["life_user_id"])
    assert item["extraction_status"] == "expired"
    assert item["canonical_text"] == body()["text"]
    with memory.store.connect() as db:
        assert db.execute("SELECT payload FROM memory_jobs").fetchone()[0] is None


def test_sensitive_consent_and_recall_permission_apply_to_all_reads(setup):
    memory, alice, bob = setup
    owner = alice["life_user_id"]
    memory.set_permissions(owner, {"sensitive_consent": False})
    source = body(text="今天去医院做了检查")
    assert memory.sources.record(alice, source)["status"] == "permission_denied"
    memory.set_permissions(owner, {"sensitive_consent": True})
    first = memory.sources.record(alice, source)
    assert memory.sources.detail(owner, first["source_id"])["sensitivity"] == "sensitive"
    assert memory.sources.items(bob["life_user_id"]) == []
    assert memory.sources.detail(bob["life_user_id"], first["source_id"]) is None
    memory.set_permissions(owner, {"sensitive_consent": False})
    assert memory.sources.items(owner) == []
    assert memory.sources.detail(owner, first["source_id"]) is None
    assert memory.sources.coverage(owner)["total"] == 0
    memory.set_permissions(owner, {"recall_consent": False})
    assert memory.sources.items(owner) == []
    assert memory.sources.coverage(owner) == {"status": "permission_denied"}


def test_coverage_contains_only_counts_and_status_without_historical_completeness_claim(setup):
    memory, alice, _ = setup
    memory.sources.record(alice, body())
    memory.sources.set_status(alice["life_user_id"], "m1", "failed")
    coverage = memory.sources.coverage(alice["life_user_id"])
    assert coverage == {"status": "available", "total": 1, "states": {"active": 1},
                        "extraction_status": {"failed": 1}, "historical_coverage": "not_verified"}
    assert body()["text"] not in str(coverage)
    with pytest.raises(ValueError, match="INVALID_SOURCE_STATUS"):
        memory.sources.set_status(alice["life_user_id"], "m1", "arbitrary")


@pytest.mark.parametrize("state", ["withdrawn", "superseded"])
def test_item_invalidation_tombstones_all_linked_sources_and_vectors_only(setup, state):
    memory, alice, _ = setup
    owner = alice["life_user_id"]
    linked = [body(), body("m2", "我一直喜欢龙井茶", "03")]
    source_ids = [memory.sources.record(alice, source)["source_id"] for source in linked]
    unrelated = memory.sources.record(alice, body("unrelated", "我喜欢摄影"))["source_id"]
    item = save(memory, alice, linked[0])
    save(memory, alice, linked[1])
    vectors(memory, alice, item["memory_id"], *source_ids, unrelated)
    memory.invalidate(owner, item["memory_id"], state)
    assert [i["source_id"] for i in memory.sources.items(owner)] == [unrelated]
    with memory.store.connect() as db:
        rows = db.execute("SELECT text,state,extraction_status FROM memory_sources WHERE message_id IN ('m1','m2')").fetchall()
        assert all(r["text"] is None and r["state"] == state and r["extraction_status"] == "revoked" for r in rows)
        assert [r[0] for r in db.execute("SELECT memory_id FROM memory_vectors")] == [unrelated]
    assert not memory.sources.set_status(owner, "m1", "extracted")
    assert memory.sources.record(alice, linked[0])["status"] == "revoked"
    assert memory.sources.record(alice, {**linked[0], "source_message_id": "new-id"})["status"] == "revoked"
    assert memory.sources.detail(owner, source_ids[0]) is None


def test_source_withdrawal_invalidates_all_linked_items_and_scrubs_pending_payload(setup):
    memory, alice, bob = setup
    owner = alice["life_user_id"]
    source = body(text="我喜欢茶也喜欢摄影")
    memory.enqueue(alice, source)
    source_id = memory.sources.items(owner)[0]["source_id"]
    first = save(memory, alice, source)
    second = save(memory, alice, source, key="fact:interest:photo", value="摄影")
    vectors(memory, alice, source_id, first["memory_id"], second["memory_id"])
    assert memory.sources.withdraw(bob["life_user_id"], source_id) is None
    assert len(memory.list_items(owner)) == 2
    result = memory.sources.withdraw(owner, source_id)
    assert result["invalidated_count"] == 2
    assert memory.list_items(owner) == []
    assert memory.sources.items(owner) == []
    assert memory.sources.withdraw(owner, source_id)["invalidated_count"] == 0
    assert not memory.run_one(lambda **_kwargs: pytest.fail("revoked job was processed"))
    with memory.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM memory_evidence").fetchone()[0] == 0
        job = db.execute("SELECT status,payload FROM memory_jobs").fetchone()
        assert job["status"] == "revoked" and job["payload"] is None
    assert memory.enqueue(alice, {**source, "source_message_id": "replay"})["status"] == "revoked"
    assert memory.sources.record(bob, source)["accepted"]


def test_invalidation_and_source_tombstone_roll_back_together(setup, monkeypatch):
    memory, alice, _ = setup
    owner = alice["life_user_id"]
    source_id = memory.sources.record(alice, body())["source_id"]
    item = save(memory, alice, body())
    def fail(*_args):
        raise RuntimeError("synthetic vector deletion error")
    monkeypatch.setattr(memory.sources, "_delete_vectors", fail)
    with pytest.raises(RuntimeError):
        memory.invalidate(owner, item["memory_id"])
    assert memory.detail(owner, item["memory_id"])["state"] == "active"
    assert memory.sources.detail(owner, source_id)["canonical_text"] == body()["text"]
    assert len(memory.detail(owner, item["memory_id"])["sources"]) == 1


def test_record_failure_is_not_reported_as_queue_success(setup, monkeypatch):
    memory, alice, _ = setup
    def fail(*_args):
        raise RuntimeError("synthetic disk failure")
    monkeypatch.setattr(memory.sources, "record", fail)
    with pytest.raises(RuntimeError, match="synthetic disk failure"):
        memory.enqueue(alice, body())
    with memory.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_jobs").fetchone()[0] == 0
