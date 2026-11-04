"""Stage A uses synthetic SQLite files and fixed clocks, never a cloud API."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from io import BytesIO
import json
import sqlite3

import pytest
from PIL import Image

from app.config import Settings
from app.image_provider import validate_image_bytes
from app.memory import Candidate, MemoryService
from app.moments import MomentSettings, Moments
from app.recollection_policy import CONSENT_VERSION
from app.store import Store


UTC = timezone.utc


def instant(value):
    return datetime.fromisoformat(value).astimezone(UTC)


@dataclass(frozen=True)
class StageASettings(Settings):
    moment_windows_v03: bool = True
    moment_settlement_scan_limit: int = 96
    moment_score_lease_seconds: int = 120
    moment_scheduler_external: bool = False
    moment_image_generation_enabled: bool = False
    moment_workers_enabled: bool = False


def build(tmp_path, *, zone="Asia/Hong_Kong", start="2026-11-03T00:00:00+08:00"):
    settings = StageASettings(
        database_path=tmp_path / "stage-a.sqlite3", internal_token="synthetic-internal",
        jwt_secret="synthetic-jwt", jwt_refresh_secret="synthetic-refresh",
        memos_base_url="http://memos.invalid", memos_api_token="", timezone=zone,
        allowed_origins=(),
    )
    store = Store(settings.database_path)
    store.initialize()
    memory = MemoryService(store, settings)
    memory.initialize()
    moments = Moments(store, settings, memory)
    user = store.bootstrap_user(
        librechat_user_id="synthetic-a", memos_user_id="users/a", memos_username="a",
        display_name="Synthetic A", memory_consent=True, image_consent=True,
    )
    configure(moments, user, instant(start), timezone=zone)
    return moments, user, store, memory


def configure(moments, user, now, **changes):
    config = {k: v for k, v in moments.config(user["life_user_id"]).items()
              if k in MomentSettings.model_fields}
    config.update(enabled=True, **changes)
    with patch("app.moments.utc_now", return_value=now.isoformat()):
        return moments.configure(user, MomentSettings(**config))


def rows(store):
    with store.connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM moments ORDER BY julianday(window_end),slot")]


def seed(memory, store, user, text, source, when, *, occurred=None, conversation="synthetic-chat"):
    owner = user["life_user_id"]
    event = store.create_event(
        user_id=owner, source_type="chat", source_message_ids=[source],
        conversation_id=conversation, occurred_at=(occurred or when).isoformat(),
        title=text[:28], summary=text, confidence=.95, consent_state="granted",
        status="published", idempotency_key=f"{owner}:{source}",
    )
    candidate = Candidate(
        candidate_type="life_event", canonical_text=text, evidence_quote=text,
        occurred_state="occurred", experience_owner="self",
        confidence=.95, sensitivity="ordinary", image_candidate=True,
    )
    return memory.save(owner, candidate, f"synthetic:{source}", source, conversation,
                       text, when, event["event_id"])


def test_new_window_policy_covers_the_whole_day():
    assert MomentSettings().ends == ["11:00", "16:00", "24:00"]


def test_v03_rejects_night_end_before_midnight(tmp_path):
    moments, user, _, _ = build(tmp_path)
    with pytest.raises(ValueError, match="FINAL_WINDOW_MUST_END_AT_24"):
        configure(moments, user, instant("2026-11-03T10:00:00+08:00"),
                  ends=["11:00", "16:00", "23:00"])


def test_night_closes_on_previous_business_date_after_five_minutes(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天晚上在河边散步，看见晚霞。", "night",
         instant("2026-11-03T23:59:59+08:00"))
    moments.schedule(instant("2026-11-04T00:04:59+08:00"))
    assert len(rows(store)) == 2
    moments.schedule(instant("2026-11-04T00:05:00+08:00"))
    result = rows(store)
    assert len(result) == 3
    assert [r["local_date"] for r in result] == ["2026-11-03"] * 3
    assert [r["slot"] for r in result] == [0, 1, 2]
    assert result[-1]["window_end"] == "2026-11-03T16:00:00+00:00"
    assert result[-1]["settle_after_utc"] == "2026-11-03T16:05:00+00:00"
    assert result[-1]["status"] == "awaiting_score"
    assert all(r["policy_version"] == "v03-a" for r in result)


@pytest.mark.parametrize("source_time,slot", [
    ("00:00:00", 0), ("10:59:59", 0), ("11:00:00", 1),
    ("15:59:59", 1), ("16:00:00", 2), ("23:59:59", 2),
])
def test_source_boundaries_are_half_open(tmp_path, source_time, slot):
    moments, user, store, memory = build(tmp_path)
    item = seed(memory, store, user, "今天第一次参加公园读书活动，特别开心。", "boundary",
                instant(f"2026-11-03T{source_time}+08:00"))
    moments.schedule(instant("2026-11-04T00:05:00+08:00"))
    with store.connect() as db:
        matches = db.execute("""SELECT m.slot FROM moments m JOIN recollection_candidates c
            ON c.window_id=m.moment_id WHERE c.memory_id=?""", (item["memory_id"],)).fetchall()
    assert [r[0] for r in matches] == [slot]


@pytest.mark.parametrize("zone,day,hours", [
    ("America/New_York", "2026-03-08", 23),
    ("America/New_York", "2026-11-01", 25),
    ("Australia/Lord_Howe", "2026-04-05", 24.5),
    ("Australia/Lord_Howe", "2026-10-04", 23.5),
    ("Asia/Kathmandu", "2026-11-03", 24),
])
def test_dst_and_fractional_offsets_preserve_contiguous_utc_intervals(tmp_path, zone, day, hours):
    from zoneinfo import ZoneInfo
    local_start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(zone))
    moments, _, store, _ = build(tmp_path, zone=zone, start=local_start.isoformat())
    next_midnight = local_start + timedelta(days=1)
    moments.schedule(next_midnight.astimezone(UTC) + timedelta(minutes=5))
    result = rows(store)
    assert len(result) == 3
    assert instant(result[0]["window_start"]) == local_start.astimezone(UTC)
    assert all(instant(a["window_end"]) == instant(b["window_start"])
               for a, b in zip(result, result[1:]))
    assert (instant(result[-1]["window_end"]) - instant(result[0]["window_start"])).total_seconds() / 3600 == hours


@pytest.mark.parametrize("destination", ["UTC", "America/Los_Angeles", "Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_zone_change_neither_repeats_business_keys_nor_loses_utc_time(tmp_path, destination):
    moments, user, store, _ = build(tmp_path)
    change_at = instant("2026-11-03T12:00:00+08:00")
    moments.schedule(change_at)
    before = rows(store)
    configure(moments, user, change_at, timezone=destination)
    moments.schedule(instant("2026-11-07T12:00:00+00:00"))
    result = rows(store)
    assert {k:v for k,v in result[0].items() if k != "late_checked_at"} == {
        k:v for k,v in before[0].items() if k != "late_checked_at"
    }
    assert len({(r["user_id"], r["local_date"], r["slot"]) for r in result}) == len(result)
    assert all(instant(a["window_end"]) == instant(b["window_start"])
               for a, b in zip(result, result[1:]))
    assert any(r["timezone"] == destination for r in result)
    # Every instant in the consumed interval belongs to exactly one settlement.
    point = instant(result[0]["window_start"])
    while point < instant(result[-1]["window_end"]):
        assert sum(instant(r["window_start"]) <= point < instant(r["window_end"]) for r in result) == 1
        point += timedelta(minutes=17)
    moments.schedule(instant("2026-11-07T12:00:00+00:00"))
    assert [
        {k:v for k,v in row.items() if k != "late_checked_at"}
        for row in rows(store)
    ] == [
        {k:v for k,v in row.items() if k != "late_checked_at"}
        for row in result
    ]


def test_repeated_policy_changes_and_restart_use_persisted_cursor(tmp_path):
    moments, user, store, memory = build(tmp_path)
    moments.schedule(instant("2026-11-03T12:00:00+08:00"))
    configure(moments, user, instant("2026-11-03T12:05:00+08:00"), timezone="UTC")
    configure(moments, user, instant("2026-11-03T12:06:00+08:00"), timezone="Asia/Tokyo")
    restarted = Moments(store, moments.settings, memory)
    restarted.schedule(instant("2026-11-05T12:00:00+00:00"))
    result = rows(store)
    assert all(instant(a["window_end"]) == instant(b["window_start"])
               for a, b in zip(result, result[1:]))
    assert len({(r["local_date"], r["slot"]) for r in result}) == len(result)
    assert any(r["timezone"] == "Asia/Tokyo" for r in result)


def test_database_itself_rejects_duplicate_business_slot(tmp_path):
    moments, _, store, _ = build(tmp_path)
    moments.schedule(instant("2026-11-03T12:00:00+08:00"))
    item = rows(store)[0]
    with store.connect() as db:
        columns = list(item)
        duplicate = dict(item, moment_id="duplicate", window_start="2026-11-03T01:00:00+00:00",
                         window_end="2026-11-03T04:00:00+00:00", policy_version="future-policy")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"INSERT INTO moments ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                       [duplicate[c] for c in columns])


def test_no_consent_records_skip_without_candidates_or_requests(tmp_path):
    moments, user, store, _ = build(tmp_path)
    store.update_consent(user["life_user_id"], memory_consent=False)
    moments.schedule(instant("2026-11-03T12:00:00+08:00"))
    result = rows(store)
    assert len(result) == 1 and result[0]["status"] == "skipped"
    assert result[0]["error_code"] == "SKIPPED_NO_CONSENT"
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM recollection_candidates").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0


def test_text_recall_does_not_require_image_consent(tmp_path):
    moments, user, store, memory = build(tmp_path)
    seed(memory, store, user, "今天上午第一次参加公园读书活动，特别开心。",
         "text-only", instant("2026-11-03T09:00:00+08:00"))
    store.update_consent(user["life_user_id"], image_consent=False)
    configure(moments, store.get_user(user["life_user_id"]),
              instant("2026-11-03T09:30:00+08:00"))
    moments.schedule(instant("2026-11-03T11:00:00+08:00"))
    result = rows(store)
    assert len(result) == 1 and result[0]["status"] == "awaiting_score"
    assert moments.authorized(user["life_user_id"])
    assert moments.image_authorized(user["life_user_id"]) is False


def test_stage_a_cannot_invoke_existing_image_generator(tmp_path, monkeypatch):
    moments, _, _, _ = build(tmp_path)
    monkeypatch.setattr(moments, "generate", lambda *_: pytest.fail("Image API forbidden in stage A"))
    assert moments.settings.moment_image_generation_enabled is False
    assert moments.run_one() is False


def test_v03_image_budget_is_persistent_and_hard_limited(tmp_path):
    from dataclasses import replace

    moments, user, store, memory = build(tmp_path)
    owner = user["life_user_id"]
    item = seed(
        memory, store, user,
        "今天下午在阳台给绿萝浇水，旁边放着黄色马克杯和蓝色笔记本。",
        "budget-source",
        instant("2026-11-03T09:00:00+08:00"),
    )
    moments.set_egress_consent(
        owner, "image_generation", "kolors", True, CONSENT_VERSION
    )
    moments.set_egress_consent(
        owner, "prompt_generation", "deepseek", True, CONSENT_VERSION
    )
    moments.settings = replace(
        moments.settings,
        moment_image_generation_enabled=True,
        memory_llm_key="synthetic",
        moment_prompt_request_budget=2,
        moment_image_request_budget=1,
        moment_image_provider="kolors",
    )
    calls = []

    class Provider:
        def generate(self, request, trace_id):
            calls.append((request.prompt, trace_id))
            image = Image.new("RGB", (96, 128), (40, 80, 60))
            pixels = image.load()
            for y in range(128):
                for x in range(96):
                    pixels[x, y] = ((x * 3 + y) % 256, (x + y) % 256, x * y % 256)
            output = BytesIO()
            image.save(output, format="PNG")
            return validate_image_bytes(output.getvalue(), "image/png")

    moments.provider = Provider()
    selection = json.dumps([{
        "memory_id": item["memory_id"],
        "outcome": "SELECTED",
        "text": item["canonical_text"],
        "occurred_at": "2026-11-03T07:00:00+00:00",
        "sources": [{
            "message_id": "budget-source",
            "quote": item["canonical_text"],
        }],
        "policy": {
            "storage_status": "PRIVATE_TEXT",
            "image_dispatch_allowed": True,
        },
    }])
    review = json.dumps({"candidates": json.loads(selection)})
    for index, moment_id in enumerate((
        "mom_" + "a" * 24,
        "mom_" + "b" * 24,
    )):
        with store.connect() as db:
            db.execute(
                """INSERT INTO moments
                (moment_id,user_id,window_start,window_end,timezone,slot,status,
                 source_memory_ids,selection,caption,created_at,updated_at,review_json)
                VALUES (?,?,?,?,?,?, 'queued',?,?,?,?,?,?)""",
                (
                    moment_id, owner,
                    f"2026-11-0{index + 3}T00:00:00+00:00",
                    f"2026-11-0{index + 3}T03:00:00+00:00",
                    "Asia/Hong_Kong", index,
                    json.dumps([item["memory_id"]]), selection,
                    "阳台绿萝、黄色马克杯和蓝色笔记本",
                    instant("2026-11-03T01:00:00+00:00").isoformat(),
                    instant("2026-11-03T01:00:00+00:00").isoformat(),
                    review,
                ),
            )

    assert moments.run_one() is True
    assert moments.detail(owner, "mom_" + "a" * 24)["status"] == "generated"
    assert len(calls) == 1
    assert "今天下午在阳台给绿萝浇水" in calls[0][0]
    assert "给盆栽浇水" in calls[0][0]
    assert "正在把水从浇水壶倒向盆栽土壤" in calls[0][0]
    assert "不得只画静止绿植和浇水壶" in calls[0][0]
    evidence = json.loads(
        moments.detail(owner, "mom_" + "a" * 24)["prompt_evidence_json"]
    )
    assert evidence["scene"] == "下午阳台室内绿植旁"
    assert {"绿萝", "黄色杯子", "蓝色笔记本"}.issubset(evidence["objects"])
    with store.connect() as db:
        ledger = [dict(row) for row in db.execute(
            "SELECT * FROM recollection_image_calls"
        )]
        prompt_tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert len(ledger) == 1
    assert "recollection_prompt_calls" not in prompt_tables
    assert ledger[0]["moment_id"] == "mom_" + "a" * 24
    assert ledger[0]["status"] == "succeeded"
    assert ledger[0]["sha256"]

    restarted = Moments(store, moments.settings, memory, image_provider=moments.provider)
    assert restarted.run_one() is True
    assert restarted.detail(owner, "mom_" + "b" * 24)["error_code"] == "IMAGE_REQUEST_BUDGET"
    assert len(calls) == 1
