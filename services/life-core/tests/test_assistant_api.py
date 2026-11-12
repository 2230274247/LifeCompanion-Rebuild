"""Internal assistant plan/execute wiring, no real provider."""
import httpx
from dataclasses import replace

from test_api import bootstrap, make_app, token_for


def auth(user="lc-user-a"):
    return {"Authorization": f"Bearer {token_for(user)}"}


def enable_planner(app):
    settings = replace(app.state.settings, memory_llm_key="synthetic")
    app.state.settings = settings
    app.state.memory.settings = settings
    app.state.planner.settings = settings


def plan(client, query, source_user_id="lc-user-a"):
    return client.post("/internal/v1/assistant/plan", headers={"X-Internal-Token": "test-internal"}, json={
        "source_user_id": source_user_id, "query": query,
        "conversation_id": "c1", "source_message_id": "u1", "recent_messages": [],
    })


def test_plan_returns_tasks_and_gates_without_recall_consent(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        enable_planner(app)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})

        class Provider:
            def __init__(self, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def post(self, *_args, **_kwargs):
                return httpx.Response(200, request=httpx.Request("POST", "https://synthetic.invalid"),
                                      json={"choices": [{"message": {"content": (
                    '{"version":"1","tasks":[{"action":"overview","query":"最近做了什么",'
                    '"window":{"relative_days":14},"selection":"interesting"}]}')}}]})
        monkeypatch.setattr("app.assistant_plan.httpx.Client", Provider)

        response = plan(client, "你觉得我近期最有意思的一件事是什么")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "planned"
        assert payload["tasks"][0]["action"] == "overview"

        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": False})
        assert plan(client, "最近做了什么").json()["status"] == "permission_denied"


def test_plan_without_llm_key_reports_unavailable(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        assert plan(client, "最近做了什么").json()["status"] == "planner_unavailable"


def test_execute_runs_overview_and_memory_without_forging_success(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        enable_planner(app)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        app.state.memos.create_private_memo = lambda event: f"memos/{event['event_id']}"
        # Two dated events already ingested; overview must list them regardless of query wording.
        for message, day, text in (("a", "2026-11-06T10:00:00+08:00", "今天下午和朋友在公园散步，看见秋天的银杏树"),
                                   ("b", "2026-11-04T10:00:00+08:00", "昨天项目验收顺利通过了")):
            response = client.post("/internal/v1/events/ingest", headers={"X-Internal-Token": "test-internal"},
                                   json={"source_user_id": "lc-user-a", "source_message_id": message,
                                         "conversation_id": "c1", "text": text, "occurred_at": day})
            assert response.status_code == 200

        class Provider:
            def __init__(self, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def post(self, *_args, **_kwargs):
                return httpx.Response(200, request=httpx.Request("POST", "https://synthetic.invalid"),
                                      json={"choices": [{"message": {"content": (
                    '{"version":"1","tasks":[{"action":"overview","query":"最近做了什么",'
                    '"window":{"relative_days":14}}]}')}}]})
        monkeypatch.setattr("app.assistant_plan.httpx.Client", Provider)

        response = client.post("/internal/v1/assistant/execute",
                               headers={"X-Internal-Token": "test-internal"}, json={
                                   "source_user_id": "lc-user-a", "query": "最近做了什么",
                                   "conversation_id": "c1", "source_message_id": "u1",
                                   "recent_messages": []})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "executed"
        assert payload["results"][0]["action"] == "overview"
        assert payload["results"][0]["status"] == "matched"
        assert len(payload["results"][0]["items"]) == 2


def test_execute_preserves_matched_profile_evidence_without_unrelated_background(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        enable_planner(app)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})

        class Provider:
            def __init__(self, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def post(self, *_args, **_kwargs):
                return httpx.Response(200, request=httpx.Request("POST", "https://synthetic.invalid"),
                                      json={"choices": [{"message": {"content": (
                                          '{"version":"1","tasks":[{"action":"search_memory",'
                                          '"query":"日常饮品偏好"}]}')}}]})
        monkeypatch.setattr("app.assistant_plan.httpx.Client", Provider)
        # A semantic hit can live only in profile, with no event items.
        profiles = [
            {"memory_id": "tea", "kind": "stable_fact", "canonical_text": "喜欢喝龙井茶",
             "valid_from": "2025-08-10T09:00:00+08:00"},
            {"memory_id": "residence", "kind": "stable_fact", "canonical_text": "住在北京",
             "valid_from": "2025-09-01T09:00:00+08:00"},
        ]
        monkeypatch.setattr(app.state.memory.retriever, "retrieve", lambda *_args, **_kwargs: {
            "status": "matched", "items": [], "profile": profiles,
            "retrieval": {"mode": "semantic_only", "profile_match_ids": ["tea"],
                          "keyword_retrieval": False},
        })
        response = client.post("/internal/v1/assistant/execute",
                               headers={"X-Internal-Token": "test-internal"}, json={
                                   "source_user_id": "lc-user-a", "query": "我平常喝什么饮料",
                                   "conversation_id": "c1", "source_message_id": "u1"})
        assert response.status_code == 200
        task = response.json()["results"][0]
        assert task["status"] == "matched"
        assert task["items"] == [{"memory_id": "tea", "kind": "stable_fact",
                                  "text": "喜欢喝龙井茶", "url": "/knowledge/tea",
                                  "valid_from": "2025-08-10T09:00:00+08:00"}]
        assert task["retrieval"]["keyword_retrieval"] is False


def test_execute_reports_business_status_without_forging_success(monkeypatch, tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        enable_planner(app)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})

        class Provider:
            def __init__(self, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def post(self, *_args, **_kwargs):
                return httpx.Response(200, request=httpx.Request("POST", "https://synthetic.invalid"),
                                      json={"choices": [{"message": {"content": (
                    '{"version":"1","tasks":['
                    '{"action":"query_reminders"},'
                    '{"action":"prepare_reminder","reminder":{"title":"买花"}},'
                    '{"action":"web_search","query":"今天天气"},'
                    '{"action":"clarify","clarification":"请告诉具体时间"}'
                    ']}')}}]})
        monkeypatch.setattr("app.assistant_plan.httpx.Client", Provider)

        response = client.post("/internal/v1/assistant/execute",
                               headers={"X-Internal-Token": "test-internal"}, json={
                                   "source_user_id": "lc-user-a", "query": "提醒和天气",
                                   "conversation_id": "c1", "source_message_id": "u1",
                                   "recent_messages": []})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "executed"
        by_action = {r["action"]: r for r in payload["results"]}
        assert by_action["query_reminders"]["status"] == "ready"
        assert by_action["prepare_reminder"]["status"] == "needs_draft"
        assert by_action["prepare_reminder"]["fields"]["title"] == "买花"
        assert by_action["web_search"]["status"] == "unavailable"
        assert by_action["clarify"]["status"] == "clarify"
        assert by_action["clarify"]["clarification"] == "请告诉具体时间"
        # Business execution never forges a successful write or search.
        assert all(r.get("status") not in ("succeeded", "searched") for r in payload["results"])
