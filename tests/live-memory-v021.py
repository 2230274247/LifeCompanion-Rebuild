"""Isolated life-core DB + real configured LLM and official Memos API."""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/life-core"))
for path in (root / "infra/.env", root / "products/librechat-custom/.env"):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

from app.config import load_settings
from app.main import create_app

stamp = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()
run_id = uuid.uuid4().hex[:12]
settings = replace(load_settings(), database_path=root / f"infra/runtime/v02-memory-reminders/live-{run_id}.sqlite3")
checks = {}
result = {"started_at": stamp, "isolation": "separate life-core SQLite; synthetic sources only",
          "checks": checks, "model": settings.memory_llm_model}


def token(user):
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=")
    parts = [enc({"alg":"HS256","typ":"JWT"}), enc({"id":user,"exp":int(time.time())+600})]
    parts.append(base64.urlsafe_b64encode(hmac.new(settings.jwt_secret.encode(), b".".join(parts),
                                                  hashlib.sha256).digest()).rstrip(b"="))
    return {"Authorization":"Bearer "+b".".join(parts).decode()}


try:
    assert settings.memory_llm_key, "no real LLM key configured"
    with httpx.Client(timeout=20, trust_env=False) as upstream:
        memos_auth = {"Authorization":"Bearer "+settings.memos_api_token}
        creator = upstream.get(settings.memos_base_url+"/api/auth/me",headers=memos_auth).json()["user"]["name"]
        app = create_app(settings)
        with TestClient(app) as client:
            internal = {"X-Internal-Token": settings.internal_token}
            for user in ("synthetic-v021-a", "synthetic-v021-b"):
                assert client.post("/internal/v1/users/bootstrap",headers=internal,json={
                    "librechat_user_id":user,"memos_user_id":creator,"memory_consent":True,
                }).status_code == 200
            auth = token("synthetic-v021-a")
            client.patch("/api/v1/me/settings",headers=auth,json={"recall_consent":True})
            def source(text, mid):
                return {"source_user_id":"synthetic-v021-a","source_message_id":run_id+mid,
                        "conversation_id":"synthetic-"+run_id,"text":text,"occurred_at":stamp}
            queued = client.post("/internal/v1/events/enqueue",headers=internal,
                                 json=source("我平常喜欢龙井茶", "-fact"))
            assert queued.json()["accepted"]
            deadline = time.monotonic()+100
            while time.monotonic()<deadline:
                facts = client.get("/api/v1/knowledge",headers=auth).json()["items"]
                if facts:
                    break
                time.sleep(0.25)
            assert facts and facts[0]["kind"]=="stable_fact", "real provider extraction did not finish"
            with app.state.store.connect() as db:
                version = db.execute("SELECT classifier_version FROM memory_evidence").fetchone()[0]
                job = dict(db.execute("SELECT status,payload,attempts FROM memory_jobs").fetchone())
            assert job["status"]=="succeeded" and job["payload"] is None
            assert version.startswith("llm:")
            checks["real_llm_to_durable_fact"] = "PASS"
            recalled = client.get("/api/v1/knowledge/recall?q=今天喝什么茶",headers=auth).json()["items"]
            assert len(recalled)==1 and "龙井" in recalled[0]["canonical_text"]
            checks["new_query_retrieval"] = "PASS"
            assert client.get("/api/v1/knowledge/recall?q=喝茶",headers=token("synthetic-v021-b")).json()["items"]==[]
            checks["two_scoped_identities"] = "PASS (signed test identities, not two browser logins)"
            published = client.post("/internal/v1/events/ingest",headers=internal,
                json=source("今天加入了一直想加入的项目组！", "-event"))
            assert published.status_code==200 and published.json()["event"]["status"]=="published"
            event = published.json()["event"]
            memo = upstream.get(settings.memos_base_url+"/api/"+event["memo_ref"],headers=memos_auth)
            assert memo.status_code==200 and memo.json()["visibility"]=="PRIVATE" and memo.json()["creator"]==creator
            checks["real_private_memos_publish_and_readback"] = "PASS"
            merged = client.post("/internal/v1/events/ingest",headers=internal,
                json=source("这个项目组真的很棒！", "-merge")).json()
            assert merged["event"]["event_id"]==event["event_id"]
            checks["cross_message_event_merge"] = "PASS"
            all_items = client.get("/api/v1/knowledge",headers=auth).json()["items"]
            for item in all_items:
                deleted = client.delete("/api/v1/knowledge/"+item["memory_id"],headers=auth)
                assert deleted.status_code==200 and deleted.json()["cleanup"]!="pending"
            assert client.get("/api/v1/knowledge/recall?q=喝茶",headers=auth).json()["items"]==[]
            assert upstream.get(settings.memos_base_url+"/api/"+event["memo_ref"],headers=memos_auth).status_code==404
            checks["withdrawal_blocks_recall_and_deletes_only_new_synthetic_memo"] = "PASS"
            result["provider_job"] = {k:job[k] for k in ("status","attempts")}
            result["classifier_version"] = version
    result["status"] = "PASS"
except Exception as exc:
    result["status"] = "FAIL"
    result["error_type"] = type(exc).__name__
finally:
    result["ended_at"] = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()
    (root/"evidence/v02-memory-reminders/live-memory.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=False))
sys.exit(0 if result["status"]=="PASS" else 1)
