"""Offline tests. Optional real-model check: LIFE_MEMORY_MODEL_CACHE=<local cache>."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import threading

import pytest

from app.embedding import LocalEmbedding, MODEL_NAME
from app.memory import MemoryService
from app.retrieval import MemoryRetriever
from app.store import Store


NOW = datetime(2026, 11, 8, 0, 30, tzinfo=UTC)


class Embedder:
    model_name = "test-chinese-semantic-v1"

    def __init__(self, vectors=None):
        self.vectors = vectors or {}
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        # Orthogonal fallback deliberately avoids accidental semantic matches.
        return [self.vectors.get(text, [0.0, 1.0, 0.0]) for text in texts]

    def query_embed(self, texts):
        self.calls.append(list(texts))
        return [self.vectors.get(text, [1.0, 0.0, 0.0]) for text in texts]


@pytest.fixture
def memory(tmp_path):
    store = Store(tmp_path / "memory.sqlite")
    store.initialize()
    settings = SimpleNamespace(timezone="Asia/Shanghai", memory_embedding_cache=tmp_path / "models")
    service = MemoryService(store, settings)
    service.initialize()
    service.set_permissions("alice", {"recall_consent": True})
    service.set_permissions("bob", {"recall_consent": True})
    return service


def put(memory, key, text, *, user="alice", kind="life_event", semantic_key=None,
        sensitivity="ordinary", state="active", importance=0.5, valid_from=None, value=""):
    stamp = (valid_from or NOW).isoformat()
    semantic_key = semantic_key or f"event:2026-11-08:{key}"
    with memory.store.connect() as db:
        db.execute("""INSERT INTO memory_items
            (memory_id,user_id,kind,semantic_key,canonical_text,value,state,importance,
             confidence,sensitivity,image_candidate,valid_from,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key,user,kind,semantic_key,text,value,state,importance,0.95,sensitivity,0,stamp,stamp,stamp))
    return next(item for item in memory.list_items(user) if item["memory_id"] == key) if state == "active" else None


def hit(memory, key, *, user="alice", conversation="c1", message="m1", stamp=NOW):
    with memory.store.connect() as db:
        db.execute("INSERT INTO memory_recall_hits VALUES (?,?,?,?,?)",
                   (user, conversation, message, key, stamp.isoformat()))


def retriever(memory, embedder=None, **kwargs):
    return MemoryRetriever(memory, embedder=embedder, now=lambda zone: NOW.astimezone(zone), **kwargs)


def ids(result, field="items"):
    return [item["memory_id"] for item in result[field]]


def test_permission_denied_before_read_or_embedding_and_clears_cache(memory, monkeypatch):
    put(memory, "a", "星河项目组举行例会")
    embedder = Embedder()
    retrieval = retriever(memory, embedder)
    retrieval.retrieve("alice", "星河项目组")
    assert retrieval._cache
    memory.set_permissions("alice", {"recall_consent": False})
    calls = len(embedder.calls)
    monkeypatch.setattr(memory, "list_items", lambda _: pytest.fail("must not read before consent"))
    result = retrieval.retrieve("alice", "星河项目组")
    assert result["status"] == "permission_denied"
    assert result["items"] == result["profile"] == []
    assert result["retrieval"]["semantic_status"] == "permission_denied"
    assert len(embedder.calls) == calls
    assert not retrieval._cache


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_does_not_return_profile_or_encode(memory, query):
    put(memory, "tea", "平常喜欢绿茶", kind="stable_fact", semantic_key="fact:drink_preference")
    embedder = Embedder()
    result = retriever(memory, embedder).retrieve("alice", query)
    assert result["items"] == result["profile"] == []
    assert result["retrieval"]["semantic_status"] == "empty_query"
    assert not embedder.calls


def test_sensitive_texts_filtered_before_encoding_and_sensitive_profile_needs_consent(memory):
    put(memory, "safe", "星河项目组举行例会")
    put(memory, "medical", "星河项目组讨论医疗诊断", sensitivity="sensitive")
    put(memory, "unknown", "项目进展未知", sensitivity="unknown")
    put(memory, "address", "我住在杭州", kind="stable_fact", semantic_key="fact:residence", sensitivity="sensitive")
    embedder = Embedder()
    retrieval = retriever(memory, embedder)
    result = retrieval.retrieve("alice", "星河项目组", recent_messages=[{"role":"user", "content":"刚才去医院了"}])
    assert ids(result) == ["safe"]
    assert not result["profile"]
    assert not any("医院" in text or "医疗" in text or "进展未知" in text or "杭州" in text
                   for call in embedder.calls for text in call)
    calls = len(embedder.calls)
    result = retrieval.retrieve("alice", "医疗诊断")
    assert result["retrieval"]["semantic_status"] == "sensitive_query_blocked"
    assert len(embedder.calls) == calls
    memory.set_permissions("alice", {"sensitive_consent": True})
    result = retrieval.retrieve("alice", "星河项目组")
    assert "medical" in ids(result)
    assert ids(result, "profile") == ["address"]
    memory.set_permissions("alice", {"sensitive_consent": False})
    retrieval.retrieve("alice", "星河项目组")
    assert all(key[1] not in {"medical", "unknown", "address"} for key in retrieval._cache)


def test_real_vector_contract_recalls_chinese_synonym_without_keyword_overlap(memory):
    text, query = "午间享用了丰盛的美食", "中午吃饭的经历"
    original = put(memory, "meal", text)
    put(memory, "noise", "修理自行车轮胎")
    embedder = Embedder({text:[0.99,0.01,0], query:[1,0,0]})
    retrieval = retriever(memory, embedder)
    assert retrieval._lexical(query, original) == 0
    result = retrieval.retrieve("alice", query)
    assert ids(result) == ["meal"]
    assert result["items"][0] == original
    assert result["retrieval"]["mode"] == "hybrid"
    assert result["retrieval"]["semantic_status"] == "ready"


def test_entity_exact_wins_and_other_named_entities_do_not_leak(memory):
    put(memory, "orion", "我加入了星河项目组")
    put(memory, "dipper", "北斗项目组举行了例会", importance=0.99)
    result = retriever(memory, Embedder()).retrieve("alice", "星河项目组怎么样")
    assert ids(result) == ["orion"]


def test_ordinary_query_does_not_include_old_context(memory):
    put(memory, "project", "星河项目组举行例会")
    put(memory, "walk", "我去公园散步")
    embedder = Embedder()
    result = retriever(memory, embedder).retrieve("alice", "公园散步", recent_messages=[
        {"role":"user", "content":"我加入了星河项目组"}])
    assert ids(result) == ["walk"]
    assert not result["retrieval"]["context_used"]
    assert embedder.calls[0] == ["公园散步"]


def test_anaphora_uses_relevant_user_context_among_last_four_user_turns(memory):
    put(memory, "orion", "星河项目组举行了例会")
    put(memory, "dipper", "北斗项目组举行了例会")
    recent = [
        {"role":"user", "content":"我加入了北斗项目组"},
        {"role":"assistant", "content":"你是指北斗项目组吗"},
        {"role":"user", "content":"昨天参加了星河项目组"},
        {"role":"user", "content":"我喝了茶"},
        {"role":"assistant", "content":"北斗项目组很棒"},
        {"role":"user", "content":"谢谢"},
    ]
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目后来怎么样", recent_messages=recent)
    assert ids(result) == ["orion"]
    assert result["retrieval"]["context_source"] == "recent_users"


def test_context_outside_four_user_turns_and_assistant_only_cannot_anchor(memory):
    put(memory, "orion", "星河项目组举行例会")
    recent = [{"role":"user", "content":"我加入星河项目组"}]
    recent += [{"role":"user", "content":"谢谢"} for _ in range(4)]
    recent += [{"role":"assistant", "content":"星河项目组"}]
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目呢", recent_messages=recent)
    assert not result["items"]
    assert result["retrieval"]["context_source"] == "ambiguous"


def test_no_cross_window_unique_project_guess(memory):
    put(memory, "only", "我加入星河项目组", importance=0.99)
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目怎么样", conversation_id="fresh")
    assert not result["items"]
    assert result["retrieval"]["context_source"] == "ambiguous"


def test_same_conversation_latest_recall_hit_can_anchor_related_event(memory):
    put(memory, "joined", "我加入了星河项目组")
    put(memory, "meeting", "星河项目组举行了例会")
    put(memory, "other", "我加入了北斗项目组")
    hit(memory, "joined")
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目后来怎么样", conversation_id="c1")
    assert set(ids(result)) == {"joined", "meeting"}
    assert result["retrieval"]["context_source"] == "recall_hits"


@pytest.mark.parametrize("variant", ["other_user", "other_conversation", "expired", "future", "withdrawn"])
def test_recall_hit_isolation_and_lifecycle(memory, variant):
    put(memory, "joined", "我加入星河项目组")
    kwargs = {}
    if variant == "other_user":
        kwargs["user"] = "bob"
    elif variant == "other_conversation":
        kwargs["conversation"] = "elsewhere"
    elif variant == "expired":
        kwargs["stamp"] = NOW - timedelta(hours=3)
    elif variant == "future":
        kwargs["stamp"] = NOW + timedelta(hours=1)
    elif variant == "withdrawn":
        memory.invalidate("alice", "joined")
    hit(memory, "joined", **kwargs)
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目怎么样", conversation_id="c1")
    assert result["items"] == []


def test_multiple_unthemed_hits_and_multi_entity_context_remain_ambiguous(memory):
    put(memory, "a", "我加入星河项目组", importance=0.99)
    put(memory, "b", "我加入北斗项目组", importance=0.1)
    hit(memory, "a")
    hit(memory, "b")
    retrieval = retriever(memory, Embedder())
    assert retrieval.retrieve("alice", "那个呢", conversation_id="c1")["items"] == []
    recent = [{"role":"user", "content":"星河项目组和北斗项目组"}]
    assert retrieval.retrieve("alice", "那个项目呢", recent_messages=recent)["items"] == []


def test_latest_hit_turn_does_not_blend_older_subject(memory):
    put(memory, "a", "我加入星河项目组")
    put(memory, "b", "我加入北斗项目组")
    hit(memory, "a", message="old", stamp=NOW - timedelta(minutes=5))
    hit(memory, "b", message="new")
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目呢", conversation_id="c1")
    assert ids(result) == ["b"]


@pytest.mark.parametrize("query,expected", [("今天公园散步", "today"), ("昨天公园散步", "yesterday"),
                                         ("2026-11-07公园散步", "yesterday"), ("11月7日公园散步", "yesterday")])
def test_event_calendar_day_uses_semantic_key_and_excludes_other_days(memory, query, expected):
    put(memory, "today", "公园散步", semantic_key="event:2026-11-08:walk", valid_from=NOW - timedelta(days=10))
    put(memory, "yesterday", "公园散步", semantic_key="event:2026-11-07:walk", valid_from=NOW)
    result = retriever(memory, Embedder()).retrieve("alice", query)
    assert ids(result) == [expected]


def test_date_filter_does_not_make_unrelated_topic_a_match(memory):
    put(memory, "noise", "修理自行车轮胎", semantic_key="event:2026-11-07:repair")
    result = retriever(memory, Embedder()).retrieve("alice", "昨天潜水")
    assert not result["items"]
    generic = retriever(memory, Embedder()).retrieve("alice", "昨天发生了什么")
    assert ids(generic) == ["noise"]


def test_namedless_hit_only_anchors_that_event(memory):
    put(memory, "anonymous", "加入了一直想加入的项目组")
    put(memory, "other", "星河项目组举行例会")
    hit(memory, "anonymous")
    result = retriever(memory, Embedder()).retrieve("alice", "那个项目呢", conversation_id="c1")
    assert ids(result) == ["anonymous"]


def test_conversational_filler_cannot_trigger_arbitrary_semantic_recall(memory):
    put(memory, "a", "修理自行车轮胎")
    embedder = Embedder({"谢谢":[1,0,0], "修理自行车轮胎":[1,0,0]})
    result = retriever(memory, embedder).retrieve("alice", "谢谢")
    assert not result["items"]
    assert not embedder.calls


def test_valid_from_fallback_obeys_user_timezone(memory):
    put(memory, "walk", "公园散步", semantic_key="legacy-walk", valid_from=NOW)
    with memory.store.connect() as db:
        db.execute("INSERT INTO user_preferences VALUES (?,?,?)", ("alice", "America/Los_Angeles", NOW.isoformat()))
    result = retriever(memory, Embedder()).retrieve("alice", "今天公园散步")
    assert ids(result) == ["walk"]  # 11/7 in Los Angeles, 11/8 in Shanghai.


@pytest.mark.parametrize("query", ["以前带过什么", "昨天带什么", "2026-11-07带什么"])
def test_explicit_past_never_returns_future_plans(memory, query):
    put(memory, "plan", "明天带雨伞", kind="future_plan", semantic_key="plan:2026-11-09:umbrella")
    put(memory, "old-plan", "带雨伞", kind="future_plan", semantic_key="plan:2026-11-07:umbrella")
    result = retriever(memory, Embedder()).retrieve("alice", query)
    assert not result["items"]


@pytest.mark.parametrize("query", ["明天要带什么东西", "明天带什么", "明天带哪些", "明天带雨伞"])
def test_future_plan_preserves_date_constraint_and_carrying_recall(memory, query):
    put(memory, "tomorrow", "带雨伞", kind="future_plan", semantic_key="plan:2026-11-09:umbrella")
    put(memory, "today", "带U盘", kind="future_plan", semantic_key="plan:2026-11-08:usb")
    put(memory, "unknown-day", "带文件", kind="future_plan", semantic_key="plan:unspecified:file")
    result = retriever(memory, Embedder()).retrieve("alice", query)
    assert ids(result) == ["tomorrow"]


def test_mixed_chinese_usb_term_and_bare_calendar_query(memory):
    put(memory, "usb", "带U盘", kind="future_plan", semantic_key="plan:2026-11-09:usb")
    put(memory, "walk", "公园散步")
    retrieval = retriever(memory, Embedder())
    assert ids(retrieval.retrieve("alice", "明天U盘")) == ["usb"]
    assert ids(retrieval.retrieve("alice", "今天")) == ["walk"]


def test_profile_is_separate_common_active_bounded_and_original(memory):
    original = put(memory, "tea", "我平常喝龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    put(memory, "other", "孤立的一次偏好", kind="stable_fact", semantic_key="fact:other")
    for index, key in enumerate(["name", "occupation", "language", "timezone", "dietary_preference"]):
        put(memory, f"profile-{index}", "常用资料" * 70, kind="stable_fact", semantic_key=f"fact:{key}")
    put(memory, "inactive", "我以前喝红茶", kind="stable_fact", semantic_key="fact:drink_preference", state="superseded")
    result = retriever(memory, Embedder()).retrieve("alice", "喝茶")
    assert not result["items"]
    assert 1 <= len(result["profile"]) <= 4
    assert sum(len(item["canonical_text"]) + len(item["value"]) for item in result["profile"]) <= 1200
    assert result["profile"][0] == original
    assert not {"other", "inactive"} & set(ids(result, "profile"))


def test_profile_match_ids_distinguish_resident_facts_from_query_hits(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    retrieval = retriever(memory, Embedder())
    related = retrieval.retrieve("alice", "喝茶")
    unrelated = retrieval.retrieve("alice", "修理自行车")
    assert ids(related, "profile") == ids(unrelated, "profile") == ["tea"]
    assert related["retrieval"]["profile_match_ids"] == ["tea"]
    assert unrelated["retrieval"]["profile_match_ids"] == []
    assert related["status"] == unrelated["status"] == "matched"


def test_profile_oversized_item_is_skipped_without_truncating_original(memory):
    put(memory, "large", "资料" * 700, kind="stable_fact", semantic_key="fact:name")
    small = put(memory, "small", "平常喜欢红茶", kind="stable_fact", semantic_key="fact:drink_preference")
    result = retriever(memory, Embedder()).retrieve("alice", "你好")
    assert result["profile"] == [small]


@pytest.mark.parametrize("query", ["忘记我喜欢龙井茶", "别记这件事", "撤回这条记忆"])
def test_explicit_withdrawal_suppresses_profile_and_events(memory, query):
    put(memory, "tea", "喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    put(memory, "event", "龙井茶品鉴")
    embedder = Embedder()
    result = retriever(memory, embedder).retrieve("alice", query)
    assert result["status"] == "excluded"
    assert result["profile"] == result["items"] == []
    assert not embedder.calls


def test_recent_explicit_withdrawal_excludes_profile_before_persistence(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    result = retriever(memory, Embedder()).retrieve("alice", "喝什么茶", recent_messages=[
        {"role":"user", "content":"忘记我喜欢龙井茶"}])
    assert not result["profile"]


def test_withdrawal_at_end_of_long_context_still_removes_profile(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    result = retriever(memory, Embedder()).retrieve("alice", "喝茶", recent_messages=[
        {"role":"user", "content":"闲聊" * 600 + "。忘记我喜欢龙井茶"}])
    assert not result["profile"]


def test_vector_cache_removed_on_withdrawal_content_change_model_change_and_delete(memory):
    put(memory, "a", "公园散步")
    embedder = Embedder()
    retrieval = retriever(memory, embedder)
    retrieval.retrieve("alice", "散步")
    old = set(retrieval._cache)
    result = retrieval.retrieve("alice", "散步")
    assert result["retrieval"]["cache_hits"] == 1
    with memory.store.connect() as db:
        db.execute("UPDATE memory_items SET canonical_text='公园遛弯' WHERE memory_id='a'")
    retrieval.retrieve("alice", "散步")
    assert old.isdisjoint(retrieval._cache)
    old = set(retrieval._cache)
    embedder.model_name = "different-model"
    retrieval.retrieve("alice", "散步")
    assert old.isdisjoint(retrieval._cache)
    memory.invalidate("alice", "a")
    assert not retrieval.retrieve("alice", "散步")["items"]
    assert not retrieval._cache
    put(memory, "b", "公园散步")
    retrieval.retrieve("alice", "散步")
    with memory.store.connect() as db:
        db.execute("DELETE FROM memory_items WHERE memory_id='b'")
    retrieval.retrieve("alice", "散步")
    assert not retrieval._cache


def test_cache_user_isolation_even_for_identical_memory_id_and_text(memory, monkeypatch):
    row = put(memory, "shared-id", "公园散步")
    monkeypatch.setattr(memory, "list_items", lambda user: [{**row, "user_id":user}])
    embedder = Embedder()
    retrieval = retriever(memory, embedder)
    first = retrieval.retrieve("alice", "散步")
    second = retrieval.retrieve("bob", "散步")
    assert first["retrieval"]["embedded_count"] == second["retrieval"]["embedded_count"] == 1
    assert second["retrieval"]["cache_hits"] == 0
    assert {key[0] for key in retrieval._cache} == {"alice", "bob"}
    assert second["items"][0]["user_id"] == "bob"


def test_defensive_owner_filter_rejects_foreign_rows_before_embedding(memory, monkeypatch):
    foreign = put(memory, "foreign", "星河项目组举行例会", user="bob")
    monkeypatch.setattr(memory, "list_items", lambda _: [foreign])
    embedder = Embedder()
    result = retriever(memory, embedder).retrieve("alice", "星河项目组")
    assert not result["items"]
    assert not embedder.calls


def test_budget_bounds_embedding_count_chars_candidates_and_cache(memory):
    for index in range(12):
        put(memory, f"e{index:02}", f"公园散步编号{index}")
    embedder = Embedder()
    retrieval = retriever(memory, embedder, embedding_budget=3, candidate_budget=5,
                          embedding_char_budget=100, cache_size=2)
    result = retrieval.retrieve("alice", "公园散步")
    meta = result["retrieval"]
    assert meta["candidate_count"] == 12
    assert meta["semantic_candidates"] == meta["embedded_count"] == 3
    assert meta["budget_exhausted"]
    assert len(embedder.calls[1]) == 3
    assert sum(len(text) for call in embedder.calls for text in call) <= 100
    assert len(retrieval._cache) <= 2
    assert len(result["items"]) <= 5


def test_weak_overlap_is_not_enough_and_items_capped_at_eight(memory):
    put(memory, "weak", "项目组计划观测星空")
    retrieval = retriever(memory, Embedder())
    assert not retrieval.retrieve("alice", "组员分享水果")["items"]
    for index in range(12):
        put(memory, f"walk-{index}", "公园散步")
    result = retrieval.retrieve("alice", "公园散步")
    assert len(result["items"]) == 8


def test_embedding_failure_falls_back_to_keyword_entity_and_reports_failure(memory):
    put(memory, "a", "公园散步")

    class Broken:
        def embed(self, texts):
            raise RuntimeError("local inference failed")

    result = retriever(memory, Broken()).retrieve("alice", "公园遛弯")
    assert ids(result) == ["a"]
    assert result["retrieval"]["semantic_status"] == "embedding_failed"
    assert result["retrieval"]["mode"] == "keyword_entity"


@pytest.mark.parametrize("bad", [[[float("nan"), 0]], [[0, 0]], [], [[1, 0], [1, 0]]])
def test_invalid_vector_output_degrades_without_polluting_cache(memory, bad):
    put(memory, "a", "公园散步")

    class Broken(Embedder):
        def embed(self, texts):
            return bad

    retrieval = retriever(memory, Broken())
    result = retrieval.retrieve("alice", "公园散步")
    assert ids(result) == ["a"]
    assert result["retrieval"]["semantic_status"] == "embedding_failed"
    assert not retrieval._cache


def test_zero_embedding_budget_and_char_budget_fall_back_without_encoding(memory):
    put(memory, "a", "公园散步")
    for kwargs in ({"embedding_budget":0}, {"embedding_char_budget":2}):
        embedder = Embedder()
        result = retriever(memory, embedder, **kwargs).retrieve("alice", "公园散步")
        assert ids(result) == ["a"]
        assert result["retrieval"]["semantic_status"] == "budget_exhausted"
        assert not embedder.calls


def test_retrieve_never_loads_model_and_warmup_is_explicit_offline(memory, monkeypatch):
    put(memory, "a", "公园散步")
    memory.settings.memory_embedding_cache.mkdir()
    calls = []

    class FakeModel:
        def __init__(self, **kwargs):
            calls.append((threading.current_thread().name, kwargs))

        def embed(self, texts, **kwargs):
            return [[1, 0] for _ in texts]

        query_embed = embed

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=FakeModel))
    retrieval = retriever(memory)
    before = retrieval.retrieve("alice", "公园散步")
    assert before["retrieval"]["semantic_status"] == "not_warmed"
    assert not calls
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(retrieval.warmup).result() == "ready"
    assert len(calls) == 1
    assert calls[0][0] != threading.current_thread().name
    assert calls[0][1] == dict(model_name=MODEL_NAME, cache_dir=str(memory.settings.memory_embedding_cache),
                              threads=2, local_files_only=True, lazy_load=False)
    assert retrieval.retrieve("alice", "公园散步")["retrieval"]["semantic_status"] == "ready"


def test_missing_cache_does_not_import_or_load_and_is_reported(memory, monkeypatch):
    put(memory, "a", "公园散步")
    monkeypatch.setitem(sys.modules, "fastembed", None)
    retrieval = retriever(memory)
    assert retrieval.warmup() == "cache_missing"
    result = retrieval.retrieve("alice", "公园散步")
    assert ids(result) == ["a"]
    assert result["retrieval"]["semantic_status"] == "cache_missing"


def test_failed_local_load_is_not_retried_online(memory, monkeypatch):
    memory.settings.memory_embedding_cache.mkdir()
    calls = []

    def broken(**kwargs):
        calls.append(kwargs)
        raise ValueError("incomplete local cache")

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=broken))
    retrieval = retriever(memory)
    assert retrieval.warmup() == "load_failed"
    assert len(calls) == 1 and calls[0]["local_files_only"] is True
    assert retrieval.retrieve("alice", "散步")["retrieval"]["semantic_status"] == "load_failed"
    assert len(calls) == 1


def test_warming_request_falls_back_without_waiting_for_model_load(memory, monkeypatch):
    put(memory, "a", "公园散步")
    memory.settings.memory_embedding_cache.mkdir()
    entered, release = threading.Event(), threading.Event()

    class SlowModel:
        def __init__(self, **kwargs):
            entered.set()
            assert release.wait(timeout=5)

        def embed(self, texts, **kwargs):
            return [[1, 0] for _ in texts]

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=SlowModel))
    retrieval = retriever(memory)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(retrieval.warmup)
        try:
            assert entered.wait(timeout=5)
            result = retrieval.retrieve("alice", "公园散步")
            assert ids(result) == ["a"]
            assert result["retrieval"]["semantic_status"] == "warming"
        finally:
            release.set()
        assert future.result() == "ready"


def test_concurrent_retrieval_serializes_embedder_and_keeps_cache_user_isolated(memory):
    put(memory, "a", "公园散步")
    put(memory, "b", "公园散步", user="bob")
    embedder = Embedder()
    retrieval = retriever(memory, embedder)
    users = ["alice", "bob"] * 10
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda user: retrieval.retrieve(user, "公园散步"), users))
    for user, result in zip(users, results):
        assert all(item["user_id"] == user for item in result["items"])
    assert sum(len(call) for call in embedder.calls) == len(users) + 2
    assert len(retrieval._cache) == 2


@pytest.mark.skipif(not os.environ.get("LIFE_MEMORY_MODEL_CACHE"), reason="opt-in: requires predownloaded local model")
def test_real_local_bge_chinese_semantic_recall_without_download(memory, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("offline model test must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    cache = Path(os.environ["LIFE_MEMORY_MODEL_CACHE"])
    backend = LocalEmbedding(cache)
    with ThreadPoolExecutor(max_workers=1) as pool:
        status = pool.submit(backend.warmup).result()
    assert status == "ready", "configured model cache must contain the complete offline model"
    put(memory, "meal", "午间享用了丰盛的美食")
    put(memory, "noise", "修理自行车轮胎")
    result = retriever(memory, backend).retrieve("alice", "中午吃饭的经历")
    assert "meal" in ids(result)
    assert result["retrieval"]["mode"] == "hybrid"
