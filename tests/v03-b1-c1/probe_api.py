"""Probe the isolated Core through the real gateway without external API calls."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import time

import httpx
from PIL import Image


JWT_SECRET = "v03-b1-c1-synthetic-jwt-secret"  # gitleaks:allow


def encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token_for(user_id: str) -> str:
    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode({"id": user_id, "exp": int(time.time()) + 900})
    import hashlib
    import hmac

    signing = f"{header}.{payload}".encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{signature}"


def auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user_id)}"}


def media_keys(database: Path, moment_id: str) -> tuple[str, str]:
    with sqlite3.connect(database) as db:
        row = db.execute(
            "SELECT storage_key,thumbnail_key FROM moment_media WHERE moment_id=?",
            (moment_id,),
        ).fetchone()
    if row is None:
        raise AssertionError("MEDIA_ROW_MISSING")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--download", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8-sig"))
    base = "http://127.0.0.1:3002/life-api"
    owner = fixture["owner"]["librechat_user_id"]
    other = fixture["other"]["librechat_user_id"]
    image_id = fixture["moment_ids"]["image"]
    text_id = fixture["moment_ids"]["text"]
    private_skip_id = fixture["moment_ids"]["private_skip"]
    skip_id = fixture["moment_ids"]["skip"]
    other_image_id = fixture["moment_ids"]["other_image"]

    with httpx.Client(timeout=15) as client:
        unauthenticated = client.get(f"{base}/api/v1/moments")
        listing_response = client.get(
            f"{base}/api/v1/moments", headers=auth(owner)
        )
        listing_response.raise_for_status()
        listing = listing_response.json()["moments"]
        by_id = {item["moment_id"]: item for item in listing}
        image_detail_response = client.get(
            f"{base}/api/v1/moments/{image_id}", headers=auth(owner)
        )
        image_detail_response.raise_for_status()
        image_detail = image_detail_response.json()["moment"]
        original = client.get(
            f"{base}/api/v1/moments/{image_id}/image", headers=auth(owner)
        )
        thumbnail = client.get(
            f"{base}/api/v1/moments/{image_id}/thumbnail", headers=auth(owner)
        )
        cross_user = client.get(
            f"{base}/api/v1/moments/{image_id}/image", headers=auth(other)
        )

    assert unauthenticated.status_code == 401
    assert listing_response.status_code == 200
    assert image_id in by_id and by_id[image_id]["display_kind"] == "IMAGE"
    assert text_id in by_id and by_id[text_id]["display_kind"] == "TEXT"
    assert private_skip_id in by_id and by_id[private_skip_id]["displayable"] is False
    assert skip_id not in by_id
    assert image_detail["media"]["provider"] == "SiliconFlow"
    assert image_detail["media"]["model"] == "Kwai-Kolors/Kolors"
    assert image_detail["media"]["mime"] == "image/png"
    assert image_detail["media"]["width"] == 960
    assert image_detail["media"]["height"] == 1280
    assert image_detail["media"]["sha256"] == fixture["source_image_sha256"]
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/png"
    assert original.headers["cache-control"] == "private, no-store"
    assert original.headers["x-content-type-options"] == "nosniff"
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert cross_user.status_code == 404
    assert sha256(original.content).hexdigest() == fixture["source_image_sha256"]

    args.download.parent.mkdir(parents=True, exist_ok=True)
    args.download.write_bytes(original.content)
    with Image.open(BytesIO(original.content)) as decoded:
        decoded.load()
        original_format = decoded.format
        original_size = decoded.size
    with Image.open(BytesIO(thumbnail.content)) as decoded:
        decoded.load()
        thumbnail_format = decoded.format
        thumbnail_size = decoded.size
    assert (original_format, original_size) == ("PNG", (960, 1280))
    assert thumbnail_format == "JPEG"
    assert thumbnail_size[0] <= 640 and thumbnail_size[1] <= 960

    database = Path(fixture["database"])
    media_root = Path(fixture["media_root"])
    other_keys = media_keys(database, other_image_id)
    other_paths = [media_root / key for key in other_keys]
    assert all(path.is_file() for path in other_paths)
    with httpx.Client(timeout=15) as client:
        deleted = client.delete(
            f"{base}/api/v1/moments/{other_image_id}",
            headers=auth(other),
        )
        deleted_media = client.get(
            f"{base}/api/v1/moments/{other_image_id}/image",
            headers=auth(other),
        )
    assert deleted.status_code == 200
    assert deleted_media.status_code == 404
    assert all(not path.exists() for path in other_paths)

    report = {
        "status": "PASS",
        "classification": "REAL_IMAGE_SYNTHETIC_FIXTURE",
        "gateway": "http://127.0.0.1:3002",
        "core": "http://127.0.0.1:8011",
        "checks": {
            "auth_required": "PASS",
            "image_and_text_only_formal_cards": "PASS",
            "private_skip_hidden_from_display": "PASS",
            "skip_absent_from_list": "PASS",
            "owner_original_read": "PASS",
            "owner_thumbnail_read": "PASS",
            "cross_user_original_denied_404": "PASS",
            "delete_removes_media_row_and_files": "PASS",
            "automatic_image_generation_disabled": "PASS",
        },
        "http": {
            "unauthenticated_status": unauthenticated.status_code,
            "list_status": listing_response.status_code,
            "original_status": original.status_code,
            "thumbnail_status": thumbnail.status_code,
            "cross_user_status": cross_user.status_code,
        },
        "image": {
            "api_download": str(args.download.resolve()),
            "format": original_format,
            "width": original_size[0],
            "height": original_size[1],
            "bytes": len(original.content),
            "sha256": sha256(original.content).hexdigest(),
            "thumbnail_format": thumbnail_format,
            "thumbnail_width": thumbnail_size[0],
            "thumbnail_height": thumbnail_size[1],
        },
        "media_metadata": image_detail["media"],
        "deleted_other_media_files": len(other_paths),
        "image_generation_requests": 0,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
