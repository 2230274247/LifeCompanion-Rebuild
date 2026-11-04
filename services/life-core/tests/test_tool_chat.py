"""Chat state tests use external HTTP fixtures, never provider acceptance."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx

from test_api import bootstrap, make_app
from test_memory_pipeline import auth
from test_tools import weather_response
from app.tool_chat import ToolChoice


def configured(app):
    app.state.tools.settings = replace(app.state.settings, tool_request_budget=2,
                                      tool_weather_provider="open_meteo")
    calls = []

    def respond(request):
        calls.append(request)
        if "geocoding-api" in request.url.host:
            return httpx.Response(200, json={"results": [
                {"name": "Shanghai", "country": "China", "admin1": "Shanghai",
                 "latitude": 31.23, "longitude": 121.47},
                {"name": "Shanghai", "country": "Other", "admin1": "Other",
                 "latitude": 30., "longitude": 120.},
            ]})
        return weather_response()

    app.state.tools.transport = httpx.MockTransport(respond)
    return calls


def chat(client, text="上海天气怎么样？", message="weather-source"):
    return client.post("/internal/v1/tools/chat", headers={"X-Internal-Token": "test-internal"},
                       json={"source_user_id": "lc-user-a", "source_message_id": message,
                             "conversation_id": "weather-chat", "text": text})


def test_explicit_weather_waits_for_stored_place_choice_and_replays(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = configured(app)
        response = chat(client)
        assert response.status_code == 200
        item = response.json()
        assert item["status"] == "choose_place"
        assert len(item["places"]) == 2 and len(calls) == 1
        assert chat(client).json() == item
        url = f"/api/v1/tool-chats/{item['interaction_id']}/select"
        choice = {"revision": item["revision"], "place_index": 1}
        selected = client.post(url, headers=auth(), json=choice)
        assert selected.status_code == 200
        assert selected.json()["status"] == "succeeded"
        assert selected.json()["execution"]["result"]["requested_coordinates"]["latitude"] == 30.
        assert len(calls) == 2
        assert client.post(url, headers=auth(), json=choice).json() == selected.json()
        assert len(calls) == 2


def test_missing_place_asks_one_question_and_ordinary_chat_stays_quiet(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = configured(app)
        assert chat(client, "今天天气怎么样？").json()["status"] == "needs_place"
        for i, text in enumerate(("我喜欢晴朗的天气", "他说上海天气怎么样？", "天气系统是什么", "我很担心天气")):
            assert chat(client, text, f"ordinary-{i}").json() == {"handled": False}
        assert calls == []


def test_foreign_stale_invalid_and_cancelled_selection_cannot_call_provider(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        bootstrap(client, "lc-user-b", "users/b")
        calls = configured(app)
        item = chat(client).json()
        url = f"/api/v1/tool-chats/{item['interaction_id']}"
        choice = {"revision": item["revision"], "place_index": 0}
        assert client.post(url+"/select", headers=auth("lc-user-b"), json=choice).status_code == 404
        assert client.post(url+"/select", headers=auth(), json={**choice, "revision": 999}).status_code == 409
        assert client.post(url+"/select", headers=auth(), json={**choice, "place_index": 99}).status_code == 422
        assert client.delete(url, headers=auth("lc-user-b")).status_code == 404
        assert client.delete(url, headers=auth()).status_code == 200
        assert client.post(url+"/select", headers=auth(), json=choice).status_code == 409
        assert len(calls) == 1


def test_polite_prefix_is_not_sent_as_a_location(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = configured(app)
        assert chat(client, "请帮我查一下上海天气怎么样？").json()["status"] == "choose_place"
        assert calls[0].url.params["name"] == "上海"


def test_cancel_clears_both_location_and_weather_receipts(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        configured(app)
        item = chat(client).json()
        url = f"/api/v1/tool-chats/{item['interaction_id']}"
        client.post(url+"/select", headers=auth(), json={"revision": 2, "place_index": 0}).raise_for_status()
        client.delete(url, headers=auth()).raise_for_status()
        rows = client.get("/api/v1/tool-executions", headers=auth()).json()["executions"]
        assert len(rows) == 2
        assert all(row["status"] == "deleted" and row["result"] == {} for row in rows)


def test_place_form_is_revision_guarded_and_result_expiry_is_durable(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = configured(app)
        item = chat(client, "明天天气怎么样？").json()
        url = f"/api/v1/tool-chats/{item['interaction_id']}/select"
        response = client.post(url, headers=auth(), json={"revision": item["revision"], "place_query": "Shanghai"})
        assert response.status_code == 200
        assert response.json()["forecast_date"] is not None
        assert len(calls) == 1
        with app.state.store.connect() as db:
            db.execute("UPDATE tool_chats SET expires_at='2000-01-01T00:00:00+00:00'")
        response = client.get("/api/v1/tool-chats?conversation_id=weather-chat", headers=auth())
        assert response.json() == {"interactions": []}
        assert client.post(url, headers=auth(), json={"revision": 2, "place_index": 0}).status_code == 409
        assert len(calls) == 1
        executions = client.get("/api/v1/tool-executions", headers=auth()).json()["executions"]
        assert all(row["result"] == {} for row in executions)


def test_cancellation_during_weather_http_cannot_restore_any_receipt(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        configured(app)
        item = chat(client).json()
        started, release = Event(), Event()

        def respond(_request):
            started.set()
            assert release.wait(10)
            return weather_response()

        app.state.tools.transport = httpx.MockTransport(respond)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(app.state.tool_chat.select, owner, item["interaction_id"],
                                  ToolChoice(revision=2, place_index=0))
            try:
                assert started.wait(10)
                assert app.state.tool_chat.delete(owner, item["interaction_id"])
            finally:
                release.set()
            assert pending.result()["status"] == "cancelled"
        rows = app.state.tools.list(owner)
        assert len(rows) == 2 and all(row["result"] == {} for row in rows)


def test_budget_failure_is_persisted_and_duplicate_click_never_retries(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = configured(app)
        app.state.tools.settings = replace(app.state.tools.settings, tool_request_budget=1)
        item = chat(client).json()
        url = f"/api/v1/tool-chats/{item['interaction_id']}/select"
        choice = {"revision": 2, "place_index": 0}
        first = client.post(url, headers=auth(), json=choice).json()
        assert first["status"] == "blocked"
        assert first["execution"]["error_code"] == "TOOL_REQUEST_BUDGET"
        assert client.post(url, headers=auth(), json=choice).json() == first
        assert len(calls) == 1
