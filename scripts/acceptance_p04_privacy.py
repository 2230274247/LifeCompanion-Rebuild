"""Real clock, HTTP, SQLite, Memos and optional browser; no cloud model/image calls."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, token, utc_now
from verify_rebuild_workspace import verify


def main():
    verify(ROOT)
    if os.environ.get("LIFE_P04_RUN_BROWSER") == "1":
        built = (ROOT / "products/librechat-custom/client/dist/index.html").read_text(encoding="utf-8")
        served = httpx.get("http://127.0.0.1:3091/login", timeout=15,
                           headers={"Accept-Encoding": "identity"}, trust_env=False)
        served.raise_for_status()
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', built)
        assert scripts and all(source in served.text for source in scripts), "FRONTEND_RELOAD_REQUIRED"
    run_id = uuid.uuid4().hex[:16]
    evidence = ROOT / f"evidence/p04/privacy-{run_id}"
    runtime = ROOT / f"infra/runtime/p04/privacy-{run_id}"
    evidence.mkdir(parents=True)
    runtime.mkdir(parents=True)
    original = load_settings()
    settings = replace(
        original, database_path=runtime / "life.sqlite3",
        memory_llm_key="", neo4j_uri="", vikunja_users={},
        reminder_scheduler_external=True)
    accounts = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))
    account = accounts["a"]
    login = httpx.post("http://127.0.0.1:3091/api/auth/login",
                       json={"email": account["email"], "password": account["password"]}, timeout=20)
    login.raise_for_status()
    auth = {"Authorization": "Bearer " + login.json()["token"]}
    other_source = f"p04-other-{run_id}"
    other_auth = token(settings, other_source)
    internal = {"X-Internal-Token": settings.internal_token}
    result = {"status": "FAIL", "run_id": run_id, "started_at": utc_now(),
              "scope": "real synthetic source ingest/Memos, configurable real-clock background job, Core restart and HTTP privacy; not model scoring or generated-image acceptance",
              "database": str(settings.database_path.relative_to(ROOT)),
              "provider_calls": 0, "image_status": "BLOCKED_IMAGE_PROVIDER", "checks": {}}
    app, server, worker, client = start(settings)
    gateway = None
    output = (runtime / "gateway.log").open("ab")
    owner = memory_id = None
    try:
        boot = client.post("/internal/v1/users/bootstrap", headers=internal, json={
            "librechat_user_id": account["librechat_user_id"],
            "memos_user_id": account["memos_user_id"], "display_name": "Synthetic P04 Privacy",
            "memory_consent": True, "image_consent": False})
        boot.raise_for_status()
        owner = boot.json()["life_user_id"]
        client.post("/internal/v1/users/bootstrap", headers=internal, json={
            "librechat_user_id": other_source, "memos_user_id": "",
            "display_name": "Synthetic P04 Other", "memory_consent": False,
            "image_consent": False}).raise_for_status()
        assert client.put("/api/v1/moment-settings", headers=auth, json={"enabled": True}).status_code == 403
        result["checks"]["enable_without_separate_image_consent_refused"] = "PASS"
        client.patch("/api/v1/me/settings", headers=auth, json={"image_consent": True}).raise_for_status()
        local = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        close = local.replace(second=0, microsecond=0) + timedelta(minutes=2)
        ends = sorted([(close + timedelta(minutes=2 * index)).strftime("%H:%M") for index in range(3)])
        assert close.date() == (close + timedelta(minutes=4)).date(), "MIDNIGHT_TEST_NEEDS_DIFFERENT_WINDOW"
        client.put("/api/v1/moment-settings", headers=auth, json={
            "enabled": True, "timezone": "Asia/Hong_Kong", "ends": ends}).raise_for_status()
        text = "【P04隔离合成聊天】今天第一次在公园散步，看见银杏，特别放松。"
        source = f"p04-privacy-source-{run_id}"
        body = {"source_user_id": account["librechat_user_id"], "source_message_id": source,
                "conversation_id": f"p04-privacy-conversation-{run_id}",
                "text": text, "occurred_at": datetime.now(UTC).isoformat()}
        event_response = client.post("/internal/v1/events/ingest", headers=internal, json=body, timeout=45)
        event_response.raise_for_status()
        event = event_response.json()["event"]
        assert event["memo_ref"] and event["status"] == "published"
        with app.state.store.connect() as db:
            memory_id = db.execute("SELECT memory_id FROM memory_items WHERE event_id=?", (event["event_id"],)).fetchone()[0]
        memo = app.state.memos.__class__(
            settings.memos_base_url, settings.memos_user_tokens[account["memos_user_id"]]
        ).get_private_memo(event["memo_ref"], account["memos_user_id"])
        assert source in memo["content"]
        result["checks"]["persisted_event_evidence_and_real_private_memos_read"] = "PASS"
        body.update(source_message_id=f"p04-empty-{run_id}", text="晚安", occurred_at=datetime.now(UTC).isoformat())
        empty = client.post("/internal/v1/events/ingest", headers=internal, json=body)
        empty.raise_for_status()
        assert not empty.json()["accepted"]
        result["checks"]["empty_talk_not_an_invented_event"] = "PASS"
        print(json.dumps({"phase": "waiting_real_clock", "configured_ends": ends,
                          "window_closes_at": close.isoformat()}), flush=True)
        deadline = time.monotonic() + 165
        rows = []
        while time.monotonic() < deadline:
            rows = client.get("/api/v1/moments", headers=auth).json()["moments"]
            if rows and rows[0]["status"] == "pending_provider":
                break
            time.sleep(.5)
        assert len(rows) == 1 and rows[0]["status"] == "pending_provider", "BACKGROUND_WINDOW_NOT_COMPLETED"
        identifier = rows[0]["moment_id"]
        assert rows[0]["source_memory_ids"] == [memory_id] and rows[0]["caption"] == event["summary"]
        assert datetime.fromisoformat(rows[0]["window_end"]).timestamp() <= time.time()
        detail = client.get(f"/api/v1/moments/{identifier}", headers=auth).json()["moment"]
        assert detail["image_data"] is None and detail["error_code"] == "IMAGE_PROVIDER_UNAVAILABLE"
        result["window"] = {"configured_ends": ends, "actual_window_end": detail["window_end"],
                            "observed_at": utc_now(), "source_memory_id": memory_id,
                            "moment_id": identifier, "image_data_present": False}
        result["checks"]["real_clock_configured_background_text_job_no_browser"] = "PASS"
        result["cross_account_statuses"] = [
            client.get(f"/api/v1/moments/{identifier}", headers=other_auth).status_code,
            client.post(f"/api/v1/moments/{identifier}/retry", headers=other_auth).status_code,
            client.delete(f"/api/v1/moments/{identifier}", headers=other_auth).status_code,
        ]
        assert result["cross_account_statuses"] == [404, 404, 404]
        result["checks"]["cross_account_read_retry_delete_refused"] = "PASS"
        stop(server, worker, client)
        # Simulate a process crash after dispatch, without sending a paid image request.
        with app.state.store.connect() as db:
            db.execute("UPDATE moments SET status='generating' WHERE moment_id=?", (identifier,))
        app, server, worker, client = start(settings)
        detail = client.get(f"/api/v1/moments/{identifier}", headers=auth).json()["moment"]
        assert detail["status"] == "unknown" and detail["retry_allowed"] is False
        rejected = client.post(f"/api/v1/moments/{identifier}/retry", headers=auth)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "IMAGE_RESULT_RECONCILIATION_REQUIRED"
        assert len(client.get("/api/v1/moments", headers=auth).json()["moments"]) == 1
        result["checks"]["injected_inflight_restart_unknown_retry_409_no_duplicate"] = "PASS"
        if os.environ.get("LIFE_P04_RUN_BROWSER") == "1":
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            origin = f"http://127.0.0.1:{port}"
            code = ("import {createGateway} from './apps/product-portal/server.mjs'; "
                    f"createGateway({{chatTarget:'http://127.0.0.1:3091',lifeTarget:'{str(client.base_url).rstrip('/')}'}})"
                    f".listen({port},'127.0.0.1');")
            gateway = subprocess.Popen(["node", "--input-type=module", "-e", code], cwd=ROOT,
                                       stdout=output, stderr=output,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(40):
                try:
                    if httpx.get(origin + "/login", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            fixture = {"origin": origin, "moment_id": identifier, "expected_caption": detail["caption"]}
            (evidence / "browser-fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
            with (evidence / "browser-console.txt").open("w", encoding="utf-8") as console:
                browser = subprocess.Popen(
                    ["node", "scripts/acceptance_p04_privacy_ui.cjs"], cwd=ROOT,
                    env={**os.environ, "LIFE_P04_EVIDENCE": str(evidence)},
                    stdout=console, stderr=console,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    browser.wait(timeout=150)
                    assert browser.returncode == 0, "PRIVACY_BROWSER_FAILED"
                finally:
                    if browser.poll() is None:
                        browser.terminate()
                        browser.wait(timeout=15)
            result["checks"]["desktop_mobile_unknown_has_no_retry_and_revoked_refresh"] = "PASS"
        client.patch("/api/v1/me/settings", headers=auth, json={"image_consent": False}).raise_for_status()
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM moments WHERE moment_id=?", (identifier,)).fetchone()
            assert row["status"] == "cancelled" and not row["caption"] and row["selection"] == "[]"
            assert row["image"] is None and row["mime"] is None
            calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert calls == 0
        result["model_call_rows"] = calls
        result["checks"]["revocation_synchronously_scrubs_text_selection_image"] = "PASS"
        stop(server, worker, client)
        app, server, worker, client = start(settings)
        detail = client.get(f"/api/v1/moments/{identifier}", headers=auth).json()["moment"]
        assert detail["status"] == "cancelled" and detail["caption"] == "" and detail["image_data"] is None
        result["checks"]["scrubbed_state_survives_another_core_restart"] = "PASS"
        result["status"] = "PASS"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        raise
    finally:
        cleanup_errors = []
        if owner:
            try:
                app.state.moments.revoke_owner(owner)
                if memory_id:
                    response = client.delete(f"/api/v1/knowledge/{memory_id}", headers=auth)
                    response.raise_for_status()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if gateway is not None and gateway.poll() is None:
            gateway.terminate()
            gateway.wait(timeout=15)
        stop(server, worker, client)
        output.close()
        result.update(cleanup_errors=cleanup_errors, ended_at=utc_now())
        if cleanup_errors:
            result["status"] = "FAIL"
        (evidence / "privacy-live.json").write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if cleanup_errors and not result.get("error_type"):
            raise RuntimeError("ISOLATED_PRIVACY_CLEANUP_FAILED")


if __name__ == "__main__":
    main()
