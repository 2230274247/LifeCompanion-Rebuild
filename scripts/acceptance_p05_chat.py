"""Real persisted LibreChat source -> built business bridge -> Core -> UI/provider.

No chat model generation. Uses the existing cumulative P05 provider ledger.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import socket
import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path

import httpx

from acceptance_environment import ENVFILE
from acceptance_p03_live import ROOT, load_settings, start, stop, utc_now
from verify_rebuild_workspace import verify


def seed(account, run_id):
    baseline = json.loads((ROOT / "infra/runtime/p00/baseline-state.json").read_text(encoding="utf-8"))
    source = {"text": "Shanghai天气怎么样？", "conversation_id": str(uuid.uuid4()),
              "message_id": f"p05-weather-{run_id}"}
    inspected = json.loads(subprocess.check_output(
        ["docker", "inspect", "lcr-acceptance-20261103-mongo-1"], text=True, encoding="utf-8"))[0]
    assert inspected["Config"]["Labels"]["com.docker.compose.project"] == "lcr-acceptance-20261103"
    script = """
const template=db.conversations.findOne({conversationId:TEMPLATE});
if (!template || String(template.user)!==OWNER) throw new Error('SYNTHETIC_OWNER_MISMATCH');
const source=SOURCE, now=new Date(), messages=[];
for (const assistant of [false,true]) {
  const id=db.messages.insertOne({
    messageId:source.message_id+(assistant?'-assistant':''), user:template.user,
    conversationId:source.conversation_id, __v:0, _meiliIndex:false, createdAt:now,
    updatedAt:now, expiredAt:null, endpoint:'DeepSeek', model:'deepseek-flash',
    error:false, isCreatedByUser:!assistant, isTemporary:false,
    parentMessageId:assistant?source.message_id:'00000000-0000-0000-0000-000000000000',
    sender:assistant?'Synthetic acceptance':'User', text:assistant?'':source.text,
    ...(assistant?{content:[{type:'text',text:'Synthetic acceptance source; no model generation.'}]}:{}),
    tokenCount:0,unfinished:false
  });
  messages.push(id.insertedId);
}
delete template._id;
Object.assign(template,{conversationId:source.conversation_id,messages,
  title:'P05 isolated weather acceptance',createdAt:now,updatedAt:now});
db.conversations.insertOne(template);
print(JSON.stringify({inserted:2}));
""".replace("TEMPLATE", json.dumps(baseline["d"]["conversation_id"])).replace(
        "OWNER", json.dumps(account["librechat_user_id"])).replace("SOURCE", json.dumps(source))
    completed = subprocess.run(["docker", "exec", "lcr-acceptance-20261103-mongo-1", "mongosh",
                               "LibreChatAcceptance", "--quiet", "--eval", script], capture_output=True)
    assert completed.returncode == 0, "SOURCE_INSERT_FAILED"
    return source


def main(resume_source=None):
    identity = verify(ROOT)
    run_id = uuid.uuid4().hex[:16]
    evidence = ROOT / f"evidence/p05/chat-{run_id}"
    evidence.mkdir()
    runtime = ROOT / "infra/runtime/p05"
    settings = replace(load_settings(), database_path=runtime / "tools-acceptance.sqlite3",
                       memory_llm_request_budget=0, moment_scoring_request_budget=0,
                       memos_api_token="", neo4j_uri="", vikunja_users={},
                       reminder_scheduler_external=True, tool_request_budget=6,
                       tool_weather_provider="open_meteo", tool_route_provider="osrm_demo",
                       tool_search_url="")
    config_hash = hashlib.sha256(ENVFILE.read_bytes()).hexdigest()
    result = {"status": "FAIL", "started_at": utc_now(), "identity": identity,
              "scope": "real synthetic Mongo source + compiled bridge + Core/provider/browser; no model-generated chat turn",
              "model_calls": 0, "image_calls": 0, "cumulative_network_cap": 6, "checks": {}}
    account = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))["a"]
    app, server, worker, client = start(settings)
    gateway = None
    output = (runtime / f"chat-gateway-{run_id}.log").open("ab")
    try:
        built = (ROOT / "products/librechat-custom/client/dist/index.html").read_text(encoding="utf-8")
        served = None
        for _ in range(30):
            try:
                candidate = httpx.get("http://127.0.0.1:3091/login", timeout=2, trust_env=False)
                if candidate.status_code == 200:
                    served = candidate
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.5)
        assert served is not None, "ISOLATED_LIBRECHAT_STARTUP_FAILED"
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', built)
        assert scripts and all(source in served.text for source in scripts), "FRONTEND_RELOAD_REQUIRED"
        with app.state.store.connect() as db:
            before = db.execute("SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0]
        assert before <= 6
        result["requests_before"] = before
        login = httpx.post("http://127.0.0.1:3091/api/auth/login",
                          json={"email": account["email"], "password": account["password"]},
                          timeout=20, trust_env=False)
        login.raise_for_status()
        auth = {"Authorization": "Bearer "+login.json()["token"]}
        if resume_source:
            previous = Path(resume_source).resolve()
            assert previous.is_relative_to((ROOT / "evidence/p05").resolve())
            previous_fixture = json.loads((previous / "browser-fixture.json").read_text(encoding="utf-8"))
            source = {key: previous_fixture[key] for key in ("text", "conversation_id", "message_id")}
            result["resumed_source"] = str(previous.relative_to(ROOT))
        else:
            source = seed(account, run_id)
        response = httpx.get("http://127.0.0.1:3091/api/messages",
                            params={"conversationId": source["conversation_id"]},
                            headers=auth, timeout=20, trust_env=False)
        response.raise_for_status()
        messages = response.json()
        if isinstance(messages, dict):
            messages = messages["messages"]
        persisted = next(item for item in messages if item["messageId"] == source["message_id"])
        assert persisted["isCreatedByUser"] and persisted["text"] == source["text"]
        result["checks"]["real_authenticated_persisted_source"] = "PASS"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        core = str(client.base_url).rstrip("/")
        code = ("import {createGateway} from './apps/product-portal/server.mjs'; "
                f"createGateway({{chatTarget:'http://127.0.0.1:3091',lifeTarget:'{core}'}})"
                f".listen({port},'127.0.0.1');")
        gateway = subprocess.Popen(["node", "--input-type=module", "-e", code], cwd=ROOT,
                                   stdout=output, stderr=output,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(40):
            try:
                if httpx.get(origin+"/login", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        fixture = {"origin": origin, **source}

        def browser(mode):
            (evidence / "browser-fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
            with (evidence / f"browser-{mode}-console.txt").open("w", encoding="utf-8") as console:
                child = subprocess.Popen(["node", "scripts/acceptance_p05_chat_ui.cjs"], cwd=ROOT,
                    env={**os.environ, "LIFE_P05_EVIDENCE": str(evidence), "LIFE_P05_UI_MODE": mode},
                    stdout=console, stderr=console, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    child.wait(timeout=180)
                    assert child.returncode == 0, "WEATHER_BROWSER_FAILED"
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=15)

        if not resume_source:
            browser("before")
        # Execute the actual compiled bridge with the HTTP-verified persisted object.
        bridge = """
const {withLifeReminder}=require('/app/packages/api/dist/index.cjs');
let input='';process.stdin.on('data',c=>input+=c);
process.stdin.on('end',async()=>{
  const x=JSON.parse(input);
  const p=await withLifeReminder([{role:'user',content:x.message.text}],x.connection,x.message,
    Promise.resolve({message:x.persisted}));
  const content=p[p.length-1].content;
  const result=JSON.parse(content.slice(content.lastIndexOf('\\n')+1));
  console.log('BRIDGE_RESULT:'+JSON.stringify(result));process.exit(0);
});
"""
        bridge_endpoint = core.replace("127.0.0.1", "host.docker.internal")
        payload = {"connection": {"endpoint": bridge_endpoint, "token": settings.internal_token,
                                  "userId": account["librechat_user_id"]},
                   "message": {"text": source["text"], "messageId": source["message_id"],
                               "conversationId": source["conversation_id"]}, "persisted": persisted}
        completed = subprocess.run(["docker", "exec", "-i", "lcr-acceptance-20261103-librechat-1",
                                   "node", "-e", bridge], input=json.dumps(payload), cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", timeout=50)
        assert completed.returncode == 0, "COMPILED_BRIDGE_FAILED"
        marker = next(line for line in completed.stdout.splitlines() if line.startswith("BRIDGE_RESULT:"))
        item = json.loads(marker.removeprefix("BRIDGE_RESULT:"))
        result["bridge_receipt"] = item
        assert item["status"] in ("choose_place", "succeeded"), "PLACE_LOOKUP_NOT_CONFIRMED"
        fixture["already_succeeded"] = item["status"] == "succeeded"
        fixture["interaction_id"] = item["interaction_id"]
        fixture["place_index"] = next(index for index, place in enumerate(item["places"])
                                     if place["country"] in ("China", "中国"))
        fixture["place"] = item["places"][fixture["place_index"]]
        browser("after")
        result["checks"]["compiled_bridge_weather_choice_desktop_mobile_clear"] = "PASS"
        with app.state.store.connect() as db:
            after = db.execute("SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0]
            assert after <= 6 and after-before <= 2
            assert db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM recollection_model_calls").fetchone()[0] == 0
        assert hashlib.sha256(ENVFILE.read_bytes()).hexdigest() == config_hash
        result.update(status="PASS", requests_after=after, added_network_requests=after-before,
                      provider_configuration_unchanged=True)
    finally:
        with app.state.store.connect() as db:
            result["final_network_requests"] = db.execute(
                "SELECT COALESCE(sum(network_requests),0) FROM tool_executions").fetchone()[0]
        if gateway is not None and gateway.poll() is None:
            gateway.terminate()
            gateway.wait(timeout=15)
        output.close()
        stop(server, worker, client)
        result["ended_at"] = utc_now()
        (evidence / "chat-live.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"status": result["status"], "evidence": str(evidence.relative_to(ROOT))}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-source", type=Path)
    main(parser.parse_args().resume_source)
