"""Replay V0.3 compatibility gaps using synthetic data and no network."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import tempfile

import httpx

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / ".work/p00-p07-20261103"
sys.path.insert(0, str(ACTIVE / "services/life-core"))

from app.config import Settings
from app.memory import Candidate, MemoryService
from app.moments import Moments, MomentSettings
from app.store import Store


def replay():
    results = []
    with tempfile.TemporaryDirectory(prefix="v03-audit-") as temp:
        settings = Settings(
            database_path=Path(temp) / "synthetic.sqlite3",
            internal_token="synthetic",
            jwt_secret="synthetic",
            jwt_refresh_secret="synthetic",
            memos_base_url="http://memos.invalid",
            memos_api_token="",
            timezone="Asia/Hong_Kong",
            allowed_origins=(),
        )
        store = Store(settings.database_path)
        store.initialize()
        memory = MemoryService(store, settings)
        memory.initialize()
        moments = Moments(store, settings, memory)
        user = store.bootstrap_user(
            librechat_user_id="v03-audit-synthetic",
            memos_user_id="users/synthetic",
            memos_username="synthetic",
            display_name="Synthetic",
            memory_consent=True,
            image_consent=True,
        )
        owner = user["life_user_id"]
        moments.configure(user, MomentSettings(enabled=True))
        with store.connect() as db:
            db.execute(
                "UPDATE moment_settings SET enabled_at=? WHERE user_id=?",
                ("2026-11-03T00:00:00+00:00", owner),
            )
        moments.schedule(datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        with store.connect() as db:
            rows = [dict(r) for r in db.execute(
                "SELECT window_start,window_end,slot,status FROM moments "
                "WHERE user_id=? ORDER BY window_end", (owner,)
            )]
            columns = [r["name"] for r in db.execute("PRAGMA table_info(moments)")]
        morning = next(r for r in rows if r["window_end"] == "2026-11-04T11:00:00+08:00")
        results.append({
            "id": "A-WINDOW",
            "observed_default_ends": MomentSettings().ends,
            "observed_morning_start": morning["window_start"],
            "expected_morning_start": "2026-11-04T00:00:00+08:00",
            "matches_v03": morning["window_start"] == "2026-11-04T00:00:00+08:00",
        })
        before = len(rows)
        moments.configure(user, MomentSettings(enabled=True, timezone="UTC"))
        moments.schedule(datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        with store.connect() as db:
            same_slot = [dict(r) for r in db.execute(
                "SELECT window_start,window_end,timezone,slot FROM moments "
                "WHERE user_id=? AND slot=0 AND window_end LIKE '2026-11-04%'",
                (owner,),
            )]
        results.append({
            "id": "A-TIMEZONE",
            "before_total": before,
            "same_end_local_day_slot_after_zone_change": same_slot,
            "matches_v03": len(same_slot) <= 1,
            "scope": "Settlement replay only; no image or model calls.",
        })
        texts = ["今天在公园跑了三公里。", "今天在公园跑了三公里，回来感觉精神很好。"]
        keys = [
            memory.key_for(Candidate(
                candidate_type="life_event", canonical_text=text,
                evidence_quote=text, occurred_state="occurred",
                confidence=0.9, sensitivity="ordinary", image_candidate=True,
            ), text, datetime(2026, 11, 4, 2, tzinfo=timezone.utc))
            for text in texts
        ]
        results.append({
            "id": "A-AGGREGATION",
            "same_running_event_keys_equal": keys[0] == keys[1],
            "matches_v03": keys[0] == keys[1],
            "scope": "Pure semantic-key check; model duplicate rejection not exercised.",
        })
        results.append({
            "id": "A-SCHEMA",
            "has_local_date": "local_date" in columns,
            "has_policy_version": "policy_version" in columns,
            "has_provider_job_id": "provider_job_id" in columns,
            "matches_v03": all(k in columns for k in (
                "local_date", "policy_version", "provider_job_id"
            )),
        })
        calls = []

        def transport(request):
            calls.append(request.method)
            if request.method == "POST":
                return httpx.Response(200, json={
                    "data": [{"url": "https://chatglm.cn/synthetic.png"}]
                })
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nnot-an-image")

        original_client = httpx.Client
        try:
            httpx.Client = lambda **kwargs: original_client(
                transport=httpx.MockTransport(transport), **kwargs
            )
            moments.settings = replace(
                settings, memory_llm_provider="zhipu",
                memory_llm_key="synthetic", memory_llm_url="https://synthetic.invalid",
            )
            image, mime = moments.generate("Synthetic occurred event.")
        finally:
            httpx.Client = original_client
        results.append({
            "id": "B-CORRUPT-IMAGE",
            "transport": "httpx.MockTransport; zero external requests",
            "accepted_bytes": len(image),
            "accepted_mime": mime,
            "corrupt_image_accepted": image.endswith(b"not-an-image"),
            "matches_v03": not image.endswith(b"not-an-image"),
        })
        try:
            MomentSettings(ends=["11:00", "16:00", "00:05"])
            accepted_midnight_end = True
        except ValueError:
            accepted_midnight_end = False
        results.append({
            "id": "A-POLICY",
            "next_day_0005_expressible_as_existing_sorted_ends": accepted_midnight_end,
            "matches_v03": accepted_midnight_end,
            "note": "Window end and execution delay must be separate fields.",
        })
    assert len(results) == 6
    assert all(result["matches_v03"] is False for result in results)
    return {
        "status": "PASS",
        "meaning": "Six compatibility gaps reproduced; NOT V0.3 acceptance.",
        "data": "synthetic temporary database, removed on context exit",
        "external_requests": 0,
        "results": results,
    }


if __name__ == "__main__":
    result = replay()
    (ROOT / "evidence/v03-audit/gap-replays.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
