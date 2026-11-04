"""Exercise the real provider, LibreChat and extraction with synthetic data only."""

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import uuid

import httpx

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parents[1]
module_spec = spec_from_file_location("dialog_acceptance", ROOT / "tests/live-reminder-dialog-v022.py")
dialog = module_from_spec(module_spec)
module_spec.loader.exec_module(dialog)


def run():
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "checks": {}, "status": "FAIL"}
    try:
        settings = dialog.settings()
        assert settings.memory_llm_provider == "zhipu"
        assert settings.memory_llm_key
        report["runtime_configuration"] = {
            "provider": settings.memory_llm_provider, "model": settings.memory_llm_model,
            "base_url": settings.memory_llm_url,
        }
        from app.memory import MemoryService
        from app.reminder_drafts import ReminderDrafts
        from app.store import Store

        isolated = replace(settings, database_path=ROOT / "infra/runtime/zhipu-extraction.sqlite3")
        store = Store(isolated.database_path)
        store.initialize()
        candidate = MemoryService(store, isolated)._llm("我一直喜欢喝龙井茶。")
        assert candidate and candidate.fact_key == "drink_preference" and "龙井" in candidate.value
        assert candidate._classifier.startswith("llm:" + settings.memory_llm_model)
        report["checks"]["real_memory_schema_extraction"] = "PASS"
        fields = ReminderDrafts(store, isolated, None).extract("明天在北京14:30提醒我取合成测试文件")
        assert fields["title"] and fields["event_time"] == "14:30:00"
        assert fields["timezone"] == "Asia/Shanghai"
        report["checks"]["real_reminder_schema_extraction"] = "PASS"

        account = dialog.accounts()["c"]
        login = httpx.post("http://127.0.0.1:3080/api/auth/login",
                           json={"email": account["email"], "password": account["password"]},
                           timeout=15)
        login.raise_for_status()
        with httpx.Client(base_url="http://127.0.0.1:3001", timeout=90, headers={
            "Authorization": "Bearer " + login.json()["token"],
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
        }) as client:
            for endpoint, model, spec in [
                ("Zhipu", settings.memory_llm_model, "life-companion-zhipu"),
                ("DeepSeek", "deepseek-flash", "life-companion"),
            ]:
                text = "这是一条合成聊天接口测试。请只回复：接口测试成功。"
                response = client.post("/api/agents/chat/" + endpoint, json={
                    "text": text, "messageId": str(uuid.uuid4()),
                    "parentMessageId": "00000000-0000-0000-0000-000000000000",
                    "conversationId": "new", "endpoint": endpoint, "endpointType": "custom",
                    "model": model, "spec": spec,
                    "isCreatedByUser": True, "sender": "User", "timezone": "Asia/Shanghai",
                })
                response.raise_for_status()
                conversation = response.json()["conversationId"]
                with client.stream("GET", "/api/agents/chat/stream/" + conversation) as stream:
                    stream.raise_for_status()
                    for line in stream.iter_lines():
                        if line.startswith("data: "):
                            payload = json.loads(line[6:])
                            if payload.get("final") or payload.get("event") == "done":
                                break
                saved = client.get("/api/messages/" + conversation)
                saved.raise_for_status()
                assistants = [m for m in saved.json() if not m.get("isCreatedByUser")]
                assert assistants and not any(m.get("error") for m in assistants)
                output = " ".join(
                    m.get("text", "") + " " + " ".join(
                        p.get("text", "") if isinstance(p.get("text"), str)
                        else (p.get("text") or {}).get("value", "")
                        for p in m.get("content", []) if p.get("type") == "text"
                    ) for m in assistants
                )
                assert "接口测试成功" in output
                title = None
                for _ in range(15):
                    result = client.get("/api/convos/" + conversation)
                    result.raise_for_status()
                    title = result.json().get("title")
                    if title and title != "New Chat":
                        break
                    time.sleep(1)
                assert title and title != "New Chat"
                report["checks"][endpoint] = {
                    "status": "PASS", "saved_user_message": any(m.get("text") == text for m in saved.json()),
                    "assistant_reply": "接口测试成功", "generated_title": title,
                    "conversation_id": conversation,
                    "legacy_spec_endpoint_pair": endpoint == "DeepSeek",
                }
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            report["http_status"] = exc.response.status_code
    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    evidence = ROOT / "evidence/v022-zhipu"
    evidence.mkdir(exist_ok=True)
    path = evidence / ("live-integration-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(run())
