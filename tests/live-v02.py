"""Opt-in local acceptance: existing test account, real APIs, same-source ingest retry."""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--conversation", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
accounts = json.loads((root / "infra/runtime/test-accounts.json").read_text(encoding="utf-8"))
secrets = {}
for line in (root / "infra/.env").read_text(encoding="utf-8-sig").splitlines():
    if line and not line.lstrip().startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        secrets[key] = value

database = root / "services/life-core/data/life-core.sqlite3"
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT e.*, u.librechat_user_id, u.memos_user_id FROM events e
           JOIN users u ON e.user_id = u.life_user_id
           WHERE e.conversation_id = ? ORDER BY e.created_at DESC LIMIT 1""",
        (args.conversation,),
    ).fetchone()
    assert row is not None, "No real event for the tested conversation"
    event = dict(row)
    before_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

with httpx.Client(timeout=30, trust_env=False) as client:
    account = accounts["librechat"]
    login = client.post("http://127.0.0.1:3001/api/auth/login", json={
        "email": account["email"], "password": account["password"],
    })
    assert login.status_code == 200, "Login failed"
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    listing = client.get("http://127.0.0.1:3001/life-api/api/v1/memories", headers=headers)
    assert listing.status_code == 200, "Memory list failed"
    memory = next(item for item in listing.json()["memories"] if item["event_id"] == event["event_id"])
    detail = client.get(f"http://127.0.0.1:3001/life-api/api/v1/memories/{event['event_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["memory"]["content"] == memory["content"]
    anonymous = client.get("http://127.0.0.1:3001/life-api/api/v1/memories")
    assert anonymous.status_code == 401, "Refresh cookie must not authorize life-core"
    bad_token = client.get("http://127.0.0.1:3001/life-api/api/v1/memories", headers={"Authorization": "Bearer invalid"})
    assert bad_token.status_code == 401
    blocked_internal = client.get("http://127.0.0.1:3001/life-api/internal/v1/events/ingest")
    assert blocked_internal.status_code == 404
    empty = client.get("http://127.0.0.1:3001/life-api/api/v1/memories?q=absent-acceptance-filter-2026", headers=headers)
    assert empty.json()["total"] == 0 and empty.json()["memories"] == []
    memo_headers = {"Authorization": f"Bearer {secrets['MEMOS_API_TOKEN']}"}
    memo = client.get(f"http://127.0.0.1:5230/api/{event['memo_ref']}", headers=memo_headers)
    assert memo.status_code == 200
    assert memo.json()["visibility"] == "PRIVATE"
    assert memo.json()["creator"] == event["memos_user_id"]
    assert memo.json()["content"] == memory["content"]
    retry = client.post("http://127.0.0.1:8010/internal/v1/events/ingest",
        headers={"X-Internal-Token": secrets["LIFE_INTERNAL_TOKEN"]},
        json={
            "source_user_id": event["librechat_user_id"],
            "source_message_id": json.loads(event["source_message_ids"])[0],
            "conversation_id": args.conversation,
            "text": event["summary"],
            "occurred_at": event["occurred_at"],
        },
    )
    assert retry.status_code == 200
    assert retry.json()["event"]["event_id"] == event["event_id"]
    assert retry.json()["event"]["memo_ref"] == event["memo_ref"]
    assert retry.json()["event"]["status"] == "published"

with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before_count
    job = connection.execute("SELECT status FROM task_runs WHERE upstream_reference = ?", (event["memo_ref"],)).fetchone()
    assert job and job[0] == "succeeded"

result = {
    "tested_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
    "conversation_id": args.conversation,
    "event_id": event["event_id"],
    "source_message_ids": json.loads(event["source_message_ids"]),
    "memo_ref": event["memo_ref"],
    "status": "PASS",
    "checks": {
        "real_login": "PASS", "real_memories_and_detail": "PASS",
        "private_memos_content_and_owner": "PASS", "same_source_retry": "PASS",
        "event_count_unchanged_after_retry": "PASS", "publish_task_succeeded": "PASS",
        "anonymous_and_invalid_token_denied": "PASS", "internal_route_blocked": "PASS",
        "real_empty_search": "PASS",
    },
}
(root / args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
