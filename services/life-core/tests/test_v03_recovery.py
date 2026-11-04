"""Stage A migration, multiprocess settlement, and crash recovery contracts."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context
from unittest.mock import patch
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.memory import MemoryService
from app.moments import MomentSettings, Moments
from app.moment_windows import LEGACY_ENDS
from app.recollection_scoring import VERSION, WEIGHTS
from app.store import Store
from test_v03_selection import scorer_fixture
from test_v03_windows import StageASettings, build, configure, instant, rows, seed
from test_memory_pipeline import auth


def settings_for(path, *, v03=True):
    return StageASettings(
        database_path=Path(path), internal_token="synthetic-internal",
        jwt_secret="synthetic-jwt", jwt_refresh_secret="synthetic-refresh",
        memos_base_url="http://memos.invalid", memos_api_token="",
        timezone="Asia/Hong_Kong", allowed_origins=(),
        moment_windows_v03=v03,
    )


def test_old_schema_migrates_twice_without_data_loss_and_rolls_back_safely(tmp_path):
    path = tmp_path / "migration.sqlite3"
    legacy = settings_for(path, v03=False)
    store = Store(path)
    store.initialize()
    memory = MemoryService(store, legacy)
    memory.initialize()
    old_moments = Moments(store, legacy, memory)
    user = store.bootstrap_user(
        librechat_user_id="legacy-user", memos_user_id="users/legacy",
        memos_username="legacy", display_name="Legacy",
        memory_consent=True, image_consent=True,
    )
    with patch("app.moments.utc_now", return_value="2026-11-03T00:00:00+00:00"):
        old_moments.configure(user, MomentSettings(
            enabled=True, ends=list(LEGACY_ENDS), timezone="Asia/Hong_Kong"))
    seed(memory, store, user, "今天下午在公园散步，看见晚霞。", "legacy-source",
         instant("2026-11-03T12:00:00+08:00"))
    old_moments.schedule(instant("2026-11-03T12:30:00+08:00"))
    before = rows(store)
    assert before and before[0]["local_date"] is None

    upgraded = settings_for(path)
    Moments(store, upgraded, memory)
    Moments(store, upgraded, memory)
    after = rows(store)
    assert after[0]["moment_id"] == before[0]["moment_id"]
    assert after[0]["window_start"] == before[0]["window_start"]
    migrated_config = Moments(store, upgraded, memory).config(user["life_user_id"])
    assert migrated_config["ends"] == ["11:00", "17:00", "24:00"]
    with store.connect() as db:
        indexes = {row["name"] for row in db.execute("PRAGMA index_list(moments)")}
        migrations = {row["name"] for row in db.execute("SELECT name FROM schema_migrations")}
        audits = [row[0] for row in db.execute(
            "SELECT actor FROM permission_audit WHERE user_id=?",
            (user["life_user_id"],),
        )]
    assert "idx_moment_business_key" in indexes
    assert "moment_windows_v03" in migrations
    assert "v03_night_coverage_migration" in audits

    rolled_back = Moments(store, legacy, memory)
    assert rolled_back.detail(user["life_user_id"], after[0]["moment_id"]) is not None
    assert rows(store)[0]["moment_id"] == before[0]["moment_id"]


def test_business_key_migration_reports_conflicts_without_deleting_rows(tmp_path):
    moments, user, store, _ = build(tmp_path)
    moments.schedule(instant("2026-11-03T12:00:00+08:00"))
    original = rows(store)[0]
    with store.connect() as db:
        db.execute("DROP INDEX idx_moment_business_key")
        columns = list(original)
        duplicate = dict(
            original, moment_id="legacy-duplicate",
            window_start="2026-11-03T00:00:00+00:00",
            window_end="2026-11-03T01:00:00+00:00",
            policy_version="legacy",
        )
        db.execute(
            f"INSERT INTO moments ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [duplicate[name] for name in columns],
        )
    Moments(store, moments.settings, moments.memory)
    assert len(rows(store)) == 2
    with store.connect() as db:
        conflicts = [dict(row) for row in db.execute(
            "SELECT * FROM moment_migration_conflicts")]
    assert len(conflicts) == 1
    assert "2026-11-03" in conflicts[0]["detail"]


def _schedule_worker(path, now):
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    from app.config import Settings
    from app.memory import MemoryService
    from app.moments import Moments
    from app.store import Store
    settings = Settings(
        database_path=Path(path), internal_token="synthetic-internal",
        jwt_secret="synthetic-jwt", jwt_refresh_secret="synthetic-refresh",
        memos_base_url="http://memos.invalid", memos_api_token="",
        timezone="Asia/Hong_Kong", allowed_origins=(),
        moment_windows_v03=True, moment_settlement_scan_limit=96,
    )
    store = Store(Path(path))
    memory = MemoryService(store, settings)
    Moments(store, settings, memory).schedule(datetime.fromisoformat(now))


def test_two_processes_settle_exactly_one_business_row(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。",
         "concurrent", instant("2026-11-03T09:00:00+08:00"))
    now = instant("2026-11-03T11:00:00+08:00").isoformat()
    context = get_context("spawn")
    with context.Pool(2) as pool:
        pool.starmap(_schedule_worker, [(str(store.database_path), now)] * 2)
    result = rows(store)
    assert len(result) == 1
    assert result[0]["local_date"] == "2026-11-03" and result[0]["slot"] == 0
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM recollection_candidates").fetchone()[0] == 1


def test_expired_claim_before_request_is_replayed_once(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。",
         "unrequested", instant("2026-11-03T09:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    with store.connect() as db:
        db.execute("""UPDATE moments SET status='scoring',score_claim_id='dead-worker',
            score_lease_until='2026-11-03T02:59:00+00:00'""")
    restarted = Moments(store, moments.settings, memory)
    restarted.scorer.transport = moments.scorer.transport
    assert restarted.score_one()
    assert len(calls) == 1
    # A++ keeps the text but does not infer image egress from the legacy boolean consent.
    assert rows(store)[0]["status"] == "private_text"


@pytest.mark.parametrize("call_status", ["running", "unknown"])
def test_expired_request_without_safe_result_is_never_resubmitted(tmp_path, call_status):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。",
         "unknown", instant("2026-11-03T09:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    identifier = rows(store)[0]["moment_id"]
    with store.connect() as db:
        db.execute("""UPDATE moments SET status='scoring',score_claim_id='dead-worker',
            score_lease_until='2026-11-03T02:59:00+00:00'""")
        db.execute("""INSERT INTO recollection_model_calls
            (window_id,user_id,model,version,input_hash,status,started_at,error_code)
            VALUES (?,?,'synthetic',?,'hash',?,?,'SCORING_RESULT_UNKNOWN')""",
            (identifier,user["life_user_id"],VERSION,call_status,
             "2026-11-03T03:00:00+00:00"))
    restarted = Moments(store, moments.settings, memory)
    assert restarted.score_one()
    assert not restarted.score_one()
    assert calls == []
    assert rows(store)[0]["status"] == "score_unknown"


def test_persisted_success_is_finalized_after_crash_without_second_request(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。",
         "cached", instant("2026-11-03T09:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    row = rows(store)[0]
    start, end = instant(row["window_start"]), instant(row["window_end"])
    inputs, _ = moments.candidate_inputs(user["life_user_id"], start, end)
    moments.scorer.settings = moments.settings
    ranked = moments.scorer.evaluate(
        user["life_user_id"], row["moment_id"], {"start":row["window_start"],"end":row["window_end"]},
        inputs, moments.config(user["life_user_id"])["weights"])
    assert calls == ["MOCK_SCORING"] and ranked
    with store.connect() as db:
        db.execute("""UPDATE moments SET status='scoring',score_claim_id='dead-after-success',
            score_lease_until='2026-11-03T02:59:00+00:00'""")
    restarted = Moments(store, moments.settings, memory)
    assert restarted.score_one()
    assert calls == ["MOCK_SCORING"]
    assert rows(store)[0]["status"] == "private_text"


def test_late_retelling_is_attached_to_selected_review_without_rescore(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天早上在公园跑了三公里，回来感觉精神很好。",
         "run-a", instant("2026-11-03T09:00:00+08:00"),
         occurred=instant("2026-11-03T09:00:00+08:00"))
    calls = scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    first = rows(store)[0]
    moments.schedule(instant("2026-11-03T11:05:00+08:00"))
    assert "late_evidence" not in moments.detail(
        user["life_user_id"], first["moment_id"]
    )["review"]
    seed(memory, store, user, "早晨在公园跑步三公里，真的很放松。",
         "run-b", instant("2026-11-03T10:59:59+08:00"),
         occurred=instant("2026-11-03T09:00:00+08:00"))
    moments.schedule(instant("2026-11-03T11:10:00+08:00"))
    result = rows(store)
    assert len(result) == 1 and result[0]["moment_id"] == first["moment_id"]
    detail = moments.detail(user["life_user_id"], first["moment_id"])
    selected = next(item for item in detail["review"]["candidates"]
                    if item["outcome"] == "SELECTED")
    assert len(selected["memory_ids"]) == 2
    assert {source["message_id"] for source in selected["sources"]} == {"run-a", "run-b"}
    assert len(detail["source_memory_ids"]) == 2
    assert calls == ["MOCK_SCORING"]
    assert "LATE_RETELLING_ATTACHED_WITHOUT_RESCORE" in detail["review"]["notes"]


def test_late_reconciliation_rotates_past_the_scan_limit(tmp_path):
    moments, user, store, memory = build(tmp_path)
    moments.settings = replace(moments.settings, moment_settlement_scan_limit=2)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    moments.schedule(instant("2026-11-03T16:05:00+08:00"))
    moments.schedule(instant("2026-11-04T00:05:00+08:00"))
    assert len(rows(store)) == 3

    seed(memory, store, user, "晚上在河边散步，看见很美的晚霞。", "late-night",
         instant("2026-11-03T20:00:00+08:00"))
    for minute in range(10, 30):
        moments.schedule(instant(f"2026-11-04T00:{minute:02}:00+08:00"))

    night = next(row for row in rows(store) if row["slot"] == 2)
    assert night["status"] == "awaiting_score"
    assert night["review_json"] and json.loads(night["review_json"])["late_evidence"] is True


def test_grouped_member_revision_change_revokes_stale_selection(tmp_path):
    moments, user, store, memory = build(tmp_path)
    for index, text in enumerate([
        "早上在公园跑了三公里，特别开心。",
        "早晨在公园跑步三公里，感觉很放松。",
    ]):
        seed(memory, store, user, text, f"revision-{index}",
             instant(f"2026-11-03T09:0{index}:00+08:00"))
    scorer_fixture(moments)
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    assert moments.score_one()
    identifier = rows(store)[0]["moment_id"]
    selected = json.loads(rows(store)[0]["source_memory_ids"])
    changed = sorted(selected)[-1]
    with store.connect() as db:
        db.execute(
            "UPDATE memory_items SET revision=revision+1 WHERE memory_id=?",
            (changed,),
        )
    detail = moments.detail(user["life_user_id"], identifier)
    assert detail["status"] == "cancelled"
    assert detail["caption"] == "" and detail["selection"] == [] and detail["review"] == {}


def test_authenticated_timezone_change_is_synchronized_into_v03_policy(tmp_path):
    settings = replace(
        settings_for(tmp_path / "api.sqlite3"),
        moment_workers_enabled=False,
        moment_scheduler_external=True,
        jwt_secret="test-jwt",
        jwt_refresh_secret="test-refresh",
    )
    app = create_app(settings)
    client = TestClient(app)
    with client:
        bootstrap = client.post(
            "/internal/v1/users/bootstrap",
            headers={"X-Internal-Token":"synthetic-internal"},
            json={
                "librechat_user_id":"timezone-user","memos_user_id":"users/timezone",
                "memos_username":"timezone","display_name":"Timezone",
                "memory_consent":True,"image_consent":True,
            },
        )
        assert bootstrap.status_code == 200
        user = app.state.store.get_user(bootstrap.json()["life_user_id"])
        with patch("app.moments.utc_now", return_value="2026-11-03T00:00:00+00:00"):
            app.state.moments.configure(user, MomentSettings(
                enabled=True, timezone="Asia/Hong_Kong"))
        response = client.patch(
            "/api/v1/me/settings",
            headers=auth("timezone-user"),
            json={"timezone":"America/New_York"},
        )
        assert response.status_code == 200
        assert response.json()["timezone"] == "America/New_York"
        assert app.state.moments.config(user["life_user_id"])["timezone"] == "America/New_York"
        with app.state.store.connect() as db:
            state = db.execute(
                "SELECT * FROM moment_schedule_state WHERE user_id=?",
                (user["life_user_id"],),
            ).fetchone()
        assert state["pending_timezone"] == "America/New_York"
        assert state["pending_effective_utc"]


def test_authenticated_image_revocation_keeps_v03_text_settlement(tmp_path):
    settings = replace(
        settings_for(tmp_path / "image-consent.sqlite3"),
        moment_workers_enabled=False,
        moment_scheduler_external=True,
        jwt_secret="test-jwt",
        jwt_refresh_secret="test-refresh",
    )
    app = create_app(settings)
    client = TestClient(app)
    with client:
        bootstrap = client.post(
            "/internal/v1/users/bootstrap",
            headers={"X-Internal-Token":"synthetic-internal"},
            json={
                "librechat_user_id":"image-off-user","memos_user_id":"users/image-off",
                "memos_username":"image-off","display_name":"Image Off",
                "memory_consent":True,"image_consent":True,
            },
        )
        assert bootstrap.status_code == 200
        user = app.state.store.get_user(bootstrap.json()["life_user_id"])
        with patch("app.moments.utc_now", return_value="2026-11-03T00:00:00+00:00"):
            app.state.moments.configure(user, MomentSettings(
                enabled=True, timezone="Asia/Hong_Kong"))
        seed(app.state.memory, app.state.store, user,
             "今天上午第一次参加公园读书活动，特别开心。", "text-only-api",
             instant("2026-11-03T09:00:00+08:00"))
        app.state.moments.schedule(instant("2026-11-03T11:00:00+08:00"))
        assert rows(app.state.store)[0]["status"] == "awaiting_score"
        with app.state.store.connect() as db:
            db.execute("""UPDATE moments SET image=?,mime='image/png',
                caption='保留文字',selection='[{"allowed":true}]'""",
                (b"synthetic-derived-image",))

        response = client.patch(
            "/api/v1/me/settings",
            headers=auth("image-off-user"),
            json={"image_consent":False},
        )
        assert response.status_code == 200
        row = rows(app.state.store)[0]
        assert row["status"] == "awaiting_score"
        assert row["image"] is None and row["mime"] is None
        assert row["caption"] == "保留文字"
        assert json.loads(row["selection"]) == [{"allowed":True}]
