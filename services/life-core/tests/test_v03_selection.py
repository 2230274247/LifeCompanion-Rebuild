"""Grounded event grouping and owner-readable selection explanations."""
from dataclasses import replace
import json

import httpx
import pytest

from app.moments import Moments
from app.recollection_scoring import WEIGHTS
from test_v03_windows import build, instant, rows, seed


def test_retellings_merge_and_preserve_all_original_quotes(tmp_path):
    moments, user, store, memory = build(tmp_path)
    messages = [
        ("run-a", "今天早上在公园跑了三公里，回来感觉精神很好。"),
        ("run-b", "早晨在公园跑步三公里，真的很放松。"),
        ("run-c", "刚才那次跑步，回来之后我还觉得很开心。"),
    ]
    originals = []
    for minute, (source, text) in enumerate(messages):
        originals.append(seed(memory, store, user, text, source,
                              instant(f"2026-11-03T09:0{minute}:00+08:00"),
                              occurred=instant("2026-11-03T09:00:00+08:00")))
    inputs, rejected = moments.candidate_inputs(user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"), instant("2026-11-03T11:00:00+08:00"))
    assert not rejected and len(inputs) == 1
    assert set(inputs[0]["memory_ids"]) == {m["memory_id"] for m in originals}
    assert {s["message_id"]: s["quote"] for s in inputs[0]["sources"]} == dict(messages)
    with store.connect() as db:
        assert {r[0]: r[1] for r in db.execute("SELECT message_id,evidence_quote FROM memory_evidence")} == dict(messages)


@pytest.mark.parametrize("second", [
    "今天早上又在公园跑了三公里，这是第二次。",
    "今天下午在公园跑了三公里，回来感觉精神很好。",
    "今天早上在另一座公园跑了三公里，回来感觉精神很好。",
])
def test_similar_but_independent_occurrences_do_not_merge(tmp_path, second):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天早上在公园跑了三公里，回来感觉精神很好。", "first",
         instant("2026-11-03T09:00:00+08:00"))
    seed(memory, store, user, second, "second", instant("2026-11-03T15:00:00+08:00"))
    inputs, _ = moments.candidate_inputs(user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"), instant("2026-11-04T00:00:00+08:00"))
    assert len(inputs) == 2


def test_ambiguous_same_topic_is_not_silently_merged(tmp_path):
    moments, user, store, memory = build(tmp_path)
    for index, text in enumerate(["今天跑步了，感觉很好。", "今天去跑步，真开心。"]):
        seed(memory, store, user, text, f"run-{index}", instant(f"2026-11-03T09:0{index}:00+08:00"))
    inputs, _ = moments.candidate_inputs(user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"), instant("2026-11-03T11:00:00+08:00"))
    assert len(inputs) == 2


def test_same_text_anchors_far_apart_are_independent_occurrences(tmp_path):
    moments, user, store, memory = build(tmp_path)
    first = seed(memory, store, user, "今天早上在公园跑了三公里，回来精神很好。",
                 "far-a", instant("2026-11-03T09:00:00+08:00"),
                 occurred=instant("2026-11-03T07:30:00+08:00"))
    second = seed(memory, store, user, "今天早上在公园跑了三公里，脚有点酸。",
                  "far-b", instant("2026-11-03T15:00:00+08:00"),
                  occurred=instant("2026-11-03T14:30:00+08:00"))
    inputs, _ = moments.candidate_inputs(user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"), instant("2026-11-04T00:00:00+08:00"))
    assert {item["memory_id"] for item in inputs} == {
        first["memory_id"], second["memory_id"]
    }


def test_same_morning_similar_runs_hours_apart_are_independent_occurrences(tmp_path):
    moments, user, store, memory = build(tmp_path)
    first = seed(
        memory, store, user,
        "今天早上在公园跑了三公里，回来精神很好。",
        "same-morning-a",
        instant("2026-11-03T08:00:00+08:00"),
        occurred=instant("2026-11-03T08:00:00+08:00"),
    )
    second = seed(
        memory, store, user,
        "今天早上在公园跑了三公里，脚有点酸。",
        "same-morning-b",
        instant("2026-11-03T09:30:00+08:00"),
        occurred=instant("2026-11-03T09:30:00+08:00"),
    )
    inputs, _ = moments.candidate_inputs(
        user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"),
        instant("2026-11-03T11:00:00+08:00"),
    )
    assert {item["memory_id"] for item in inputs} == {
        first["memory_id"], second["memory_id"]
    }


def test_ambiguous_bridge_does_not_transitively_merge_all_occurrences(tmp_path):
    moments, user, store, memory = build(tmp_path)
    messages = [
        ("bridge-a", "今天早上在公园跑了三公里，回来精神很好。", "08:00"),
        ("bridge-b", "今天早上在公园跑了三公里，感觉轻松。", "08:20"),
        ("bridge-c", "今天早上在公园跑了三公里，脚有点酸。", "08:40"),
    ]
    seeded = [
        seed(
            memory,
            store,
            user,
            text,
            source,
            instant(f"2026-11-03T{clock}:00+08:00"),
            occurred=instant(f"2026-11-03T{clock}:00+08:00"),
        )
        for source, text, clock in messages
    ]
    inputs, _ = moments.candidate_inputs(
        user["life_user_id"],
        instant("2026-11-03T00:00:00+08:00"),
        instant("2026-11-03T11:00:00+08:00"),
    )
    assert len(inputs) == 2
    assert set(inputs[0]["memory_ids"]) == {
        seeded[0]["memory_id"], seeded[1]["memory_id"]
    }
    assert inputs[1]["memory_ids"] == [seeded[2]["memory_id"]]


def scorer_fixture(moments, ratings=None, requests=None):
    calls = []
    moments.settings = replace(moments.settings, memory_llm_key="synthetic",
                               moment_scoring_request_budget=10)
    def respond(request):
        calls.append("MOCK_SCORING")
        if requests is not None:
            requests.append(request)
        inputs = json.loads(json.loads(request.content)["messages"][1]["content"])["candidates"]
        output = []
        for item in inputs:
            source = item["sources"][0]
            value = (ratings or {}).get(source["message_id"], .95)
            dimensions = dict.fromkeys(WEIGHTS, value)
            dimensions.update(privacy_suitability=1., source_sufficiency=1.,
                              event_clarity=1., window_relevance=1.)
            output.append({
                "memory_id": item["memory_id"], "eligible": value >= .4,
                "dimensions": dimensions,
                "reason_code": "MEANINGFUL_EVENT" if value >= .4 else "ROUTINE_EVENT",
                "source_message_ids": [s["message_id"] for s in item["sources"]],
                "evidence_quote": source["quote"],
            })
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps({"candidates": output})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100}})
    moments.scorer.transport = httpx.MockTransport(respond)
    return calls


def test_grouped_retelling_context_is_explicit_to_p04_scorer(tmp_path):
    moments, user, store, memory = build(tmp_path)
    for index, text in enumerate([
        "今天早上在公园跑了三公里，回来感觉精神很好。",
        "早晨在公园跑步三公里，真的很放松。",
        "今天上午在公园跑了三公里，特别开心。",
    ]):
        seed(memory, store, user, text, f"run-{index}",
             instant(f"2026-11-03T09:0{index}:00+08:00"))
    requests = []
    scorer_fixture(moments, requests=requests)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    body = json.loads(requests[0].content)
    assert "same_occurrence_retellings" in body["messages"][0]["content"]
    candidates = json.loads(body["messages"][1]["content"])["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["same_occurrence_retellings"] == 3


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_day_selects_zero_to_three_events_and_explains_each_window(tmp_path, count):
    moments, user, store, memory = build(tmp_path)
    for index in range(count):
        seed(memory, store, user, f"今天在第{index}处参加了第一次纪念活动，特别开心。",
             f"source-{index}", instant(f"2026-11-03T{[9, 12, 20][index]:02}:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-04T00:05:00+08:00"))
    while moments.score_one():
        pass
    result = rows(store)
    assert len(result) == 3
    assert sum(bool(json.loads(r["source_memory_ids"])) for r in result) == count
    assert len(calls) == count
    for row in result:
        detail = moments.detail(user["life_user_id"], row["moment_id"])
        assert "review" in detail and detail["review"]["decision"]
        assert detail["image_data"] is None


def test_running_beats_breakfast_and_other_candidates_have_reasons(tmp_path):
    moments, user, store, memory = build(tmp_path)
    messages = [
        ("running", "今天第一次参加公园三公里跑步，完成后特别开心。"),
        ("breakfast", "今天早上吃了普通早餐。"),
        ("reading", "今天早上读完了这本书，特别有感触。"),
    ]
    for index, (source, text) in enumerate(messages):
        seed(memory, store, user, text, source, instant(f"2026-11-03T09:0{index}:00+08:00"))
    scorer_fixture(moments, {"running": .95, "breakfast": .2, "reading": .7})
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    review = moments.detail(user["life_user_id"], rows(store)[0]["moment_id"])["review"]
    assert review["decision"] == "SELECTED"
    by_source = {r["sources"][0]["message_id"]: r for r in review["candidates"]}
    assert by_source["running"]["outcome"] == "SELECTED"
    assert by_source["breakfast"]["outcome"] == "EXCLUDED"
    assert by_source["reading"]["outcome"] == "NOT_SELECTED"
    assert by_source["reading"]["reason_code"] == "LOWER_RANK"
    assert all(set(r["dimensions"]) == set(WEIGHTS) for r in review["candidates"])
    assert {r["sources"][0]["message_id"]: r["sources"][0]["quote"] for r in review["candidates"]} == dict(messages)


def test_all_members_of_selected_event_are_reserved_across_windows(tmp_path):
    moments, user, store, memory = build(tmp_path)
    for index, text in enumerate(["早上在公园跑了三公里，特别开心。", "早晨在公园跑步三公里，感觉很放松。"]):
        seed(memory, store, user, text, f"run-{index}", instant(f"2026-11-03T09:0{index}:00+08:00"))
    scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    assert len(json.loads(rows(store)[0]["source_memory_ids"])) == 2


def test_late_extraction_is_attached_to_its_already_settled_source_window(tmp_path):
    moments, user, store, memory = build(tmp_path)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert rows(store)[0]["status"] == "skipped"
    seed(memory, store, user, "今天上午第一次在公园跑步，特别开心。", "late",
         instant("2026-11-03T10:59:59+08:00"))
    moments.schedule(instant("2026-11-03T11:10:00+08:00"))
    assert len(rows(store)) == 1 and rows(store)[0]["status"] == "awaiting_score"


def test_restart_keeps_fresh_scoring_claim_and_never_resubmits_unknown(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。", "source",
         instant("2026-11-03T09:00:00+08:00"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    with store.connect() as db:
        db.execute("""UPDATE moments SET status='scoring',score_claim_id='live-worker',
            score_lease_until='2099-01-01T00:00:00+00:00'""")
    Moments(store, moments.settings, memory)
    assert rows(store)[0]["status"] == "scoring"
