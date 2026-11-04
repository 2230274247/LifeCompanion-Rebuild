"""Verify an exhausted real acceptance ledger with network access disabled."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from unittest.mock import patch

import httpx

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.config import load_settings
from app.memory import MemoryProviderQuotaError, MemoryService
from app.store import Store, utc_now


def main():
    run_id = sys.argv[1]
    if not re.fullmatch(r"[0-9a-f]{16}", run_id):
        raise ValueError("INVALID_ACCEPTANCE_RUN")
    path = ROOT / f"infra/runtime/p02/relationships-{run_id}.sqlite3"
    if not path.is_file():
        raise ValueError("ACCEPTANCE_DATABASE_MISSING")
    settings = replace(load_settings(), database_path=path, memory_llm_request_budget=12)
    store = Store(path)
    memory = MemoryService(store, settings)
    memory.initialize()
    attempts = []

    def reject_network(*args, **kwargs):
        attempts.append(1)
        raise AssertionError("NETWORK_MUST_NOT_BE_REACHED")

    try:
        with store.connect() as db:
            before = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert before == settings.memory_llm_request_budget
        with patch.object(httpx.Client, "send", reject_network):
            try:
                memory._llm("synthetic budget check")
            except MemoryProviderQuotaError as exc:
                assert str(exc) == "MEMORY_MODEL_REQUEST_BUDGET"
            else:
                raise AssertionError("REQUEST_BUDGET_NOT_ENFORCED")
        with store.connect() as db:
            after = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert before == after and attempts == []
        result = {
            "status": "PASS", "run_id": run_id, "checked_at": utc_now(),
            "persisted_requests_before": before, "persisted_requests_after": after,
            "http_send_attempts": len(attempts), "additional_generation_calls": 0,
            "scope": "real persisted acceptance ledger and LangMem/SDK; HTTP transport disabled",
        }
        (ROOT / "evidence/p02/deepseek-request-budget.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        memory.graph.close()


if __name__ == "__main__":
    main()
