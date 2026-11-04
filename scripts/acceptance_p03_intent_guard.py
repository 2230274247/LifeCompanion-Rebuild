"""Real internal chat bridge; negative inputs create no draft or Vikunja task."""
import json
import uuid
from dataclasses import replace

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, utc_now
from verify_rebuild_workspace import verify


CASES = [
    "明天9点不用提醒我喝水",
    "明天9点不再提醒我喝水",
    "明天9点不想再收到喝水提醒",
    "不要设置明天9点的闹钟",
    "别再提醒我明天9点开会",
    "朋友说：“明天9点提醒我开会。”",
    "她明天9点提醒我开会",
    "明天她9点提醒我开会",
    "昨天9点提醒我喝水",
    "如果明天9点下雨就提醒我",
    "明天9点提醒小王喝水",
]


def main():
    verify(ROOT)
    database = ROOT / "infra/runtime/p02/business-workflow-d01ceaa96f09438b.sqlite3"
    assert database.is_file() and database.resolve().is_relative_to((ROOT / "infra/runtime/p02").resolve())
    settings = replace(
        load_settings(), database_path=database, memory_llm_key="", memos_api_token="",
        neo4j_uri="", vikunja_users={}, reminder_scheduler_external=True)
    account = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))["a"]
    login = httpx.post("http://127.0.0.1:3091/api/auth/login",
                       json={"email": account["email"], "password": account["password"]}, timeout=20)
    login.raise_for_status()
    auth = {"Authorization": "Bearer " + login.json()["token"]}
    internal = {"X-Internal-Token": settings.internal_token}
    run_id = uuid.uuid4().hex[:16]
    result = {"status": "FAIL", "run_id": run_id, "started_at": utc_now(), "cases": [],
              "scope": "authenticated real internal HTTP chat bridge, synthetic input IDs, real Vikunja",
              "provider_calls": 0, "not_a_human_labelled_200_case_benchmark": True}
    app, server, worker, client = start(settings)
    created = []
    try:
        response = client.get("/api/v1/me", headers=auth)
        response.raise_for_status()
        owner = response.json()["life_user_id"]
        client.patch("/api/v1/me/settings", headers=auth,
                     json={"notification_consent": True}).raise_for_status()
        config = app.state.provisioning.config(owner)
        assert config, "EXPECTED_PREVIOUSLY_VERIFIED_SYNTHETIC_ACCOUNT"
        def tasks():
            return app.state.reminders._request(
                config, "GET", f"/projects/{config['project_id']}/tasks",
                params={"per_page": 100}).json()["items"]
        def counts():
            with app.state.store.connect() as db:
                return {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                        for table in ("reminders", "reminder_drafts", "reminder_submissions")}
        baseline = counts()
        assert tasks() == []
        for index, text in enumerate(CASES):
            response = client.post("/internal/v1/reminders/execute", headers=internal, json={
                "source_user_id": account["librechat_user_id"],
                "source_message_id": f"guard-{run_id}-{index}", "text": text,
                "conversation_id": f"guard-{run_id}"})
            response.raise_for_status()
            value = response.json()
            assert value["status"] in ("no_action", "clarify") and not value.get("draft_id")
            result["cases"].append({"text": text, "intent": value["intent"],
                                    "status": value["status"]})
        assert counts() == baseline and tasks() == []
        result["negative_input_created_drafts"] = 0
        result["negative_input_created_tasks"] = 0
        for index, text in enumerate(("明天9点提醒我带绿色U盘，不是银色的",
                                      "不用提前，明天9点提醒我喝水")):
            response = client.post("/internal/v1/reminders/execute", headers=internal, json={
                "source_user_id": account["librechat_user_id"],
                "source_message_id": f"positive-{run_id}-{index}", "text": text,
                "conversation_id": f"guard-{run_id}"}, timeout=45)
            response.raise_for_status()
            value = response.json()
            assert value["status"] == "scheduled", value
            created.append(value["draft_id"])
            draft = app.state.reminder_drafts.get(owner, value["draft_id"])
            assert draft["preview"]["scheduled_at"].endswith("09:00:00+08:00")
            if index == 0:
                assert "不是银色" in draft["reminder"]["title"]
        assert len(tasks()) == 2
        with app.state.store.connect() as db:
            model_calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert model_calls == 0
        result.update(status="PASS", positive_control_tasks=2, model_call_rows=model_calls)
    except Exception as exc:
        result.update(error_type=type(exc).__name__)
        raise
    finally:
        for identifier in created:
            app.state.reminder_drafts.cancel(owner, identifier)
        stop(server, worker, client)
        result["ended_at"] = utc_now()
        (ROOT / f"evidence/p03/intent-guard-live-{run_id}.json").write_text(
            json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
