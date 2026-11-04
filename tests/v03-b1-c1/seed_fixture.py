"""Seed an isolated V0.3 B1/C1 fixture from the verified B0 PNG."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image


WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE / "services" / "life-core"))

from app.config import Settings  # noqa: E402
from app.memory import Candidate, MemoryService  # noqa: E402
from app.moments import MomentSettings, Moments  # noqa: E402
from app.store import Store  # noqa: E402


JWT_SECRET = "v03-b1-c1-synthetic-jwt-secret"  # gitleaks:allow
INTERNAL_TOKEN = "v03-b1-c1-synthetic-internal-token"  # gitleaks:allow
OWNER_LIBRECHAT_ID = "lc-b1-owner"
OTHER_LIBRECHAT_ID = "lc-b1-other"
IMAGE_MOMENT_ID = "mom_101010101010101010101010"
TEXT_MOMENT_ID = "mom_202020202020202020202020"
PRIVATE_SKIP_MOMENT_ID = "mom_303030303030303030303030"
SKIP_MOMENT_ID = "mom_404040404040404040404040"
OTHER_IMAGE_MOMENT_ID = "mom_505050505050505050505050"
OCCURRED_AT = datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc)


def settings_for(database: Path, media_root: Path) -> Settings:
    return Settings(
        database_path=database,
        internal_token=INTERNAL_TOKEN,
        jwt_secret=JWT_SECRET,
        jwt_refresh_secret="v03-b1-c1-synthetic-refresh-secret",  # gitleaks:allow
        memos_base_url="http://127.0.0.1:9",
        memos_api_token="",
        timezone="Asia/Hong_Kong",
        allowed_origins=("http://127.0.0.1:4175",),
        moment_image_provider="kolors",
        moment_image_generation_enabled=False,
        moment_workers_enabled=False,
        moment_scheduler_external=True,
        moment_windows_v03=True,
        moment_media_root=media_root,
        image_provider_api_key="",
    )


def seed_memory(memory: MemoryService, store: Store, user: dict, text: str, key: str):
    event = store.create_event(
        user_id=user["life_user_id"],
        source_type="chat",
        source_message_ids=[key],
        conversation_id="synthetic-b1-c1",
        occurred_at=OCCURRED_AT.isoformat(),
        title=text[:28],
        summary=text,
        confidence=0.95,
        consent_state="granted",
        status="published",
        idempotency_key=f"{user['life_user_id']}:{key}",
    )
    candidate = Candidate(
        candidate_type="life_event",
        canonical_text=text,
        evidence_quote=text,
        occurred_state="occurred",
        confidence=0.95,
        sensitivity="ordinary",
        image_candidate=True,
    )
    return memory.save(
        user["life_user_id"],
        candidate,
        f"synthetic:{key}",
        key,
        "synthetic-b1-c1",
        text,
        OCCURRED_AT,
        event["event_id"],
    )


def insert_moment(
    store: Store,
    *,
    moment_id: str,
    owner: str,
    source_id: str,
    day: int,
    status: str,
    caption: str,
    storage_status: str,
    imageability: str,
):
    review = {
        "candidates": [
            {
                "memory_id": source_id,
                "outcome": "SELECTED",
                "policy": {
                    "storage_status": storage_status,
                    "imageability": imageability,
                    "image_dispatch_allowed": imageability == "SAFE_SCENE",
                },
            }
        ]
    }
    stamp = f"2026-11-{day:02d}T03:00:00+00:00"
    with store.connect() as db:
        db.execute(
            """INSERT INTO moments
            (moment_id,user_id,window_start,window_end,timezone,slot,status,
             source_memory_ids,selection,caption,attempts,created_at,updated_at,
             review_json)
            VALUES (?,?,?,?,?,0,?,?,?,?,0,?,?,?)""",
            (
                moment_id,
                owner,
                f"2026-11-{day:02d}T00:00:00+00:00",
                stamp,
                "Asia/Hong_Kong",
                status,
                json.dumps([source_id]),
                "[]",
                caption,
                stamp,
                stamp,
                json.dumps(review, ensure_ascii=False),
            ),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--source-image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.media_root.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = args.source_image.read_bytes()
    image_sha = hashlib.sha256(image_bytes).hexdigest()
    with Image.open(args.source_image) as image:
        image.load()
        width, height = image.size
        image_format = image.format
    if (image_format, width, height, image_sha) != (
        "PNG",
        960,
        1280,
        "9bbd0cb588f51cbf579235547f7e55aa4d8c06e09912f9c0881fabdfd31e240b",
    ):
        raise SystemExit("SOURCE_IMAGE_DOES_NOT_MATCH_VERIFIED_B0")

    settings = settings_for(args.database, args.media_root)
    store = Store(settings.database_path)
    store.initialize()
    memory = MemoryService(store, settings)
    memory.initialize()
    moments = Moments(store, settings, memory)

    owner = store.bootstrap_user(
        librechat_user_id=OWNER_LIBRECHAT_ID,
        memos_user_id="users/v03-b1-owner",
        memos_username="v03-b1-owner",
        display_name="B1 合成验收用户",
        memory_consent=True,
        image_consent=True,
    )
    other = store.bootstrap_user(
        librechat_user_id=OTHER_LIBRECHAT_ID,
        memos_user_id="users/v03-b1-other",
        memos_username="v03-b1-other",
        display_name="B1 合成隔离用户",
        memory_consent=True,
        image_consent=True,
    )
    for user in (owner, other):
        moments.configure(
            user,
            MomentSettings(enabled=False, timezone="Asia/Hong_Kong"),
        )
        moments.set_egress_consent(
            user["life_user_id"],
            "image_generation",
            "kolors",
            True,
            "recollection-egress-v1",
        )

    image_source = seed_memory(
        memory,
        store,
        owner,
        "清晨在厨房给薄荷浇水，阳光落在白瓷杯和刚烤好的吐司上。",
        "v03-b1-image",
    )
    text_source = seed_memory(
        memory,
        store,
        owner,
        "晚饭后沿河散步，听见远处有人练习萨克斯。",
        "v03-b1-text",
    )
    other_source = seed_memory(
        memory,
        store,
        other,
        "傍晚在阳台收衣服时看见粉色的云。",
        "v03-b1-other",
    )

    insert_moment(
        store,
        moment_id=IMAGE_MOMENT_ID,
        owner=owner["life_user_id"],
        source_id=image_source["memory_id"],
        day=4,
        status="generated",
        caption="清晨在厨房给薄荷浇水，为自己留下一杯热茶。",
        storage_status="PRIVATE_TEXT",
        imageability="SAFE_SCENE",
    )
    insert_moment(
        store,
        moment_id=TEXT_MOMENT_ID,
        owner=owner["life_user_id"],
        source_id=text_source["memory_id"],
        day=3,
        status="private_text",
        caption="晚饭后沿河散步，听见远处有人练习萨克斯。",
        storage_status="PRIVATE_TEXT",
        imageability="TEXT_ONLY",
    )
    insert_moment(
        store,
        moment_id=PRIVATE_SKIP_MOMENT_ID,
        owner=owner["life_user_id"],
        source_id=text_source["memory_id"],
        day=2,
        status="private_text",
        caption="这条私密内容不得作为正式回忆展示。",
        storage_status="PRIVATE_TEXT",
        imageability="PRIVATE_SKIP",
    )
    insert_moment(
        store,
        moment_id=SKIP_MOMENT_ID,
        owner=owner["life_user_id"],
        source_id=text_source["memory_id"],
        day=1,
        status="skipped",
        caption="",
        storage_status="SKIP",
        imageability="NOT_APPLICABLE",
    )
    insert_moment(
        store,
        moment_id=OTHER_IMAGE_MOMENT_ID,
        owner=other["life_user_id"],
        source_id=other_source["memory_id"],
        day=4,
        status="generated",
        caption="另一位合成用户的独立回忆。",
        storage_status="PRIVATE_TEXT",
        imageability="SAFE_SCENE",
    )

    primary_media = moments.media_store.store(
        owner["life_user_id"],
        IMAGE_MOMENT_ID,
        image_bytes,
        declared_mime="image/png",
        provider="SiliconFlow",
        model="Kwai-Kolors/Kolors",
        trace_id="ti_1u95f5u974melfugf5",
        prompt_summary="清晨厨房，虚构人物为薄荷浇水，白瓷杯与吐司，暖色自然光。",
        policy_status="PRIVATE_TEXT",
    )
    cleanup_media = moments.media_store.store(
        other["life_user_id"],
        OTHER_IMAGE_MOMENT_ID,
        image_bytes,
        declared_mime="image/png",
        provider="SiliconFlow",
        model="Kwai-Kolors/Kolors",
        trace_id="ti_1u95f5u974melfugf5",
        prompt_summary="合成跨用户隔离及删除测试。",
        policy_status="PRIVATE_TEXT",
    )

    result = {
        "status": "SYNTHETIC_FIXTURE_READY",
        "classification": "REAL_IMAGE_IN_SYNTHETIC_FIXTURE",
        "database": str(args.database.resolve()),
        "media_root": str(args.media_root.resolve()),
        "source_image": str(args.source_image.resolve()),
        "source_image_sha256": image_sha,
        "source_image_format": image_format,
        "source_image_width": width,
        "source_image_height": height,
        "owner": {
            "librechat_user_id": owner["librechat_user_id"],
            "life_user_id": owner["life_user_id"],
        },
        "other": {
            "librechat_user_id": other["librechat_user_id"],
            "life_user_id": other["life_user_id"],
        },
        "moment_ids": {
            "image": IMAGE_MOMENT_ID,
            "text": TEXT_MOMENT_ID,
            "private_skip": PRIVATE_SKIP_MOMENT_ID,
            "skip": SKIP_MOMENT_ID,
            "other_image": OTHER_IMAGE_MOMENT_ID,
        },
        "primary_media": primary_media,
        "cleanup_media": cleanup_media,
        "automatic_generation": {
            "LIFE_MOMENT_IMAGE_GENERATION_ENABLED": False,
            "LIFE_MOMENT_WORKERS_ENABLED": False,
            "LIFE_MOMENT_SCHEDULER_EXTERNAL": True,
            "image_generation_requests": 0,
        },
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
