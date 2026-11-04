"""Run the browser against a fresh Core and an actual separate HTTP gateway."""
import json
import os
import socket
import subprocess
import time
import uuid
from dataclasses import replace

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, utc_now
from verify_rebuild_workspace import verify


def main():
    verify(ROOT)
    run_id = uuid.uuid4().hex[:16]
    evidence = ROOT / f"evidence/p03/business-ui-{run_id}"
    evidence.mkdir()
    runtime = ROOT / f"infra/runtime/p02/business-ui-{run_id}"
    runtime.mkdir()
    settings = replace(
        load_settings(), database_path=runtime / "life.sqlite3", memory_llm_key="",
        memory_llm_request_budget=0, memos_api_token="", neo4j_uri="", vikunja_users={},
        reminder_scheduler_external=True,
        reminder_webhook_url="http://host.docker.internal:9/unused-business-ui-callback")
    app, server, worker, client = start(settings)
    gateway = None
    output = (runtime / "gateway.log").open("ab")
    result = {"status": "FAIL", "run_id": run_id, "provider_calls": 0,
              "started_at": utc_now(), "database": str(settings.database_path.relative_to(ROOT))}
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        core_url = str(client.base_url).rstrip("/")
        origin = f"http://127.0.0.1:{port}"
        code = (
            "import {createGateway} from './apps/product-portal/server.mjs'; "
            f"createGateway({{chatTarget:'http://127.0.0.1:3091',lifeTarget:'{core_url}'}})"
            f".listen({port},'127.0.0.1');")
        gateway = subprocess.Popen(
            ["node", "--input-type=module", "-e", code], cwd=ROOT,
            stdout=output, stderr=output,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ready = False
        for _ in range(30):
            if gateway.poll() is not None:
                break
            try:
                response = httpx.get(origin + "/login", timeout=2)
                ready = response.status_code == 200
            except httpx.HTTPError:
                pass
            if ready:
                break
            time.sleep(.5)
        assert ready, "TEMPORARY_GATEWAY_NOT_READY"
        env = {**os.environ, "LIFE_ACCEPTANCE_CORE_URL": core_url,
               "LIFE_ACCEPTANCE_ORIGIN": origin, "LIFE_ACCEPTANCE_UI_EVIDENCE": str(evidence)}
        with (evidence / "browser-console.txt").open("w", encoding="utf-8") as console:
            browser = subprocess.Popen(
                ["node", "scripts/acceptance_p03_chips_ui.cjs"], cwd=ROOT, env=env,
                stdout=console, stderr=console,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                deadline = time.monotonic() + 240
                while browser.poll() is None and time.monotonic() < deadline:
                    time.sleep(.5)
                assert browser.poll() == 0, "BUSINESS_BROWSER_CHECK_FAILED_OR_TIMED_OUT"
            finally:
                if browser.poll() is None:
                    browser.terminate()
                    browser.wait(timeout=15)
        report = json.loads((evidence / "chips-live-ui.json").read_text(encoding="utf-8"))
        assert report["status"] == "PASS"
        with app.state.store.connect() as db:
            owner = db.execute("SELECT life_user_id FROM users").fetchone()[0]
            calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        states = []
        for scenario in report["scenarios"]:
            state = app.state.reminder_drafts.workflow.snapshot(owner, scenario["draft_id"])
            assert state["values"]["workflow_version"] == 2
            assert state["values"]["status"] == "cancelled" and state["next"] == []
            record = app.state.store.get_reminder(scenario["reminder_id"], owner)
            assert record["revision"] == 2 and record["status"] == "cancelled"
            states.append({"draft_id": scenario["draft_id"], "next": state["next"],
                           "status": state["values"]["status"], "business_revision": record["revision"]})
        assert calls == 0
        result.update(status="PASS", gateway_origin=origin, temporary_core_url=core_url,
                      graph_states=states, model_call_rows=calls,
                      browser_report=str((evidence / "chips-live-ui.json").relative_to(ROOT)))
    finally:
        if gateway is not None and gateway.poll() is None:
            gateway.terminate()
            gateway.wait(timeout=15)
        stop(server, worker, client)
        output.close()
        result["ended_at"] = utc_now()
        (evidence / "business-backend-proof.json").write_text(
            json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
