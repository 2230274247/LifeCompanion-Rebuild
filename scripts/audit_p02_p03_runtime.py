"""Read-only persisted evidence audit; never invoke a generation provider."""
import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify


def connect(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def main():
    identity = verify(ROOT)
    environment()
    from app.config import load_settings
    from neo4j import GraphDatabase

    settings = load_settings()
    relationship = json.loads(
        (ROOT / "evidence/p02/relationships-97b5ef4146644c32.json").read_text(encoding="utf-8"))
    delivery = json.loads(
        (ROOT / "evidence/p03/delivery-recovery-0f6f567301144310.json").read_text(encoding="utf-8"))
    report = {"status": "FAIL", "checked_at": datetime.now(UTC).isoformat(),
              "provider_calls": 0, "identity": identity, "checks": {}}
    with connect(ROOT / "infra/runtime/p02/relationships-97b5ef4146644c32.sqlite3") as db:
        usage = dict(db.execute(
            "SELECT count(*) AS requests, sum(input_tokens) AS input_tokens, "
            "sum(output_tokens) AS output_tokens FROM memory_model_calls").fetchone())
        assert usage == {"requests": 12, "input_tokens": 33756, "output_tokens": 1779}
        statuses = {row["status"]: row["n"] for row in db.execute(
            "SELECT status,count(*) AS n FROM memory_model_calls GROUP BY status")}
        assert statuses == {"succeeded": 12}
        pending = db.execute(
            "SELECT count(*) FROM memory_graph_jobs WHERE status!='succeeded'").fetchone()[0]
        assert pending == 0
        report["p02_sqlite"] = {**usage, "statuses": statuses, "pending_graph_jobs": pending}
    owner = "life_" + hashlib.sha256(
        b"p02-timeline-a-97b5ef4146644c32").hexdigest()[:20]
    with GraphDatabase.driver(settings.neo4j_uri,
                              auth=(settings.neo4j_user, settings.neo4j_password)) as driver:
        with driver.session() as session:
            rows = [dict(row) for row in session.run(
                "MATCH (p:Entity {owner_id:$owner})-[r:RELATED]->(o:Entity) "
                "RETURN p.name AS person,o.name AS organization,r.type AS type,"
                "r.state AS state,r.event_date AS event_date,r.event_end_date AS event_end_date "
                "ORDER BY person,type,event_date", owner=owner)]
    assert rows == relationship["graph_rows"]
    report["p02_graph_rows"] = rows
    report["checks"]["persisted_p02_usage_and_live_graph_match_original_evidence"] = "PASS"

    with connect(ROOT / delivery["database"]) as db:
        outbox = [dict(row) for row in db.execute(
            "SELECT event_id,status,attempts,last_error FROM reminder_notifications")]
        assert len(outbox) == 1 and outbox[0]["status"] == "accepted"
        assert outbox[0]["attempts"] == 2
        runs = [dict(row) for row in db.execute(
            "SELECT status,users,notifications_accepted,error_code FROM reminder_scheduler_runs")]
        assert runs == delivery["scheduler_runs"]
        assert db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0] == 0
        unfinished = db.execute(
            "SELECT count(*) FROM reminder_notifications WHERE status IN ('pending','sending')").fetchone()[0]
        assert unfinished == 0
    report["p03_sqlite"] = {"outbox": outbox, "scheduler_runs": runs,
                            "model_calls": 0, "unfinished_notifications": unfinished}
    with connect((ROOT / delivery["database"]).parent / "scheduler.sqlite3") as db:
        jobs = db.execute("SELECT count(*) FROM apscheduler_jobs").fetchone()[0]
        assert jobs == 1
        report["p03_persisted_scheduler_jobs"] = jobs
    report["checks"]["persisted_p03_retry_acceptance_and_scheduler_match"] = "PASS"
    report["head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report["status"] = "PASS"
    (ROOT / "evidence/p03/final-runtime-audit.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
