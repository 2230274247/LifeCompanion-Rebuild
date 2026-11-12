from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx
from PIL import Image

from app.moments import MomentSettings, Moments
from test_api import bootstrap, make_app
from test_memory_pipeline import auth


def prepare(app, client, monkeypatch):
    user = bootstrap(client)
    bootstrap(client, "lc-user-b", "users/b")
    monkeypatch.setattr(app.state.memos, "create_private_memo", lambda event: "memos/" + event["event_id"])
    client.patch("/api/v1/me/settings", headers=auth(), json={"image_consent": True})
    moments = app.state.moments
    moments.configure(app.state.store.get_user(user["life_user_id"]), MomentSettings(enabled=True))
    # Explicit frozen clock for unit selection only; live acceptance never alters this.
    beginning = datetime.now(timezone.utc) - timedelta(hours=3)
    with app.state.store.connect() as db:
        db.execute("UPDATE moment_settings SET enabled_at=? WHERE user_id=?", (beginning.isoformat(),user["life_user_id"]))
    return user["life_user_id"], beginning


def save(client, text, source, when):
    result = client.post("/internal/v1/events/ingest",headers={"X-Internal-Token":"test-internal"},
        json={"source_user_id":"lc-user-a","source_message_id":source,"conversation_id":"test-chat",
              "text":text,"occurred_at":when.isoformat()})
    assert result.status_code == 200
    return result.json()


def test_selection_explains_three_candidates_and_rejects_future(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"【模拟聊天】今天在公园散步。","ordinary",start+timedelta(minutes=1))
        save(client,"【模拟聊天】今天和朋友在公园散步，特别放松。","emotion",start+timedelta(minutes=2))
        best = save(client,"【模拟聊天】今天第一次加入了一直想加入的项目组，特别开心！","special",start+timedelta(minutes=3))
        save(client,"明天带绿色 U 盘，不是银色的。","plan",start+timedelta(minutes=4))
        ranked = app.state.moments.select(owner,start,datetime.now(timezone.utc),app.state.moments.config(owner))
        assert len(ranked) == 3
        assert app.state.memory.detail(owner, ranked[0]["memory_id"])["event_id"] == best["event"]["event_id"]
        assert ranked[0]["dimensions"]["uniqueness"] == 1
        assert ranked[0]["score"] > ranked[-1]["score"]
        assert not any("U 盘" in i["text"] for i in ranked)


def test_schedule_dedup_provider_failure_restart_retry_and_owner(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"【模拟聊天】今天在公园散步，看见银杏，特别放松。","event",start+timedelta(minutes=1))
        now = datetime.now(timezone.utc)
        # Force the last configured window to close around the saved source in this unit test.
        app.state.moments.schedule(now+timedelta(days=1))
        rows = app.state.moments.list(owner)
        assert len(rows) == 1 and len(rows[0]["source_memory_ids"]) == 1
        identifier = rows[0]["moment_id"]
        app.state.moments.schedule(now+timedelta(days=1))
        assert len(app.state.moments.list(owner)) == 1
        assert app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "pending_provider"
        app.state.moments.settings = replace(
            app.state.moments.settings,
            memory_llm_provider="zhipu",
            memory_llm_key="synthetic",
            image_provider_api_key="synthetic",
        )
        app.state.moments.retry(owner,identifier)
        monkeypatch.setattr(app.state.moments,"generate",lambda _text: (_ for _ in ()).throw(httpx.ReadTimeout("synthetic")))
        app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "unknown"
        restarted = Moments(app.state.store,app.state.moments.settings,app.state.memory)
        assert not restarted.run_one()
        assert client.get(f"/api/v1/moments/{identifier}",headers=auth("lc-user-b")).status_code == 404
        assert client.post(f"/api/v1/moments/{identifier}/retry",headers=auth("lc-user-b")).status_code == 404
        app.state.moments.retry(owner,identifier)
        monkeypatch.setattr(app.state.moments,"generate",lambda _text: (b"\x89PNG\r\n\x1a\nsynthetic","image/png"))
        app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "published"
        memory_id = rows[0]["source_memory_ids"][0]
        event_id = app.state.memory.detail(owner,memory_id)["event_id"]
        assert app.state.moments.media_for_event(owner,event_id)["ai_generated"] is True
        client.delete(f"/api/v1/knowledge/{memory_id}",headers=auth())
        item = app.state.moments.detail(owner,identifier)
        assert item["status"] == "cancelled" and item["image_data"] is None and item["caption"] == ""


def test_no_consent_no_event_no_invented_moment_and_revoked_inflight(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch("/api/v1/me/settings", headers=auth(), json={"image_consent": False})
        assert client.put("/api/v1/moment-settings",headers=auth(),json={"enabled":True}).status_code == 403
        owner,start = prepare(app,client,monkeypatch)
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        assert app.state.moments.list(owner) == []
        save(client,"【模拟聊天】今天第一次在公园散步，看见银杏，特别开心！","event",start+timedelta(minutes=1))
        # Use a different day after the empty window was already finalized.
        with app.state.store.connect() as db:
            db.execute("DELETE FROM moments WHERE user_id=? AND status='skipped'",(owner,))
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        app.state.moments.settings = replace(
            app.state.moments.settings,
            memory_llm_provider="zhipu",
            memory_llm_key="synthetic",
            image_provider_api_key="synthetic",
        )
        def revoke_during_provider(_caption):
            app.state.store.update_consent(owner,image_consent=False)
            return b"\x89PNG\r\n\x1a\nsynthetic","image/png"
        monkeypatch.setattr(app.state.moments,"generate",revoke_during_provider)
        app.state.moments.run_one()
        item = app.state.moments.list(owner)[0]
        assert item["status"] == "cancelled"
        assert app.state.moments.detail(owner,item["moment_id"])["image_data"] is None


def test_generated_image_publishes_silently_and_memos_failure_is_recoverable(
    tmp_path, monkeypatch
):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app, client, monkeypatch)
        save(
            client,
            "【模拟聊天】今天在公园散步，看见银杏，特别放松。",
            "publish",
            start + timedelta(minutes=1),
        )
        output = BytesIO()
        Image.new("RGB", (128, 96), (49, 90, 72)).save(output, format="PNG")
        app.state.moments.settings = replace(
            app.state.moments.settings, image_provider_api_key="synthetic"
        )
        monkeypatch.setattr(
            app.state.moments,
            "generate",
            lambda _caption: (output.getvalue(), "image/png"),
        )
        original_publish = app.state.moments.publish_event
        app.state.moments.publish_event = lambda _event: (_ for _ in ()).throw(
            RuntimeError("synthetic memos outage")
        )
        app.state.moments.schedule(datetime.now(timezone.utc) + timedelta(days=1))
        assert app.state.moments.run_one()
        items = app.state.moments.list(owner)
        assert len(items) == 1
        item = app.state.moments.detail(owner, items[0]["moment_id"])
        assert item["status"] == "generated"
        assert item["error_code"] == "MEMOS_PUBLISH_FAILED"
        assert item["image_data"].startswith("data:image/png;base64,")
        assert item["image_width"] == 128 and item["image_height"] == 96

        app.state.moments.publish_event = original_publish
        assert app.state.moments.publish_generated_one()
        published = app.state.moments.detail(owner, items[0]["moment_id"])
        assert published["status"] == "published"
        assert published["error_code"] is None

        event = app.state.moments.memory_source_event(owner, items[0]["moment_id"])
        assert event["status"] == "published"
        media = app.state.moments.media_for_event(owner, event["event_id"], include_image=True)
        assert media["width"] == 128 and media["height"] == 96
        assert media["thumbnail_data"].startswith("data:image/jpeg;base64,")
        assert not app.state.moments.publish_generated_one()
