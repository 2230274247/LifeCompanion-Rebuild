"""Source provenance through the authenticated ingestion and withdrawal APIs."""
from test_api import bootstrap, make_app, token_for


def auth(user="lc-user-a"):
    return {"Authorization": f"Bearer {token_for(user)}"}


def ingest(client, text, message="original"):
    return client.post("/internal/v1/events/ingest", headers={"X-Internal-Token": "test-internal"}, json={
        "source_user_id": "lc-user-a", "source_message_id": message,
        "conversation_id": "source-conversation", "text": text,
        "occurred_at": "2026-11-09T10:00:00+08:00",
    })


def test_original_survives_no_extracted_candidate_and_has_private_detail(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        response = ingest(client, "蕨类植物的叶片很有意思。")
        assert response.status_code == 200
        sources = app.state.memory.sources.items(user["life_user_id"])
        assert len(sources) == 1
        assert sources[0]["canonical_text"] == "蕨类植物的叶片很有意思。"
        source_id = sources[0]["memory_id"]
        assert client.get(f"/api/v1/memory-sources/{source_id}", headers=auth()).status_code == 200
        assert client.get(f"/api/v1/knowledge/{source_id}", headers=auth()).json()["item"]["kind"] == "user_message"
        bootstrap(client, "lc-user-b", "users/b")
        assert client.get(f"/api/v1/memory-sources/{source_id}", headers=auth("lc-user-b")).status_code == 404
        assert "source_coverage" in client.get("/api/v1/memory-status", headers=auth()).json()


def test_same_message_cannot_be_replaced_with_different_original(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        assert ingest(client, "我平常喜欢龙井茶").status_code == 200
        changed = ingest(client, "我平常喜欢红茶")
        assert changed.status_code == 409
        assert changed.json()["detail"]["code"] == "SOURCE_MESSAGE_CONFLICT"
        assert "龙井" in app.state.memory.sources.items(user["life_user_id"])[0]["canonical_text"]


def test_withdraw_original_invalidates_derived_facts_and_blocks_replay(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"recall_consent": True})
        assert ingest(client, "我平常喜欢龙井茶").json()["accepted"]
        source_id = app.state.memory.sources.items(user["life_user_id"])[0]["memory_id"]
        result = client.delete(f"/api/v1/memory-sources/{source_id}", headers=auth())
        assert result.status_code == 200
        assert app.state.memory.list_items(user["life_user_id"]) == []
        assert app.state.memory.sources.items(user["life_user_id"]) == []
        assert not ingest(client, "我平常喜欢龙井茶", "replayed-new-id").json()["accepted"]
        assert app.state.memory.sources.items(user["life_user_id"]) == []


def test_recording_permission_denied_never_archives_original(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"memory_consent": False, "recall_consent": True})
        assert not ingest(client, "我平常喜欢龙井茶").json()["accepted"]
        assert app.state.memory.sources.items(user["life_user_id"]) == []
