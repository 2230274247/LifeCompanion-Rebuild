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
