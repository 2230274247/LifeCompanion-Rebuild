"""Pure-vector regression tests; this filename also supplies shared test fixtures.

Document and query vectors are controlled independently. No text matching is
implemented by the fake, and every database is created under pytest tmp_path.
Optional real-model check: LIFE_MEMORY_MODEL_CACHE=<local cache>.
"""
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
MATCH = [1.0, 0.0, 0.0]
ORTHOGONAL = [0.0, 1.0, 0.0]


class Embedder:
    model_name = "test-chinese-semantic-v1"
    status = "ready"

    def __init__(self, vectors=None, queries=None, *, default_document=None):
        self.vectors = vectors or {}
        self.queries = queries or {}
        self.default_document = ORTHOGONAL if default_document is None else default_document
        self.calls = []
        self.query_calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [self.vectors.get(text, self.default_document) for text in texts]

    def query_embed(self, texts):
        self.query_calls.append(list(texts))
        return [self.queries.get(text, MATCH) for text in texts]


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
        # This fixture explicitly supplies verified event dates. Production never
        # trusts legacy keys as evidence of occurrence.
        try:
            day = datetime.strptime(semantic_key.split(':')[1], '%Y-%m-%d').date().isoformat() if kind == 'life_event' else None
        except (ValueError, IndexError):
            day = None
        db.execute("""INSERT INTO memory_items
            (memory_id,user_id,kind,semantic_key,canonical_text,value,state,importance,
             confidence,sensitivity,image_candidate,valid_from,created_at,updated_at,
             occurrence_start,occurrence_end,occurrence_precision)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key,user,kind,semantic_key,text,value,state,importance,0.95,sensitivity,0,stamp,stamp,stamp,
             day,day,'day' if day else 'unknown'))
    return next(item for item in memory.list_items(user) if item["memory_id"] == key) if state == "active" else None


def hit(memory, key, *, user="alice", conversation="c1", message="m1", stamp=NOW):
    with memory.store.connect() as db:
        db.execute("INSERT INTO memory_recall_hits VALUES (?,?,?,?,?)",
                   (user, conversation, message, key, stamp.isoformat()))


def retriever(memory, embedder=None, **kwargs):
    return MemoryRetriever(memory, embedder=embedder, now=lambda zone: NOW.astimezone(zone), **kwargs)


def ready(memory, vectors=None, queries=None, **kwargs):
    retrieval = retriever(memory, Embedder(vectors, queries), **kwargs)
    retrieval.prepare_user("alice")
    return retrieval


def prepare_app(app, vectors=None, queries=None):
    """Prepare synthetic HTTP-test records, with no local model or network access.

    Without an explicit mapping every synthetic document is aligned to the
    default query. These integration tests exercise permissions/provenance;
    semantic relevance itself is covered by independently controlled vectors.
    """
    memory = app.state.memory
    with memory.store.connect() as db:
        users = [row[0] for row in db.execute("SELECT user_id FROM memory_permissions")]
    # The same encoder also handles later background writes; a newly ingested
    # record must not receive a different vector just because a mapping was
    # captured before it existed.
    embedder = Embedder(vectors, queries, default_document=MATCH if vectors is None else ORTHOGONAL)
    memory.retriever = MemoryRetriever(memory, embedder)
    for user in users:
        memory.retriever.prepare_user(user)
    return memory.retriever


def ids(result, field="items"):
    return [item["memory_id"] for item in result[field]]


def persisted(retrieval, user="alice", model=None):
    with retrieval.memory.store.connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM memory_vectors WHERE user_id=? AND model=? ORDER BY memory_id",
            (user, model or retrieval.model))]


def test_permission_denied_before_read_or_embedding_and_purges_persistent_vectors(memory, monkeypatch):
    put(memory, "a", "星河项目组举行例会")
    retrieval = ready(memory, {"星河项目组举行例会": MATCH})
    assert ids(retrieval.retrieve("alice", "项目近况")) == ["a"]
    assert len(persisted(retrieval)) == 1
    memory.set_permissions("alice", {"recall_consent": False})
    calls = (list(retrieval.embedder.calls), list(retrieval.embedder.query_calls))
    monkeypatch.setattr(memory, "list_items", lambda _: pytest.fail("must not read before consent"))
    result = retrieval.retrieve("alice", "项目近况")
    assert result["status"] == "permission_denied"
    assert result["items"] == result["profile"] == []
    assert result["retrieval"]["semantic_status"] == "permission_denied"
    assert (retrieval.embedder.calls, retrieval.embedder.query_calls) == calls
    assert persisted(retrieval) == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_does_not_return_profile_or_encode(memory, query):
    put(memory, "tea", "平常喜欢绿茶", kind="stable_fact", semantic_key="fact:drink_preference")
    embedder = Embedder()
    result = retriever(memory, embedder).retrieve("alice", query)
    assert result["items"] == result["profile"] == []
    assert result["retrieval"]["semantic_status"] == "empty_query"
    assert embedder.calls == embedder.query_calls == []


def test_sensitive_texts_filtered_before_encoding_and_sensitive_profile_needs_consent(memory):
    memory.set_permissions("alice", {"sensitive_consent": False})
    put(memory, "safe", "星河项目组举行例会")
    put(memory, "medical", "星河项目组讨论医疗诊断", sensitivity="sensitive")
    put(memory, "unknown", "项目进展未知", sensitivity="unknown")
    put(memory, "address", "我住在杭州", kind="stable_fact", semantic_key="fact:residence", sensitivity="sensitive")
    retrieval = ready(memory, {"星河项目组举行例会": MATCH, "星河项目组讨论医疗诊断": MATCH})
    result = retrieval.retrieve("alice", "项目近况", recent_messages=[{"role":"user", "content":"刚才去医院了"}])
    assert ids(result) == ["safe"]
    assert not result["profile"]
    assert retrieval.embedder.calls == [["星河项目组举行例会"]]
    assert retrieval.embedder.query_calls == [["项目近况"]]
    result = retrieval.retrieve("alice", "医疗诊断")
    assert result["retrieval"]["semantic_status"] == "sensitive_query_blocked"
    assert retrieval.embedder.query_calls == [["项目近况"]]
    memory.set_permissions("alice", {"sensitive_consent": True})
    retrieval.prepare_user("alice")
    result = retrieval.retrieve("alice", "项目近况")
    assert set(ids(result)) == {"safe", "medical"}
    assert ids(result, "profile") == ["address"]
    memory.set_permissions("alice", {"sensitive_consent": False})
    retrieval.retrieve("alice", "项目近况")
    assert {row["memory_id"] for row in persisted(retrieval)} == {"safe"}


def test_vector_contract_recalls_chinese_synonym_without_keyword_matching(memory):
    text, query = "午间享用了丰盛的美食", "中午吃饭经历"
    original = put(memory, "meal", text)
    put(memory, "noise", "修理自行车轮胎")
    retrieval = ready(memory, {text: [0.99, 0.01, 0]})
    result = retrieval.retrieve("alice", query)
    assert ids(result) == ["meal"]
    assert result["items"][0] == original
    assert result["retrieval"]["mode"] == "semantic_only"
    assert result["retrieval"]["keyword_retrieval"] is False
    assert result["retrieval"]["semantic_status"] == "ready"


def test_identical_entity_text_and_importance_cannot_override_vectors(memory):
    put(memory, "literal", "星河项目组怎么样", importance=0.99)
    put(memory, "meaning", "新团队欢迎了我")
    retrieval = ready(memory, {"新团队欢迎了我": MATCH})
    assert ids(retrieval.retrieve("alice", "星河项目组怎么样")) == ["meaning"]


def test_ordinary_query_does_not_include_old_context(memory):
    put(memory, "project", "星河项目组举行例会")
    put(memory, "walk", "我去公园散步")
    retrieval = ready(memory, {"我去公园散步": MATCH})
    result = retrieval.retrieve("alice", "公园散步", recent_messages=[
        {"role":"user", "content":"我加入了星河项目组"}])
    assert ids(result) == ["walk"]
    assert not result["retrieval"]["context_used"]
    assert retrieval.embedder.query_calls == [["公园散步"]]


def test_anaphora_embeds_latest_user_context_and_never_assistant_text(memory):
    put(memory, "orion", "团队例会顺利结束")
    put(memory, "dipper", "另一个团队推迟了例会")
    query = "那个项目后来怎么样"
    combined = "昨天参加了星河项目组\n" + query
    retrieval = ready(memory, {"团队例会顺利结束": MATCH},
                      {query: ORTHOGONAL, combined: MATCH})
    recent = [
        {"role":"user", "content":"我加入了北斗项目组"},
        {"role":"assistant", "content":"北斗项目组很棒"},
        {"role":"user", "content":"昨天参加了星河项目组"},
        {"role":"assistant", "content":"另一个团队推迟了例会"},
    ]
    result = retrieval.retrieve("alice", query, recent_messages=recent)
    assert ids(result) == ["orion"]
    assert result["retrieval"]["context_source"] == "recent_users"
    assert retrieval.embedder.query_calls == [[combined]]


def test_context_outside_four_user_turns_and_assistant_only_cannot_anchor(memory):
    put(memory, "orion", "星河项目组举行例会")
    query = "那个项目呢"
    combined = "谢谢\n" + query
    retrieval = ready(memory, {"星河项目组举行例会": MATCH}, {combined: ORTHOGONAL})
    recent = [{"role":"user", "content":"我加入星河项目组"}]
    recent += [{"role":"user", "content":"谢谢"} for _ in range(4)]
    recent += [{"role":"assistant", "content":"星河项目组"}]
    result = retrieval.retrieve("alice", query, recent_messages=recent)
    assert not result["items"]
    assert retrieval.embedder.query_calls == [[combined]]
    assistant_only = retrieval.retrieve("alice", query, recent_messages=recent[-1:])
    assert assistant_only["retrieval"]["context_source"] == "ambiguous"
    assert assistant_only["items"] == []
    assert retrieval.embedder.query_calls == [[combined]]


def test_no_cross_window_unique_project_guess(memory):
    put(memory, "only", "我加入星河项目组", importance=0.99)
    retrieval = ready(memory, {"我加入星河项目组": MATCH})
    result = retrieval.retrieve("alice", "那个项目怎么样", conversation_id="fresh")
    assert not result["items"]
    assert result["retrieval"]["context_source"] == "ambiguous"
    assert retrieval.embedder.query_calls == []


def test_same_conversation_latest_recall_hit_can_anchor_related_event(memory):
    put(memory, "joined", "我加入了星河项目组")
    put(memory, "meeting", "项目组举行了例会")
    put(memory, "other", "我加入了北斗项目组")
    hit(memory, "joined")
    query = "那个项目后来怎么样"
    combined = "我加入了星河项目组\n" + query
    retrieval = ready(memory, {"我加入了星河项目组": MATCH, "项目组举行了例会": MATCH},
                      {query: ORTHOGONAL, combined: MATCH})
    result = retrieval.retrieve("alice", query, conversation_id="c1")
    assert set(ids(result)) == {"joined", "meeting"}
    assert result["retrieval"]["context_source"] == "recall_hits"
    assert retrieval.embedder.query_calls == [[combined]]


@pytest.mark.parametrize("variant", ["other_user", "other_conversation", "expired", "future", "withdrawn"])
def test_recall_hit_isolation_and_lifecycle(memory, variant):
    put(memory, "joined", "我加入星河项目组")
    retrieval = ready(memory, {"我加入星河项目组": MATCH})
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
    result = retrieval.retrieve("alice", "那个项目怎么样", conversation_id="c1")
    assert result["items"] == []
    assert result["retrieval"]["context_source"] == "ambiguous"
    assert retrieval.embedder.query_calls == []


def test_multiple_hits_require_context_instead_of_importance_guess(memory):
    put(memory, "a", "我加入星河项目组", importance=0.99)
    put(memory, "b", "我加入北斗项目组", importance=0.1)
    hit(memory, "a")
    hit(memory, "b")
    retrieval = ready(memory, {"我加入星河项目组": MATCH, "我加入北斗项目组": MATCH})
    result = retrieval.retrieve("alice", "那个呢", conversation_id="c1")
    assert result["items"] == []
    assert result["retrieval"]["context_source"] == "ambiguous"
    assert retrieval.embedder.query_calls == []


def test_multi_entity_context_is_resolved_only_by_query_vector(memory):
    put(memory, "a", "我加入星河项目组")
    put(memory, "b", "我加入北斗项目组")
    combined = "星河项目组和北斗项目组\n那个项目呢"
    retrieval = ready(memory, {"我加入星河项目组": MATCH, "我加入北斗项目组": MATCH},
                      {combined: ORTHOGONAL})
    result = retrieval.retrieve("alice", "那个项目呢", recent_messages=[
        {"role":"user", "content":"星河项目组和北斗项目组"}])
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "ready"
    assert retrieval.embedder.query_calls == [[combined]]


def test_latest_hit_turn_does_not_blend_older_subject(memory):
    put(memory, "a", "我加入星河项目组")
    put(memory, "b", "我加入北斗项目组")
    hit(memory, "a", message="old", stamp=NOW - timedelta(minutes=5))
    hit(memory, "b", message="new")
    combined = "我加入北斗项目组\n那个项目呢"
    retrieval = ready(memory, {"我加入北斗项目组": MATCH}, {combined: MATCH})
    result = retrieval.retrieve("alice", "那个项目呢", conversation_id="c1")
    assert ids(result) == ["b"]
    assert retrieval.embedder.query_calls == [[combined]]


@pytest.mark.parametrize("query,expected", [("今天公园散步", "today"), ("昨天公园散步", "yesterday"),
                                         ("2026-11-07公园散步", "yesterday"), ("11月7日公园散步", "yesterday")])
def test_event_calendar_day_uses_semantic_key_and_excludes_other_days(memory, query, expected):
    put(memory, "today", "公园散步", semantic_key="event:2026-11-08:walk", valid_from=NOW - timedelta(days=10))
    put(memory, "yesterday", "公园散步", semantic_key="event:2026-11-07:walk", valid_from=NOW)
    retrieval = ready(memory, {"公园散步": MATCH})
    result = retrieval.retrieve("alice", query)
    assert ids(result) == [expected]
    assert result["retrieval"]["semantic_candidates"] == 1
    assert result["retrieval"]["indexed_count"] == 2


def test_date_filter_does_not_make_unrelated_topic_a_match(memory):
    put(memory, "noise", "修理自行车轮胎", semantic_key="event:2026-11-07:repair")
    retrieval = ready(memory, {"修理自行车轮胎": MATCH},
                      {"昨天潜水": ORTHOGONAL, "昨天发生了什么": MATCH})
    result = retrieval.retrieve("alice", "昨天潜水")
    assert result["items"] == []
    assert result["retrieval"]["semantic_candidates"] == 1
    assert ids(retrieval.retrieve("alice", "昨天发生了什么")) == ["noise"]


def test_namedless_hit_can_anchor_semantically_related_text_without_entity_gate(memory):
    put(memory, "anonymous", "加入了一直想加入的项目组")
    put(memory, "related", "同事为新成员举办了欢迎会")
    put(memory, "other", "公园散步")
    hit(memory, "anonymous")
    retrieval = ready(memory, {"加入了一直想加入的项目组": MATCH, "同事为新成员举办了欢迎会": MATCH})
    result = retrieval.retrieve("alice", "那个项目呢", conversation_id="c1")
    assert set(ids(result)) == {"anonymous", "related"}
    assert retrieval.embedder.query_calls == [["加入了一直想加入的项目组\n那个项目呢"]]


def test_unrelated_conversational_query_uses_vectors_without_word_blacklist(memory):
    put(memory, "a", "修理自行车轮胎")
    retrieval = ready(memory, {"修理自行车轮胎": MATCH}, {"谢谢": ORTHOGONAL})
    result = retrieval.retrieve("alice", "谢谢")
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "ready"
    assert retrieval.embedder.query_calls == [["谢谢"]]


def test_legacy_recording_date_is_not_occurrence_in_any_timezone(memory):
    put(memory, "walk", "公园散步", semantic_key="legacy-walk", valid_from=NOW)
    with memory.store.connect() as db:
        db.execute("INSERT INTO user_preferences VALUES (?,?,?)", ("alice", "America/Los_Angeles", NOW.isoformat()))
    retrieval = ready(memory, {"公园散步": MATCH})
    assert ids(retrieval.retrieve("alice", "今天公园散步")) == []
    # Still semantically retrievable without a date constraint; only date inference is denied.
    assert ids(retrieval.retrieve("alice", "公园散步")) == ["walk"]


@pytest.mark.parametrize("query,encoded_query", [
    ("以前带过什么", "以前带过什么"), ("昨天带什么", "昨天带什么"), ("2026-11-07带什么", "带什么")])
def test_semantically_unrelated_future_plan_is_not_recalled_by_past_question(memory, query, encoded_query):
    put(memory, "plan", "明天带雨伞", kind="future_plan", semantic_key="plan:2026-11-09:umbrella")
    put(memory, "old-plan", "带雨伞", kind="future_plan", semantic_key="plan:2026-11-07:umbrella")
    retrieval = ready(memory, {"明天带雨伞": MATCH, "带雨伞": MATCH}, {encoded_query: ORTHOGONAL})
    result = retrieval.retrieve("alice", query)
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "ready"
    assert retrieval.embedder.query_calls == [[encoded_query]]


@pytest.mark.parametrize("query", ["明天要带什么东西", "明天带什么", "明天带哪些", "明天带雨伞"])
def test_future_plan_preserves_date_constraint_and_carrying_recall(memory, query):
    put(memory, "tomorrow", "带雨伞", kind="future_plan", semantic_key="plan:2026-11-09:umbrella")
    put(memory, "today", "带U盘", kind="future_plan", semantic_key="plan:2026-11-08:usb")
    put(memory, "unknown-day", "带文件", kind="future_plan", semantic_key="plan:unspecified:file")
    retrieval = ready(memory, {text: MATCH for text in ["带雨伞", "带U盘", "带文件"]})
    result = retrieval.retrieve("alice", query)
    assert ids(result) == ["tomorrow"]
    assert result["retrieval"]["semantic_candidates"] == 1
    assert result["retrieval"]["indexed_count"] == 3


def test_mixed_chinese_usb_term_and_bare_calendar_query(memory):
    put(memory, "usb", "带U盘", kind="future_plan", semantic_key="plan:2026-11-09:usb")
    put(memory, "walk", "公园散步")
    retrieval = ready(memory, {"带U盘": MATCH, "公园散步": MATCH})
    assert ids(retrieval.retrieve("alice", "明天U盘")) == ["usb"]
    assert ids(retrieval.retrieve("alice", "今天")) == ["walk"]


def test_profile_is_separate_common_active_bounded_and_original(memory):
    original = put(memory, "tea", "我平常喝龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    put(memory, "other", "孤立的一次偏好", kind="stable_fact", semantic_key="fact:other")
    for index, key in enumerate(["name", "occupation", "language", "timezone", "dietary_preference"]):
        put(memory, f"profile-{index}", "常用资料" * 70, kind="stable_fact", semantic_key=f"fact:{key}")
    put(memory, "inactive", "我以前喝红茶", kind="stable_fact", semantic_key="fact:drink_preference", state="superseded")
    result = ready(memory, {"我平常喝龙井茶": MATCH}).retrieve("alice", "喝茶")
    assert not result["items"]
    assert 1 <= len(result["profile"]) <= 4
    assert sum(len(item["canonical_text"]) + len(item["value"]) for item in result["profile"]) <= 1200
    assert result["profile"][0] == original
    assert not {"other", "inactive"} & set(ids(result, "profile"))
    assert result["retrieval"]["profile_match_ids"] == ["tea"]


def test_profile_match_ids_distinguish_resident_facts_from_query_hits(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    retrieval = ready(memory, {"平常喜欢龙井茶": MATCH}, {"修理自行车": ORTHOGONAL})
    related = retrieval.retrieve("alice", "喝茶")
    unrelated = retrieval.retrieve("alice", "修理自行车")
    assert ids(related, "profile") == ids(unrelated, "profile") == ["tea"]
    assert related["retrieval"]["profile_match_ids"] == ["tea"]
    assert unrelated["retrieval"]["profile_match_ids"] == []
    assert related["status"] == unrelated["status"] == "matched"
    assert memory.recall("alice", "喝茶") == []  # An unconfigured service cannot fall back to words.
    memory.retriever = retrieval
    assert [item["memory_id"] for item in memory.recall("alice", "喝茶")] == ["tea"]
    assert memory.recall("alice", "修理自行车") == []


def test_profile_oversized_item_is_skipped_without_truncating_original(memory):
    put(memory, "large", "资料" * 700, kind="stable_fact", semantic_key="fact:name")
    small = put(memory, "small", "平常喜欢红茶", kind="stable_fact", semantic_key="fact:drink_preference")
    result = ready(memory).retrieve("alice", "你好")
    assert result["profile"] == [small]


@pytest.mark.parametrize("query", ["忘记我喜欢龙井茶", "别记这件事", "撤回这条记忆"])
def test_explicit_withdrawal_suppresses_profile_and_events(memory, query):
    put(memory, "tea", "喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    put(memory, "event", "龙井茶品鉴")
    retrieval = ready(memory, {"喜欢龙井茶": MATCH, "龙井茶品鉴": MATCH})
    result = retrieval.retrieve("alice", query)
    assert result["status"] == "excluded"
    assert result["profile"] == result["items"] == []
    assert retrieval.embedder.query_calls == []


def test_recent_explicit_withdrawal_excludes_profile_before_persistence(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    retrieval = ready(memory, {"平常喜欢龙井茶": MATCH})
    result = retrieval.retrieve("alice", "喝什么茶", recent_messages=[
        {"role":"user", "content":"忘记我喜欢龙井茶"}])
    assert result["profile"] == result["items"] == []
    assert result["status"] == "excluded"
    assert retrieval.embedder.query_calls == []


def test_withdrawal_at_end_of_long_context_still_removes_profile(memory):
    put(memory, "tea", "平常喜欢龙井茶", kind="stable_fact", semantic_key="fact:drink_preference")
    retrieval = ready(memory, {"平常喜欢龙井茶": MATCH})
    assert ids(retrieval.retrieve("alice", "喝茶"), "profile") == ["tea"]
    retrieval.embedder.query_calls.clear()
    result = retrieval.retrieve("alice", "喝茶", recent_messages=[
        {"role":"user", "content":"闲聊" * 600 + "。忘记我喜欢龙井茶"}])
    assert result["profile"] == result["items"] == []
    assert result["status"] == "excluded"
    assert retrieval.embedder.query_calls == []


def test_persistent_vectors_rebuilt_on_content_or_model_change_and_purged_on_withdrawal_delete(memory):
    put(memory, "a", "公园散步")
    retrieval = ready(memory, {"公园散步": MATCH, "公园遛弯": MATCH})
    old = persisted(retrieval)[0]
    assert ids(retrieval.retrieve("alice", "散步")) == ["a"]
    assert retrieval.retrieve("alice", "散步")["retrieval"]["cache_hits"] == 1
    assert len(retrieval.embedder.calls) == 1
    with memory.store.connect() as db:
        db.execute("UPDATE memory_items SET canonical_text='公园遛弯' WHERE memory_id='a'")
    retrieval.prepare_user("alice")
    assert persisted(retrieval)[0]["content_hash"] != old["content_hash"]
    assert retrieval.embedder.calls[-1] == ["公园遛弯"]
    retrieval.embedder.model_name = "different-model"
    assert persisted(retrieval) == []
    retrieval.prepare_user("alice")
    assert persisted(retrieval)[0]["model"] == "different-model"
    assert ids(retrieval.retrieve("alice", "散步")) == ["a"]
    memory.invalidate("alice", "a")
    assert retrieval.retrieve("alice", "散步")["items"] == []
    assert persisted(retrieval) == []
    put(memory, "b", "公园散步")
    retrieval.prepare_user("alice")
    assert ids(retrieval.retrieve("alice", "散步")) == ["b"]
    with memory.store.connect() as db:
        db.execute("DELETE FROM memory_items WHERE memory_id='b'")
    assert retrieval.retrieve("alice", "散步")["items"] == []
    assert persisted(retrieval) == []


@pytest.mark.parametrize("change", ["recall_revoked", "withdrawn", "sensitive_revoked"])
def test_privacy_purge_covers_old_model_vectors_and_preserves_other_users(memory, change):
    private = change == "sensitive_revoked"
    if private:
        memory.set_permissions("alice", {"sensitive_consent": True})
    put(memory, "a", "公园散步", sensitivity="sensitive" if private else "ordinary")
    put(memory, "b", "公园散步", user="bob")
    retrieval = ready(memory, {"公园散步": MATCH})
    retrieval.prepare_user("bob")
    previous_model = retrieval.model
    retrieval.embedder.model_name = "new-model"
    retrieval.prepare_user("alice")
    retrieval.prepare_user("bob")
    assert len(persisted(retrieval, "alice", previous_model)) == 1
    assert len(persisted(retrieval, "alice")) == 1
    if change == "withdrawn":
        memory.invalidate("alice", "a")
    elif change == "recall_revoked":
        memory.set_permissions("alice", {"recall_consent": False})
    else:
        memory.set_permissions("alice", {"sensitive_consent": False})
    assert retrieval.retrieve("alice", "外出活动")["items"] == []
    with memory.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_vectors WHERE user_id='alice'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM memory_vectors WHERE user_id='bob'").fetchone()[0] == 2


def test_persistent_index_is_reused_by_new_retriever_without_document_encoding(memory):
    put(memory, "a", "公园散步")
    first = ready(memory, {"公园散步": MATCH})
    second = retriever(memory, Embedder())
    assert second.prepare_user("alice") == 1
    assert second.embedder.calls == []
    assert ids(second.retrieve("alice", "外出活动")) == ["a"]
    assert persisted(second) == persisted(first)


def test_vector_user_isolation_even_for_identical_memory_id_and_text(memory, monkeypatch):
    row = put(memory, "shared-id", "公园散步")
    monkeypatch.setattr(memory, "list_items", lambda user: [{**row, "user_id":user}])
    retrieval = ready(memory, {"公园散步": MATCH})
    retrieval.prepare_user("bob")
    assert len(persisted(retrieval, "alice")) == len(persisted(retrieval, "bob")) == 1
    for user in ["alice", "bob"]:
        result = retrieval.retrieve(user, "散步")
        assert ids(result) == ["shared-id"]
        assert result["items"][0]["user_id"] == user
    assert retrieval.embedder.calls == [["公园散步"], ["公园散步"]]


def test_defensive_owner_filter_rejects_foreign_rows_before_document_embedding(memory, monkeypatch):
    foreign = put(memory, "foreign", "星河项目组举行例会", user="bob")
    monkeypatch.setattr(memory, "list_items", lambda _: [foreign])
    retrieval = ready(memory, {"星河项目组举行例会": MATCH})
    result = retrieval.retrieve("alice", "星河项目组")
    assert result["items"] == []
    assert result["retrieval"]["candidate_count"] == 0
    assert persisted(retrieval) == []
    assert retrieval.embedder.calls == []


def test_encoding_batch_size_never_limits_candidate_set_or_persistent_index(memory):
    for index in range(12):
        put(memory, f"e{index:02}", f"公园散步编号{index}")
    retrieval = ready(memory, {f"公园散步编号{index}": MATCH for index in range(12)},
                      embedding_budget=3, candidate_budget=5, embedding_char_budget=2, cache_size=2)
    result = retrieval.retrieve("alice", "公园散步")
    meta = result["retrieval"]
    assert meta["candidate_count"] == meta["semantic_candidates"] == meta["indexed_count"] == 12
    assert not meta["budget_exhausted"]
    assert [len(call) for call in retrieval.embedder.calls] == [3, 3, 3, 3]
    assert len(persisted(retrieval)) == 12
    assert len(result["items"]) == 8


def test_lexical_overlap_is_not_enough_and_vector_hits_are_capped_at_eight(memory):
    put(memory, "weak", "项目组计划观测星空")
    retrieval = ready(memory)
    assert retrieval.retrieve("alice", "项目组计划观测星空")["items"] == []
    for index in range(12):
        put(memory, f"walk-{index:02}", f"公园散步编号{index}")
    retrieval.embedder.vectors.update({f"公园散步编号{index}": MATCH for index in range(12)})
    retrieval.prepare_user("alice")
    result = retrieval.retrieve("alice", "公园散步")
    assert ids(result) == [f"walk-{index:02}" for index in range(8)]
    assert result["retrieval"]["semantic_candidates"] == 13


def test_document_embedding_failure_leaves_index_unavailable_without_keyword_fallback(memory, monkeypatch):
    put(memory, "a", "公园散步")

    class Broken(Embedder):
        def embed(self, texts):
            raise RuntimeError("local inference failed")

    retrieval = retriever(memory, Broken())
    with pytest.raises(RuntimeError, match="local inference failed"):
        retrieval.prepare_user("alice")
    scheduled = []
    monkeypatch.setattr(retrieval, "_schedule", scheduled.append)
    result = retrieval.retrieve("alice", "公园散步")
    assert result["items"] == result["profile"] == []
    assert result["status"] == "unavailable"
    assert result["retrieval"]["semantic_status"] == "index_not_ready"
    assert result["retrieval"]["keyword_retrieval"] is False
    assert scheduled == ["alice"]
    assert persisted(retrieval) == []


@pytest.mark.parametrize("bad", [[[float("nan"), 0]], [[0, 0]], [], [[1, 0], [1, 0]]])
def test_invalid_document_vectors_are_rejected_without_polluting_persistent_index(memory, monkeypatch, bad):
    put(memory, "a", "公园散步")

    class Broken(Embedder):
        def embed(self, texts):
            return bad

    retrieval = retriever(memory, Broken())
    with pytest.raises(ValueError, match="INVALID_(?:EMBEDDING|VECTOR_COUNT)"):
        retrieval.prepare_user("alice")
    monkeypatch.setattr(retrieval, "_schedule", lambda _: None)
    result = retrieval.retrieve("alice", "公园散步")
    assert result["items"] == []
    assert result["status"] == "unavailable"
    assert result["retrieval"]["semantic_status"] == "index_not_ready"
    assert persisted(retrieval) == []


@pytest.mark.parametrize("bad", [[[float("nan"), 0]], [[0, 0]], []])
def test_invalid_query_vectors_report_unavailable_without_word_fallback(memory, bad):
    put(memory, "a", "公园散步")
    retrieval = ready(memory, {"公园散步": MATCH})
    retrieval.embedder.query_embed = lambda _: bad
    result = retrieval.retrieve("alice", "公园散步")
    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "embedding_unavailable"
    assert len(persisted(retrieval)) == 1


def test_query_dimension_mismatch_never_produces_partial_hits(memory):
    put(memory, "a", "公园散步")
    retrieval = ready(memory, {"公园散步": MATCH}, {"公园散步": [1, 0]})
    result = retrieval.retrieve("alice", "公园散步")
    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "dimension_mismatch"


def test_cold_index_is_explicitly_unavailable_and_schedules_full_preparation(memory, monkeypatch):
    put(memory, "a", "公园散步")
    retrieval = retriever(memory, Embedder({"公园散步": MATCH}), embedding_budget=0)
    scheduled = []
    monkeypatch.setattr(retrieval, "_schedule", scheduled.append)
    result = retrieval.retrieve("alice", "公园散步")
    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["retrieval"]["semantic_status"] == "index_not_ready"
    assert scheduled == ["alice"]
    assert retrieval.embedder.calls == retrieval.embedder.query_calls == []
    assert retrieval.prepare_user("alice") == 1
    assert ids(retrieval.retrieve("alice", "公园散步")) == ["a"]


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
    assert before["items"] == []
    assert before["retrieval"]["semantic_status"] == "not_warmed"
    assert not calls
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(retrieval.warmup).result() == "ready"
    assert len(calls) == 1
    assert calls[0][0] != threading.current_thread().name
    assert calls[0][1] == dict(model_name=MODEL_NAME, cache_dir=str(memory.settings.memory_embedding_cache),
                              threads=2, local_files_only=True, lazy_load=False)
    assert ids(retrieval.retrieve("alice", "公园散步")) == ["a"]


def test_missing_cache_does_not_import_or_load_and_never_uses_words(memory, monkeypatch):
    put(memory, "a", "公园散步")
    monkeypatch.setitem(sys.modules, "fastembed", None)
    retrieval = retriever(memory)
    assert retrieval.warmup() == "cache_missing"
    result = retrieval.retrieve("alice", "公园散步")
    assert result["items"] == []
    assert result["status"] == "unavailable"
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


def test_warming_request_returns_unavailable_without_waiting_for_model_load(memory, monkeypatch):
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
            assert result["items"] == []
            assert result["status"] == "unavailable"
            assert result["retrieval"]["semantic_status"] == "warming"
        finally:
            release.set()
        assert future.result() == "ready"


def test_concurrent_queries_reuse_persisted_documents_and_keep_users_isolated(memory):
    put(memory, "a", "公园散步")
    put(memory, "b", "公园散步", user="bob")
    retrieval = ready(memory, {"公园散步": MATCH})
    retrieval.prepare_user("bob")
    users = ["alice", "bob"] * 10
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda user: retrieval.retrieve(user, "公园散步"), users))
    for user, result in zip(users, results):
        assert ids(result) == (["a"] if user == "alice" else ["b"])
        assert all(item["user_id"] == user for item in result["items"])
    assert retrieval.embedder.calls == [["公园散步"], ["公园散步"]]
    assert len(retrieval.embedder.query_calls) == len(users)
    assert len(persisted(retrieval, "alice")) == len(persisted(retrieval, "bob")) == 1


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
    retrieval = retriever(memory, backend)
    retrieval.prepare_user("alice")
    result = retrieval.retrieve("alice", "中午吃饭的经历")
    assert "meal" in ids(result)
    assert result["retrieval"]["mode"] == "semantic_only"
