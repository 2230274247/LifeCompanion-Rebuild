"""Real LibreChat -> DeepSeek -> worker -> Memos acceptance, synthetic account only.

Supply an existing throwaway account JSON containing email/password. Secrets are
read locally and excluded from evidence. Run through the product gateway so that
memory reads exercise /life-api. No direct database writes or JWT minting.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ZERO = "00000000-0000-0000-0000-000000000000"


def content_text(row):
    if row.get("text"):
        return row["text"]
    result = []
    for part in row.get("content") or []:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text", "")
        if isinstance(text, dict):
            text = text.get("value", "")
        if isinstance(text, str):
            result.append(text)
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-file", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    token = ""

    def call(method, path, body=None):
        headers = {"Content-Type": "application/json", "X-LibreChat-Generation-Protocol": "2",
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(base + path, method=method, headers=headers,
                                         data=json.dumps(body).encode("utf-8") if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=100) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "GET" and path.startswith("/api/messages/"):
                return []  # A new conversation has no persisted rows yet.
            raise RuntimeError(f"HTTP_{exc.code} {method} {path}") from None

    def rows(conversation):
        body = call("GET", "/api/messages/" + conversation)
        return body if isinstance(body, list) else body.get("messages", [])

    def turn(text, conversation, parent=ZERO):
        # LibreChat's persistence contract requires canonical UUID identifiers.
        uuid.UUID(conversation)
        message_id = str(uuid.uuid4())
        previous_ids = {row.get("messageId") for row in rows(conversation)}
        started = time.monotonic()
        job = call("POST", "/api/agents/chat", {
            "text": text, "conversationId": conversation, "parentMessageId": parent,
            "messageId": message_id, "isCreatedByUser": True, "endpoint": "DeepSeek",
            "endpointType": "custom", "model": "deepseek-chat", "generationProtocolVersion": 2,
        })
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            messages = rows(conversation)
            user = next((r for r in messages if r.get("isCreatedByUser")
                         and r.get("messageId") not in previous_ids
                         and content_text(r) == text), None)
            durable_id = user.get("messageId") if user else None
            reply = next((r for r in messages if not r.get("isCreatedByUser")
                          and durable_id and r.get("parentMessageId") == durable_id
                          and r.get("unfinished") is False and content_text(r)), None)
            if reply:
                if reply.get("error") or not user or content_text(user) != text:
                    raise RuntimeError("PERSISTED_TURN_INVALID")
                return {"conversation_id": conversation, "user_message_id": durable_id,
                        "assistant_message_id": reply["messageId"], "input": text,
                        "reply": content_text(reply), "error": reply.get("error"),
                        "unfinished": reply.get("unfinished"), "model": reply.get("model"),
                        "token_count": reply.get("tokenCount"),
                        "usage": reply.get("metadata", {}).get("usage"),
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                        "stream_id": job.get("streamId")}
            time.sleep(1)
        raise RuntimeError("PERSISTED_TURN_TIMEOUT")

    account = json.loads(args.account_file.read_text(encoding="utf-8-sig"))
    login = call("POST", "/api/auth/login", {"email": account["email"], "password": account["password"]})
    token = login["token"]
    health = call("GET", "/life-api/health")
    if health.get("memory_pipeline", {}).get("extractor") != "deepseek":
        raise RuntimeError("REAL_DEEPSEEK_EXTRACTOR_REQUIRED")
    report = {"scope": "isolated synthetic account; real DeepSeek chat/extraction; official Memos",
              "health": health, "turns": [], "status": "PARTIAL"}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        conversation = str(uuid.uuid4())
        first = turn("昨天我参观了上海科技馆，看到了有趣的机器人展览。", conversation)
        report["turns"].append(first)
        save()
        second = turn("我刚才说去了哪里，看了什么？", conversation, first["assistant_message_id"])
        report["turns"].append(second)
        save()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            listing = call("GET", "/life-api/api/v1/memories?page_size=50")
            memory = next((m for m in listing.get("memories", [])
                           if first["user_message_id"] in m.get("source_message_ids", [])), None)
            if memory:
                report["memory"] = memory
                report["memory_detail"] = call("GET", "/life-api/api/v1/memories/" + memory["event_id"])
                report["memory_status"] = call("GET", "/life-api/api/v1/memory-status")
                break
            time.sleep(2)
        else:
            raise RuntimeError("REAL_EXTRACTION_OR_MEMOS_TIMEOUT")
        # A fresh conversation must recall the event through memory, not chat history.
        recall = turn("我昨天参观了什么地方，看到了什么展览？", str(uuid.uuid4()))
        report["turns"].append(recall)
        if "科技馆" not in recall["reply"] or "机器人" not in recall["reply"]:
            raise RuntimeError("CROSS_CONVERSATION_RECALL_NOT_CONFIRMED")
        report["status"] = "PASS"
        save()
        print("PASS: three persisted turns, real extraction, /life-api list/detail and fresh-chat recall")
    except Exception as exc:
        report["failure"] = type(exc).__name__ + ": " + str(exc)
        save()
        raise


if __name__ == "__main__":
    main()
