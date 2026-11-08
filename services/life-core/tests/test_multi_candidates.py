"""Isolated extraction contract tests: no database, network, or persistence wiring."""
from datetime import datetime
from types import SimpleNamespace
import json

import httpx
import pytest

from app.extraction_candidates import extract_candidates
from app.memory import Candidate

NOW = datetime.fromisoformat("2026-11-08T10:00:00+08:00")


@pytest.fixture
def service():
    return SimpleNamespace(settings=SimpleNamespace(
        memory_llm_key="fake-key", memory_llm_url="https://invalid.example/v1",
        memory_llm_model="fake-model", memory_llm_options={}, timezone="Asia/Shanghai",
    ))


def provider(monkeypatch, content, *, status=200, error=None):
    calls = []

    class FakeProvider:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if error:
                raise error
            return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("app.extraction_candidates.httpx.Client", FakeProvider)
    return calls


def model_item(quote, *, key="drink_preference", value="咖啡", kind="stable_fact", state="occurred", **changes):
    return dict(candidate_type=kind, canonical_text=quote, evidence_quote=quote,
                occurred_state=state, fact_key=key, value=value, confidence=0.9,
                sensitivity="ordinary", image_candidate=False, **changes)


def assert_grounded(items, text):
    assert len(items) <= 8
    for item in items:
        assert isinstance(item, Candidate)
        assert item.evidence_quote in text
        assert len(item.canonical_text) <= 500
        assert len(item.value) <= 100


def test_general_facts_and_distinct_relationships(service):
    text = "我的生日是5月1日，职业是教师，喜欢摄影，目标是考博，现在住在杭州。小明是我的同事，小红是我的朋友。"
    items, reason = extract_candidates(service, text, NOW)
    assert reason == "rule_candidates"
    facts = {item.fact_key: item.value for item in items}
    assert {"birthday": "5月1日", "occupation": "教师", "interest": "摄影", "goal": "考博", "residence": "杭州"}.items() <= facts.items()
    relationships = [i for i in items if i.fact_key.startswith("relationship:")]
    assert len(relationships) == 2
    assert relationships[0].fact_key != relationships[1].fact_key
    repeated, _ = extract_candidates(service, "小明是我的朋友", NOW)
    assert repeated[0].fact_key == relationships[0].fact_key
    assert_grounded(items, text)


def test_one_clause_can_have_multiple_facts(service):
    text = "我是一名程序员也喜欢摄影"
    items, _ = extract_candidates(service, text, NOW)
    assert {item.fact_key: item.value for item in items} == {"occupation": "程序员", "interest": "摄影"}
    assert all(item.evidence_quote == text for item in items)


@pytest.mark.parametrize("value", ["拿铁", "饮料", "咖啡", "红茶", "龙井", "气泡水"])
def test_general_drinks(service, value):
    items, _ = extract_candidates(service, f"我喜欢喝{value}", NOW)
    assert [(i.fact_key, i.value) for i in items] == [("drink_preference", value)]


def test_negation_and_current_correction(service):
    items, _ = extract_candidates(service, "我现在不喜欢咖啡", NOW)
    assert [(i.fact_key, i.value) for i in items] == [("drink_avoidance", "咖啡")]
    items, _ = extract_candidates(service, "我不喜欢茶，但喜欢咖啡", NOW)
    assert {(i.fact_key, i.value) for i in items} == {("drink_avoidance", "茶"), ("drink_preference", "咖啡")}
    text = "我以前喜欢龙井，现在更喜欢红茶"
    items, _ = extract_candidates(service, text, NOW)
    assert [(i.fact_key, i.value) for i in items] == [("drink_preference", "红茶")]
    assert "龙井" not in items[0].canonical_text
    assert_grounded(items, text)
    items, _ = extract_candidates(service, "我以前喜欢龙井现在更喜欢红茶", NOW)
    assert [(i.fact_key, i.value) for i in items] == [("drink_preference", "红茶")]


@pytest.mark.parametrize("text", [
    "今天很开心", "我喜欢咖啡吗？", "如果我喜欢咖啡，我就住在杭州", "我可能住在杭州",
    "我并没有参加学术会议", "我没有完成项目", "助手说我喜欢咖啡", "他喜欢咖啡",
    "我不是不喜欢咖啡", "我没有喜欢咖啡", "假设我是一名程序员", "我不住在杭州",
    "我不居住在杭州", "我不参加了", "今天不开心了", "我感觉好多了",
    "我可能喜欢摄影并且喜欢咖啡", "我的朋友喜欢咖啡",
    "今天没在公园散步", "我没散步", "今天项目没结束",
])
def test_non_assertions_do_not_become_facts(service, text):
    assert extract_candidates(service, text, NOW)[0] == []


def test_occurred_uncertain_question_and_plan_are_separated(service):
    text = "今天我参加了学术会议，但可能获奖。我的项目已经完成了，明天结果会公布吗？明天去北京参加会议，出门准备带雨伞。"
    items, _ = extract_candidates(service, text, NOW)
    events = [i for i in items if i.candidate_type == "life_event"]
    plans = [i for i in items if i.candidate_type == "future_plan"]
    assert len(events) == 2
    assert len(plans) == 2
    assert all(i.occurred_state == "occurred" for i in events)
    assert all(i.occurred_state == "planned" and not i.image_candidate for i in plans)
    assert not any("可能" in i.evidence_quote or "吗" in i.evidence_quote for i in items)
    assert_grounded(items, text)


def test_forget_applies_to_entire_input_before_provider(service, monkeypatch):
    calls = provider(monkeypatch, "not JSON")
    assert extract_candidates(service, "我喜欢拿铁。别记这件事", NOW, True) == ([], "explicit_exclusion")
    assert calls == []


def test_rule_limit_and_field_limits(service):
    text = "。".join(f"朋友{i}是我的同事" for i in range(12))
    items, _ = extract_candidates(service, text, NOW)
    assert len(items) == 8
    assert_grounded(items, text)
    assert extract_candidates(service, "我的目标是" + "学" * 101, NOW)[0] == []


def test_llm_single_batch_and_exact_user_source(service, monkeypatch):
    text = "我喜欢拿铁，生日是5月1日。"
    payload = {"items": [model_item("我喜欢拿铁", value="拿铁"), model_item("生日是5月1日", key="birthday", value="5月1日")]}
    calls = provider(monkeypatch, json.dumps(payload, ensure_ascii=False))
    items, reason = extract_candidates(service, text, NOW, True)
    assert reason == "llm_validated" and len(items) == 2 and len(calls) == 1
    messages = calls[0][1]["json"]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert json.loads(messages[1]["content"])["user_message"] == text
    assert items[1].sensitivity == "sensitive"
    assert_grounded(items, text)


def test_llm_legacy_single_candidate(service, monkeypatch):
    provider(monkeypatch, json.dumps(model_item("我喜欢咖啡"), ensure_ascii=False))
    items, _ = extract_candidates(service, "我喜欢咖啡", NOW, True)
    assert len(items) == 1 and items[0].canonical_text == "喜欢喝咖啡"


@pytest.mark.parametrize("text", ["我今天给开源库补了文档", "今天我正式入职新公司"])
def test_llm_event_not_vetoed_by_old_event_vocabulary(service, monkeypatch, text):
    provider(monkeypatch, json.dumps({"items": [model_item(text, kind="life_event", key="other", value="")]}, ensure_ascii=False))
    items, _ = extract_candidates(service, text, NOW, True)
    assert len(items) == 1 and items[0].canonical_text == text


@pytest.mark.parametrize("payload", ["bad JSON", "[]", '{"items":{}}', '{"items":[{}]}',
                                        json.dumps({"items": [model_item("我喜欢咖啡")] * 9})])
def test_llm_malformed_output_is_explicit(service, monkeypatch, payload):
    provider(monkeypatch, payload)
    with pytest.raises(ValueError, match="MEMORY_INVALID_MODEL_OUTPUT"):
        extract_candidates(service, "我喜欢咖啡", NOW, True)


@pytest.mark.parametrize("source,item", [
    ("我喜欢咖啡", model_item("我喜欢红茶", value="红茶")),
    ("我现在不喜欢咖啡", model_item("喜欢咖啡")),
    ("我以前喜欢龙井，现在喜欢红茶", model_item("我以前喜欢龙井", value="龙井")),
    ("我可能喜欢咖啡", model_item("喜欢咖啡")),
    ("我喜欢咖啡吗？", model_item("喜欢咖啡")),
    ("用户：今天天气不错\n助手：我喜欢咖啡", model_item("我喜欢咖啡")),
    ("明天去北京参加会议", model_item("明天去北京参加会议", kind="life_event", key="other", value="")),
    ("今天很开心", model_item("今天很开心", kind="life_event", key="other", value="")),
])
def test_llm_grounding_and_scope(service, monkeypatch, source, item):
    provider(monkeypatch, json.dumps({"items": [item]}, ensure_ascii=False))
    with pytest.raises(ValueError, match="MEMORY_UNGROUNDED_OUTPUT"):
        extract_candidates(service, source, NOW, True)


def test_provider_failures_never_fall_back(service, monkeypatch):
    provider(monkeypatch, "{}", status=503)
    with pytest.raises(ValueError, match="MEMORY_PROVIDER_UNAVAILABLE"):
        extract_candidates(service, "我喜欢咖啡", NOW, True)
    provider(monkeypatch, "{}", error=httpx.ConnectError("fake offline"))
    with pytest.raises(httpx.ConnectError, match="fake offline"):
        extract_candidates(service, "我喜欢咖啡", NOW, True)


def test_personal_context_does_not_transfer_named_third_party_preferences(service):
    items, _ = extract_candidates(service, "我住在杭州，张三喜欢咖啡", NOW)
    assert [(i.fact_key, i.value) for i in items] == [("residence", "杭州")]


@pytest.mark.parametrize("text,key,value", [
    ("我是一名建筑师", "occupation", "建筑师"),
    ("我从事软件开发", "occupation", "软件开发"),
    ("我的爱好是摄影", "interest", "摄影"),
    ("我的兴趣是天文", "interest", "天文"),
])
def test_generic_fact_grammar(service, text, key, value):
    items, _ = extract_candidates(service, text, NOW)
    assert [(i.fact_key, i.value) for i in items] == [(key, value)]


def test_relationship_object_grammar_is_consistent(service):
    keys = []
    for text in ["小明是我的同事", "我的同事叫小明", "我和小明是同事"]:
        items, _ = extract_candidates(service, text, NOW)
        assert len(items) == 1
        keys.append(items[0].fact_key)
    assert len(set(keys)) == 1


def test_rule_event_uses_completion_grammar_not_old_topics(service):
    items, _ = extract_candidates(service, "我今天给开源库补了文档", NOW)
    assert len(items) == 1 and items[0].candidate_type == "life_event"


def test_multiple_interests_and_drinks_in_one_clause(service):
    text = "我喜欢摄影和跑步和喝拿铁和红茶"
    items, _ = extract_candidates(service, text, NOW)
    assert {(i.fact_key, i.value) for i in items} == {
        ("interest", "摄影"), ("interest", "跑步"),
        ("drink_preference", "拿铁"), ("drink_preference", "红茶"),
    }
    assert_grounded(items, text)


@pytest.mark.parametrize("changes", [
    {"canonical_text": "字" * 501}, {"value": "字" * 101}, {"fact_key": "arbitrary"},
    {"confidence": 2}, {"sensitivity": "secret"}, {"unexpected": True},
])
def test_model_candidate_constraints_are_preserved(service, monkeypatch, changes):
    item = {**model_item("我喜欢咖啡"), **changes}
    provider(monkeypatch, json.dumps(item, ensure_ascii=False))
    with pytest.raises(ValueError, match="MEMORY_INVALID_MODEL_OUTPUT"):
        extract_candidates(service, "我喜欢咖啡", NOW, True)


@pytest.mark.parametrize("source,item", [
    ("我喜欢咖啡", model_item("我喜欢咖啡", kind="life_event", key="other", value="")),
    ("我喜欢咖啡", model_item("我喜欢咖啡", key="drink_avoidance")),
])
def test_model_cannot_retype_preference_as_event_or_avoidance(service, monkeypatch, source, item):
    provider(monkeypatch, json.dumps(item, ensure_ascii=False))
    with pytest.raises(ValueError, match="MEMORY_UNGROUNDED_OUTPUT"):
        extract_candidates(service, source, NOW, True)


def test_model_plan_and_uncertain_clause(service, monkeypatch):
    source = "明天去北京参加会议，但可能下雨"
    provider(monkeypatch, json.dumps({"items": [model_item("明天去北京参加会议", kind="future_plan", key="other", value="", state="planned")]}, ensure_ascii=False))
    items, _ = extract_candidates(service, source, NOW, True)
    assert len(items) == 1 and items[0].occurred_state == "planned"
    assert items[0].image_candidate is False


def test_model_no_memory_and_empty_batch(service, monkeypatch):
    for payload in [{"items": []}, model_item("今天很开心", kind="no_memory", key="other", value="", state="uncertain")]:
        provider(monkeypatch, json.dumps(payload, ensure_ascii=False))
        assert extract_candidates(service, "今天很开心", NOW, True)[0] == []


@pytest.mark.parametrize("text", [
    "今天下午和朋友在公园散步，看见秋天的银杏树，感觉特别放松。",
    "【模拟聊天】今天在公园散步。",
    "【模拟聊天】今天和朋友在公园散步，特别放松。",
    "【模拟聊天】今天第一次加入了一直想加入的项目组，特别开心！",
    "今天感觉很开心，努力了很久的项目终于结束了",
    "今天项目终于结束了，感觉很开心。",
])
def test_real_event_keeps_entire_narrative_and_emotion(service, text):
    items, _ = extract_candidates(service, text, NOW)
    assert len(items) == 1 and items[0].candidate_type == "life_event"
    assert items[0].canonical_text == items[0].evidence_quote == text


def test_plan_retains_negative_qualifier_and_punctuation(service):
    text = "明天带绿色 U 盘，不是银色的。"
    items, _ = extract_candidates(service, text, NOW)
    assert len(items) == 1 and items[0].candidate_type == "future_plan"
    assert items[0].canonical_text == items[0].evidence_quote == text
    assert items[0].occurred_state == "planned" and not items[0].image_candidate
    items, _ = extract_candidates(service, "明天项目就结束了", NOW)
    assert len(items) == 1 and items[0].candidate_type == "future_plan"


def test_restored_narrative_stops_at_uncertain_question_and_other_fact(service):
    text = "今天在公园散步，感觉很放松，但可能明天获奖。我的生日是五月一日。"
    items, _ = extract_candidates(service, text, NOW)
    event = next(i for i in items if i.candidate_type == "life_event")
    assert event.canonical_text == "今天在公园散步，感觉很放松"
    assert any(i.fact_key == "birthday" and i.value == "五月一日" for i in items)
    assert not any("可能" in i.evidence_quote for i in items)


@pytest.mark.parametrize("evidence", ["今天在公园散步", "今天在公园散步，看见银杏，感觉很放松。"])
def test_model_event_restores_safe_original_narrative(service, monkeypatch, evidence):
    text = "今天在公园散步，看见银杏，感觉很放松。"
    provider(monkeypatch, json.dumps(model_item(evidence, kind="life_event", key="other", value=""), ensure_ascii=False))
    items, _ = extract_candidates(service, text, NOW, True)
    assert len(items) == 1 and items[0].canonical_text == items[0].evidence_quote == text


def test_model_narrative_cannot_cover_uncertainty_or_hidden_assistant_source(service, monkeypatch):
    for text in ["今天在公园散步，但可能获奖。", "助手：今天在公园散步\n用户：今天很开心"]:
        provider(monkeypatch, json.dumps(model_item(text, kind="life_event", key="other", value=""), ensure_ascii=False))
        with pytest.raises(ValueError, match="MEMORY_UNGROUNDED_OUTPUT"):
            extract_candidates(service, text, NOW, True)


def test_use_llm_without_key_uses_rules(service, monkeypatch):
    service.settings.memory_llm_key = ""
    calls = provider(monkeypatch, "bad JSON")
    items, _ = extract_candidates(service, "我喜欢咖啡", NOW, True)
    assert len(items) == 1 and calls == []
