"""Storage/HTTP/Neo4j temporal checks; does not claim model extraction passed."""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from acceptance_p02_relationships import ROOT, load_settings, start, stop, token
from app.memory import Candidate, MemoryEntity, MemoryRelation
from app.store import Store, utc_now


def main():
    run_id = uuid.uuid4().hex[:16]
    settings = replace(load_settings(), memory_llm_key="",
        database_path=ROOT/f"infra/runtime/p02/graph-timeline-{run_id}.sqlite3")
    app, server, worker, client = start(settings)
    store = Store(settings.database_path)
    owner, other = f"timeline-a-{run_id}", f"timeline-b-{run_id}"
    headers = token(settings, owner)
    result = {"run_id":run_id,"started_at":utc_now(),"provider_calls":0,
              "scope":"typed synthetic fixtures -> authoritative SQLite -> real HTTP/Neo4j; no model extraction"}
    try:
        for user in (owner,other):
            response = client.post("/internal/v1/users/bootstrap",
                headers={"X-Internal-Token":settings.internal_token},
                json={"librechat_user_id":user,"memos_user_id":"synthetic","memory_consent":True})
            response.raise_for_status()
        client.patch("/api/v1/me/settings",headers=headers,json={"recall_consent":True}).raise_for_status()
        uid = store.get_user_by_librechat_id(owner)["life_user_id"]
        fixtures = [
            ("a","小王","青禾科技","works_at","2026-10-23，小王在青禾科技工作。"),
            ("b","小李","远帆科技","works_at","2026-10-25，小李在远帆科技工作。"),
            ("c","小陈","青禾科技","invited","2026-10-26，小陈邀请我加入青禾科技。"),
            ("d","小王","远帆科技","works_at","2026-10-29，小王从青禾科技跳槽到远帆科技工作。"),
            ("e","小陈","远帆科技","invited","2026-11-03，小陈邀请我加入远帆科技，我还没有加入这家公司。"),
            ("f","小王","青禾科技","works_at","2026-10-24，小王在青禾科技工作。"),
        ]
        now = datetime.now(UTC)
        identifiers = []
        for suffix, person, company, kind, text in fixtures:
            candidate = Candidate(candidate_type="stable_fact",fact_key="relationship",
                canonical_text=f"{person}在{company}工作" if kind=="works_at" else text,
                evidence_quote=text,occurred_state="occurred",value=company,confidence=1,
                sensitivity="ordinary",
                entities=[MemoryEntity(name=person,entity_type="person"),
                          MemoryEntity(name=company,entity_type="organization")],
                relations=[MemoryRelation(source=person,target=company,relation_type=kind)])
            key = app.state.memory.key_for(candidate,text,now)
            mid = app.state.memory.save(uid,candidate,key,f"{run_id}-{suffix}",
                f"conversation-{run_id}-{suffix}",text,now)["memory_id"]
            identifiers.append(mid)
            repeated = app.state.memory.save(uid,candidate,key,f"{run_id}-{suffix}",
                f"conversation-{run_id}-{suffix}",text,now)
            assert repeated["memory_id"]==mid
        checks = {}

        def recall(query, auth=headers):
            response = client.get("/api/v1/knowledge/recall",headers=auth,params={"q":query})
            response.raise_for_status()
            return response.json()["items"]

        queries = [
            ("小王目前在哪家公司工作？","远帆科技"),
            ("2026-10-24小王在哪家公司工作？","青禾科技"),
            ("小李目前在哪家公司工作？","远帆科技"),
            ("谁邀请我加入青禾科技？","青禾科技"),
            ("谁邀请我加入远帆科技？","远帆科技"),
        ]
        for query, expected in queries:
            rows = recall(query)
            assert len(rows)==1 and rows[0]["value"]==expected, query
        assert recall("我目前在哪家公司工作？")==[]
        checks["current_historical_person_company_and_invitation_queries"] = "PASS"
        assert identifiers[0]==identifiers[-1] and len(set(identifiers))==5
        detail = client.get("/api/v1/knowledge/"+identifiers[0],headers=headers).json()["item"]
        assert len(detail["sources"])==2 and detail["event_end_date"]=="2026-10-29"
        assert detail["state"]=="superseded" and detail["event_date"]=="2026-10-23"
        checks["late_history_merge_source_replay_and_no_duplicate_record"] = "PASS"
        for mid in set(identifiers):
            assert client.get("/api/v1/knowledge/"+mid,headers=token(settings,other)).status_code==404
        assert recall(queries[0][0],token(settings,other))==[]
        checks["cross_account_http_isolation"] = "PASS"
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            with store.connect() as db:
                remaining = db.execute("SELECT count(*) FROM memory_graph_jobs WHERE status!='succeeded'").fetchone()[0]
            if not remaining:
                break
            time.sleep(.2)
        assert not remaining
        with app.state.memory.graph.driver.session() as session:
            graph_rows = [dict(row) for row in session.run(
                "MATCH (p:Entity {owner_id:$owner})-[r:RELATED]->(o:Entity) "
                "RETURN p.name AS person,o.name AS company,r.type AS type,r.state AS state,"
                "r.event_date AS event_date,r.event_end_date AS event_end_date "
                "ORDER BY person,type,event_date",owner=uid)]
        assert len(graph_rows)==5
        assert any(row["person"]=="小王" and row["company"]=="青禾科技" and
                   row["state"]=="superseded" and row["event_end_date"]=="2026-10-29" for row in graph_rows)
        assert identifiers[0] in app.state.memory.graph.search_memory_ids(uid,"小王工作",as_of="2026-10-24")
        checks["real_neo4j_projection_and_temporal_lookup"] = "PASS"
        result["graph_rows"]=graph_rows
        stop(server,worker,client)
        app, server, worker, client = start(settings)
        for query,expected in queries:
            rows=recall(query)
            assert len(rows)==1 and rows[0]["value"]==expected
        checks["http_server_restart_preserves_temporal_results"] = "PASS"
        for mid in set(identifiers):
            client.delete("/api/v1/knowledge/"+mid,headers=headers).raise_for_status()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            with app.state.memory.graph.driver.session() as session:
                residue=session.run("MATCH (n {owner_id:$owner}) RETURN count(n) AS n",owner=uid).single()["n"]
            if residue==0:
                break
            time.sleep(.2)
        assert residue==0 and recall("小王目前在哪家公司工作？")==[]
        checks["all_synthetic_history_withdrawn_and_graph_content_removed"] = "PASS"
        result.update(status="PASS",checks=checks)
    except Exception as exc:
        result.update(status="FAIL",error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        stop(server,worker,client)
        result["ended_at"]=utc_now()
        (ROOT/"evidence/p02/graph-timeline.json").write_text(
            json.dumps(result,ensure_ascii=True,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=True))


if __name__=="__main__":
    main()
