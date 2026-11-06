"""Isolated stage A API/selection acceptance. All model responses are explicit MockTransport."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import hashlib
import html
import json

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
SERVICE_TESTS = ROOT / "services" / "life-core" / "tests"
import sys

sys.path.insert(0, str(ROOT / "services" / "life-core"))
sys.path.insert(0, str(SERVICE_TESTS))

from app.config import Settings
from app.main import create_app
from app.moments import MomentSettings
from app.recollection_scoring import WEIGHTS
from app.reminder_scheduler import MOMENT_SETTLEMENT_JOB_ID, RECONCILE_JOB_ID, create_scheduler
from test_api import token_for


STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUTPUT = ROOT / "evidence" / "v03-stage-a" / "acceptance" / STAMP
OUTPUT.mkdir(parents=True, exist_ok=False)
DB_PATH = OUTPUT / "stage-a.sqlite3"


def auth(user_id="stage-a-user"):
    return {"Authorization": f"Bearer {token_for(user_id)}"}


settings = Settings(
    database_path=DB_PATH,
    internal_token="stage-a-internal",
    jwt_secret="test-jwt",
    jwt_refresh_secret="test-refresh",
    memos_base_url="http://memos.invalid",
    memos_api_token="",
    timezone="Asia/Hong_Kong",
    allowed_origins=(),
    memory_llm_key="synthetic-mock-only",
    moment_scoring_request_budget=8,
    moment_windows_v03=True,
    moment_settlement_scan_limit=96,
    moment_score_lease_seconds=120,
    moment_scheduler_external=True,
    moment_workers_enabled=False,
    moment_image_generation_enabled=False,
)
app = create_app(settings)
client = TestClient(app)
request_log = []


def scoring_response(request):
    request_log.append({"path": request.url.path, "mode": "MOCK_SCORING"})
    candidates = json.loads(json.loads(request.content)["messages"][1]["content"])["candidates"]
    output = []
    for candidate in candidates:
        source_ids = [source["message_id"] for source in candidate["sources"]]
        if any(value.startswith("run-") for value in source_ids):
            rating, reason = .95, "MEANINGFUL_EVENT"
        elif "reading" in source_ids:
            rating, reason = .70, "MEANINGFUL_EVENT"
        else:
            rating, reason = .20, "ROUTINE_EVENT"
        dimensions = {name: rating for name in WEIGHTS}
        dimensions.update(
            privacy_suitability=1.0,
            source_sufficiency=1.0,
            event_clarity=1.0,
            window_relevance=1.0,
        )
        output.append({
            "memory_id": candidate["memory_id"],
            "eligible": rating >= .4,
            "dimensions": dimensions,
            "reason_code": reason,
            "source_message_ids": source_ids,
            "evidence_quote": candidate["sources"][0]["quote"],
        })
    return httpx.Response(
        200,
        json={
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"candidates": output}, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
        },
    )


with client:
    bootstrap = client.post(
        "/internal/v1/users/bootstrap",
        headers={"X-Internal-Token": "stage-a-internal"},
        json={
            "librechat_user_id": "stage-a-user",
            "memos_user_id": "users/stage-a",
            "memos_username": "stage-a",
            "display_name": "Stage A Synthetic",
            "memory_consent": True,
            "image_consent": True,
        },
    )
    bootstrap.raise_for_status()
    owner = bootstrap.json()["life_user_id"]
    app.state.memos.create_private_memo = lambda event: f"synthetic/{event['event_id']}"

    with patch("app.moments.utc_now", return_value="2026-11-03T00:00:00+00:00"):
        configured = client.put(
            "/api/v1/moment-settings",
            headers=auth(),
            json={
                "enabled": True,
                "timezone": "Asia/Hong_Kong",
                "ends": ["11:00", "16:00", "24:00"],
            },
        )
        configured.raise_for_status()

    messages = [
        ("run-a", "今天早上在公园跑了三公里，回来感觉精神很好。", "2026-11-03T09:00:00+08:00"),
        ("breakfast", "今天早上吃了普通早餐。", "2026-11-03T09:01:00+08:00"),
        ("run-b", "早晨在公园跑步三公里，真的很放松。", "2026-11-03T09:02:00+08:00"),
        ("reading", "今天上午第一次参加公园读书活动，特别有感触。", "2026-11-03T09:03:00+08:00"),
        ("run-c", "今天上午在公园跑了三公里，特别开心。", "2026-11-03T09:04:00+08:00"),
    ]
    ingested = []
    for source_id, text, occurred_at in messages:
        response = client.post(
            "/internal/v1/events/ingest",
            headers={"X-Internal-Token": "stage-a-internal"},
            json={
                "source_user_id": "stage-a-user",
                "source_message_id": source_id,
                "conversation_id": "stage-a-chat",
                "text": text,
                "occurred_at": occurred_at,
            },
        )
        response.raise_for_status()
        assert response.json().get("accepted") is True, response.json()
        ingested.append({"source_id": source_id, "text": text, "response": response.json()})

    app.state.moments.scorer.transport = httpx.MockTransport(scoring_response)
    app.state.moments.schedule(datetime.fromisoformat("2026-11-03T11:00:00+08:00"))
    scored = []
    while app.state.moments.score_one():
        scored.append("score_one")
    image_worker_changed_data = app.state.moments.run_one()
    settle_endpoint = client.post(
        "/internal/v1/moments/settle",
        headers={"X-Internal-Token": "stage-a-internal"},
    )
    settle_endpoint.raise_for_status()

    with app.state.store.connect() as db:
        rows = [dict(row) for row in db.execute(
            """SELECT moment_id,local_date,slot,window_start,window_end,settle_after_utc,
                timezone,policy_version,status,source_memory_ids,review_json
                FROM moments ORDER BY local_date,slot"""
        )]
        model_calls = [dict(row) for row in db.execute(
            """SELECT window_id,status,input_hash,result_json,error_code
                FROM recollection_model_calls ORDER BY started_at"""
        )]
        candidate_rows = [dict(row) for row in db.execute(
            """SELECT window_id,memory_id,member_memory_ids,source_message_ids,
                score,eligible,reason_code,selected,source_revisions
                FROM recollection_candidates ORDER BY score DESC"""
        )]

    selected_row = next(row for row in rows if json.loads(row["source_memory_ids"]))
    detail = app.state.moments.detail(owner, selected_row["moment_id"])
    review = detail["review"]
    by_source = {
        candidate["sources"][0]["message_id"]: candidate
        for candidate in review["candidates"]
    }
    assert review["decision"] == "SELECTED"
    assert review["scoring_mode"] == "MOCK_SCORING"
    assert by_source["run-a"]["outcome"] == "SELECTED"
    assert by_source["breakfast"]["outcome"] == "EXCLUDED"
    assert by_source["reading"]["outcome"] == "NOT_SELECTED"
    assert by_source["reading"]["reason_code"] == "LOWER_RANK"
    selected = next(candidate for candidate in review["candidates"]
                    if candidate["outcome"] == "SELECTED")
    assert {source["message_id"] for source in selected["sources"]} == {"run-a", "run-b", "run-c"}
    assert image_worker_changed_data is False
    assert request_log and all(entry["path"].endswith("/chat/completions") for entry in request_log)
    assert all("images/generations" not in entry["path"] for entry in request_log)

    scheduler_path = OUTPUT / "scheduler.sqlite3"
    first_scheduler = create_scheduler(
        scheduler_path, interval_seconds=60, scheduler_class=BackgroundScheduler
    )
    first_scheduler.start(paused=True)
    scheduler_ids_before = sorted(job.id for job in first_scheduler.get_jobs())
    first_scheduler.shutdown(wait=False)
    second_scheduler = create_scheduler(
        scheduler_path, interval_seconds=60, scheduler_class=BackgroundScheduler
    )
    second_scheduler.start(paused=True)
    scheduler_ids_after = sorted(job.id for job in second_scheduler.get_jobs())
    second_scheduler.shutdown(wait=False)
    assert scheduler_ids_before == scheduler_ids_after
    assert set(scheduler_ids_after) == {RECONCILE_JOB_ID, MOMENT_SETTLEMENT_JOB_ID}

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": {
            "api": "MOCK_SCORING",
            "image_api": "DISABLED",
            "database": "SYNTHETIC_SQLITE",
            "scheduler": "REAL_APSCHEDULER_SQLALCHEMY_JOBSTORE",
            "memos": "SYNTHETIC_FUNCTION",
        },
        "database": str(DB_PATH),
        "database_sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest(),
        "configure": configured.json(),
        "ingested": ingested,
        "scored_loop": scored,
        "settle_endpoint": settle_endpoint.json(),
        "image_worker_changed_data": image_worker_changed_data,
        "network_request_log": request_log,
        "moments": rows,
        "model_calls": model_calls,
        "candidate_rows": candidate_rows,
        "selected_moment": detail,
        "scheduler": {
            "job_ids_before_restart": scheduler_ids_before,
            "job_ids_after_restart": scheduler_ids_after,
            "jobstore_size": scheduler_path.stat().st_size,
        },
    }
    (OUTPUT / "acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cards = []
    for candidate in review["candidates"]:
        source_rows = "".join(
            f"<li><code>{html.escape(source['message_id'])}</code>"
            f"<blockquote>{html.escape(source['quote'])}</blockquote></li>"
            for source in candidate["sources"]
        )
        dimensions = "".join(
            f"<span>{html.escape(name)} <b>{value:.2f}</b></span>"
            for name, value in candidate["dimensions"].items()
        )
        cards.append(f"""
        <article class="candidate {candidate['outcome'].lower()}">
          <div class="outcome">{html.escape(candidate['outcome'])}</div>
          <h2>{html.escape(candidate['text'].splitlines()[0])}</h2>
          <p class="reason">理由码：<code>{html.escape(candidate['reason_code'])}</code>
             · 得分：{candidate['score'] if candidate['score'] is not None else '未评分'}</p>
          <div class="dimensions">{dimensions}</div>
          <h3>原始来源证据</h3><ul>{source_rows}</ul>
        </article>""")
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LifeCompanion V0.3 阶段 A 选择审查</title>
<style>
:root{{--ink:#14251f;--paper:#f4f0e5;--run:#146b4a;--warn:#a64b2a;--muted:#68746d}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 80% 5%,#d5e6d6,transparent 34%),var(--paper);
color:var(--ink);font:16px/1.55 Georgia,"Noto Serif SC",serif}}main{{max-width:1180px;margin:auto;padding:48px 28px 72px}}
.eyebrow{{font:700 12px/1.2 Consolas,monospace;letter-spacing:.18em;color:var(--run);text-transform:uppercase}}
h1{{font-size:clamp(34px,6vw,72px);line-height:.98;letter-spacing:-.04em;margin:12px 0 20px;max-width:900px}}
.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:28px 0 38px}}
.summary div{{border-top:3px solid var(--ink);padding-top:10px}}.summary b{{display:block;font-size:20px}}
.window{{font:13px/1.5 Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}}
.candidates{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;align-items:start}}
.candidate{{background:#fffdf7;border:1px solid #c9c3b4;padding:20px;box-shadow:0 13px 34px #26372b12}}
.candidate.selected{{border:3px solid var(--run)}}.candidate.not_selected{{border-color:#ae944e}}
.candidate.excluded{{opacity:.82}}.outcome{{font:700 12px/1 monospace;letter-spacing:.12em;color:var(--muted)}}
h2{{font-size:24px;line-height:1.18;margin:14px 0 8px}}h3{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin-top:22px}}
.reason,.window{{font:12px/1.6 Consolas,monospace;color:var(--muted)}}.dimensions{{display:flex;flex-wrap:wrap;gap:5px}}
.dimensions span{{background:#e7eadf;padding:3px 6px;font:11px/1.4 Consolas,monospace}}ul{{padding-left:18px}}
blockquote{{margin:5px 0;padding-left:10px;border-left:2px solid var(--run);font-size:14px}}code{{font-family:Consolas,monospace}}
.foot{{margin-top:36px;border-top:1px solid #918e82;padding-top:16px;font:12px/1.6 Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}}
@media(max-width:820px){{main{{padding:28px 18px 48px}}.summary{{grid-template-columns:repeat(2,1fr)}}.candidates{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">STAGE A · REVIEWABLE SELECTION RECORD</div>
<h1>为什么选中跑步，而不是早餐或阅读</h1>
<p>本页由阶段 A 的真实 API 链路输出生成。评分响应为 <b>MOCK_SCORING</b>，不是真实模型准确率证据；图片能力和真实 Kolors API 均未启用。</p>
<section class="summary">
  <div><span>决定</span><b>{html.escape(review['decision'])}</b></div>
  <div><span>候选数</span><b>{len(review['candidates'])}</b></div>
  <div><span>得分阈值</span><b>{review['threshold']:.2f}</b></div>
  <div><span>证据消息</span><b>{len(selected['sources'])}</b></div>
</section>
<p class="window">BUSINESS {html.escape(str(selected_row['local_date']))} SLOT {selected_row['slot']} ·
UTC {html.escape(selected_row['window_start'])} → {html.escape(selected_row['window_end'])} ·
POLICY {html.escape(selected_row['policy_version'])}</p>
<section class="candidates">{''.join(cards)}</section>
<p class="foot">DATABASE {html.escape(str(DB_PATH))}<br>SHA256 {result['database_sha256']}</p>
</main></body></html>"""
    (OUTPUT / "selection-review.html").write_text(document, encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "decision": review["decision"],
        "selected_sources": [source["message_id"] for source in selected["sources"]],
        "model_calls": len(model_calls),
        "image_api_calls": 0,
        "scheduler_jobs": scheduler_ids_after,
    }, ensure_ascii=False))
