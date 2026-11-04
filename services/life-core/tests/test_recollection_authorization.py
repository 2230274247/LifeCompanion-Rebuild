"""Purpose grants and the final network boundary; offline transports only."""
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.moments import Moments, _ScoringEgressTransport
from app.recollection_policy import CONSENT_VERSION, assess_candidate, validate_judgment
from app.recollection_scoring import ScoringFailed
from app.config import Settings
from test_api import bootstrap
from test_memory_pipeline import auth
from test_v03_selection import scorer_fixture
from test_v03_windows import build, instant, rows, seed


def test_grant_api_requires_authenticated_owner_explicit_provider_and_version(tmp_path):
    app = create_app(Settings(
        database_path=tmp_path / "life.db", internal_token="test-internal",
        jwt_secret="test-jwt", jwt_refresh_secret="test-refresh",
        memos_base_url="http://memos.invalid", memos_api_token="test-memos",
        timezone="Asia/Hong_Kong", allowed_origins=("http://localhost:3001",),
        moment_windows_v03=True, moment_workers_enabled=False,
        moment_image_generation_enabled=False,
    ))
    with TestClient(app) as client:
        first = bootstrap(client)
        second = bootstrap(client, "lc-user-b", "users/b")
        route = "/api/v1/moment-egress-consents/semantic_scoring"
        body = {"provider": "deepseek", "granted": True, "consent_version": CONSENT_VERSION}
        assert client.put(route, json=body).status_code == 401
        assert client.put(route, headers=auth(), json={**body, "user_id":second["life_user_id"]}).status_code == 422
        assert client.put(route, headers=auth(), json={**body, "provider":"kolors"}).status_code == 422
        assert client.put(route, headers=auth(), json={**body, "consent_version":"old"}).status_code == 422
        assert client.put(route, headers=auth(), json=body).status_code == 200
        assert app.state.moments.egress_allowed(first["life_user_id"],"semantic_scoring","deepseek")
        assert not app.state.moments.egress_allowed(second["life_user_id"],"semantic_scoring","deepseek")
        assert not app.state.moments.egress_allowed(first["life_user_id"],"image_generation","kolors")
        response = client.put(route, headers=auth(), json={**body,"granted":False})
        assert response.status_code == 200
        assert not app.state.moments.egress_allowed(first["life_user_id"],"semantic_scoring","deepseek")


def test_aplusplus_schema_upgrade_preserves_stage_a_rows(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天在公园跑了三公里，完成了训练目标。",
         "schema-upgrade", instant("2026-11-03T09:00:00+08:00"))
    scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    with store.connect() as db:
        moment_ids = [row[0] for row in db.execute("SELECT moment_id FROM moments")]
        candidate_ids = [row[0] for row in db.execute(
            "SELECT memory_id FROM recollection_candidates")]
        db.execute("DROP TABLE recollection_egress_consents")
        db.execute("ALTER TABLE recollection_candidates DROP COLUMN policy_json")

    Moments(store, moments.settings, memory)
    Moments(store, moments.settings, memory)

    with store.connect() as db:
        columns = {row["name"] for row in db.execute(
            "PRAGMA table_info(recollection_candidates)")}
        tables = {row["name"] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert [row[0] for row in db.execute("SELECT moment_id FROM moments")] == moment_ids
        assert [row[0] for row in db.execute(
            "SELECT memory_id FROM recollection_candidates")] == candidate_ids
        assert [row[0] for row in db.execute(
            "SELECT policy_json FROM recollection_candidates")] == [
                "{}" for _ in candidate_ids
            ]
    assert "policy_json" in columns
    assert "recollection_egress_consents" in tables


def test_final_transport_rechecks_revocation_and_trusted_endpoint_before_network():
    transport = _ScoringEgressTransport(lambda: False)
    transport.delegate = httpx.MockTransport(lambda _: pytest.fail("Unconsented network"))
    request = httpx.Request("POST","https://api.deepseek.com/v1/chat/completions")
    with pytest.raises(ScoringFailed, match="EGRESS_REVOKED"):
        transport.handle_request(request)
    allowed = _ScoringEgressTransport(lambda: True)
    allowed.delegate = httpx.MockTransport(lambda _: pytest.fail("Untrusted destination"))
    with pytest.raises(ScoringFailed, match="UNTRUSTED"):
        allowed.handle_request(httpx.Request("POST","https://untrusted.invalid/v1/chat/completions"))
    transport.close()
    allowed.close()


def test_privacy_or_non_event_sources_cannot_become_visual_facts_by_copying_substring():
    for text, span, kind in (
        ("今天不是晴天。", "晴天", "WEATHER"),
        ("今天我没穿红衣。", "穿红衣", "CLOTHING"),
        ("我不知道是否下雨。", "下雨", "WEATHER"),
        ("这是AI生成的故事：今天在公园跑步。", "在公园跑步", "ACTION"),
    ):
        candidate = {"memory_id":"m1", "sources":[{"message_id":"q","quote":text}]}
        value = {
            "occurrence":"SELF_OCCURRED","memorial":"KEEP_PRIVATE_TEXT",
            "imageability":"SAFE_SCENE","egress_preference":"UNSPECIFIED",
            "memorial_reason":"fixture","image_reason":"fixture",
            "visual_facts":[{"fact_type":kind,"statement":span,"source_span":span,
                             "source_message_ids":["q"]}],
        }
        with pytest.raises(ValueError, match="VISUAL_FACT_UNSUPPORTED"):
            validate_judgment(value,candidate)


def test_existing_queued_v03_row_without_policy_cannot_use_legacy_image_generator(tmp_path, monkeypatch):
    moments, user, store, memory = build(tmp_path)
    item = seed(memory,store,user,"今天在公园跑了三公里，完成了第一次训练目标。",
                "safe",instant("2026-11-03T09:00:00+08:00"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    with store.connect() as db:
        db.execute("""UPDATE moments SET status='queued',caption='original-source-caption',
            source_memory_ids=?""", ('["'+item["memory_id"]+'"]',))
    moments.settings = replace(moments.settings,moment_image_generation_enabled=True)
    monkeypatch.setattr(moments,"generate",lambda _:pytest.fail("Legacy provider must not be called"))
    assert moments.run_one()
    assert rows(store)[0]["status"] == "private_text"
    assert rows(store)[0]["caption"] == "original-source-caption"
    assert rows(store)[0]["attempts"] == 0


def test_image_consent_withdrawal_clears_image_but_keeps_private_text(tmp_path):
    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    text = "今天在公园跑了三公里，完成了第一次训练目标。"
    item = seed(memory, store, user, text, "image-clear",
                instant("2026-11-03T09:00:00+08:00"))
    scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    with store.connect() as db:
        moment_id = db.execute("SELECT moment_id FROM moments").fetchone()[0]
        db.execute("""UPDATE moments SET status='generated',image=?,mime='image/png'
            WHERE moment_id=?""", (b"synthetic-image", moment_id))

    moments.clear_images(owner)

    with store.connect() as db:
        row = db.execute("SELECT * FROM moments WHERE moment_id=?",
                         (moment_id,)).fetchone()
    assert row["status"] == "private_text"
    assert row["image"] is None and row["mime"] is None
    assert row["caption"] == text
    assert row["source_memory_ids"] == f'["{item["memory_id"]}"]'


def test_local_assessment_does_not_treat_goal_plan_word_as_future():
    value = assess_candidate({"memory_id":"m1","sources":[{
        "message_id":"q","quote":"今天是减肥计划第一天，跑步已完成，我想记住这个开始。",
    }]})
    assert value["occurrence"] == "SELF_OCCURRED"
