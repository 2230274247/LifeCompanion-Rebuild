"""One bounded real-P04 scoring acceptance on an isolated synthetic database."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import hashlib
import html
import json
import os
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
SERVICE_TESTS = ROOT / "services" / "life-core" / "tests"
sys.path.insert(0, str(ROOT / "services" / "life-core"))
sys.path.insert(0, str(SERVICE_TESTS))

from app.config import Settings
from app.main import create_app
from test_api import token_for


STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUTPUT = ROOT / "evidence" / "v03-stage-a" / "acceptance" / f"{STAMP}-real-scoring"
OUTPUT.mkdir(parents=True, exist_ok=False)
DB_PATH = OUTPUT / "stage-a-real.sqlite3"
ENV_FILE = ROOT / "infra" / "runtime" / "p00" / "acceptance.env"


def read_required_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    api_key = values.get("DEEPSEEK_API_KEY", "")
    if not api_key or any(marker in api_key.lower() for marker in ("replace", "your-", "xxx")):
        raise RuntimeError("REAL_SCORING_CREDENTIAL_UNAVAILABLE")
    return values


provider_env = read_required_env(ENV_FILE)
settings = Settings(
    database_path=DB_PATH,
    internal_token="stage-a-real-internal",
    jwt_secret="test-jwt",
    jwt_refresh_secret="test-refresh",
    memos_base_url="http://memos.invalid",
    memos_api_token="",
    timezone="Asia/Hong_Kong",
    allowed_origins=(),
    memory_llm_key=provider_env["DEEPSEEK_API_KEY"],
    memory_llm_url=provider_env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
    memory_llm_model=provider_env.get("DEEPSEEK_MODEL", "deepseek-flash"),
    memory_llm_provider="deepseek",
    moment_scoring_request_budget=1,
    moment_windows_v03=True,
    moment_settlement_scan_limit=96,
    moment_score_lease_seconds=120,
    moment_scheduler_external=True,
    moment_workers_enabled=False,
    moment_image_generation_enabled=False,
)
app = create_app(settings)
client = TestClient(app)


def auth(user_id: str = "stage-a-real-user") -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user_id)}"}


with client:
    bootstrap = client.post(
        "/internal/v1/users/bootstrap",
        headers={"X-Internal-Token": settings.internal_token},
        json={
            "librechat_user_id": "stage-a-real-user",
            "memos_user_id": "users/stage-a-real",
            "memos_username": "stage-a-real",
            "display_name": "Stage A Real Scoring",
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
    for source_id, text, message_at in messages:
        response = client.post(
            "/internal/v1/events/ingest",
            headers={"X-Internal-Token": settings.internal_token},
            json={
                "source_user_id": "stage-a-real-user",
                "source_message_id": source_id,
                "conversation_id": "stage-a-real-chat",
                "text": text,
                "occurred_at": message_at,
            },
        )
        response.raise_for_status()
        ingested.append(
            {
                "source_id": source_id,
                "text": text,
                "accepted": response.json().get("accepted"),
            }
        )

    app.state.moments.schedule(datetime.fromisoformat("2026-11-03T11:00:00+08:00"))
    scored = []
    while app.state.moments.score_one():
        scored.append("score_one")
    image_worker_changed_data = app.state.moments.run_one()

    with app.state.store.connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                """SELECT moment_id,local_date,slot,window_start,window_end,
                    settle_after_utc,timezone,policy_version,status,
                    source_memory_ids,review_json
                    FROM moments ORDER BY local_date,slot"""
            )
        ]
        calls = [
            dict(row)
            for row in db.execute(
                """SELECT window_id,status,model,input_hash,input_tokens,
                    output_tokens,error_code,result_json,started_at,completed_at
                    FROM recollection_model_calls ORDER BY started_at"""
            )
        ]
        candidate_rows = [
            dict(row)
            for row in db.execute(
                """SELECT window_id,memory_id,member_memory_ids,
                    source_message_ids,score,eligible,reason_code,
                    model_reason_code,selected,source_revisions
                    FROM recollection_candidates ORDER BY score DESC"""
            )
        ]

    selected_row = next(
        (row for row in rows if json.loads(row["source_memory_ids"])),
        None,
    )
    if selected_row is None:
        failed_rows = [row for row in rows if row["status"] != "skipped"]
        selected_row = failed_rows[0] if failed_rows else rows[0]
    detail = app.state.moments.detail(owner, selected_row["moment_id"])
    review = detail["review"]
    selected = next(
        (candidate for candidate in review.get("candidates", []) if candidate.get("outcome") == "SELECTED"),
        None,
    )
    run_candidate = next(
        (
            candidate
            for candidate in review.get("candidates", [])
            if any(source.get("message_id", "").startswith("run-") for source in candidate.get("sources", []))
        ),
        None,
    )
    run_sources = sorted(
        source["message_id"]
        for source in (run_candidate or {}).get("sources", [])
        if source["message_id"].startswith("run-")
    )
    call_succeeded = bool(calls and calls[0]["status"] == "succeeded")
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": {
            "scoring": "REAL_DEEPSEEK",
            "image_api": "DISABLED",
            "database": "SYNTHETIC_SQLITE",
            "memos": "SYNTHETIC_FUNCTION",
        },
        "provider": {
            "name": settings.memory_llm_provider,
            "model": settings.memory_llm_model,
            "base_url": settings.memory_llm_url,
            "request_budget": settings.moment_scoring_request_budget,
        },
        "database": str(DB_PATH),
        "database_sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest(),
        "configure": configured.json(),
        "ingested": ingested,
        "scored_loop": scored,
        "image_worker_changed_data": image_worker_changed_data,
        "moments": rows,
        "model_calls": calls,
        "candidate_rows": candidate_rows,
        "selected_moment": detail,
        "checks": {
            "one_real_scoring_call_succeeded": call_succeeded,
            "run_retellings_grouped": run_sources == ["run-a", "run-b", "run-c"],
            "selected_event_grounded_in_original_quotes": bool(
                selected
                and selected.get("sources")
                and all(source.get("quote") for source in selected["sources"])
            ),
            "image_worker_did_not_change_data": image_worker_changed_data is False,
        },
    }
    passed = all(result["checks"].values())
    result["status"] = "PASS" if passed else "FAIL"
    (OUTPUT / "real-scoring.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cards = []
    for candidate in review.get("candidates", []):
        source_rows = "".join(
            f"<li><code>{html.escape(source['message_id'])}</code>"
            f"<blockquote>{html.escape(source['quote'])}</blockquote></li>"
            for source in candidate.get("sources", [])
        )
        dimensions = "".join(
            f"<span>{html.escape(name)} <b>{value:.2f}</b></span>"
            for name, value in candidate.get("dimensions", {}).items()
        )
        score = candidate.get("score")
        cards.append(
            f"""
            <article class="candidate {html.escape(candidate['outcome'].lower())}">
              <div class="outcome">{html.escape(candidate['outcome'])}</div>
              <h2>{html.escape(candidate['text'].splitlines()[0])}</h2>
              <p class="reason">理由码：<code>{html.escape(candidate['reason_code'])}</code>
                 · 得分：{score if score is not None else '未评分'}</p>
              <div class="dimensions">{dimensions}</div>
              <h3>原始来源证据</h3><ul>{source_rows}</ul>
            </article>"""
        )
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LifeCompanion V0.3 阶段 A 真实评分审查</title>
<style>
:root{{--ink:#14251f;--paper:#f4f0e5;--run:#146b4a;--muted:#68746d}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 80% 5%,#d5e6d6,transparent 34%),var(--paper);
color:var(--ink);font:16px/1.55 Georgia,"Noto Serif SC",serif}}main{{max-width:1180px;margin:auto;padding:48px 28px 72px}}
.eyebrow{{font:700 12px/1.2 Consolas,monospace;letter-spacing:.18em;color:var(--run)}}
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
<div class="eyebrow">STAGE A · REAL P04 SCORING REVIEW</div>
<h1>阶段 A 真实评分选择审查</h1>
<p>本页来自隔离合成数据库与一次有上限的真实 <b>DEEPSEEK</b> 评分请求；未调用图片或 Kolors API。</p>
<section class="summary">
  <div><span>决定</span><b>{html.escape(review.get('decision', 'UNKNOWN'))}</b></div>
  <div><span>候选数</span><b>{len(review.get('candidates', []))}</b></div>
  <div><span>真实调用</span><b>{len(calls)}</b></div>
  <div><span>验收</span><b>{result['status']}</b></div>
</section>
<p class="window">BUSINESS {html.escape(str(selected_row['local_date']))} SLOT {selected_row['slot']} ·
UTC {html.escape(selected_row['window_start'])} → {html.escape(selected_row['window_end'])} ·
POLICY {html.escape(selected_row['policy_version'])}</p>
<section class="candidates">{''.join(cards)}</section>
<p class="foot">DATABASE {html.escape(str(DB_PATH))}<br>SHA256 {result['database_sha256']}</p>
</main></body></html>"""
    (OUTPUT / "selection-review.html").write_text(document, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "status": result["status"],
                "decision": review.get("decision"),
                "selected_sources": [
                    source["message_id"] for source in (selected or {}).get("sources", [])
                ],
                "model_calls": len(calls),
                "model_call_status": calls[0]["status"] if calls else None,
                "checks": result["checks"],
            },
            ensure_ascii=False,
        )
    )
