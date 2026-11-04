"""Real LangMem + isolated SQLite + isolated Neo4j acceptance for P02."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from dataclasses import replace
from datetime import datetime, UTC
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/life-core"))
runtime = root / "infra/runtime/p02"


def read_env(path):
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )


os.environ.update(read_env(root / "infra/runtime/p00/acceptance.env"))
neo = read_env(runtime / "neo4j.env")
os.environ.update(
    LIFE_NEO4J_URI="bolt://127.0.0.1:7688",
    LIFE_NEO4J_USER="neo4j",
    LIFE_NEO4J_PASSWORD=neo["NEO4J_AUTH"].split("/", 1)[1],
)

from app.config import load_settings
from app.main import create_app

stamp = datetime.now(UTC).isoformat()
run_id = uuid.uuid4().hex[:12]
settings = replace(
    load_settings(),
    database_path=runtime / f"live-{run_id}.sqlite3",
    memos_api_token="",
)
result = {"started_at": stamp, "provider": settings.memory_llm_provider,
          "model": settings.memory_llm_model, "checks": {}}


def token(user):
    encode = lambda value: base64.urlsafe_b64encode(
        json.dumps(value, ensure_ascii=True).encode()
    ).rstrip(b"=")
    parts = [
        encode({"alg": "HS256", "typ": "JWT"}),
        encode({"id": user, "exp": int(time.time()) + 900}),
    ]
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(), b".".join(parts), hashlib.sha256).digest()
    ).rstrip(b"=")
    return {"Authorization": "Bearer " + b".".join([*parts, signature]).decode()}


def await_state(client, user_auth, deadline):
    while time.monotonic() < deadline:
        with client.app.state.store.connect() as db:
            job = db.execute(
                "SELECT status,attempts FROM memory_jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        items = client.get("/api/v1/knowledge", headers=user_auth).json()["items"]
        if job and job["status"] in ("succeeded", "failed"):
            return dict(job), items
        time.sleep(0.25)
    raise TimeoutError("LANGMEM_JOB_TIMEOUT")


try:
    assert settings.memory_llm_key, "REAL_PROVIDER_KEY_MISSING"
    app = create_app(settings)
    with TestClient(app) as client:
        internal = {"X-Internal-Token": settings.internal_token}
        for user in ("synthetic-p02-a", "synthetic-p02-b"):
            response = client.post(
                "/internal/v1/users/bootstrap",
                headers=internal,
                json={
                    "librechat_user_id": user,
                    "memos_user_id": "p02-synthetic",
                    "memory_consent": True,
                    "image_consent": False,
                },
            )
            assert response.status_code == 200
        owner_auth = token("synthetic-p02-a")
        other_auth = token("synthetic-p02-b")
        assert client.patch(
            "/api/v1/me/settings", headers=owner_auth, json={"recall_consent": True}
        ).status_code == 200
        body = {
            "source_user_id": "synthetic-p02-a",
            "source_message_id": f"{run_id}-tea",
            "conversation_id": f"synthetic-p02-conversation-{run_id}",
            "text": "\u6211\u5e73\u5e38\u559c\u6b22\u559d\u9f99\u4e95\u8336",
            "occurred_at": stamp,
        }
        queued = client.post("/internal/v1/events/enqueue", headers=internal, json=body)
        assert queued.status_code == 200 and queued.json()["accepted"]
        job, items = await_state(client, owner_auth, time.monotonic() + 90)
        assert job["status"] == "succeeded" and items
        memory = items[0]
        assert memory["kind"] == "stable_fact"
        result["checks"]["real_langmem_to_sqlite"] = "PASS"
        result["checks"]["source_evidence_count"] = memory["evidence_count"]

        recalled = client.get(
            "/api/v1/knowledge/recall?q=%E4%BB%8A%E5%A4%A9%E5%96%9D%E4%BB%80%E4%B9%88%E8%8C%B6",
            headers=owner_auth,
        ).json()["items"]
        assert recalled and "\u9f99\u4e95\u8336" in recalled[0]["canonical_text"]
        assert client.get("/api/v1/knowledge/recall?q=%E5%96%9D%E8%8C%B6", headers=other_auth).json()["items"] == []
        result["checks"]["cross_session_recall_and_account_isolation"] = "PASS"

        def ingest_rule(text, suffix, conversation):
            response = client.post(
                "/internal/v1/events/ingest",
                headers=internal,
                json={
                    "source_user_id": "synthetic-p02-a",
                    "source_message_id": f"{run_id}-{suffix}",
                    "conversation_id": conversation,
                    "text": text,
                    "occurred_at": stamp,
                },
            )
            assert response.status_code == 200 and response.json()["accepted"]

        ingest_rule(
            "\u660e\u5929\u5e26\u7eff\u8272U\u76d8\uff0c\u4e0d\u662f\u94f6\u8272\u7684",
            "usb",
            f"conversation-a-{run_id}",
        )
        ingest_rule(
            "\u660e\u5929\u8fd8\u8981\u5e26\u96e8\u4f1e",
            "umbrella",
            f"conversation-b-{run_id}",
        )
        plans = client.get(
            "/api/v1/knowledge/recall?q=%E6%98%8E%E5%A4%A9%E5%B8%A6%E4%BB%80%E4%B9%88%E4%B8%9C%E8%A5%BF",
            headers=owner_auth,
        ).json()["items"]
        assert len(plans) == 2
        usb = next(item for item in plans if "U\u76d8" in item["canonical_text"])
        assert "\u7eff\u8272" in usb["canonical_text"] and "\u4e0d\u662f\u94f6\u8272" in usb["canonical_text"]
        source = client.get(f"/api/v1/knowledge/{usb['memory_id']}", headers=owner_auth).json()["item"]
        assert any(item["conversation_id"] == f"conversation-a-{run_id}" for item in source["sources"])
        result["checks"]["cross_conversation_usb_umbrella_and_source"] = "PASS"

        ingest_rule(
            "\u660e\u5929\u5e26\u7684\u7eff\u8272U\u76d8\u6539\u4e3a\u84dd\u8272U\u76d8",
            "usb-correction",
            f"conversation-c-{run_id}",
        )
        corrected = client.get(
            "/api/v1/knowledge/recall?q=%E6%98%8E%E5%A4%A9%E5%B8%A6%E4%BB%80%E4%B9%88U%E7%9B%98",
            headers=owner_auth,
        ).json()["items"]
        assert len(corrected) == 1 and "\u84dd\u8272" in corrected[0]["canonical_text"]
        assert "\u7eff\u8272" not in corrected[0]["canonical_text"]
        result["checks"]["correction_keeps_only_current_plan"] = "PASS"

        memory_id = memory["memory_id"]
        owner_id = client.app.state.store.get_user_by_librechat_id("synthetic-p02-a")["life_user_id"]
        graph_job_deadline = time.monotonic() + 20
        while time.monotonic() < graph_job_deadline:
            with client.app.state.store.connect() as db:
                graph_job = db.execute(
                    "SELECT status FROM memory_graph_jobs WHERE memory_id=?", (memory_id,)
                ).fetchone()
            if graph_job and graph_job["status"] == "succeeded":
                break
            time.sleep(0.1)
        assert graph_job and graph_job["status"] == "succeeded"
        password = neo["NEO4J_AUTH"].split("/", 1)[1]
        with GraphDatabase.driver("bolt://127.0.0.1:7688", auth=("neo4j", password)) as driver:
            with driver.session() as session:
                graph = session.run(
                    "MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id})"
                    "-[:HAS_EVIDENCE]->(e:Evidence) RETURN count(e) AS evidence",
                    owner_id=owner_id,
                    memory_id=memory_id,
                ).single()["evidence"]
        assert graph == 1
        assert memory_id in client.app.state.memory.graph.search_memory_ids(owner_id, "龙井茶")
        result["checks"]["neo4j_projection_with_real_source_edge"] = "PASS"
        result["checks"]["graph_keyword_retrieval"] = "PASS"

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get(
            "/api/v1/knowledge/recall?q=%E4%BB%8A%E5%A4%A9%E5%96%9D%E4%BB%80%E4%B9%88%E8%8C%B6",
            headers=owner_auth,
        ).json()["items"]
        assert restored and memory_id == restored[0]["memory_id"]
        result["checks"]["sqlite_restore_after_core_restart"] = "PASS"
        active = restarted.get("/api/v1/knowledge", headers=owner_auth).json()["items"]
        for item in active:
            deleted = restarted.delete(f"/api/v1/knowledge/{item['memory_id']}", headers=owner_auth)
            assert deleted.status_code == 200
        cleanup_deadline = time.monotonic() + 20
        while time.monotonic() < cleanup_deadline:
            with restarted.app.state.store.connect() as db:
                graph_jobs = db.execute(
                    "SELECT status FROM memory_graph_jobs"
                ).fetchall()
            if graph_jobs and all(job["status"] == "succeeded" for job in graph_jobs):
                break
            time.sleep(0.1)
        with GraphDatabase.driver("bolt://127.0.0.1:7688", auth=("neo4j", password)) as driver:
            with driver.session() as session:
                residue = session.run(
                    "MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) RETURN count(m) AS n",
                    owner_id=owner_id,
                    memory_id=memory_id,
                ).single()["n"]
        assert residue == 0
        result["checks"]["withdrawal_propagates_to_graph"] = "PASS"
        result["status"] = "PASS"
except Exception as exc:
    result["status"] = "FAIL"
    result["error_type"] = type(exc).__name__
    result["error_code"] = str(exc)
finally:
    result["ended_at"] = datetime.now(UTC).isoformat()
    (runtime / f"live-{run_id}.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8"
    )
print(json.dumps(result, ensure_ascii=True))
sys.exit(0 if result.get("status") == "PASS" else 1)
