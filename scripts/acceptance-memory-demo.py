"""Verify rich synthetic P5 history through gateway APIs and real DeepSeek chat.

Reads only the existing local test account. Never saves passwords or tokens.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZERO = "00000000-0000-0000-0000-000000000000"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("chat_acceptance", ROOT / "scripts/acceptance-memory-chat.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    account = json.loads((ROOT / "infra/runtime/p5/lc-account.json").read_text(encoding="utf-8-sig"))
    token = ""

    def call(method, path, body=None):
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 Chrome/126.0.0.0",
                   "X-LibreChat-Generation-Protocol": "2"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request("http://127.0.0.1:3001" + path, method=method, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=100) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and path.startswith("/api/messages/"):
                return []
            raise RuntimeError(f"HTTP_{exc.code} {method} {path}") from None

    login = call("POST", "/api/auth/login", {"email": account["email"], "password": account["password"]})
    token = login["token"]
    report = {"status": "PARTIAL", "login": "PASS", "checks": [], "turns": []}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(name, passed, evidence):
        report["checks"].append({"name": name, "status": "PASS" if passed else "FAIL", "evidence": evidence})
        save()

    health = call("GET", "/life-api/health")
    check("Real DeepSeek extractor active", health["memory_pipeline"]["extractor"] == "deepseek", health)
    first = call("GET", "/life-api/api/v1/memories?page=1&page_size=50")
    collected = []
    page = first
    page_number = 1
    while True:
        collected.extend(page["memories"])
        if not page["has_more"]:
            break
        page_number += 1
        page = call("GET", f"/life-api/api/v1/memories?page={page_number}&page_size=50")
    ids = [m["event_id"] for m in collected]
    fixtures = [m for m in collected if "合成验收历史" in m["content"] and m["occurrence_precision"] == "day"]
    check("Gateway pagination covers rich history", len(fixtures) >= 120 and len(ids) == len(set(ids)) == first["total"],
          {"total": first["total"], "pages": page_number, "unique_events": len(set(ids)),
           "dated_synthetic_events": len(fixtures), "date_min": min(m["occurrence_start"] for m in fixtures),
           "date_max": max(m["occurrence_start"] for m in fixtures)})
    dated = call("GET", "/life-api/api/v1/memories?on_date=2026-10-02&page_size=50")
    check("Date filter returns October trip", dated["total"] == 1 and "龙井村" in dated["memories"][0]["content"], dated)
    selected = dated["memories"][0]
    detail = call("GET", "/life-api/api/v1/memories/" + selected["event_id"])
    check("Detail reads actual published Memos content", detail["memory"]["content"] == selected["content"], detail)

    # Explicit warmup via authenticated retrieval; no database manipulation.
    warmups = []
    for _ in range(8):
        result = call("POST", "/life-api/api/v1/knowledge/recall", {"query": "2026年10月2日我和林晓去了哪里？"})
        warmups.append(result)
        if result.get("status") == "matched":
            break
        time.sleep(5)
    report["warmups"] = warmups
    save()

    questions = [
        ("2026年10月2日，我和林晓去了哪里？", ["龙井村"]),
        ("2025年11月，我在读书会分享了哪本书？", ["小王子"]),
        ("请回顾2026年10月的生活记录，按活动整理，并说明本次查到了多少条。", ["龙井村", "苏东坡传"]),
    ]
    for question, expected in questions:
        conversation = str(uuid.uuid4())
        started = time.monotonic()
        call("POST", "/api/agents/chat", {"text": question, "conversationId": conversation,
            "parentMessageId": ZERO, "messageId": str(uuid.uuid4()), "isCreatedByUser": True,
            "endpoint": "DeepSeek", "endpointType": "custom", "model": "deepseek-chat", "generationProtocolVersion": 2})
        deadline = time.monotonic() + 180
        turn = {"input": question, "conversation_id": conversation, "status": "FAIL"}
        while time.monotonic() < deadline:
            body = call("GET", "/api/messages/" + conversation)
            messages = body if isinstance(body, list) else body.get("messages", [])
            user = next((m for m in messages if m.get("isCreatedByUser") and helper.content_text(m) == question), None)
            reply = next((m for m in messages if user and m.get("parentMessageId") == user["messageId"]
                          and not m.get("isCreatedByUser") and m.get("unfinished") is False
                          and helper.content_text(m)), None)
            if reply:
                answer = helper.content_text(reply)
                turn.update(reply=answer, assistant_message_id=reply["messageId"], user_message_id=user["messageId"],
                            elapsed_seconds=round(time.monotonic() - started, 2), error=reply.get("error"),
                            unfinished=reply.get("unfinished"), expected_facts=expected,
                            status="PASS" if not reply.get("error") and all(x in answer for x in expected) else "FAIL")
                break
            time.sleep(1)
        report["turns"].append(turn)
        save()
        print(f"Persisted real DeepSeek turn: {turn['status']}", flush=True)
    report["status"] = "PASS" if all(c["status"] == "PASS" for c in report["checks"] + report["turns"]) else "PARTIAL"
    save()
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
