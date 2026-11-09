from datetime import datetime
from zoneinfo import ZoneInfo

from test_api import bootstrap, make_app
from test_memory_pipeline import auth
from test_hybrid_retrieval import prepare_app


def add(client, text, source, conversation):
    return client.post("/internal/v1/events/ingest",
        headers={"X-Internal-Token": "test-internal"}, json={
            "source_user_id": "lc-user-a", "source_message_id": source,
            "conversation_id": conversation, "text": text,
            "occurred_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()})


def test_cross_chat_plans_keep_negation_sources_and_isolation(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        bootstrap(client, "lc-user-b", "users/b")
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        a = add(client, "明天带绿色 U 盘，不是银色的。", "uuid-a", "chat-a").json()
        b = add(client, "明天还要带雨伞。", "uuid-b", "chat-b").json()
        assert a["accepted"] and b["accepted"]
        prepare_app(app)
        recall = client.post("/internal/v1/knowledge/recall",
            headers={"X-Internal-Token": "test-internal"}, json={
                "source_user_id": "lc-user-a", "query": "我明天要带哪些东西？",
                "conversation_id": "chat-c", "source_message_id": "uuid-c"}).json()["items"]
        assert len(recall) == 2
        assert all(i["kind"] == "future_plan" for i in recall)
        assert any("不是银色" in i["text"] for i in recall)
        assert any("雨伞" in i["text"] for i in recall)
        identifier = a["memory"]["memory_id"]
        detail = client.get(f"/api/v1/knowledge/{identifier}", headers=auth()).json()["item"]
        assert detail["sources"][0]["message_id"] == "uuid-a"
        assert client.get(f"/api/v1/knowledge/{identifier}", headers=auth("lc-user-b")).status_code == 404
        assert client.get("/api/v1/knowledge/recall?q=带哪些", headers=auth("lc-user-b")).json()["items"] == []
        links = client.get("/api/v1/chat-links?conversation_id=chat-c", headers=auth()).json()["links"]
        assert len(links) == 2
        assert client.get("/api/v1/chat-links?conversation_id=chat-c", headers=auth("lc-user-b")).json()["links"] == []
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": False})
        assert client.get("/api/v1/chat-links?conversation_id=chat-c", headers=auth()).json()["links"] == []
        assert app.state.store.list_events(a["memory"]["user_id"]) == []
        assert app.state.store.list_reminders(a["memory"]["user_id"]) == []


def test_plan_correction_deletion_replay_and_consent(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        item = add(client, "明天带绿色 U 盘，不是银色的。", "uuid-a", "chat-a").json()["memory"]
        corrected = client.patch(f"/api/v1/knowledge/{item['memory_id']}", headers=auth(),
                                 json={"text": "明天改为带蓝色 U 盘。"})
        assert corrected.status_code == 200
        prepare_app(app)
        entries = client.get("/api/v1/knowledge/recall?q=明天带哪些", headers=auth()).json()["items"]
        assert len(entries) == 1 and "蓝色" in entries[0]["canonical_text"]
        identifier = entries[0]["memory_id"]
        assert client.delete(f"/api/v1/knowledge/{identifier}", headers=auth()).status_code == 200
        add(client, "明天带绿色 U 盘，不是银色的。", "retry-source", "chat-new")
        assert client.get("/api/v1/knowledge/recall?q=明天带哪些", headers=auth()).json()["items"] == []
        client.patch("/api/v1/me/settings", headers=auth(), json={"memory_consent": False})
        assert not add(client, "明天还要带雨伞。", "denied", "chat-b").json()["accepted"]
        assert client.get("/api/v1/knowledge", headers=auth()).json()["items"] == []


def test_screenshot_project_completion_manual_add_uses_only_user_source(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        monkeypatch.setattr(app.state.memos, "create_private_memo", lambda event: "memos/" + event["event_id"])
        text = "今天感觉很开心，努力了很久的项目终于结束了"
        command = {
            "source_user_id":"lc-user-a","source_message_id":"manual-command","conversation_id":"project-chat",
            "text":"可以加入回忆里",
            "previous_user_message":{
                "source_user_id":"lc-user-a","source_message_id":"original-project-user-message",
                "conversation_id":"project-chat","text":text,
                "occurred_at":datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()}}
        headers = {"X-Internal-Token":"test-internal"}
        first = client.post("/internal/v1/memory/execute",headers=headers,json=command).json()
        assert first["status"] == "succeeded" and first["image_status"] == "not_generated"
        item = client.get("/api/v1" + first["url"],headers=auth()).json()["item"]
        assert item["canonical_text"] == text and item["kind"] == "life_event"
        assert item["sources"][0]["message_id"] == "original-project-user-message"
        assert item["importance"] >= .9
        assert client.post("/internal/v1/memory/execute",headers=headers,json=command).json()["url"] == first["url"]
        assert len(app.state.memory.list_items(item["user_id"])) == 1
        actions = client.get("/api/v1/chat-links?conversation_id=project-chat",headers=auth()).json()["actions"]
        assert actions[0]["status"] == "succeeded" and actions[0]["memory_id"] == item["memory_id"]
        client.patch("/api/v1/me/settings",headers=auth(),json={"memory_consent":False})
        assert client.post("/internal/v1/memory/execute",headers=headers,json=command).json()["status"] == "permission_required"


def test_eligibility_rejects_question_hypothetical_negation_and_assistant_invention(tmp_path, monkeypatch):
    app,client = make_app(tmp_path)
    with client:
        bootstrap(client)
        for index,text in enumerate(("如果项目终于结束了，我会很开心", "项目结束了吗", "今天很开心",
                                     "今天并没有完成项目", "怎么才能完成项目？")):
            assert not add(client,text,"excluded-"+str(index),"excluded-chat").json()["accepted"]
        assert app.state.memory.list_items(app.state.store.get_user_by_librechat_id("lc-user-a")["life_user_id"]) == []
        # A concrete future completion is a plan, not an occurred event or a fact.
        planned = add(client, "明天项目就结束了", "future", "excluded-chat").json()
        assert planned["accepted"] and planned["memory"]["kind"] == "future_plan"
        assert app.state.store.list_events(app.state.store.get_user_by_librechat_id("lc-user-a")["life_user_id"]) == []


def test_event_correction_preserves_raw_source_and_supersedes_old_retrieval(tmp_path,monkeypatch):
    app,client = make_app(tmp_path)
    with client:
        bootstrap(client)
        monkeypatch.setattr(app.state.memos,"create_private_memo",lambda event:"memos/"+event["event_id"])
        client.patch("/api/v1/me/settings",headers=auth(),json={"recall_consent":True})
        original = add(client,"今天项目终于结束了，感觉很开心。","original","chat-project").json()
        old = client.get("/api/v1/knowledge",headers=auth()).json()["items"][0]
        changed = client.patch("/api/v1/knowledge/"+old["memory_id"],headers=auth(),
                               json={"text":"今天毕业了，感觉很开心。"})
        assert changed.status_code == 200 and changed.json()["accepted"]
        assert client.get("/api/v1/knowledge/"+old["memory_id"],headers=auth()).json()["item"]["state"] == "superseded"
        prepare_app(app)
        items = client.get("/api/v1/knowledge/recall?q=今天经历了什么",headers=auth()).json()["items"]
        assert len(items) == 1 and "毕业" in items[0]["canonical_text"]
        assert app.state.store.get_event(original["event"]["event_id"])["summary"] == "今天项目终于结束了，感觉很开心。"
