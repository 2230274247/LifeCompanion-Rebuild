from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx
import json
import pytest
from PIL import Image

from app.image_provider import ImageProviderError, validate_image_bytes
from app.moments import MomentSettings, Moments
from app.recollection_scoring import WEIGHTS
from test_api import bootstrap, make_app
from test_memory_pipeline import auth


class FakeImageProvider:
    def __init__(self, *, error=None, callback=None):
        self.error = error
        self.callback = callback

    def generate(self, request, trace_id):
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        image = Image.new("RGB", (64, 64), (40, 80, 60))
        pixels = image.load()
        for y in range(64):
            for x in range(64):
                pixels[x, y] = ((x * 3 + y) % 256, (x + y * 2) % 256, (x * y) % 256)
        output = BytesIO()
        image.save(output, format="PNG")
        validated = validate_image_bytes(output.getvalue(), "image/png")
        return replace(validated, trace_id=trace_id)


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


def structured_scoring_fixture(app, monkeypatch):
    """Synthetic external responses exercise persistence; never cloud evidence."""
    moments = app.state.moments
    moments.settings = replace(moments.settings, moment_scoring_request_budget=10, memory_llm_key="synthetic")
    def respond(request):
        body = json.loads(request.content)
        candidates = json.loads(body["messages"][1]["content"])["candidates"]
        output = []
        for candidate in candidates:
            rating = {"special": .95, "emotion": .7, "ordinary": .4}.get(candidate["sources"][0]["message_id"], .95)
            dimensions = {key: rating for key in WEIGHTS}
            dimensions.update(privacy_suitability=1., source_sufficiency=1., window_relevance=1.,
                              event_clarity=1., uniqueness=1. if rating == .95 else rating)
            output.append({"memory_id":candidate["memory_id"],"eligible":True,
                "dimensions":dimensions,"reason_code":"MEANINGFUL_EVENT",
                "source_message_ids":[candidate["sources"][0]["message_id"]],
                "evidence_quote":candidate["sources"][0]["quote"]})
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{
            "content":json.dumps({"candidates":output})}}],"usage":{"prompt_tokens":100,"completion_tokens":100}})
    monkeypatch.setattr(moments.scorer,"transport",httpx.MockTransport(respond))
    return moments


def score_pending(moments):
    while moments.score_one():
        pass


def test_selection_explains_three_candidates_and_rejects_future(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"【模拟聊天】今天在公园散步。","ordinary",start+timedelta(minutes=1))
        save(client,"【模拟聊天】今天和朋友在公园散步，特别放松。","emotion",start+timedelta(minutes=2))
        best = save(client,"【模拟聊天】今天第一次加入了一直想加入的项目组，特别开心！","special",start+timedelta(minutes=3))
        save(client,"明天带绿色 U 盘，不是银色的。","plan",start+timedelta(minutes=4))
        moments = structured_scoring_fixture(app,monkeypatch)
        inputs, rejected = moments.candidate_inputs(owner,start,datetime.now(timezone.utc))
        assert not rejected
        moments.scorer.settings = moments.settings
        ranked = moments.scorer.evaluate(owner,"synthetic-selection",{},inputs,moments.config(owner)["weights"])
        assert len(ranked) == 3
        assert app.state.memory.detail(owner, ranked[0]["memory_id"])["event_id"] == best["event"]["event_id"]
        assert ranked[0]["dimensions"]["uniqueness"] == 1
        assert ranked[0]["score"] > ranked[-1]["score"]
        assert not any("U 盘" in i["text"] for i in inputs)


def test_schedule_dedup_provider_failure_restart_retry_and_owner(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"【模拟聊天】今天在公园散步，看见银杏，特别放松。","event",start+timedelta(minutes=1))
        now = datetime.now(timezone.utc)
        # Force the last configured window to close around the saved source in this unit test.
        app.state.moments.schedule(now+timedelta(days=1))
        score_pending(structured_scoring_fixture(app,monkeypatch))
        rows = app.state.moments.list(owner)
        assert len(rows) == 1 and len(rows[0]["source_memory_ids"]) == 1
        identifier = rows[0]["moment_id"]
        app.state.moments.schedule(now+timedelta(days=1))
        assert len(app.state.moments.list(owner)) == 1
        assert app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "pending_provider"
        app.state.moments.retry(owner,identifier)
        app.state.moments.provider = FakeImageProvider(
            error=ImageProviderError(
                "IMAGE_REQUEST_TIMEOUT_UNKNOWN", stage="provider_request"
            )
        )
        app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "unknown"
        restarted = Moments(app.state.store,app.state.moments.settings,app.state.memory)
        assert not restarted.run_one()
        assert client.get(f"/api/v1/moments/{identifier}",headers=auth("lc-user-b")).status_code == 404
        assert client.post(f"/api/v1/moments/{identifier}/retry",headers=auth("lc-user-b")).status_code == 404
        with pytest.raises(ValueError, match="IMAGE_RESULT_RECONCILIATION_REQUIRED"):
            app.state.moments.retry(owner,identifier)
        assert app.state.moments.detail(owner,identifier)["status"] == "unknown"


def test_known_rejection_can_retry_and_withdrawal_clears_generated_unit_fixture(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, start = prepare(app,client,monkeypatch)
        save(client,"【模拟聊天】今天在公园散步，看见银杏，特别放松。","event",start+timedelta(minutes=1))
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        score_pending(structured_scoring_fixture(app,monkeypatch))
        rows = app.state.moments.list(owner)
        identifier = rows[0]["moment_id"]
        app.state.moments.provider = FakeImageProvider(
            error=ImageProviderError(
                "IMAGE_HTTP_ERROR", stage="provider_response", status_code=429
            )
        )
        assert app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "failed"
        app.state.moments.retry(owner,identifier)
        app.state.moments.provider = FakeImageProvider()
        app.state.moments.run_one()
        assert app.state.moments.detail(owner,identifier)["status"] == "generated"
        memory_id = rows[0]["source_memory_ids"][0]
        client.delete(f"/api/v1/knowledge/{memory_id}",headers=auth())
        item = app.state.moments.detail(owner,identifier)
        assert item["status"] == "cancelled" and item["image_data"] is None and item["caption"] == ""


def test_no_consent_no_event_no_invented_moment_and_revoked_inflight(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        assert client.put("/api/v1/moment-settings",headers=auth(),json={"enabled":True}).status_code == 403
        owner,start = prepare(app,client,monkeypatch)
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        score_pending(structured_scoring_fixture(app,monkeypatch))
        assert app.state.moments.list(owner) == []
        save(client,"【模拟聊天】今天第一次在公园散步，看见银杏，特别开心！","event",start+timedelta(minutes=1))
        # Use a different day after the empty window was already finalized.
        with app.state.store.connect() as db:
            db.execute("DELETE FROM moments WHERE user_id=? AND status='skipped'",(owner,))
        app.state.moments.schedule(datetime.now(timezone.utc)+timedelta(days=1))
        score_pending(app.state.moments)
        app.state.moments.provider = FakeImageProvider(
            callback=lambda: app.state.store.update_consent(
                owner, image_consent=False
            )
        )
        app.state.moments.run_one()
        item = app.state.moments.list(owner)[0]
        assert item["status"] == "cancelled"
        detail = app.state.moments.detail(owner,item["moment_id"])
        assert detail["image_data"] is None and not detail["caption"] and not detail["selection"]
