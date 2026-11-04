"""One real DeepSeek batch, persisted quota, real source APIs/Memos/clock/restart."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, token, utc_now
from acceptance_environment import ENVFILE
from verify_rebuild_workspace import verify
from app.recollection_scoring import ScoringBlocked


def seed_sources(account, run_id):
    baseline = json.loads((ROOT / "infra/runtime/p00/baseline-state.json").read_text(encoding="utf-8"))
    sources = [
        {"text":"今天在家吃了早餐，是一碗燕麦粥，没有其他特别的事。"},
        {"text":"今天去图书馆读书，完成了平常的一页练习。"},
        {"text":"今天终于完成了坚持一年的手写回忆录，这是我第一次独立完成一本书，我特别开心。"},
    ]
    conversation = str(uuid.uuid4())
    for index, source in enumerate(sources):
        source.update(message_id=f"p04-scoring-{run_id}-{index}",conversation_id=conversation,
                      written_at=utc_now())
    script = """
const template = db.conversations.findOne({conversationId:TEMPLATE});
if (!template || String(template.user) !== OWNER) throw new Error('SYNTHETIC_OWNER_MISMATCH');
const sources = SOURCES;
const messages = [];
for (const source of sources) {
  const now = new Date(source.written_at);
  const inserted = db.messages.insertOne({
    messageId:source.message_id, user:template.user, conversationId:source.conversation_id,
    __v:0, _meiliIndex:false, createdAt:now, updatedAt:now, expiredAt:null,
    endpoint:'DeepSeek', model:'deepseek-flash', error:false, isCreatedByUser:true,
    isTemporary:false, parentMessageId:'00000000-0000-0000-0000-000000000000',
    sender:'User', text:source.text, tokenCount:0, unfinished:false
  });
  messages.push(inserted.insertedId);
}
delete template._id;
Object.assign(template, {conversationId:sources[0].conversation_id, messages,
  title:'P04 isolated synthetic source evidence', createdAt:new Date(), updatedAt:new Date()});
db.conversations.insertOne(template);
print(JSON.stringify({inserted:sources.length}));
""".replace("TEMPLATE",json.dumps(baseline["d"]["conversation_id"])).replace(
        "OWNER",json.dumps(account["librechat_user_id"])).replace("SOURCES",json.dumps(sources))
    process = subprocess.run(["docker","exec","lcr-acceptance-20261103-mongo-1","mongosh",
        "LibreChatAcceptance","--quiet","--eval",script],capture_output=True,text=True)
    assert process.returncode == 0, "SYNTHETIC_SOURCE_INSERT_FAILED"
    return sources


def main(browser=False):
    identity = verify(ROOT)
    run_id = uuid.uuid4().hex[:16]
    evidence = ROOT / f"evidence/p04/scoring-{run_id}"
    evidence.mkdir(parents=True)
    runtime = ROOT / "infra/runtime/p04/scoring-acceptance"
    runtime.mkdir(parents=True,exist_ok=True)
    config_hash = hashlib.sha256(ENVFILE.read_bytes()).hexdigest()
    persistent_database = runtime / "life.sqlite3"
    database_path = persistent_database
    if browser:
        assert persistent_database.exists(), "PERSISTENT_ACCEPTANCE_DATABASE_REQUIRED_FOR_BROWSER"
        database_path = runtime / f"life-browser-{run_id}.sqlite3"
        with sqlite3.connect(persistent_database) as source, sqlite3.connect(database_path) as target:
            source.backup(target)
    settings = replace(load_settings(),database_path=database_path,
        memory_llm_request_budget=0, moment_scoring_request_budget=0 if browser else 2,
        moment_scoring_max_candidates=3,moment_scoring_max_tokens=1800,
        neo4j_uri="",vikunja_users={},reminder_scheduler_external=True)
    assert settings.memory_llm_provider == "deepseek" and settings.memory_llm_key
    inspected = json.loads(subprocess.check_output(
        ["docker","inspect","lcr-acceptance-20261103-mongo-1"],text=True,encoding="utf-8"))[0]
    labels = inspected["Config"]["Labels"]
    assert labels["com.docker.compose.project"] == "lcr-acceptance-20261103"
    assert ROOT.resolve() in __import__("pathlib").Path(labels["com.docker.compose.project.working_dir"]).resolve().parents
    if browser:
        built = (ROOT / "products/librechat-custom/client/dist/index.html").read_text(encoding="utf-8")
        served = httpx.get("http://127.0.0.1:3091/login",timeout=15,trust_env=False)
        served.raise_for_status()
        scripts = re.findall(r'<script[^>]+src="([^"]+)"',built)
        assert scripts and all(source in served.text for source in scripts), "FRONTEND_RELOAD_REQUIRED"
    accounts = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))
    account = accounts["a"]
    login = httpx.post("http://127.0.0.1:3091/api/auth/login",json={
        "email":account["email"],"password":account["password"]},timeout=20,trust_env=False)
    login.raise_for_status()
    auth = {"Authorization":"Bearer "+login.json()["token"]}
    internal = {"X-Internal-Token":settings.internal_token}
    result = {"status":"FAIL","run_id":run_id,"started_at":utc_now(),"identity":identity,
        "database":str(settings.database_path.relative_to(ROOT)),
        "persistent_quota_source":str(persistent_database.relative_to(ROOT)),
        "scope":"persisted synthetic Mongo messages verified by LibreChat HTTP; actual DeepSeek scoring/Memos/clock/Core/UI, not actual chat generation or image generation",
        "request_budget":2,"image_calls":0,"image_status":"BLOCKED_IMAGE_PROVIDER",
        "exact_money_cost":"UNKNOWN","checks":{}}
    app, server, worker, client = start(settings)
    gateway = None
    output = (runtime / f"gateway-{run_id}.log").open("ab")
    try:
        with app.state.store.connect() as db:
            prior_calls = db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0]
            existing = db.execute("""SELECT moment_id,user_id FROM moments
                WHERE status IN ('queued','pending_provider','generated') LIMIT 1""").fetchone()
        result["calls_before"] = prior_calls
        if prior_calls:
            assert existing, "PREVIOUS_ATTEMPT_NOT_REPLAYABLE_NO_NEW_CLOUD_REQUEST"
            owner, identifier = existing["user_id"], existing["moment_id"]
            result["checks"]["reused_persisted_success_without_new_scoring"] = "PASS"
        else:
            assert not browser, "BROWSER_REPLAY_REQUIRES_PERSISTED_SCORING_NO_NEW_REQUEST"
            boot = client.post("/internal/v1/users/bootstrap",headers=internal,json={
                "librechat_user_id":account["librechat_user_id"],"memos_user_id":account["memos_user_id"],
                "display_name":"P04 isolated scoring acceptance","memory_consent":True,"image_consent":False})
            boot.raise_for_status()
            owner = boot.json()["life_user_id"]
            client.patch("/api/v1/me/settings",headers=auth,json={"image_consent":True}).raise_for_status()
            local = datetime.now(ZoneInfo("Asia/Hong_Kong"))
            close = local.replace(second=0,microsecond=0)+timedelta(minutes=2)
            ends = sorted((close+timedelta(minutes=2*i)).strftime("%H:%M") for i in range(3))
            assert close.date() == (close+timedelta(minutes=4)).date(), "MIDNIGHT_NEEDS_DIFFERENT_WINDOW"
            client.put("/api/v1/moment-settings",headers=auth,json={
                "enabled":True,"timezone":"Asia/Hong_Kong","ends":ends}).raise_for_status()
            sources = seed_sources(account,run_id)
            for source in sources:
                response = httpx.get("http://127.0.0.1:3091/api/messages",headers=auth,
                    params={"conversationId":source["conversation_id"],"messageId":source["message_id"]},
                    timeout=15,trust_env=False)
                response.raise_for_status()
                persisted = response.json()["messages"]
                assert len(persisted) == 1 and persisted[0]["text"] == source["text"]
                assert persisted[0]["isCreatedByUser"] is True
                response = client.post("/internal/v1/events/ingest",headers=internal,json={
                    "source_user_id":account["librechat_user_id"],"source_message_id":source["message_id"],
                    "conversation_id":source["conversation_id"],"text":source["text"],
                    "occurred_at":source["written_at"]},timeout=45)
                response.raise_for_status()
                event = response.json()["event"]
                assert event["status"] == "published" and event["memo_ref"]
                memo = app.state.memos.__class__(settings.memos_base_url,
                    settings.memos_user_tokens[account["memos_user_id"]]).get_private_memo(
                        event["memo_ref"],account["memos_user_id"])
                assert source["message_id"] in memo["content"]
            result["source_fixture"] = sources
            result["checks"]["three_owned_persisted_messages_and_real_memos_verified"] = "PASS"
            print(json.dumps({"phase":"waiting_real_clock","ends":ends,"closes_at":close.isoformat(),
                              "cloud_call_upper_bound":2}),flush=True)
            deadline = time.monotonic()+190
            rows = []
            while time.monotonic() < deadline:
                rows = client.get("/api/v1/moments",headers=auth).json()["moments"]
                if rows and rows[0]["status"] not in ("awaiting_score","scoring","queued"):
                    break
                time.sleep(.5)
            assert len(rows) == 1 and rows[0]["status"] == "pending_provider", "REAL_SCORING_DID_NOT_SELECT_EVENT"
            identifier = rows[0]["moment_id"]
            result["window"] = {"configured_ends":ends,"window_end":rows[0]["window_end"],"observed_at":utc_now()}
            result["checks"]["background_actual_clock_structured_selection_text_only"] = "PASS"
        detail = client.get(f"/api/v1/moments/{identifier}",headers=auth).json()["moment"]
        with app.state.store.connect() as db:
            candidates = [dict(r) for r in db.execute(
                "SELECT * FROM recollection_candidates WHERE window_id=? ORDER BY score DESC",(identifier,))]
            calls = [dict(r) for r in db.execute("SELECT * FROM recollection_model_calls ORDER BY started_at")]
        assert len(candidates) == 3 and sum(row["selected"] for row in candidates) == 1
        assert len(detail["selection"]) == 3 and len(detail["source_memory_ids"]) == 1
        assert detail["image_data"] is None and detail["error_code"] == "IMAGE_PROVIDER_UNAVAILABLE"
        assert detail["caption"] and all(len(json.loads(row["dimensions"])) == 8 for row in candidates)
        result["selected_caption"] = detail["caption"]
        result["candidates"], result["calls"] = candidates, calls
        result["checks"]["three_persisted_eight_dimension_scores_one_selected_source_quote"] = "PASS"
        unknown_user = "p04-scoring-other-" + run_id
        client.post("/internal/v1/users/bootstrap",headers=internal,json={
            "librechat_user_id":unknown_user,"memos_user_id":"","memory_consent":False}).raise_for_status()
        assert client.get(f"/api/v1/moments/{identifier}",headers=token(settings,unknown_user)).status_code == 404
        result["checks"]["foreign_account_detail_denied"] = "PASS"
        stop(server,worker,client)
        app,server,worker,client = start(settings)
        restored = client.get(f"/api/v1/moments/{identifier}",headers=auth).json()["moment"]
        assert restored["caption"] == detail["caption"] and restored["selection"] == detail["selection"]
        assert not app.state.moments.score_one()
        for candidate_window, cap, expected in (
                (identifier,2,"SCORING_ALREADY_ATTEMPTED"),
                ("budget-rejection-"+run_id,len(calls),"SCORING_REQUEST_BUDGET")):
            app.state.moments.scorer.settings = replace(settings,moment_scoring_request_budget=cap)
            try:
                app.state.moments.scorer.evaluate(owner,candidate_window,{},[],{})
            except ScoringBlocked as exc:
                assert str(exc) == expected, "WRONG_SCORING_REJECTION_REASON"
            else:
                raise AssertionError("PERSISTENT_BUDGET_OR_WINDOW_REPLAY_NOT_BLOCKED")
        result["checks"]["core_restart_window_replay_and_persistent_cap_no_new_requests"] = "PASS"
        if browser:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port = sock.getsockname()[1]
            origin = f"http://127.0.0.1:{port}"
            code = ("import {createGateway} from './apps/product-portal/server.mjs'; "
                f"createGateway({{chatTarget:'http://127.0.0.1:3091',lifeTarget:'{str(client.base_url).rstrip('/')}'}})"
                f".listen({port},'127.0.0.1');")
            gateway = subprocess.Popen(["node","--input-type=module","-e",code],cwd=ROOT,
                stdout=output,stderr=output,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            for _ in range(40):
                try:
                    if httpx.get(origin+"/login",timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            (evidence / "browser-fixture.json").write_text(json.dumps({
                "origin":origin,"moment_id":identifier,"expected_caption":detail["caption"]}),encoding="utf-8")
            with (evidence / "browser-console.txt").open("w",encoding="utf-8") as console:
                child = subprocess.Popen(["node","scripts/acceptance_p04_scoring_ui.cjs"],cwd=ROOT,
                    env={**os.environ,"LIFE_P04_EVIDENCE":str(evidence)},stdout=console,stderr=console,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                try:
                    child.wait(timeout=140)
                    assert child.returncode == 0, "SCORING_BROWSER_FAILED"
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=15)
            result["checks"]["desktop_mobile_readable_scores_and_revocation"] = "PASS"
            # Fault-inject a skipped window carrying an old rejected candidate.
            # This is not a real clock/legacy production-data claim.
            skipped_id = "skip-withdraw-" + run_id
            stamp = utc_now()
            with app.state.store.connect() as db:
                db.execute("""INSERT INTO moments
                    (moment_id,user_id,window_start,window_end,timezone,slot,status,
                     source_memory_ids,selection,caption,created_at,updated_at)
                    VALUES (?,?,?,?,'Asia/Hong_Kong',0,'skipped','[]','[]','',?,?)""",
                    (skipped_id,owner,stamp,stamp,stamp,stamp))
                app.state.moments.save_candidate(db,skipped_id,owner,{
                    "memory_id":candidates[0]["memory_id"],
                    "source_revision":candidates[0]["source_revision"],
                    "input_hash":candidates[0]["input_hash"],
                    "source_message_ids":json.loads(candidates[0]["source_message_ids"]),
                    "reason_code":"SOURCE_QUOTE_MISSING","selected":False})
            excluded = client.post(
                f"/api/v1/knowledge/{candidates[0]['memory_id']}/exclude-moments",headers=auth)
            excluded.raise_for_status()
            rows = client.get("/api/v1/moments",headers=auth).json()["moments"]
            assert not any(row["moment_id"] == skipped_id for row in rows)
            with app.state.store.connect() as db:
                assert db.execute("SELECT status FROM moments WHERE moment_id=?",
                                  (skipped_id,)).fetchone()[0] == "skipped"
                assert db.execute("SELECT count(*) FROM recollection_candidates WHERE window_id=?",
                                  (skipped_id,)).fetchone()[0] == 0
            result["checks"]["fault_injected_skipped_window_exclusion_http_no_empty_card"] = "PASS"
        with app.state.store.connect() as db:
            after = db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0]
            memory_calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert after == len(calls) <= 2 and memory_calls == 0
        assert hashlib.sha256(ENVFILE.read_bytes()).hexdigest() == config_hash
        result.update(status="PASS",calls_after=after,added_scoring_calls=after-prior_calls,
                      extraction_model_calls=memory_calls,provider_configuration_unchanged=True)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        # Only our bounded assertion codes are safe to publish.
        result["error_code"] = str(exc) if isinstance(exc,AssertionError) else "ACCEPTANCE_OPERATION_FAILED"
        raise
    finally:
        with app.state.store.connect() as db:
            result["final_call_ledger"] = [dict(r) for r in db.execute("SELECT * FROM recollection_model_calls")]
        if gateway is not None and gateway.poll() is None:
            gateway.terminate()
            gateway.wait(timeout=15)
        stop(server,worker,client)
        output.close()
        result["ended_at"] = utc_now()
        (evidence / "scoring-live.json").write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding="utf-8")
        print(json.dumps({"status":result["status"],"report":str((evidence/"scoring-live.json").relative_to(ROOT)),
                          "scoring_call_rows":len(result["final_call_ledger"])}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser",action="store_true")
    main(parser.parse_args().browser)
