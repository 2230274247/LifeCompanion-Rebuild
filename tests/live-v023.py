"""Synthetic official-API tests, isolated application and real upstream providers."""
import json
import base64
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v023"
EVIDENCE = ROOT / "evidence/v023"
sys.path.insert(0, str(ROOT / "services/life-core"))
for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v


def setup():
    path = RUNTIME / "accounts.json"
    accounts = json.loads(path.read_text()) if path.exists() else {}
    for label in dict.fromkeys(("a", "b", "d", *(sys.argv[2:3]))):
        if label in accounts:
            continue
        suffix = secrets.token_hex(4)
        account = dict(email=f"v023-{label}-{suffix}@example.invalid", name=f"V023 Synthetic {label}",
                       username=f"v023-{label}-{suffix}", password=secrets.token_urlsafe(24) + "aA1!")
        result = httpx.post("http://127.0.0.1:3023/api/auth/register",
                            json={**account, "confirm_password": account["password"]}, timeout=20)
        if result.status_code != 200:
            raise RuntimeError(f"SYNTHETIC_REGISTER_HTTP_{result.status_code}")
        accounts[label] = account
        path.write_text(json.dumps(accounts), encoding="utf8")
    print("Synthetic accounts prepared in the isolated app; credentials retained only in ignored runtime.")


def login(label="a"):
    from app.provisioning import protect, unprotect
    session = RUNTIME / f"session-{label}.dpapi"
    if session.exists():
        saved = unprotect(session.read_text())
        if min(saved["expires"], token_expiry(saved["token"])-30) > time.time():
            return httpx.Client(base_url="http://127.0.0.1:3023", timeout=120, trust_env=False,
                                headers={"Authorization": "Bearer " + saved["token"]}), saved["user"]
    account = json.loads((RUNTIME / "accounts.json").read_text())[label]
    result = httpx.post("http://127.0.0.1:3023/api/auth/login",
                        json={"email": account["email"], "password": account["password"]}, timeout=20)
    result.raise_for_status()
    session.write_text(protect({**result.json(), "expires": min(time.time() + 600, token_expiry(result.json()["token"])-30)}), encoding="utf8")
    client = httpx.Client(base_url="http://127.0.0.1:3023", timeout=120, trust_env=False,
                         headers={"Authorization": "Bearer " + result.json()["token"]})
    return client, result.json()["user"]


def token_expiry(token):
    encoded = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded)%4)))["exp"]


def chat(client, text, conversation_id="new", parent_id="00000000-0000-0000-0000-000000000000"):
    source = str(uuid.uuid4())
    response = client.post("/api/agents/chat/Zhipu", json={
        "text": text, "messageId": source,
        "parentMessageId": parent_id, "conversationId": conversation_id,
        "endpoint": "Zhipu", "endpointType": "custom", "model": "glm-4.7", "spec": "life-companion-zhipu",
        "isCreatedByUser": True, "sender": "User", "timezone": "Asia/Shanghai"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36"})
    response.raise_for_status()
    conversation = response.json()["conversationId"]
    with client.stream("GET", f"/api/agents/chat/stream/{conversation}") as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line.startswith("data: "):
                value = json.loads(line[6:])
                if value.get("final") or value.get("event") == "done":
                    break
    for _ in range(60):
        messages = client.get(f"/api/messages/{conversation}").json()
        if isinstance(messages, list):
            saved = [m for m in messages if m.get("text") == text and m.get("isCreatedByUser")]
            if saved and any(not m.get("isCreatedByUser") and m.get("parentMessageId") == saved[-1]["messageId"]
                             and not m.get("unfinished") for m in messages):
                return conversation, saved[0]["messageId"], messages
        time.sleep(0.5)
    raise RuntimeError("SOURCE_NOT_PERSISTED")


def stage_b():
    client, user = login()
    other, _ = login("b")
    core = "http://127.0.0.1:8023"
    internal = {"X-Internal-Token": os.environ["LIFE_INTERNAL_TOKEN"]}
    # Only new isolated identities receive explicit test permissions.
    response = httpx.post(core + "/internal/v1/users/bootstrap", headers=internal, json={
        "librechat_user_id": user["id"], "memos_user_id": "", "memory_consent": True})
    response.raise_for_status()
    client.patch("/life-api/api/v1/me/settings", json={"notification_consent": True, "recall_consent": True}).raise_for_status()
    client.post("/life-api/api/v1/reminder-provisioning").raise_for_status()
    text = "明天早上提醒我带绿色 U 盘，不是银色的。"
    conversation, source, messages = chat(client, text)
    drafts = client.get("/life-api/api/v1/reminder-drafts", params={"conversation_id": conversation}).json()["drafts"]
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["missing_fields"] == ["event_time"], draft["missing_fields"]
    assert "不是银色" in draft["title"]
    assert draft["quick_choice"]["field"] == "event_time"
    state = {"conversation_id": conversation, "source_message_id": source, "draft_id": draft["draft_id"]}
    (RUNTIME / "b-state.json").write_text(json.dumps(state), encoding="utf8")
    # Leave A's selection for the browser, prove direct complete creation with B example.
    c2, s2, _ = chat(client, "明天下午 3 点在 1101 开会，明天早上 9 点提醒我。")
    ds = client.get("/life-api/api/v1/reminder-drafts", params={"conversation_id": c2}).json()["drafts"][0]
    assert ds["status"] == "scheduled", ds["status"]
    assert "15:00" in ds["preview"]["event_at"] and "09:00" in ds["preview"]["scheduled_at"]
    identifier = ds["reminder"]["reminder_id"]
    assert other.get("/life-api/api/v1/reminders/" + identifier).status_code == 404
    detail = client.get("/life-api/api/v1/reminders/" + identifier)
    assert detail.json()["reminder"]["source"]["source_message_id"] == s2
    report = {"status": "PASS", "real_provider": "Zhipu glm-4.7", "real_task_id": ds["reminder"]["upstream_task_id"],
              "checks": {"a_only_time_missing_and_negative_constraint": "PASS",
                         "b_complete_request_created_without_second_confirmation": "PASS",
                         "event_and_notification_times_distinct": "PASS", "cross_account_detail_denied": "PASS"},
              "browser_a_selection": "PENDING", "device_delivery": "UNKNOWN"}
    (EVIDENCE / "stage-b-live.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report))


def stage_c():
    client, _user = login()
    other, _ = login("b")
    state = {}
    for label, text in (("a", "明天带绿色 U 盘，不是银色的。"), ("b", "明天还要带雨伞。")):
        conversation, source, _ = chat(client, text)
        for _ in range(90):
            links = client.get("/life-api/api/v1/chat-links", params={"conversation_id": conversation}).json()["links"]
            saved = []
            for link in links:
                detail = client.get("/life-api/api/v1/knowledge/" + link["memory_id"]).json()["item"]
                if any(s["message_id"] == source for s in detail["sources"]):
                    saved.append(link)
            if saved:
                break
            time.sleep(.5)
        assert len(saved) == 1, f"MEMORY_NOT_LINKED_{label}"
        identifier = saved[0]["memory_id"]
        item = client.get("/life-api/api/v1/knowledge/" + identifier).json()["item"]
        assert any(s["message_id"] == source for s in item["sources"]), "SOURCE_UUID_MISMATCH"
        assert item["kind"] == "future_plan"
        assert other.get("/life-api/api/v1/knowledge/" + identifier).status_code == 404
        state[label] = {"conversation_id": conversation, "source_message_id": source, "memory_id": identifier}
    conversation, source, messages = chat(client, "我明天要带哪些东西？")
    answer = "\n".join(m.get("text") or "\n".join(p.get("text", "") for p in (m.get("content") or []) if p.get("type") == "text")
                       for m in messages if not m.get("isCreatedByUser"))
    assert all(word in answer for word in ("绿色", "银色", "雨伞")), "MULTI_FACT_LLM_RECALL_FAILED"
    links = client.get("/life-api/api/v1/chat-links", params={"conversation_id": conversation}).json()["links"]
    assert {state[k]["memory_id"] for k in ("a", "b")}.issubset({link["memory_id"] for link in links}), "RECALL_LINKS_MISSING"
    state["c"] = {"conversation_id": conversation, "source_message_id": source}
    (RUNTIME / "c-state.json").write_text(json.dumps(state), encoding="utf8")
    report = {"status": "PASS", "provider": "real Zhipu glm-4.7",
              "checks": {"two_new_chats_saved": "PASS", "third_chat_recalls_both_and_negation": "PASS",
                         "durable_uuid_sources": "PASS", "owner_scoped_details": "PASS", "recall_business_links": "PASS"},
              "answer_synthetic": answer, "entities": state}
    (EVIDENCE / "stage-c-live.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("answer_synthetic","entities")}))


def memos_setup():
    accounts = json.loads((RUNTIME / "accounts.json").read_text())
    tokens_path = RUNTIME / "memos-tokens.json"
    tokens = json.loads(tokens_path.read_text()) if tokens_path.exists() else {}
    label = sys.argv[2] if len(sys.argv)>2 else "a"
    account = accounts[label]
    client, user = login(label)
    with httpx.Client(base_url="http://127.0.0.1:5230",timeout=30,trust_env=False) as upstream:
        if not account.get("memos_user_id"):
            result = upstream.post("/api/users",headers={"Authorization":"Bearer "+os.environ["MEMOS_API_TOKEN"]},
                json={"username":account["username"],"password":account["password"],
                      "displayName":account["name"],"role":"USER","state":"NORMAL"})
            result.raise_for_status()
            account["memos_user_id"] = result.json()["name"]
            (RUNTIME / "accounts.json").write_text(json.dumps(accounts),encoding="utf8")
        if account["memos_user_id"] not in tokens:
            result = upstream.post("/api/auth/signin",json={
                "passwordCredentials":{"username":account["username"],"password":account["password"]}})
            result.raise_for_status()
            result = upstream.post("/api/"+account["memos_user_id"]+"/personalAccessTokens",
                headers={"Authorization":"Bearer "+result.json()["accessToken"]},
                json={"description":"V023 isolated synthetic acceptance","expiresInDays":7})
            result.raise_for_status()
            tokens[account["memos_user_id"]] = result.json()["token"]
            tokens_path.write_text(json.dumps(tokens),encoding="utf8")
    response = httpx.post("http://127.0.0.1:8023/internal/v1/users/bootstrap",
        headers={"X-Internal-Token":os.environ["LIFE_INTERNAL_TOKEN"]},json={
            "librechat_user_id":user["id"],"memos_user_id":account["memos_user_id"],
            "memos_username":account["username"],"display_name":account["name"],"memory_consent":True})
    response.raise_for_status()
    print("PASS: isolated synthetic Memos user and server-only token prepared. Production config unchanged.")


def stage_d():
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    label = sys.argv[2] if len(sys.argv)>2 else "d"
    client,_user = login(label)
    other,_ = login("b")
    client.patch("/life-api/api/v1/me/settings",json={"memory_consent":True,"image_consent":True}).raise_for_status()
    now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    boundary = (now+timedelta(minutes=3)).replace(second=0,microsecond=0)
    assert boundary.hour < 23, "LIVE_WINDOW_REQUIRES_NON_MIDNIGHT_TEST_SLOT"
    config = {"enabled":True,"timezone":"Asia/Hong_Kong",
              "ends":[(boundary+timedelta(minutes=i)).strftime("%H:%M") for i in (0,3,6)]}
    client.put("/life-api/api/v1/moment-settings",json=config).raise_for_status()
    state = {"configured_at":now.isoformat(),"execution_at":boundary.isoformat(),"sources":[]}
    for text in ("【V023模拟聊天】今天在公园散步，看见银杏树。",
                 "【V023模拟聊天】今天和朋友在公园散步，感觉特别放松。",
                 "【V023模拟聊天】今天第一次加入了一直想加入的项目组，特别开心！"):
        conversation,source,_ = chat(client,text)
        for _ in range(100):
            links = client.get("/life-api/api/v1/chat-links",params={"conversation_id":conversation}).json()["links"]
            own = []
            for link in links:
                detail = client.get("/life-api/api/v1/knowledge/"+link["memory_id"]).json()["item"]
                if detail["kind"] == "life_event" and any(s["message_id"] == source for s in detail["sources"]):
                    own.append(link)
            if own:
                break
            time.sleep(.5)
        assert own, "OCCURRED_EVENT_NOT_PERSISTED"
        memory_id = own[0]["memory_id"]
        state["sources"].append({"conversation_id":conversation,"source_message_id":source,"memory_id":memory_id})
    (RUNTIME / "d-state.json").write_text(json.dumps(state),encoding="utf8")
    print("Three real synthetic chat events persisted; waiting for the configured wall-clock execution.",flush=True)
    target = None
    for attempt in range(55):
        if token_expiry(client.headers["Authorization"].removeprefix("Bearer "))-time.time()<40:
            client.close()
            client,_user = login(label)
        response = client.get("/life-api/api/v1/moments")
        response.raise_for_status()
        listing = response.json()["moments"]
        found = [m for m in listing if m["window_end"] == boundary.isoformat()]
        if found:
            target = client.get("/life-api/api/v1/moments/"+found[0]["moment_id"]).json()["moment"]
            if target["status"] not in ("queued","generating"):
                break
        if attempt%4 == 0:
            print("Live job: "+(target["status"] if target else "awaiting_window"),flush=True)
        time.sleep(5)
    assert target, "SCHEDULER_DID_NOT_CREATE_MOMENT"
    assert len(target["source_memory_ids"]) == 1 and target["source_memory_ids"][0] == state["sources"][2]["memory_id"], "WRONG_EVENT_SELECTED"
    assert len(target["selection"]) == 3, "THREE_REAL_CANDIDATES_REQUIRED"
    assert other.get("/life-api/api/v1/moments/"+target["moment_id"]).status_code == 404
    state["moment_id"] = target["moment_id"]
    (RUNTIME / "d-state.json").write_text(json.dumps(state),encoding="utf8")
    report = {k:v for k,v in target.items() if k != "image_data"}
    report["real_image"] = bool(target.get("image_data"))
    report["acceptance"] = "PASS" if report["real_image"] and target["status"] == "generated" else "PARTIAL"
    (EVIDENCE / "stage-d-live.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"acceptance":report["acceptance"],"provider_status":target["status"],
                      "real_image":report["real_image"],"three_candidates_and_owner_isolation":"PASS"}))


def screenshot_scenario():
    client,_user = login()
    text = "今天感觉很开心，努力了很久的项目终于结束了"
    conversation,source,messages = chat(client,text)
    parent = [m for m in messages if not m.get("isCreatedByUser")][-1]["messageId"]
    _conversation,command,messages = chat(client,"可以加入回忆里",conversation,parent)
    response = client.get("/life-api/api/v1/chat-links",params={"conversation_id":conversation})
    response.raise_for_status()
    actions = response.json()["actions"]
    action = next(a for a in actions if a["message_id"] == command)
    assert action["status"] == "succeeded", "MANUAL_SAVE_NOT_CONFIRMED"
    identifier = action["memory_id"]
    item = client.get("/life-api/api/v1/knowledge/"+identifier).json()["item"]
    assert item["canonical_text"] == text
    assert any(s["message_id"] == source for s in item["sources"])
    assert item["image_candidate"] == 1
    report = {"acceptance":"PASS","synthetic_scenario":True,"conversation_id":conversation,
              "source_message_id":source,"command_message_id":command,"memory_id":identifier,
              "checks":{"exact_project_completion_saved":"PASS","manual_followup_receipt":"PASS",
                        "no_assistant_details_in_memory":"PASS","image_candidate_after_validation":"PASS"}}
    (RUNTIME / "screenshot-state.json").write_text(json.dumps(report),encoding="utf8")
    (EVIDENCE / "screenshot-scenario-live.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps(report))


if __name__ == "__main__":
    {"setup": setup, "b": stage_b, "c": stage_c, "memos":memos_setup, "d":stage_d, "screenshot":screenshot_scenario}[sys.argv[1]]()
