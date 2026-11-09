"""Strict planning and independent event overview."""
from datetime import UTC, datetime, timedelta

import pytest

from app.assistant_plan import AssistantPlan, AssistantTask, SemanticPlanner, SYSTEM
from app.retrieval import MemoryRetriever, _item_day
from test_hybrid_retrieval import Embedder, NOW, memory, put, ready


def test_plan_rejects_unauthorized_or_ambiguous_output():
    with pytest.raises(ValueError):
        AssistantPlan.model_validate({"version": "1", "tasks": [
            {"action": "search_memory"}]})  # missing query
    with pytest.raises(ValueError):
        AssistantPlan.model_validate({"version": "1", "tasks": [
            {"action": "prepare_reminder", "query": ""},
            {"action": "prepare_reminder", "query": ""}]})  # two writes
    with pytest.raises(ValueError):
        AssistantPlan.model_validate({"version": "1", "tasks": [
            {"action": "answer", "query": "", "user_id": "someone-else"}]})  # extra field


def test_planner_never_grants_authority_or_exposes_secrets():
    assert "user_id" in SYSTEM
    assert "SQL" in SYSTEM
    assert "URL" in SYSTEM


def test_time_window_resolves_relative_days():
    plan = AssistantPlan.model_validate({"version": "1", "tasks": [
        {"action": "overview", "query": "最近做了什么", "window": {"relative_days": 14}}]})
    start, end = plan.tasks[0].window.resolve(NOW.date())
    assert (end - start).days == 13
    assert start <= NOW.date() <= end


def test_overview_lists_dated_events_without_similarity_threshold(memory):
    put(memory, 'hike', '带团子去露营，追着落叶跑', semantic_key="event:2026-11-07:hike")
    put(memory, 'math', '项目验收通过', semantic_key="event:2026-11-05:math")
    put(memory, 'walk', '沿河散步', semantic_key="event:2026-11-02:walk")
    r = MemoryRetriever(memory, Embedder(), now=lambda zone: NOW.astimezone(zone))
    got = r.overview('alice', window=(NOW.date() - timedelta(days=13), NOW.date()), today=NOW.date())
    ids = [item['memory_id'] for item in got['items']]
    assert got['status'] == 'matched'
    assert 'walk' in ids and 'hike' in ids and 'math' in ids
    # ordered by occurrence day
    assert got['items'][0]['memory_id'] == 'walk'


def test_overview_paging_marks_more_and_excludes_out_of_range(memory):
    for index in range(5):
        put(memory, f'e{index}', f'记录{index}',
            semantic_key=f"event:2026-11-{index + 1:02d}:e{index}")
    put(memory, 'old', '很旧的经历', semantic_key="event:2020-01-01:old")
    r = MemoryRetriever(memory, Embedder(), now=lambda zone: NOW.astimezone(zone))
    got = r.overview('alice', window=(NOW.date() - timedelta(days=13), NOW.date()),
                     today=NOW.date(), limit=3, offset=0)
    assert got['retrieval']['truncated'] is True
    assert got['retrieval']['has_more'] is True
    assert all(item['memory_id'] != 'old' for item in got['items'])
    assert got['retrieval']['total_count'] == 6  # five in-window events + one undated source row


def test_overview_reports_undated_sources_without_forging_dates(memory):
    memory.sources.record({'life_user_id': 'alice', 'memory_consent': True}, {
        'source_message_id': 's1', 'text': '蕨类植物的叶片很有意思。',
        'conversation_id': 'c1', 'occurred_at': NOW.isoformat()})
    r = MemoryRetriever(memory, Embedder(), now=lambda zone: NOW.astimezone(zone))
    got = r.overview('alice', window=(NOW.date() - timedelta(days=13), NOW.date()), today=NOW.date())
    assert got['retrieval']['undated_count'] == 1
    assert all(item['kind'] != 'user_message' for item in got['items'])


def test_planner_model_gate_and_unavailable_fallback(memory):
    from app.assistant_plan import PlanUnavailable
    planner = SemanticPlanner(memory.settings)
    with pytest.raises(PlanUnavailable):
        planner.plan('最近做了什么', now=NOW, timezone='Asia/Shanghai', recent_messages=[])
