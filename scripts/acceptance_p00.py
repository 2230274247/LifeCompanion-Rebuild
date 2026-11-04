"""Real official APIs and persisted data; synthetic accounts, no mocked providers."""
from __future__ import annotations

import json
import secrets
import sys
import time
import uuid
from pathlib import Path

import httpx

from acceptance_environment import RUNTIME, ROOT, dotenv, ENVFILE
from verify_rebuild_workspace import verify

verify(ROOT)
BASE = "http://127.0.0.1:3031"
CORE = "http://127.0.0.1:8031"
EVIDENCE = ROOT / "evidence/p00"


def check(response, label):
    if response.is_error:
        raise RuntimeError(f"{label}_HTTP_{response.status_code}")
    return response


def accounts():
    return json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))


def login(label="a"):
    account = accounts()[label]
    client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    response = check(client.post("/api/auth/login", json={
        "email": account["email"], "password": account["password"],
    }), "LOGIN")
    client.headers["Authorization"] = "Bearer " + response.json()["token"]
    return client, response.json()["user"]


def setup():
    path = RUNTIME / "accounts.json"
    values = accounts() if path.exists() else {}
    tokens_path = RUNTIME / "memos-tokens.json"
    tokens = json.loads(tokens_path.read_text())
    env = dotenv(ENVFILE)
    for label in "abcdefgh":
        item = values.setdefault(label, {
            "username": f"lcr-p00-{label}-{secrets.token_hex(4)}",
            "email": f"lcr-p00-{label}-{secrets.token_hex(5)}@example.invalid",
            "name": f"Rebuild Synthetic {label.upper()}",
            "password": secrets.token_urlsafe(30) + "aA1!",
        })
        path.write_text(json.dumps(values), encoding="utf-8")
        if not item.get("registered"):
            check(httpx.post(BASE + "/api/auth/register", json={
                **{k: item[k] for k in ("username", "email", "name", "password")},
                "confirm_password": item["password"],
            }, timeout=25, trust_env=False), "REGISTER")
            item["registered"] = True
            path.write_text(json.dumps(values), encoding="utf-8")
        client, user = login(label)
        item["librechat_user_id"] = user["id"]
        with httpx.Client(base_url="http://127.0.0.1:5241", timeout=25, trust_env=False) as memos:
            if not item.get("memos_user_id"):
                created = check(memos.post("/api/users", json={
                    "username": item["username"], "password": item["password"],
                    "displayName": item["name"], "role": "USER",
                }), "MEMOS_REGISTER")
                item["memos_user_id"] = created.json()["name"]
                path.write_text(json.dumps(values), encoding="utf-8")
            auth = check(memos.post("/api/auth/signin", json={
                "passwordCredentials": {"username": item["username"],
                                        "password": item["password"]},
            }), "MEMOS_LOGIN").json()["accessToken"]
            if item["memos_user_id"] not in tokens:
                pat = check(memos.post("/api/" + item["memos_user_id"] + "/personalAccessTokens",
                    headers={"Authorization": "Bearer " + auth},
                    json={"description": "Rebuild isolated P00 acceptance", "expiresInDays": 7}
                ), "MEMOS_TOKEN").json()["token"]
                tokens[item["memos_user_id"]] = pat
                tokens_path.write_text(json.dumps(tokens), encoding="utf-8")
        check(httpx.post(CORE + "/internal/v1/users/bootstrap",
            headers={"X-Internal-Token": env["LIFE_INTERNAL_TOKEN"]}, json={
                "librechat_user_id": user["id"], "memos_user_id": item["memos_user_id"],
                "memos_username": item["username"], "display_name": item["name"],
                "memory_consent": True, "image_consent": False,
            }, trust_env=False), "IDENTITY_MAPPING")
        check(client.patch("/life-api/api/v1/me/settings",
                           json={"recall_consent": True}), "TEST_RECALL_CONSENT")
        client.close()
        path.write_text(json.dumps(values), encoding="utf-8")
        print(f"Synthetic account {label}: registered, distinct Memos identity, mapped.", flush=True)
    (EVIDENCE / "accounts-summary.json").write_text(json.dumps({
        "accounts": 8, "synthetic": True, "distinct_librechat_ids": len({
            a["librechat_user_id"] for a in values.values()}),
        "distinct_memos_ids": len({a["memos_user_id"] for a in values.values()}),
        "image_consent": False, "notification_consent": False,
    }, indent=2), encoding="utf-8")


def chat(client, text):
    message = str(uuid.uuid4())
    response = check(client.post("/api/agents/chat/Zhipu", json={
        "text": text, "messageId": message, "parentMessageId": str(uuid.UUID(int=0)),
        "conversationId": "new", "endpoint": "Zhipu", "endpointType": "custom",
        "model": "glm-4.7", "spec": "life-companion-zhipu",
        "isCreatedByUser": True, "sender": "User", "timezone": "Asia/Hong_Kong",
    }, headers={"User-Agent": "Mozilla/5.0 Chrome/142.0.0.0 Safari/537.36"}), "CHAT_SUBMIT")
    conversation = response.json()["conversationId"]
    with client.stream("GET", f"/api/agents/chat/stream/{conversation}") as stream:
        check(stream, "CHAT_STREAM")
        for line in stream.iter_lines():
            if line.startswith("data: "):
                value = json.loads(line[6:])
                if value.get("final") or value.get("event") == "done":
                    break
    for _ in range(40):
        messages = check(client.get(f"/api/messages/{conversation}"), "HISTORY").json()
        sources = [m for m in messages if m.get("text") == text and m.get("isCreatedByUser")]
        answers = [m for m in messages if not m.get("isCreatedByUser") and not m.get("unfinished")]
        if sources and answers:
            return conversation, sources[0]["messageId"], messages
        time.sleep(.5)
    raise RuntimeError("CHAT_NOT_PERSISTED_OR_NO_COMPLETED_ANSWER")


def run():
    report = {"evidence_level": "REBUILD_RUNTIME_VERIFIED", "checks": {},
              "provider": "existing Zhipu glm-4.7", "new_chat_call_limit": 4,
              "image_calls": 0, "real_device_delivery": "UNKNOWN"}
    session, user = login()
    other, _ = login("b")
    state = {}
    started = time.monotonic()
    for label, text in (("a", "明天带绿色 U 盘，不是银色的。"),
                        ("b", "明天还要带雨伞。"),
                        ("c", "我明天要带哪些东西？"),
                        ("d", "明天早上提醒我带绿色 U 盘，不是银色的。")):
        print(f"Real chat {label} started.", flush=True)
        try:
            conversation, message, messages = chat(session, text)
            state[label] = {"conversation_id": conversation, "source_message_id": message}
            state[label]["messages"] = messages
            report["checks"][f"chat_{label}_persisted"] = "PASS"
            own = check(session.get(f"/api/messages/{conversation}"), "REFRESH_HISTORY").json()
            assert len(own) >= 2
            denied = other.get(f"/api/messages/{conversation}")
            report["checks"][f"chat_{label}_other_user"] = (
                "PASS" if denied.status_code in (403, 404) or denied.json() == [] else "FAIL"
            )
        except Exception as exc:
            report["checks"][f"chat_{label}_persisted"] = f"FAIL:{type(exc).__name__}:{exc}"
        print(f"Real chat {label}: {report['checks'][f'chat_{label}_persisted']}", flush=True)
    if "c" in state:
        answer = "\n".join(m.get("text") or "\n".join(
            part.get("text", "") for part in m.get("content", []) if part.get("type") == "text"
        ) for m in state["c"]["messages"] if not m.get("isCreatedByUser"))
        report["checks"]["usb_umbrella_both_recalled"] = (
            "PASS" if all(word in answer for word in ("绿色", "银色", "雨伞")) else "FAIL"
        )
        report["synthetic_recall_answer"] = answer
    if "d" in state:
        result = session.get("/life-api/api/v1/reminder-drafts",
                             params={"conversation_id": state["d"]["conversation_id"]})
        report["checks"]["draft_list_http"] = result.status_code
        if result.status_code == 200:
            drafts = result.json()["drafts"]
            report["reminder_drafts"] = [{
                k: d.get(k) for k in ("draft_id", "status", "missing_fields", "quick_choice", "title")
            } for d in drafts]
            if drafts:
                report["checks"]["draft_owner_isolation"] = other.patch(
                    "/life-api/api/v1/reminder-drafts/" + drafts[0]["draft_id"],
                    json={"title": "unauthorized synthetic edit"},
                    headers={"If-Match": str(drafts[0]["revision"])},
                ).status_code
    state["provider"] = report["provider"]
    # Only synthetic messages and opaque IDs; login secrets are never in state/evidence.
    (RUNTIME / "baseline-state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["overall"] = "PARTIAL"
    (EVIDENCE / "live-baseline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "checks": report["checks"]}), flush=True)


if __name__ == "__main__":
    {"setup": setup, "run": run}[sys.argv[1]]()
