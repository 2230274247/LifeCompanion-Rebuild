"""Read-only tool execution boundaries; fixtures never count as provider acceptance."""
from test_api import bootstrap, make_app
from test_memory_pipeline import auth
from dataclasses import replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app.tools import ToolExecution, ToolRequest


def test_tool_catalog_is_authenticated_and_has_parameter_schemas(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        assert client.get("/api/v1/tools").status_code == 401
        response = client.get("/api/v1/tools",headers=auth())
        assert response.status_code == 200
        tools = response.json()["tools"]
        assert {tool["name"] for tool in tools} >= {"weather","route","search"}
        assert all(tool["read_only"] and tool["parameters"]["type"] == "object" for tool in tools)


def test_default_tool_budget_never_calls_a_provider(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        response = client.post("/api/v1/tools/execute",headers=auth(),json={
            "name":"weather","idempotency_key":"default-weather-request",
            "parameters":{"latitude":31.2304,"longitude":121.4737,"place_label":"Public test landmark"}})
        assert response.status_code == 200
        assert response.json()["status"] == "blocked"
        assert response.json()["network_requests"] == 0


def weather_request(key="same-weather-request"):
    return ToolRequest(name="weather",idempotency_key=key,parameters={
        "latitude":31.2304,"longitude":121.4737,"place_label":"Public landmark"})


def weather_response():
    return httpx.Response(200,json={"current":{"time":datetime.now(timezone.utc).isoformat(),
        "temperature_2m":20.,"precipitation":0.},"current_units":{
            "temperature_2m":"C","precipitation":"mm"}})


def test_atomic_tool_cap_and_same_request_replay_survive_restart(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        settings = replace(app.state.settings,tool_request_budget=1,tool_weather_provider="open_meteo")
        requests = []
        def respond(request):
            requests.append(request)
            return weather_response()
        tools = ToolExecution(app.state.store,settings,transport=httpx.MockTransport(respond))
        def execute(key):
            return tools.execute(owner,weather_request(key))
        keys = ["weather-first","weather-second"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute,keys))
        assert sorted(row["status"] for row in results) == ["blocked","succeeded"]
        key = next(key for key,row in zip(keys,results) if row["status"] == "succeeded")
        restarted = ToolExecution(app.state.store,settings,transport=httpx.MockTransport(respond))
        assert restarted.execute(owner,weather_request(key))["status"] == "succeeded"
        assert restarted.execute(owner,weather_request("new-weather-after-restart"))["status"] == "blocked"
        assert len(requests) == 1


def test_idempotency_conflict_does_not_consume_another_request(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        app.state.tools.execute(owner,weather_request())
        changed = weather_request()
        changed.parameters["latitude"] = 30.
        with pytest.raises(ValueError,match="TOOL_IDEMPOTENCY_CONFLICT"):
            app.state.tools.execute(owner,changed)


def test_foreign_tool_read_and_delete_are_denied(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        bootstrap(client,"lc-user-b","users/b")
        response = client.post("/api/v1/tools/execute",headers=auth(),json=weather_request().model_dump())
        identifier = response.json()["execution_id"]
        assert client.get(f"/api/v1/tool-executions/{identifier}",headers=auth("lc-user-b")).status_code == 404
        assert client.delete(f"/api/v1/tool-executions/{identifier}",headers=auth("lc-user-b")).status_code == 404


def test_route_missing_origin_asks_one_field_without_any_provider_call(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        response = client.post("/api/v1/tools/execute",headers=auth(),json={
            "name":"route","idempotency_key":"missing-origin-request",
            "parameters":{"destination":{"latitude":31.2,"longitude":121.4}}})
        assert response.json()["status"] == "needs_input"
        assert response.json()["result"] == {"missing_field":"origin"}
        assert response.json()["network_requests"] == 0


@pytest.mark.parametrize("parameters",[
    {"latitude":91,"longitude":121,"place_label":"invalid"},
    {"latitude":31,"longitude":121,"place_label":"invalid","url":"http://127.0.0.1:1234"},
    {"latitude":31,"longitude":121,"place_label":"invalid","timezone":"Invalid/Zone"},
])
def test_invalid_or_unrecognized_parameters_never_dispatch(tmp_path,parameters):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        response = client.post("/api/v1/tools/execute",headers=auth(),json={
            "name":"weather","idempotency_key":"invalid-parameters-request","parameters":parameters})
        assert response.status_code == 422
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM tool_executions").fetchone()[0] == 0


@pytest.mark.parametrize("kind",["timeout","rate_limit","oversize","malformed"])
def test_tool_failure_is_sanitized_and_same_request_never_repeats(tmp_path,kind):
    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        settings = replace(app.state.settings,tool_request_budget=2,tool_weather_provider="open_meteo")
        requests = []
        def respond(request):
            requests.append(request)
            if kind == "timeout":
                raise httpx.ReadTimeout("PRIVATE_SENTINEL")
            if kind == "rate_limit":
                return httpx.Response(429,text="PRIVATE_SENTINEL")
            return httpx.Response(200,content=b"x"*262145 if kind == "oversize" else b"PRIVATE_SENTINEL")
        tools = ToolExecution(app.state.store,settings,transport=httpx.MockTransport(respond))
        first = tools.execute(owner,weather_request())
        assert first["status"] == ("unknown" if kind == "timeout" else "failed")
        assert "PRIVATE_SENTINEL" not in str(first)
        assert tools.execute(owner,weather_request()) == first
        assert len(requests) == 1


@pytest.mark.parametrize("action",["delete","expire"])
def test_inflight_tool_response_cannot_restore_deleted_or_expired_data(tmp_path,action):
    app, client = make_app(tmp_path)
    with client:
        owner = bootstrap(client)["life_user_id"]
        settings = replace(app.state.settings,tool_request_budget=1,tool_weather_provider="open_meteo")
        def respond(request):
            identifier = tools.list(owner)[0]["execution_id"]
            if action == "delete":
                tools.delete(owner,identifier)
            else:
                with app.state.store.connect() as db:
                    db.execute("UPDATE tool_executions SET expires_at='2000-01-01T00:00:00+00:00'")
                tools.cleanup()
            return weather_response()
        tools = ToolExecution(app.state.store,settings,transport=httpx.MockTransport(respond))
        first = tools.execute(owner,weather_request())
        assert first["status"] == ("deleted" if action == "delete" else "expired")
        assert first["result"] == {}
        assert tools.execute(owner,weather_request())["result"] == {}
        with app.state.store.connect() as db:
            assert db.execute("SELECT sum(network_requests) FROM tool_executions").fetchone()[0] == 1
