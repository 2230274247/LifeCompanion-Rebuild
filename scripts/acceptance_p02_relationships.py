"""Real HTTP, LangMem, SQLite and Neo4j relational timeline acceptance."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import sys
import threading
import time
import traceback
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import uvicorn

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.config import load_settings
from app.main import create_app
from app.store import Store, utc_now


def token(settings, user):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")
    parts = [encode({"alg":"HS256","typ":"JWT"}),
             encode({"id":user,"exp":int(time.time())+3600})]
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(),b".".join(parts),hashlib.sha256).digest()).rstrip(b"=")
    return {"Authorization":"Bearer "+b".".join([*parts,signature]).decode()}


def start(settings):
    sock = socket.socket()
    sock.bind(("127.0.0.1",0))
    port = sock.getsockname()[1]
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    deadline = time.monotonic()+20
    while not server.started and worker.is_alive() and time.monotonic()<deadline:
        time.sleep(.1)
    if not server.started:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        raise RuntimeError("ISOLATED_HTTP_STARTUP_FAILED")
    return app, server, worker, httpx.Client(
        base_url=f"http://127.0.0.1:{port}",trust_env=False,timeout=15)


def stop(server, worker, client):
    client.close()
    server.should_exit = True
    worker.join(timeout=45)
    if worker.is_alive():
        raise RuntimeError("ISOLATED_HTTP_SHUTDOWN_TIMEOUT")


def main():
    run_id = uuid.uuid4().hex[:16]
    settings = replace(load_settings(),
        database_path=ROOT/f"infra/runtime/p02/relationships-{run_id}.sqlite3",
        memos_api_token="", memory_llm_request_budget=12)
    assert settings.memory_llm_key and settings.memory_llm_provider == "deepseek"
    store = Store(settings.database_path)
    owner, other = f"p02-timeline-a-{run_id}", f"p02-timeline-b-{run_id}"
    owner_auth, other_auth = token(settings, owner), token(settings, other)
    internal = {"X-Internal-Token":settings.internal_token}
    result = {"run_id":run_id,"started_at":utc_now(),"checks":{},
              "provider":settings.memory_llm_provider,
              "model":settings.memory_llm_model,"request_budget":settings.memory_llm_request_budget,
              "max_output_tokens_per_request":settings.memory_llm_max_tokens,
              "cost":"UNKNOWN","scope":"real localhost HTTP with synthetic source IDs"}
    checks = result["checks"]
    app, server, worker, client = start(settings)
    try:
        for source_user in (owner, other):
            response = client.post("/internal/v1/users/bootstrap",headers=internal,json={
                "librechat_user_id":source_user,"memos_user_id":"p02-synthetic",
                "memory_consent":True,"image_consent":False})
            response.raise_for_status()
        response = client.patch("/api/v1/me/settings",headers=owner_auth,json={"recall_consent":True})
        response.raise_for_status()
        uid = store.get_user_by_librechat_id(owner)["life_user_id"]
        bodies = []
        inputs = [
            ("wang-old","2026-10-23，小王在青禾科技工作。"),
            ("li","2026-10-25，小李在远帆科技工作。"),
            ("chen-invite-a","2026-10-26，小陈邀请我加入青禾科技。"),
            ("wang-current","2026-10-29，小王从青禾科技跳槽到远帆科技工作。"),
            ("chen-invite-b","2026-11-03，小陈邀请我加入远帆科技，我还没有加入这家公司。"),
            ("wang-late","2026-10-24，小王在青禾科技工作。"),
        ]
        elapsed = []
        for suffix, text in inputs:
            body = {"source_user_id":owner,"source_message_id":f"{run_id}-{suffix}",
                "conversation_id":f"{run_id}-conversation-{suffix}","text":text,
                "occurred_at":datetime.now(UTC).isoformat()}
            bodies.append(body)
            started = time.monotonic()
            queued = client.post("/internal/v1/events/enqueue",headers=internal,json=body)
            queued.raise_for_status()
            assert queued.json()["accepted"]
            job_id = queued.json()["job_id"]
            deadline = time.monotonic()+135
            while time.monotonic()<deadline:
                with store.connect() as db:
                    job = dict(db.execute("SELECT * FROM memory_jobs WHERE job_id=?", (job_id,)).fetchone())
                    row = db.execute(
                        "SELECT m.* FROM memory_items m JOIN memory_evidence e "
                        "ON m.memory_id=e.memory_id AND m.user_id=e.user_id "
                        "WHERE e.user_id=? AND e.message_id=?", (uid,body["source_message_id"])).fetchone()
                if job["status"] in ("failed","succeeded","blocked_provider"):
                    break
                time.sleep(.25)
            assert job["status"] == "succeeded" and row is not None, f"NO_GROUNDED_RELATION:{suffix}:{job['status']}"
            assert row["semantic_key"].startswith("relation:"), f"WRONG_FACT_KIND:{suffix}"
            elapsed.append(round(time.monotonic()-started,3))
            print(json.dumps({"sample":suffix,"status":"persisted","seconds":elapsed[-1]}),flush=True)
        checks["six_real_langmem_relations_over_twelve_day_timeline"] = "PASS"

        def recall(query, headers=owner_auth):
            response = client.get("/api/v1/knowledge/recall",headers=headers,params={"q":query})
            response.raise_for_status()
            return response.json()["items"]

        current = recall("小王目前在哪家公司工作？")
        historical = recall("2026-10-24小王在哪家公司工作？")
        invitation = recall("谁邀请我加入青禾科技？")
        invitation_b = recall("谁邀请我加入远帆科技？")
        li = recall("小李目前在哪家公司工作？")
        assert len(current)==1 and current[0]["value"]=="远帆科技"
        assert len(historical)==1 and historical[0]["value"]=="青禾科技"
        assert len(li)==1 and li[0]["value"]=="远帆科技"
        assert len(invitation)==1 and ":invited:" in invitation[0]["semantic_key"]
        assert len(invitation_b)==1 and ":invited:" in invitation_b[0]["semantic_key"]
        assert recall("我目前在哪家公司工作？") == [], "UNPROVEN_SELF_EMPLOYMENT"
        checks["people_companies_invitations_and_current_history"] = "PASS"
        detail = client.get("/api/v1/knowledge/"+historical[0]["memory_id"],headers=owner_auth).json()["item"]
        assert len(detail["sources"])==2 and detail["event_date"]=="2026-10-23"
        assert detail["event_end_date"]=="2026-10-29"
        checks["late_source_merges_with_historical_interval"] = "PASS"
        with store.connect() as db:
            before = db.execute("SELECT count(*) FROM memory_items WHERE user_id=?", (uid,)).fetchone()[0]
        for body in bodies:
            response = client.post("/internal/v1/events/enqueue",headers=internal,json=body)
            assert response.json()["status"]=="succeeded"
        with store.connect() as db:
            after = db.execute("SELECT count(*) FROM memory_items WHERE user_id=?", (uid,)).fetchone()[0]
        assert before==after==5
        checks["same_source_replay_does_not_create_memory_or_provider_job"] = "PASS"
        assert recall("小王目前在哪家公司工作？", other_auth)==[]
        for item in (current[0],historical[0],li[0],invitation[0],invitation_b[0]):
            assert client.get("/api/v1/knowledge/"+item["memory_id"],headers=other_auth).status_code==404
        checks["cross_account_api_reads_refused"] = "PASS"

        deadline = time.monotonic()+25
        while time.monotonic()<deadline:
            with store.connect() as db:
                pending = db.execute("SELECT count(*) FROM memory_graph_jobs WHERE status!='succeeded'").fetchone()[0]
            if pending==0:
                break
            time.sleep(.2)
        assert pending==0
        with app.state.memory.graph.driver.session() as session:
            rows = [dict(row) for row in session.run(
                "MATCH (p:Entity {owner_id:$owner})-[r:RELATED]->(o:Entity) "
                "RETURN p.name AS person,o.name AS organization,r.type AS type,"
                "r.state AS state,r.event_date AS event_date,r.event_end_date AS event_end_date "
                "ORDER BY person,type,event_date", owner=uid)]
        assert len(rows)==5
        assert any(r["person"]=="小王" and r["organization"]=="青禾科技"
            and r["state"]=="superseded" and r["event_end_date"]=="2026-10-29" for r in rows)
        assert historical[0]["memory_id"] in app.state.memory.graph.search_memory_ids(
            uid,"小王工作",as_of="2026-10-24")
        checks["real_neo4j_relationships_with_valid_time"] = "PASS"
        result["graph_rows"] = rows
        stop(server,worker,client)
        app, server, worker, client = start(settings)
        assert recall("小王目前在哪家公司工作？")[0]["value"]=="远帆科技"
        assert recall("2026-10-24小王在哪家公司工作？")[0]["value"]=="青禾科技"
        checks["real_http_server_restart_restores_current_and_history"] = "PASS"
        result["extraction_seconds"]=elapsed
        result["status"]="PASS"
    except Exception as exc:
        result.update(status="FAIL",error_type=type(exc).__name__,error=str(exc))
        (ROOT/f"infra/runtime/p02/relationships-{run_id}-failure.txt").write_text(
            traceback.format_exc(),encoding="utf-8")
    finally:
        stop(server,worker,client)
        with store.connect() as db:
            result["provider_requests"] = [dict(row) for row in db.execute(
                "SELECT model,status,input_tokens,output_tokens,error_code FROM memory_model_calls")]
        result["total_requests"] = len(result["provider_requests"])
        result["input_tokens"] = sum(row["input_tokens"] or 0 for row in result["provider_requests"])
        result["output_tokens"] = sum(row["output_tokens"] or 0 for row in result["provider_requests"])
        result["usage_complete"] = all(
            row["input_tokens"] is not None and row["output_tokens"] is not None
            for row in result["provider_requests"])
        result["ended_at"]=utc_now()
        target = ROOT/f"evidence/p02/relationships-{run_id}.json"
        target.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    sys.exit(main())
