"""Privacy and paid-request safety; sentinel bytes are not generated-image evidence."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.image_provider import ImageProviderError
from app.moments import MomentSettings
from test_api import make_app
from test_memory_pipeline import auth
from test_v023_moments import FakeImageProvider, prepare, save


def seeded(app, client, monkeypatch, *, status="generated"):
    owner, start = prepare(app, client, monkeypatch)
    save(client, "【模拟聊天】今天第一次在公园散步，看见银杏，特别开心。",
         "privacy-source", start + timedelta(minutes=1))
    with app.state.store.connect() as db:
        memory_id = db.execute("SELECT memory_id FROM memory_items WHERE user_id=?", (owner,)).fetchone()[0]
        db.execute("""INSERT INTO moments
            (moment_id,user_id,window_start,window_end,timezone,slot,status,source_memory_ids,
             selection,caption,image,mime,attempts,error_code,created_at,updated_at)
            VALUES ('privacy-moment',?,?,?,?,0,?,?,?,?,?,?,1,?,?,?)""",
            (owner, start.isoformat(), (start + timedelta(hours=1)).isoformat(),
             "Asia/Hong_Kong", status, json.dumps([memory_id]), '[{"private":"sentinel"}]',
             "private-caption-sentinel", b"SYNTHETIC_NON_IMAGE_SENTINEL", "application/octet-stream",
             "PROVIDER_RESULT_UNKNOWN" if status == "unknown" else None,
             start.isoformat(), start.isoformat()))
    return owner, memory_id


@pytest.mark.parametrize("permission", ["image_consent", "memory_consent"])
def test_consent_revocation_synchronously_scrubs_all_derived_content(tmp_path, monkeypatch, permission):
    app, client = make_app(tmp_path)
    with client:
        owner, _ = seeded(app, client, monkeypatch)
        response = client.patch("/api/v1/me/settings", headers=auth(), json={permission: False})
        assert response.status_code == 200
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM moments WHERE user_id=?", (owner,)).fetchone()
        assert row["status"] == "cancelled"
        assert row["image"] is None and row["caption"] == "" and row["selection"] == "[]"
        assert row["mime"] is None


def test_sensitive_memory_permission_does_not_authorize_automatic_image_reuse(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, memory_id = seeded(app, client, monkeypatch)
        app.state.memory.set_permissions(owner, {"sensitive_consent": True})
        with app.state.store.connect() as db:
            db.execute("UPDATE memory_items SET sensitivity='sensitive' WHERE memory_id=?", (memory_id,))
        assert not app.state.moments.authorized(owner, [memory_id])
        detail = client.get("/api/v1/moments/privacy-moment", headers=auth()).json()["moment"]
        assert detail["status"] == "cancelled"
        assert detail["image_data"] is None and not detail["caption"] and not detail["selection"]


def test_unknown_provider_result_cannot_be_resubmitted_by_retry(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        seeded(app, client, monkeypatch, status="unknown")
        response = client.post("/api/v1/moments/privacy-moment/retry", headers=auth())
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "IMAGE_RESULT_RECONCILIATION_REQUIRED"
        with app.state.store.connect() as db:
            row = db.execute("SELECT status,attempts FROM moments").fetchone()
        assert tuple(row) == ("unknown", 1)


def test_provider_server_error_is_unknown_and_cannot_charge_again(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, _ = seeded(app, client, monkeypatch, status="queued")
        moments = app.state.moments
        moments.provider = FakeImageProvider(
            error=ImageProviderError(
                "IMAGE_HTTP_ERROR", stage="provider_response", status_code=502
            )
        )
        assert moments.run_one()
        assert moments.detail(owner, "privacy-moment")["status"] == "unknown"
        assert client.post("/api/v1/moments/privacy-moment/retry", headers=auth()).status_code == 409


def test_read_rechecks_source_even_when_invalidation_hook_was_not_called(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, memory_id = seeded(app, client, monkeypatch)
        app.state.memory.invalidate(owner, memory_id)
        rows = client.get("/api/v1/moments", headers=auth()).json()["moments"]
        assert rows[0]["status"] == "cancelled" and rows[0]["caption"] == ""
        assert app.state.moments.detail(owner, "privacy-moment")["image_data"] is None


def test_disabling_automation_keeps_authorized_history_until_consent_is_revoked(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, _ = seeded(app, client, monkeypatch)
        app.state.moments.configure(app.state.store.get_user(owner), MomentSettings(enabled=False))
        detail = app.state.moments.detail(owner, "privacy-moment")
        assert detail["status"] == "generated" and detail["caption"] == "private-caption-sentinel"
        assert not app.state.moments.authorized(owner, detail["source_memory_ids"])
        client.patch("/api/v1/me/settings", headers=auth(), json={"image_consent": False})
        assert app.state.moments.detail(owner, "privacy-moment")["caption"] == ""


def test_legacy_cancelled_row_cannot_expose_payload_left_by_old_code(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, _ = seeded(app, client, monkeypatch, status="cancelled")
        app.state.store.update_consent(owner, image_consent=False)
        rows = client.get("/api/v1/moments", headers=auth()).json()["moments"]
        assert rows[0]["caption"] == ""
        detail = app.state.moments.detail(owner, "privacy-moment")
        assert detail["image_data"] is None and detail["selection"] == []


def test_revocation_does_not_publish_empty_skipped_windows(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        owner, _ = prepare(app, client, monkeypatch)
        app.state.moments.schedule(datetime.now(timezone.utc) + timedelta(days=1))
        assert app.state.moments.list(owner) == []
        client.patch("/api/v1/me/settings", headers=auth(), json={"image_consent": False})
        assert app.state.moments.list(owner) == []
