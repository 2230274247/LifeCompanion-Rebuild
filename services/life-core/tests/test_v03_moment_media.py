from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image

from app.image_provider import ImageProviderError, validate_image_bytes
from app.recollection_policy import CONSENT_VERSION
from test_api import bootstrap, make_app
from test_memory_pipeline import auth
from test_v03_windows import instant, seed


MOMENT_ID = "mom_0123456789abcdef01234567"


def encoded_image(image_format: str, size=(960, 1280)) -> bytes:
    image = Image.new("RGB", size, (42, 74, 58))
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = ((x * 3 + y) % 256, (x + y * 2) % 256, (x * y) % 256)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_purpose_consents_are_independent_and_round_trip(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        initial = client.get("/api/v1/me", headers=auth()).json()
        assert initial["egress_consents"] == {
            "consent_version": CONSENT_VERSION,
            "semantic_scoring": {"provider": "deepseek", "granted": False},
            "prompt_generation": {"provider": "deepseek", "granted": False},
            "image_generation": {"provider": "kolors", "granted": False},
        }

        wrong = client.put(
            "/api/v1/moment-egress-consents/semantic_scoring",
            headers=auth(),
            json={
                "provider": "kolors",
                "granted": True,
                "consent_version": CONSENT_VERSION,
            },
        )
        assert wrong.status_code == 422
        for purpose, provider in (
            ("semantic_scoring", "deepseek"),
            ("prompt_generation", "deepseek"),
            ("image_generation", "kolors"),
        ):
            response = client.put(
                f"/api/v1/moment-egress-consents/{purpose}",
                headers=auth(),
                json={
                    "provider": provider,
                    "granted": True,
                    "consent_version": CONSENT_VERSION,
                },
            )
            assert response.status_code == 200

        current = client.get("/api/v1/me", headers=auth()).json()["egress_consents"]
        assert current["semantic_scoring"]["granted"] is True
        assert current["prompt_generation"]["granted"] is True
        assert current["image_generation"]["granted"] is True


def prepared_app(tmp_path):
    app, client = make_app(tmp_path)
    client.__enter__()
    user = bootstrap(client)
    client.patch("/api/v1/me/settings", headers=auth(), json={"image_consent": True})
    owner = user["life_user_id"]
    memory = app.state.memory
    item = seed(
        memory,
        app.state.store,
        app.state.store.get_user(owner),
        "今天在厨房给薄荷浇水，阳光落在白瓷杯和吐司上。",
        "b1-media-source",
        instant("2026-11-04T09:00:00+08:00"),
    )
    with app.state.store.connect() as db:
        db.execute(
            """INSERT INTO moments
            (moment_id,user_id,window_start,window_end,timezone,slot,status,
             source_memory_ids,selection,caption,attempts,created_at,updated_at,
             review_json)
            VALUES (?,?,?,?,?,0,'generated',?,?,?,0,?,?,'{}')""",
            (
                MOMENT_ID,
                owner,
                "2026-11-04T00:00:00+00:00",
                "2026-11-04T03:00:00+00:00",
                "Asia/Hong_Kong",
                json.dumps([item["memory_id"]]),
                json.dumps(
                    [
                        {
                            "memory_id": item["memory_id"],
                            "outcome": "SELECTED",
                            "policy": {
                                "storage_status": "PRIVATE_TEXT",
                                "imageability": "SAFE_SCENE",
                                "image_dispatch_allowed": True,
                            },
                        }
                    ]
                ),
                "清晨在厨房给薄荷浇水，为自己留下一杯热茶。",
                "2026-11-04T03:00:00+00:00",
                "2026-11-04T03:00:00+00:00",
            ),
        )
    return app, client, owner, MOMENT_ID, item["memory_id"]


def test_png_jpeg_webp_require_matching_declared_mime():
    for image_format, mime in (
        ("PNG", "image/png"),
        ("JPEG", "image/jpeg"),
        ("WEBP", "image/webp"),
    ):
        result = validate_image_bytes(encoded_image(image_format), mime)
        assert result.image_format == image_format
        assert result.mime == mime
        assert result.mime_policy == "STRICT_MATCH"


def test_fake_mismatched_and_truncated_images_are_rejected():
    png = encoded_image("PNG")
    cases = (
        (png, "image/jpeg", "IMAGE_MIME_FORMAT_MISMATCH"),
        (png, None, "IMAGE_MIME_FORMAT_MISMATCH"),
        (b"\x89PNG\r\n\x1a\nnot-an-image", "image/png", "IMAGE_DECODE_FAILED"),
        (png[: len(png) // 2], "image/png", "IMAGE_DECODE_FAILED"),
    )
    for data, declared, code in cases:
        with pytest.raises(ImageProviderError) as caught:
            validate_image_bytes(data, declared)
        assert caught.value.code == code


def test_owner_reads_original_and_thumbnail_and_cross_user_gets_404(tmp_path):
    app, client, owner, moment_id, _ = prepared_app(tmp_path)
    try:
        original = encoded_image("PNG")
        app.state.moments.media_store.store(
            owner,
            moment_id,
            original,
            declared_mime="image/png",
            provider="SiliconFlow",
            model="Kwai-Kolors/Kolors",
            trace_id="trace-b1-media",
            prompt_summary="厨房薄荷与白瓷杯",
            policy_status="PRIVATE_TEXT",
        )
        image = client.get(
            f"/api/v1/moments/{moment_id}/image", headers=auth()
        )
        thumbnail = client.get(
            f"/api/v1/moments/{moment_id}/thumbnail", headers=auth()
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["cache-control"] == "private, no-store"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert image.content == original
        assert thumbnail.status_code == 200
        assert thumbnail.headers["content-type"] == "image/jpeg"
        with Image.open(BytesIO(thumbnail.content)) as thumb:
            assert thumb.format == "JPEG"
            assert thumb.width <= 640 and thumb.height <= 960

        bootstrap(client, "lc-user-b", "users/b")
        assert client.get(
            f"/api/v1/moments/{moment_id}/image", headers=auth("lc-user-b")
        ).status_code == 404
        detail = client.get(
            f"/api/v1/moments/{moment_id}", headers=auth()
        ).json()["moment"]
        assert detail["display_kind"] == "IMAGE"
        assert detail["media"]["sha256"] == __import__("hashlib").sha256(original).hexdigest()
        assert "storage_key" not in detail["media"]
    finally:
        client.__exit__(None, None, None)


def test_delete_and_consent_revocation_remove_database_and_files(tmp_path):
    app, client, owner, moment_id, _ = prepared_app(tmp_path)
    try:
        app.state.moments.media_store.store(
            owner,
            moment_id,
            encoded_image("WEBP"),
            declared_mime="image/webp",
            provider="SiliconFlow",
            model="Kwai-Kolors/Kolors",
            trace_id="trace-delete",
            prompt_summary="删除测试",
            policy_status="PRIVATE_TEXT",
        )
        with app.state.store.connect() as db:
            row = db.execute(
                "SELECT storage_key,thumbnail_key FROM moment_media WHERE moment_id=?",
                (moment_id,),
            ).fetchone()
        paths = [
            app.state.moments.media_store._path(row["storage_key"]),
            app.state.moments.media_store._path(row["thumbnail_key"]),
        ]
        assert all(path.is_file() for path in paths)
        assert client.delete(
            f"/api/v1/moments/{moment_id}", headers=auth()
        ).status_code == 200
        assert all(not path.exists() for path in paths)
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM moment_media").fetchone()[0] == 0
        assert client.get(
            f"/api/v1/moments/{moment_id}/image", headers=auth()
        ).status_code == 404

        with app.state.store.connect() as db:
            db.execute(
                """UPDATE moments SET status='generated',caption='撤销测试',selection='[]'
                WHERE moment_id=?""",
                (moment_id,),
            )
        app.state.moments.media_store.store(
            owner,
            moment_id,
            encoded_image("JPEG"),
            declared_mime="image/jpeg",
            provider="SiliconFlow",
            model="Kwai-Kolors/Kolors",
            trace_id="trace-revoke",
            prompt_summary="撤权测试",
            policy_status="PRIVATE_TEXT",
        )
        with app.state.store.connect() as db:
            row = db.execute(
                "SELECT storage_key,thumbnail_key FROM moment_media WHERE moment_id=?",
                (moment_id,),
            ).fetchone()
        paths = [
            app.state.moments.media_store._path(row["storage_key"]),
            app.state.moments.media_store._path(row["thumbnail_key"]),
        ]
        response = client.patch(
            "/api/v1/me/settings",
            headers=auth(),
            json={"image_consent": False},
        )
        assert response.status_code == 200
        assert all(not path.exists() for path in paths)
        with app.state.store.connect() as db:
            assert db.execute("SELECT count(*) FROM moment_media").fetchone()[0] == 0
        assert client.get(
            f"/api/v1/moments/{moment_id}/image", headers=auth()
        ).status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_skip_and_private_skip_are_not_displayable_but_private_text_is(tmp_path):
    app, client, owner, _, source_id = prepared_app(tmp_path)
    try:
        for index, (suffix, status, policy, caption) in enumerate((
            ("a", "private_text", {"storage_status": "PRIVATE_TEXT", "imageability": "TEXT_ONLY"}, "可展示文字"),
            ("b", "private_text", {"storage_status": "PRIVATE_TEXT", "imageability": "PRIVATE_SKIP"}, "不可展示"),
            ("c", "skipped", {"storage_status": "SKIP", "imageability": "NOT_APPLICABLE"}, ""),
        ), 5):
            moment_id = "mom_" + suffix * 24
            with app.state.store.connect() as db:
                db.execute(
                    """INSERT INTO moments
                    (moment_id,user_id,window_start,window_end,timezone,slot,status,
                     source_memory_ids,selection,caption,attempts,created_at,updated_at,
                     review_json)
                    VALUES (?,?,?,?,?,0,?,?,?,?,0,?,?,'{}')""",
                    (
                        moment_id,
                        owner,
                        f"2026-11-{index:02d}T00:00:00+00:00",
                        f"2026-11-{index:02d}T03:00:00+00:00",
                        "Asia/Hong_Kong",
                        status,
                        json.dumps([source_id]),
                        json.dumps(
                            [{"memory_id": source_id, "policy": policy}]
                        ),
                        caption,
                        "2026-11-04T03:00:00+00:00",
                        "2026-11-04T03:00:00+00:00",
                    ),
                )
        rows = client.get("/api/v1/moments", headers=auth()).json()["moments"]
        assert next(row for row in rows if row["moment_id"] == "mom_" + "a" * 24)[
            "display_kind"
        ] == "TEXT"
        assert next(row for row in rows if row["moment_id"] == "mom_" + "b" * 24)[
            "displayable"
        ] is False
        assert all(row["moment_id"] != "mom_" + "c" * 24 for row in rows)
    finally:
        client.__exit__(None, None, None)
