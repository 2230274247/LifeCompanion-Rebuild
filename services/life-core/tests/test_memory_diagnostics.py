from test_api import bootstrap, make_app
from test_memory_pipeline import auth, ingest
from test_hybrid_retrieval import prepare_app

HEADERS = {"X-Internal-Token": "test-internal"}


def test_recall_distinguishes_mapping_permission_no_match_and_hits(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        body = {"source_user_id": "lc-user-a", "query": "喝什么茶", "source_message_id": "q1"}
        assert client.post("/internal/v1/knowledge/recall", headers=HEADERS, json=body).json()["status"] == "user_not_mapped"
        bootstrap(client)
        assert client.post("/internal/v1/knowledge/recall", headers=HEADERS, json=body).json()["status"] == "permission_denied"
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        retrieval = prepare_app(app)
        retrieval.embedder.status = "cache_missing"
        unavailable = client.post("/internal/v1/knowledge/recall", headers=HEADERS, json=body).json()
        assert unavailable["status"] == "unavailable"
        assert unavailable["items"] == unavailable["profile"] == []
        assert unavailable["retrieval"]["keyword_retrieval"] is False
        retrieval.embedder.status = "ready"
        assert client.post("/internal/v1/knowledge/recall", headers=HEADERS, json=body).json()["status"] == "no_match"
        ingest(client, "我最喜欢喝龙井茶")
        prepare_app(app)
        found = client.post("/internal/v1/knowledge/recall", headers=HEADERS, json=body).json()
        assert found["status"] == "matched"
        assert found["items"] == [] and len(found["profile"]) == 1
        assert found["retrieval"]["profile_match_ids"] == [found["profile"][0]["memory_id"]]
        assert found["retrieval"]["keyword_retrieval"] is False
        traces = client.get("/api/v1/memory-status", headers=auth()).json()["traces"]
        assert {t["status"] for t in traces} >= {"permission_denied", "unavailable", "no_match", "matched"}
        assert "龙井" not in str(traces)
        bootstrap(client, "lc-user-b", "users/b")
        assert client.get("/api/v1/memory-status", headers=auth("lc-user-b")).json()["traces"] == []


def test_recall_accepts_wire_context_and_ignores_another_conversation(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch('/api/v1/me/settings', headers=auth(), json={'recall_consent': True})
        monkeypatch.setattr(app.state.memos, 'create_private_memo', lambda event: 'memos/'+event['event_id'])
        ingest(client, '今天加入了星河项目组', 'wire-event')
        prepare_app(app)
        body = {'source_user_id': 'lc-user-a', 'query': '那个项目后来怎么样',
                'conversation_id': 'chat-b', 'recent_messages': [
                    {'text': '星河项目组', 'conversation_id': 'chat-b'}]}
        found = client.post('/internal/v1/knowledge/recall', headers=HEADERS, json=body).json()
        assert found['retrieval']['context_source'] == 'recent_users'
        assert found['items'] and '星河' in found['items'][0]['text']
        body['recent_messages'][0]['conversation_id'] = 'unrelated-chat'
        assert client.post('/internal/v1/knowledge/recall', headers=HEADERS, json=body).json()['items'] == []


def test_telemetry_is_internal_and_redacts_free_text(tmp_path):
    _, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        body = {"source_user_id": "lc-user-a", "source_message_id": "q2", "stage": "recall",
                "status": "unavailable", "reason": "private user text 私密"}
        assert client.post("/internal/v1/memory/telemetry", json=body).status_code == 401
        assert client.post("/internal/v1/memory/telemetry", headers=HEADERS, json=body).status_code == 200
        trace = client.get("/api/v1/memory-status", headers=auth()).json()["traces"][0]
        assert trace["status"] == "unavailable" and trace["reason"] == "DETAIL_REDACTED"
