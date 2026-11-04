"""The offline evaluation must not inflate metrics or silently spend twice."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from v03_semantic_eval import (
    BudgetLedger, gate_axes, pair_counts, selection_metrics, validate_axes,
)


def test_independent_and_retold_message_pairs_have_distinct_denominators():
    messages = [
        {"key": "a", "event": "run"}, {"key": "b", "event": "run"},
        {"key": "c", "event": "another"},
    ]
    assert pair_counts(messages, [["a", "c"], ["b"]]) == {
        "false_merges": 1, "independent_pairs": 2,
        "missed_merges": 1, "same_event_pairs": 1,
    }


def test_lower_rank_is_not_false_exclusion_and_failure_cannot_count_as_pass():
    case = {"acceptable": ["a", "b"], "required": ["a", "b"]}
    valid = selection_metrics(case, [
        {"event": "a", "eligible": True, "score": .8},
        {"event": "b", "eligible": True, "score": .7},
    ])
    assert valid["reasonable"] and valid["false_exclusions"] == 0
    failed = selection_metrics({"acceptable": [None], "required": []}, [], error="timeout")
    assert not failed["reasonable"]


def test_equal_score_preserves_p04_stable_candidate_order():
    metric = selection_metrics({"acceptable": ["a"], "required": []}, [
        {"event": "a", "eligible": True, "score": .8},
        {"event": "z", "eligible": True, "score": .8},
    ])
    assert metric["selected"] == "a"


def test_global_budget_is_atomic_and_cannot_refund_unknown_attempt(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", limit=1)
    def reserve(key):
        try:
            ledger.reserve(key, b"{}")
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, ["a", "b"])) == [False, True]
    restarted = BudgetLedger(tmp_path / "budget.sqlite3", limit=1)
    with pytest.raises(ValueError):
        restarted.reserve("c", b"{}")


def test_axes_reject_fabricated_visual_facts_and_unsafe_scene():
    candidates = [{"memory_id": "a", "sources": [
        {"message_id": "msg", "quote": "今天第一次真正接纳自己。"}
    ]}]
    entry = dict(memory_id="a", memorial="KEEP", memorial_reason="内在转折",
                 imageability="TEXT_ONLY", image_reason="无外部场景事实",
                 source_message_ids=["msg"], evidence_quote="第一次真正接纳自己",
                 visual_facts=[])
    assert validate_axes({"candidates": [entry]}, candidates)
    entry["visual_facts"] = ["在晴天公园穿运动服"]
    with pytest.raises(ValueError):
        validate_axes({"candidates": [entry]}, candidates)
    entry["visual_facts"] = []
    entry["imageability"] = "SAFE_SCENE"
    with pytest.raises(ValueError):
        validate_axes({"candidates": [entry]}, candidates)


def test_unverified_visual_phrase_downgrades_only_its_candidate_without_losing_text():
    inputs = [
        {"memory_id": "a", "sources": [
            {"message_id": "a-source", "quote": "今天独立修好了旧收音机。"}
        ]},
        {"memory_id": "b", "sources": [
            {"message_id": "b-source", "quote": "今天在阳台看到了兰花开花。"}
        ]},
    ]
    def value(identifier, quote, fact):
        return dict(memory_id=identifier, memorial="KEEP", memorial_reason="个人片段",
                    imageability="SAFE_SCENE", image_reason="具体动作",
                    source_message_ids=[identifier + "-source"], evidence_quote=quote,
                    visual_facts=[fact])
    body = {"candidates": [
        value("a", "独立修好了旧收音机", "独立修好收音机"),
        value("b", "在阳台看到了兰花开花", "兰花开花"),
    ]}
    grounded = gate_axes(body, inputs)
    assert grounded[0]["memorial"] == "KEEP"
    assert grounded[0]["imageability"] == "TEXT_ONLY"
    assert grounded[0]["visual_facts"] == []
    assert grounded[0]["gate_reason"] == "UNVERIFIED_VISUAL_FACT"
    assert grounded[1]["imageability"] == "SAFE_SCENE"
    assert grounded[1]["visual_facts"] == ["兰花开花"]
    assert body["candidates"][0]["visual_facts"] == ["独立修好收音机"]
