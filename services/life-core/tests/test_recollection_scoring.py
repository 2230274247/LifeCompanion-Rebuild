"""Scoring and privacy contracts; HTTP fixtures are not cloud acceptance evidence."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
import pytest

from app.moments import MomentSettings, Moments
from app.recollection_scoring import RecollectionScorer, ScoringBlocked, ScoringFailed, WEIGHTS, validate_scores

from test_api import make_app
from test_memory_pipeline import auth
from test_v023_moments import prepare, save, structured_scoring_fixture, score_pending


def test_recollection_spending_is_disabled_by_default(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        assert getattr(app.state.settings, "moment_scoring_request_budget", None) == 0


def test_new_life_event_preserves_exact_evidence_quote(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app, client, monkeypatch)
        text = "今天第一次在公园散步，看见银杏，特别开心。"
        save(client, text, "quoted-source", start + timedelta(minutes=1))
        with app.state.store.connect() as db:
            row = db.execute("SELECT evidence_quote FROM memory_evidence WHERE user_id=?", (owner,)).fetchone()
        assert row and row["evidence_quote"] and row["evidence_quote"] in text


def test_no_model_budget_never_falls_back_to_keyword_selection(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app, client, monkeypatch)
        save(client, "今天第一次在公园散步，看见银杏，特别开心。", "no-budget", start + timedelta(minutes=1))
        app.state.moments.schedule(datetime.now(timezone.utc) + timedelta(days=1))
        assert app.state.moments.score_one()
        rows = app.state.moments.list(owner)
        assert len(rows) == 1 and rows[0]["status"] == "blocked_scoring"
        assert rows[0]["source_memory_ids"] == [] and rows[0]["caption"] == ""
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0


def one_input():
    return [{"memory_id":"event-a","text":"An occurred event","occurred_at":"2026-11-04",
             "sources":[{"message_id":"source-a","quote":"My exact source quote"}],
             "revision":1,"input_hash":"synthetic-hash"}]


def one_output():
    return {"candidates":[{"memory_id":"event-a","eligible":True,
        "dimensions":{key:1. for key in WEIGHTS},"reason_code":"MEANINGFUL_EVENT",
        "source_message_ids":["source-a"],"evidence_quote":"exact source quote"}]}


@pytest.mark.parametrize("field,value,reason", [
    ("privacy_suitability",.8,"PRIVATE_OR_SENSITIVE"),
    ("personal_meaning",.2,"LOW_PERSONAL_MEANING"),
    ("source_sufficiency",.7,"SOURCE_INSUFFICIENT"),
    ("novelty_or_development",.1,"DUPLICATE_EVENT"),
])
def test_high_emotion_does_not_override_quality_gates(field,value,reason):
    output = one_output()
    output["candidates"][0]["dimensions"][field] = value
    ranked = validate_scores(output,one_input(),WEIGHTS)
    assert not ranked[0]["eligible"] and ranked[0]["reason_code"] == reason


@pytest.mark.parametrize("change", ["foreign_source","fabricated_quote","missing_candidate","duplicate_candidate"])
def test_untrusted_scores_must_match_exact_sources_and_candidate_set(change):
    output = one_output()
    if change == "foreign_source":
        output["candidates"][0]["source_message_ids"] = ["someone-else"]
    elif change == "fabricated_quote":
        output["candidates"][0]["evidence_quote"] = "A fabricated person"
    elif change == "missing_candidate":
        output["candidates"] = []
    else:
        output["candidates"] *= 2
    with pytest.raises(ScoringFailed):
        validate_scores(output,one_input(),WEIGHTS)


def test_old_four_weights_migrate_without_giving_memory_importance_to_model():
    config = MomentSettings(weights={"importance":.5,"uniqueness":.2,"emotion":.2,"completeness":.1})
    assert config.weights == WEIGHTS


def test_persistent_request_cap_is_atomic_across_windows_and_restarts(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        settings = replace(app.state.settings,memory_llm_key="synthetic",moment_scoring_request_budget=1)
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(one_output())}}],
                                           "usage":{"prompt_tokens":123,"completion_tokens":45}})
        scorer = RecollectionScorer(app.state.store,settings,transport=httpx.MockTransport(respond))
        def evaluate(window):
            try:
                scorer.evaluate("owner",window,{},one_input(),WEIGHTS)
                return "ok"
            except ScoringBlocked:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(evaluate,["window-a","window-b"])) == ["blocked","ok"]
        restarted = RecollectionScorer(app.state.store,settings,transport=httpx.MockTransport(respond))
        with pytest.raises(ScoringBlocked):
            restarted.evaluate("owner","new-window",{},one_input(),WEIGHTS)
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM recollection_model_calls").fetchone()
            assert row["input_tokens"] == 123 and row["output_tokens"] == 45
            with pytest.raises(ScoringBlocked):
                restarted.evaluate("owner",row["window_id"],{},one_input(),WEIGHTS)
        assert len(requests) == 1


@pytest.mark.parametrize("failure", ["timeout","server","bad_json","array","bad_usage","bad_choice","truncated"])
def test_failed_or_unknown_provider_results_never_automatically_repeat(tmp_path,failure):
    app, client = make_app(tmp_path)
    with client:
        settings = replace(app.state.settings,memory_llm_key="synthetic",moment_scoring_request_budget=2)
        requests = []
        def respond(request):
            requests.append(request)
            if failure == "timeout":
                raise httpx.ReadTimeout("synthetic")
            if failure == "server":
                return httpx.Response(503)
            if failure == "bad_json":
                return httpx.Response(200,text="invalid")
            if failure == "array":
                return httpx.Response(200,json=[])
            if failure == "bad_choice":
                return httpx.Response(200,json={"choices":[1]})
            return httpx.Response(200,json={"choices":[{"finish_reason":"length" if failure == "truncated" else "stop",
                "message":{"content":"invalid"}}],"usage":[1] if failure == "bad_usage" else {}})
        scorer = RecollectionScorer(app.state.store,settings,transport=httpx.MockTransport(respond))
        with pytest.raises(ScoringFailed):
            scorer.evaluate("owner","window-a",{},one_input(),WEIGHTS)
        with pytest.raises(ScoringBlocked):
            scorer.evaluate("owner","window-a",{},one_input(),WEIGHTS)
        assert len(requests) == 1
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM recollection_model_calls").fetchone()
            assert row["status"] == ("unknown" if failure in ("timeout","server") else "failed")
            assert "synthetic" not in row["error_code"]


def test_missing_legacy_quote_skips_without_backfill_or_provider_call(tmp_path,monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"今天第一次在公园散步，看见银杏，特别开心。","legacy",start+timedelta(minutes=1))
        with app.state.store.connect() as db:
            db.execute("UPDATE memory_evidence SET evidence_quote=''")
        moments = structured_scoring_fixture(app,monkeypatch)
        moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        assert not moments.score_one() and moments.list(owner) == []
        with app.state.store.connect() as db:
            assert db.execute("SELECT reason_code FROM recollection_candidates").fetchone()[0] == "SOURCE_QUOTE_MISSING"
            assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0
            assert db.execute("SELECT evidence_quote FROM memory_evidence").fetchone()[0] == ""


def test_three_persisted_candidates_select_at_most_one_and_restart_does_not_rescore(tmp_path,monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        for index, source in enumerate(("ordinary","emotion","special")):
            save(client,f"今天第一次在第{index}个公园散步，看见银杏，特别开心。",source,start+timedelta(minutes=index+1))
        moments = structured_scoring_fixture(app,monkeypatch)
        moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        score_pending(moments)
        rows = moments.list(owner)
        assert len(rows) == 1 and len(rows[0]["source_memory_ids"]) == 1
        with app.state.store.connect() as db:
            candidates = db.execute("SELECT * FROM recollection_candidates ORDER BY score DESC").fetchall()
            assert len(candidates) == 3 and sum(row["selected"] for row in candidates) == 1
            assert candidates[0]["selected"] and "special" in candidates[0]["source_message_ids"]
            assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 1
        restarted = Moments(app.state.store,moments.settings,app.state.memory)
        assert not restarted.score_one()
        assert restarted.run_one()
        assert restarted.detail(owner,rows[0]["moment_id"])["status"] == "pending_provider"


@pytest.mark.parametrize("change", ["consent","revision","delete_job"])
def test_inflight_scoring_cannot_revive_withdrawn_or_changed_content(tmp_path,monkeypatch,change):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"今天第一次在公园散步，看见银杏，特别开心。","event",start+timedelta(minutes=1))
        moments = structured_scoring_fixture(app,monkeypatch)
        moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        identifier = moments.list(owner)[0]["moment_id"]
        original_transport = moments.scorer.transport
        def respond(request):
            if change == "consent":
                client.patch("/api/v1/me/settings",headers=auth(),json={"image_consent":False}).raise_for_status()
            elif change == "revision":
                with app.state.store.connect() as db:
                    db.execute("UPDATE memory_items SET revision=revision+1 WHERE user_id=?",(owner,))
            else:
                moments.delete(owner,identifier)
            return original_transport.handle_request(request)
        moments.scorer.transport = httpx.MockTransport(respond)
        assert moments.score_one()
        detail = moments.detail(owner,identifier)
        assert detail["status"] == "cancelled" and not detail["caption"] and not detail["selection"]
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM recollection_candidates").fetchone()[0] == 0
        assert not moments.score_one()


def test_withdrawing_an_unscored_legacy_source_does_not_publish_an_empty_card(tmp_path,monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"今天第一次在公园散步，看见银杏，特别开心。","legacy",start+timedelta(minutes=1))
        with app.state.store.connect() as db:
            memory_id = db.execute("SELECT memory_id FROM memory_items").fetchone()[0]
            db.execute("UPDATE memory_evidence SET evidence_quote=''")
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        app.state.moments.withdraw_source(owner,memory_id)
        assert app.state.moments.list(owner) == []
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM recollection_candidates").fetchone()[0] == 0
