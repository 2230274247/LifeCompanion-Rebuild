"""Real read-only providers through authenticated Core HTTP; no model calls."""
from __future__ import annotations

import json
import uuid
import argparse
from dataclasses import replace

from acceptance_p03_live import ROOT,load_settings,start,stop,token,utc_now
from verify_rebuild_workspace import verify


def main(recover_weather=False):
    verify(ROOT)
    runtime = ROOT / "infra/runtime/p05"
    runtime.mkdir(parents=True,exist_ok=True)
    run_id = uuid.uuid4().hex[:16]
    settings = replace(load_settings(),database_path=runtime / "tools-acceptance.sqlite3",
        memory_llm_key="",memory_llm_request_budget=0,moment_scoring_request_budget=0,
        memos_api_token="",neo4j_uri="",vikunja_users={},reminder_scheduler_external=True,
        tool_request_budget=4 if recover_weather else 3,
        tool_weather_provider="open_meteo",tool_route_provider="osrm_demo",
        tool_search_url="")
    result = {"status":"FAIL","started_at":utc_now(),"database":str(settings.database_path.relative_to(ROOT)),
        "scope":"authenticated real Core/provider/SQLite/restart acceptance; not chat/UI/voice/followup E2E",
        "model_calls":0,"image_calls":0,"network_request_budget":settings.tool_request_budget,
        "explicit_weather_recovery":recover_weather,"checks":{}}
    app,server,worker,client = start(settings)
    auth = token(settings,"p05-public-landmark-tester")
    other = token(settings,"p05-other-tester")
    try:
        for user in ("p05-public-landmark-tester","p05-other-tester"):
            client.post("/internal/v1/users/bootstrap",headers={"X-Internal-Token":settings.internal_token},
                json={"librechat_user_id":user,"memos_user_id":"","memory_consent":False}).raise_for_status()
        assert client.get("/api/v1/tools").status_code == 401
        assert len(client.get("/api/v1/tools",headers=auth).json()["tools"]) == 4
        result["checks"]["authenticated_catalog_and_schema"] = "PASS"
        with app.state.store.connect() as db:
            before = db.execute("SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0]
        weather = {"name":"weather","idempotency_key":"p05-real-weather-shanghai-v1","parameters":{
            "latitude":31.2304,"longitude":121.4737,"place_label":"Shanghai public landmark test"}}
        if recover_weather:
            weather["idempotency_key"] = "p05-real-weather-shanghai-recovery-v1"
            weather["parameters"]["timezone"] = "Asia/Shanghai"
        route = {"name":"route","idempotency_key":"p05-real-route-shanghai-v1","parameters":{
            "origin":{"latitude":31.2304,"longitude":121.4737},
            "destination":{"latitude":31.208,"longitude":121.444}}}
        places = {"name":"place_search","idempotency_key":"p05-real-place-shanghai-v1",
                  "parameters":{"query":"Shanghai"}}
        result["provider_receipts"] = []
        for body in (weather,route,places):
            response = client.post("/api/v1/tools/execute",headers=auth,json=body,timeout=20)
            response.raise_for_status()
            item = response.json()
            result["provider_receipts"].append(item)
            if item["status"] == "succeeded":
                assert item["result"]["sources"][0]["url"].startswith("https://")
            result["checks"]["provider_"+body["name"]] = "PASS" if item["status"] == "succeeded" else "BLOCKED"
        identifier = result["provider_receipts"][0]["execution_id"]
        assert client.get(f"/api/v1/tool-executions/{identifier}",headers=other).status_code == 404
        assert client.delete(f"/api/v1/tool-executions/{identifier}",headers=other).status_code == 404
        result["checks"]["foreign_read_delete_denied"] = "PASS"
        missing = client.post("/api/v1/tools/execute",headers=auth,json={
            "name":"route","idempotency_key":"p05-origin-missing-v1","parameters":{
                "destination":{"latitude":31.208,"longitude":121.444}}}).json()
        assert missing["status"] == "needs_input" and missing["result"]["missing_field"] == "origin"
        assert missing["network_requests"] == 0
        search = client.post("/api/v1/tools/execute",headers=auth,json={
            "name":"search","idempotency_key":"p05-search-unavailable-v1",
            "parameters":{"query":"public search test"}}).json()
        assert search["status"] == "blocked" and search["error_code"] == "TOOL_PROVIDER_UNAVAILABLE"
        assert search["network_requests"] == 0 and not search["result"]
        result["checks"]["missing_origin_and_unconfigured_search_fail_closed"] = "PASS"
        stop(server,worker,client)
        app,server,worker,client = start(settings)
        replay = client.post("/api/v1/tools/execute",headers=auth,json=weather).json()
        assert replay == result["provider_receipts"][0]
        blocked = client.post("/api/v1/tools/execute",headers=auth,
            json={**weather,"idempotency_key":"p05-budget-must-not-reset-"+run_id}).json()
        assert blocked["status"] == "blocked" and blocked["error_code"] == "TOOL_REQUEST_BUDGET"
        with app.state.store.connect() as db:
            after = db.execute("SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0]
            assert after == settings.tool_request_budget
            assert db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0
        result["checks"]["persisted_replay_restart_and_cap_no_new_requests"] = "PASS"
        providers_ok = all(item["status"] == "succeeded" for item in result["provider_receipts"])
        result.update(status="PASS" if providers_ok else "PARTIAL",
                      requests_before=before,requests_after=after,added_network_requests=after-before)
    finally:
        stop(server,worker,client)
        result["ended_at"] = utc_now()
        path = ROOT / f"evidence/p05/tools-live-{run_id}.json"
        path.write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps({"status":result["status"],"report":str(path.relative_to(ROOT))}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recover-weather",action="store_true")
    main(parser.parse_args().recover_weather)
