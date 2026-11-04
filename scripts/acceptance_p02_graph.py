"""Real graph recovery and content-deletion checks using synthetic P02 records."""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.config import load_settings
from app.memory import Candidate, MemoryEntity, MemoryRelation, MemoryService
from app.store import Store, utc_now
from app.graph import GraphProjector


def main():
    run_id = uuid.uuid4().hex
    settings = replace(
        load_settings(), database_path=ROOT / f"infra/runtime/p02/recovery-{run_id}.sqlite3"
    )
    store = Store(settings.database_path)
    store.initialize()
    memory = MemoryService(store, settings)
    memory.initialize()
    owner, other = f"recovery-a-{run_id}", f"recovery-b-{run_id}"
    candidate = Candidate(
        candidate_type="life_event",
        canonical_text="Alice works at Northstar Labs",
        evidence_quote="Alice works at Northstar Labs",
        occurred_state="occurred",
        confidence=.9,
        sensitivity="ordinary",
        entities=[
            MemoryEntity(name="Alice", entity_type="person"),
            MemoryEntity(name="Northstar Labs", entity_type="organization"),
        ],
        relations=[
            MemoryRelation(source="Alice", relation_type="works_at", target="Northstar Labs")
        ],
    )

    def save(who, suffix):
        return memory.save(
            who, candidate, f"event:{suffix}", f"{run_id}-{suffix}", f"conv-{run_id}",
            candidate.evidence_quote, datetime.now(UTC),
        )["memory_id"]

    def count(who):
        with memory.graph.driver.session() as session:
            return session.run(
                "MATCH (n {owner_id:$owner}) RETURN count(n) AS n", owner=who
            ).single()["n"]

    def job(mid):
        with store.connect() as db:
            return dict(db.execute(
                "SELECT * FROM memory_graph_jobs WHERE memory_id=?", (mid,)
            ).fetchone())

    checks = {}
    try:
        mid = save(owner, "original")
        other_mid = save(other, "other")
        while memory.project_one():
            pass
        assert count(owner) == 4 and count(other) == 4
        assert mid in memory.graph.search_memory_ids(owner, "Alice")
        assert other_mid not in memory.graph.search_memory_ids(owner, "Alice")
        checks["real_projection_and_namespaced_search"] = "PASS"

        original_project = memory.graph.project

        def invalidate_after_graph_write(who, item):
            original_project(who, item)
            memory.invalidate(who, item)

        save(owner, "original")
        memory.graph.project = invalidate_after_graph_write
        assert memory.project_one()
        assert job(mid)["status"] == "queued"
        memory.graph.project = original_project
        assert memory.project_one()
        assert count(owner) == 0 and count(other) == 4
        checks["new_generation_survives_stale_acknowledgment"] = "PASS"
        checks["withdrawal_removes_evidence_entities_and_relations"] = "PASS"
        checks["other_owner_content_preserved"] = "PASS"

        restart_mid = save(owner, "restart")
        with store.connect() as db:
            db.execute(
                "UPDATE memory_graph_jobs SET status='running' WHERE memory_id=?", (restart_mid,)
            )
        restarted = MemoryService(store, settings)
        restarted.initialize()
        try:
            assert job(restart_mid)["status"] == "queued"
            assert restarted.project_one() and job(restart_mid)["status"] == "succeeded"
            checks["interrupted_job_requeued_after_restart"] = "PASS"
        finally:
            restarted.graph.close()

        memory.invalidate(owner, restart_mid)
        unavailable = GraphProjector(store, replace(settings, neo4j_password="synthetic-invalid-password"))
        try:
            assert unavailable.run_one()
            failed = job(restart_mid)
            assert failed["status"] == "queued" and failed["last_error"] == "GRAPH_PROJECTION_FAILED"
        finally:
            unavailable.close()
        with store.connect() as db:
            db.execute("UPDATE memory_graph_jobs SET updated_at=? WHERE memory_id=?",
                       (utc_now(), restart_mid))
        assert memory.project_one() and job(restart_mid)["status"] == "succeeded"
        assert count(owner) == 0
        checks["real_auth_failure_retains_job_and_recovers"] = "PASS"

        memory.invalidate(other, other_mid)
        assert memory.project_one() and count(other) == 0
        checks["test_namespace_cleanup"] = "PASS"
        result = {"status": "PASS", "run_id": run_id, "checks": checks,
                  "ended_at": utc_now(), "provider_calls": 0}
        output = ROOT / "evidence/p02/graph-recovery.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        memory.graph.close()


if __name__ == "__main__":
    main()
