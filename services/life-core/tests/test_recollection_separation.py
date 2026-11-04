"""Production worker contracts on isolated SQLite; no external calls are allowed."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.moments import Moments
from app.recollection_policy import CONSENT_VERSION
from test_v03_selection import scorer_fixture
from test_v03_windows import build, instant, rows, seed


def test_s33_is_saved_locally_without_image_or_scoring_egress(tmp_path, monkeypatch):
    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    text = "今天我终于能说出对逝去亲人的思念，这是我自己的内心进展，只希望留下文字。"
    source = seed(memory, store, user, text, "grief", instant("2026-11-03T09:00:00+08:00"))
    store.update_consent(owner, image_consent=False)
    moments.settings = replace(moments.settings, moment_scoring_request_budget=10,
                               memory_llm_key="synthetic")
    monkeypatch.setattr(moments.scorer, "evaluate", lambda *_: pytest.fail("Unconsented scoring"))
    monkeypatch.setattr(moments, "generate", lambda *_: pytest.fail("Image forbidden"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    detail = moments.detail(owner, rows(store)[0]["moment_id"])
    assert detail["status"] == "private_text"
    assert detail["caption"] == text
    assert detail["source_memory_ids"] == [source["memory_id"]]
    assert detail["review"]["candidates"][0]["policy"]["egress_authorized"] is False
    assert detail["selection"] == []
    restarted = Moments(store, moments.settings, memory)
    assert restarted.detail(owner, detail["moment_id"])["caption"] == text
    assert restarted.score_one() is False
    assert restarted.run_one() is False
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0


def test_third_party_secret_cannot_be_automatically_memorialized(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "朋友今天私下告诉我他正在离婚，他让我保密。",
         "other-private", instant("2026-11-03T09:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    while moments.score_one():
        pass
    assert calls == []
    assert moments.list(user["life_user_id"]) == []
    assert all(not row["caption"] for row in rows(store))


def test_legacy_boolean_consents_do_not_authorize_scoring_egress(tmp_path, monkeypatch):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天第一次在公园跑完三公里，完成了个人训练目标。",
         "event", instant("2026-11-03T09:00:00+08:00"))
    moments.settings = replace(moments.settings, memory_llm_key="synthetic",
                               moment_scoring_request_budget=10)
    monkeypatch.setattr(moments.scorer, "evaluate", lambda *_: pytest.fail("Real egress forbidden"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    assert rows(store)[0]["error_code"] == "SCORING_EGRESS_NOT_AUTHORIZED"
    assert not moments.score_one()


def test_grants_are_owner_purpose_provider_and_version_scoped_and_survive_restart(tmp_path):
    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    assert not moments.egress_allowed(owner, "semantic_scoring", "deepseek")
    moments.set_egress_consent(owner, "semantic_scoring", "deepseek", True, CONSENT_VERSION)
    restarted = Moments(store, moments.settings, memory)
    assert restarted.egress_allowed(owner, "semantic_scoring", "deepseek")
    assert not restarted.egress_allowed(owner, "image_generation", "deepseek")
    assert not restarted.egress_allowed(owner, "semantic_scoring", "kolors")
    assert not restarted.egress_allowed("other-owner", "semantic_scoring", "deepseek")
    restarted.set_egress_consent(owner, "semantic_scoring", "deepseek", False, CONSENT_VERSION)
    assert not moments.egress_allowed(owner, "semantic_scoring", "deepseek")
    with pytest.raises(ValueError, match="CONSENT_VERSION_REQUIRED"):
        moments.set_egress_consent(owner, "semantic_scoring", "deepseek", True, "old")


def test_sensitive_self_text_needs_text_permission_but_never_image_permission(tmp_path):
    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    text = "今天医生告知了我的检查诊断，我决定认真治疗，只想私下记录这个决定。"
    item = seed(memory, store, user, text, "self-health", instant("2026-11-03T09:00:00+08:00"))
    with store.connect() as db:
        db.execute("UPDATE memory_items SET sensitivity='sensitive' WHERE memory_id=?", (item["memory_id"],))
    assert not moments.sources_authorized(owner, [item["memory_id"]])
    memory.set_permissions(owner, {"sensitive_consent": True})
    assert moments.sources_authorized(owner, [item["memory_id"]])
    assert not moments.image_authorized(owner, [item["memory_id"]])
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    detail = moments.detail(owner, rows(store)[0]["moment_id"])
    assert detail["caption"] == text and detail["status"] == "private_text"
    memory.set_permissions(owner, {"sensitive_consent": False})
    assert moments.detail(owner, detail["moment_id"])["caption"] == ""


def test_cached_s33_result_keeps_all_original_dimensions_and_score(tmp_path, monkeypatch):
    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    seed(memory, store, user,
         "今天我终于能说出对逝去亲人的思念，这是我自己的内心进展，只希望留下文字。",
         "grief", instant("2026-11-03T09:00:00+08:00"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    original = json.loads((Path(__file__).resolve().parents[3]
        / "evidence/v03-stage-a-plus/baseline/S33.json").read_text(encoding="utf-8"))["values"][0]
    inputs, _ = moments.candidate_inputs(owner, instant(rows(store)[0]["window_start"]),
                                         instant(rows(store)[0]["window_end"]))
    cached = {**original, "memory_id": inputs[0]["memory_id"],
              "source_revision": inputs[0]["revision"], "input_hash": inputs[0]["input_hash"]}
    monkeypatch.setattr(moments.scorer, "cached_result", lambda *_: [cached])
    monkeypatch.setattr(moments.scorer, "evaluate", lambda *_: pytest.fail("Must reuse result"))
    assert moments.score_one()
    detail = moments.detail(owner, rows(store)[0]["moment_id"])
    value = detail["selection"][0]
    assert value["score"] == original["score"]
    assert value["dimensions"] == original["dimensions"]
    assert value["eligible"] is False
    assert detail["review"]["candidates"][0]["policy"]["memorial_eligible"] is True
    assert detail["caption"]
