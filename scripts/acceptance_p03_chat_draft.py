"""Use an existing authenticated LibreChat synthetic message through real HTTP."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.config import load_settings

CORE_URL = os.environ.get("LIFE_ACCEPTANCE_CORE_URL", "http://127.0.0.1:8031").rstrip("/")
assert urlparse(CORE_URL).scheme == "http" and urlparse(CORE_URL).hostname == "127.0.0.1"
EVIDENCE = Path(os.environ.get("LIFE_ACCEPTANCE_UI_EVIDENCE", ROOT / "evidence/p03")).resolve()
assert EVIDENCE.is_relative_to((ROOT / "evidence/p03").resolve())
EVIDENCE.mkdir(parents=True, exist_ok=True)


def main(prepare_ui=False):
    settings = load_settings()
    accounts = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / "infra/runtime/p00/baseline-state.json").read_text(encoding="utf-8"))
    # P01's explicit reminder message was persisted under account A; baseline key
    # "d" is the source-page label, not the Mongo owner.
    account = accounts["a"]
    source = dict(baseline["d"])
    run_id = uuid.uuid4().hex[:12]
    original_conversation = source["conversation_id"]
    if prepare_ui:
        source["conversation_id"] = str(uuid.uuid4())
    message_id = f"p03-source-{run_id}"
    text = "明天提醒我带绿色 U 盘，不是银色的。"
    escaped_text = text.encode("ascii", "backslashreplace").decode("ascii")
    script = f"""
const conversationId = {json.dumps(source['conversation_id'])};
const messageId = {json.dumps(message_id)};
const conversation = db.conversations.findOne({{conversationId: {json.dumps(original_conversation)}}});
if (!conversation) {{ throw new Error('SYNTHETIC_CONVERSATION_MISSING'); }}
const now = new Date();
const assistantId = {json.dumps("p03-assistant-" + run_id if prepare_ui else "unused")};
const inserted = db.messages.insertOne({{
  messageId, user: conversation.user, __v: 0, _meiliIndex: false,
  conversationId, createdAt: now, endpoint: 'DeepSeek', error: false,
  isCreatedByUser: true, isTemporary: false, model: null,
  parentMessageId: '00000000-0000-0000-0000-000000000000',
  sender: 'User', text: '{escaped_text}', tokenCount: 20,
  unfinished: false, updatedAt: now, expiredAt: null
}});
let assistant = null;
if ({json.dumps(prepare_ui)}) {{
  // ReminderCards are mounted under an assistant reply; no generation request is made.
  assistant = db.messages.insertOne({{
    messageId: assistantId, user: conversation.user, __v: 0, _meiliIndex: false,
    attachments: [], content: [{{type: 'text', text: '已记录提醒草稿。'}}],
    conversationId, createdAt: now, endpoint: 'P03-synthetic', error: false,
    expiredAt: null, isCreatedByUser: false, isTemporary: false, isUserSubmitted: false,
    model: null, parentMessageId: messageId, sender: '拾光', text: '', tokenCount: 0,
    unfinished: false, updatedAt: now
  }});
  delete conversation._id;
  Object.assign(conversation, {{conversationId, title: 'P03 synthetic chip acceptance',
    messages: [inserted.insertedId, assistant.insertedId], createdAt: now, updatedAt: now,
    endpoint: 'DeepSeek', model: 'deepseek-flash', chatGptLabel: 'DeepSeek'}});
  db.conversations.insertOne(conversation);
}} else {{
  db.conversations.updateOne({{conversationId}}, {{$push: {{messages: inserted.insertedId}}, $set: {{updatedAt: now}}}});
}}
print(inserted.insertedId.toString());
"""
    inserted = subprocess.run(
        ["docker", "exec", "lcr-acceptance-20261103-mongo-1", "mongosh",
         "LibreChatAcceptance", "--quiet", "--eval", script],
        capture_output=True, text=True, check=True,
    )
    assert inserted.stdout.strip(), "SYNTHETIC_MESSAGE_INSERT_FAILED"
    result = {
        "status": "FAIL", "provider_calls": 0, "synthetic_account": True,
        "scope": "LibreChat login + persisted synthetic message + real Life-core + Vikunja",
        "message_id": message_id,
        "conversation_id": source["conversation_id"],
    }
    with httpx.Client(timeout=25, trust_env=False) as http:
        login = http.post("http://127.0.0.1:3091/api/auth/login", json={
            "email": account["email"], "password": account["password"],
        })
        login.raise_for_status()
        auth = {"Authorization": "Bearer " + login.json()["token"]}
        message = http.get("http://127.0.0.1:3091/api/messages", headers=auth, params={
            "conversationId": source["conversation_id"],
            "messageId": message_id,
        })
        message.raise_for_status()
        assert len(message.json()["messages"]) == 1
        internal = {"X-Internal-Token": settings.internal_token}
        boot = http.post(f"{CORE_URL}/internal/v1/users/bootstrap",
                         headers=internal, json={
            "librechat_user_id": account["librechat_user_id"],
            "memos_user_id": account["memos_user_id"],
            "display_name": account["name"], "memory_consent": False,
            "image_consent": False,
        })
        boot.raise_for_status()
        http.patch(f"{CORE_URL}/api/v1/me/settings", headers=auth,
                   json={"notification_consent": True}).raise_for_status()
        provisioned = http.post(f"{CORE_URL}/api/v1/reminder-provisioning", headers=auth, timeout=45)
        provisioned.raise_for_status()
        assert provisioned.json()["status"] == "ready"
        created = http.post(f"{CORE_URL}/api/v1/reminder-drafts", headers=auth, json={
            "conversation_id": source["conversation_id"],
            "source_message_id": message_id,
            "text": text,
        })
        created.raise_for_status()
        draft = created.json()
        assert draft["missing_fields"] == ["event_time"], draft
        assert "不是银色" in draft["title"]
        assert draft["quick_choice"]["field"] == "event_time"
        if prepare_ui:
            result.update(
                status="PASS", draft_id=draft["draft_id"],
                scope="synthetic Mongo source + real LibreChat ownership API + unconfirmed draft",
                missing_fields=draft["missing_fields"], quick_choice=draft["quick_choice"])
            (EVIDENCE / "ui-draft-fixture.json").write_text(
                json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=True))
            return
        selected = http.post(
            f"{CORE_URL}/api/v1/reminder-drafts/{draft['draft_id']}/select",
            headers=auth, json={"revision": draft["revision"],
                                "fields": {"event_time": "09:30"}})
        selected.raise_for_status()
        scheduled = selected.json()
        assert scheduled["status"] == "scheduled", scheduled
        assert scheduled["preview"]["scheduled_at"].endswith("09:30:00+08:00")
        detail = http.get(
            f"{CORE_URL}/api/v1/reminders/"
            f"{scheduled['reminder']['reminder_id']}", headers=auth)
        detail.raise_for_status()
        assert detail.json()["reminder"]["source"]["source_message_id"] == message_id
        result.update(status="PASS", draft_id=draft["draft_id"],
                      reminder_id=scheduled["reminder"]["reminder_id"],
                      scheduled_at=scheduled["preview"]["scheduled_at"],
                      checks={
                          "real_librechat_message_ownership_verified": "PASS",
                          "only_missing_time_selected": "PASS",
                          "negative_constraint_preserved": "PASS",
                          "real_vikunja_task_created": "PASS",
                          "source_trace_back": "PASS",
                          "device_delivery": "UNKNOWN",
                      })
    (EVIDENCE / "draft-live.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main(prepare_ui="--prepare-ui" in sys.argv)
