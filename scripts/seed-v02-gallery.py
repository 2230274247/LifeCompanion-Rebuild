"""Seed synthetic gallery data into the isolated V0.2 acceptance database only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/runtime/v023"
EVIDENCE = ROOT / "evidence/shiguang-v02"
sys.path.insert(0, str(ROOT / "services/life-core"))


def load_environment() -> None:
    for path in (ROOT / "infra/.env", ROOT / "products/librechat-custom/.env"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value


def guarded_database(value: str) -> Path:
    path = Path(value).resolve()
    expected_root = (RUNTIME / "life-core.sqlite3").resolve()
    if path != expected_root:
        raise SystemExit("REFUSED: gallery seed only accepts infra/runtime/v023/life-core.sqlite3")
    return path


def synthetic_image(seed: str, palette: tuple[tuple[int, int, int], ...]) -> tuple[bytes, bytes]:
    width, height = 1200, 900
    image = Image.new("RGB", (width, height), palette[0])
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            round(palette[0][channel] * (1 - ratio) + palette[1][channel] * ratio)
            for channel in range(3)
        )
        draw.line((0, y, width, y), fill=(*color, 255))
    digest = hashlib.sha256(seed.encode()).digest()
    for index in range(9):
        value = digest[index]
        left = (value * 11) % (width - 180)
        top = (digest[index + 8] * 7) % (height - 160)
        size = 70 + (value % 180)
        color = (*palette[(index + 2) % len(palette)], 70 + (value % 90))
        if index % 2:
            draw.ellipse((left, top, left + size, top + size), fill=color)
        else:
            draw.rounded_rectangle(
                (left, top, left + size + 80, top + size),
                radius=28,
                fill=color,
            )
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    thumbnail = image.copy()
    thumbnail.thumbnail((640, 480))
    thumb_output = BytesIO()
    thumbnail.convert("RGB").save(thumb_output, format="JPEG", quality=84, optimize=True)
    return output.getvalue(), thumb_output.getvalue()


def seed(database: Path) -> dict:
    load_environment()
    from app.memory import Candidate
    from app.memos import MemosClient
    from app.moments import Moments
    from app.store import Store, utc_now
    from app.config import load_settings
    from app.memory import MemoryService

    settings = replace(load_settings(), database_path=database)
    store = Store(database)
    store.initialize()
    memory = MemoryService(store, settings)
    memory.initialize()
    Moments(store, settings, memory)

    accounts = json.loads((RUNTIME / "accounts.json").read_text(encoding="utf-8"))
    account = accounts.get("a")
    if not account or not account.get("memos_user_id"):
        raise SystemExit("SYNTHETIC_ACCOUNT_A_MISSING")
    with store.connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE memos_user_id=?", (account["memos_user_id"],)
        ).fetchone()
    if user is None or not user["memos_user_id"]:
        raise SystemExit("SYNTHETIC_USER_MAPPING_MISSING")
    user = dict(user)
    tokens = json.loads((RUNTIME / "memos-tokens.json").read_text(encoding="utf-8"))
    token = tokens.get(user["memos_user_id"])
    if not token:
        raise SystemExit("SYNTHETIC_MEMOS_TOKEN_MISSING")
    memos = MemosClient(os.getenv("MEMOS_BASE_URL", "http://127.0.0.1:5230"), token)

    zone = ZoneInfo("Asia/Hong_Kong")
    today = datetime.now(zone).replace(hour=18, minute=0, second=0, microsecond=0)
    scenes = [
        ("公园里的银杏", "今天下班后在公园走了一圈，看见银杏开始变黄，风很轻。", today, (49, 90, 72)),
        ("阳台上的薄荷", "傍晚给阳台的薄荷浇水，叶子被夕阳照得发亮。", today - timedelta(hours=7), (32, 62, 50)),
        ("地铁口的重逢", "下班路上在地铁口碰见老同学，他还是那么沉稳。", today - timedelta(days=1), (28, 54, 72)),
        ("雨后的面包店", "雨后路过街角面包店，买了刚出炉的全麦面包。", today - timedelta(days=1, hours=6), (92, 68, 42)),
        ("周末第一杯咖啡", "周末起得早，给自己冲了一杯手冲咖啡。", today - timedelta(days=3), (83, 60, 38)),
        ("交掉报告以后", "拖了很久的报告终于交掉，回家的路都轻松了一点。", today - timedelta(days=4), (45, 66, 73)),
    ]
    palettes = [
        ((49, 90, 72), (223, 166, 27), (250, 246, 234)),
        ((32, 62, 50), (115, 143, 112), (243, 216, 139)),
        ((28, 54, 72), (100, 129, 148), (229, 217, 188)),
        ((92, 68, 42), (194, 143, 93), (250, 232, 204)),
        ((83, 60, 38), (178, 121, 79), (240, 219, 188)),
        ((45, 66, 73), (107, 137, 145), (231, 224, 206)),
    ]
    created = []
    for index, ((title, summary, occurred_at, base_color), palette) in enumerate(
        zip(scenes, palettes), start=1
    ):
        source = f"synthetic-v02-gallery-{index:02d}"
        event = store.create_event(
            user_id=user["life_user_id"],
            source_type="chat",
            source_message_ids=[source],
            conversation_id=f"synthetic-gallery-chat-{index:02d}",
            occurred_at=occurred_at.isoformat(),
            title=title,
            summary=summary,
            confidence=1.0,
            consent_state="granted",
            status="pending",
            idempotency_key=f"synthetic-v02-gallery:{index:02d}",
        )
        candidate = Candidate(
            candidate_type="life_event",
            canonical_text=summary,
            evidence_quote=summary,
            occurred_state="occurred",
            confidence=1.0,
            sensitivity="ordinary",
            image_candidate=True,
        )
        saved = memory.save(
            user["life_user_id"],
            candidate,
            memory.key_for(candidate, summary, occurred_at, settings.timezone),
            source,
            event["conversation_id"],
            summary,
            occurred_at,
            event["event_id"],
        )
        memo_ref = memos.create_private_memo(
            {**event, "memos_user_id": user["memos_user_id"]}
        )
        published = store.set_event_status(
            event["event_id"], status="published", memo_ref=memo_ref
        )
        image, thumbnail = synthetic_image(title, palette)
        moment_id = "mom_seed_" + hashlib.sha256(title.encode()).hexdigest()[:20]
        with store.connect() as db:
            db.execute(
                """
                INSERT INTO moments (
                    moment_id,user_id,window_start,window_end,timezone,slot,status,
                    source_memory_ids,selection,caption,image,mime,thumbnail,thumbnail_mime,
                    image_width,image_height,attempts,error_code,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(moment_id) DO UPDATE SET
                    status=excluded.status,image=excluded.image,mime=excluded.mime,
                    thumbnail=excluded.thumbnail,thumbnail_mime=excluded.thumbnail_mime,
                    image_width=excluded.image_width,image_height=excluded.image_height,
                    updated_at=excluded.updated_at
                """,
                (
                    moment_id,
                    user["life_user_id"],
                    (occurred_at - timedelta(hours=1)).isoformat(),
                    occurred_at.isoformat(),
                    settings.timezone,
                    index % 3,
                    "published",
                    json.dumps([saved["memory_id"]]),
                    json.dumps(
                        [{"memory_id": saved["memory_id"], "score": 1.0, "seed": True}]
                    ),
                    summary,
                    image,
                    "image/png",
                    thumbnail,
                    "image/jpeg",
                    1200,
                    900,
                    1,
                    None,
                    utc_now(),
                    utc_now(),
                ),
            )
        # Keep the source path visually distinct without changing real photos.
        with store.connect() as db:
            db.execute(
                "UPDATE events SET title=?,summary=?,occurred_at=?,updated_at=? WHERE event_id=?",
                (
                    title,
                    summary,
                    occurred_at.isoformat(),
                    utc_now(),
                    published["event_id"],
                ),
            )
        created.append(
            {
                "event_id": published["event_id"],
                "memory_id": saved["memory_id"],
                "moment_id": moment_id,
                "title": title,
                "occurred_at": occurred_at.isoformat(),
                "thumbnail_base64_bytes": len(base64.b64encode(thumbnail)),
                "media_kind": "ai_generated_illustration",
            }
        )

    report = {
        "status": "PASS",
        "isolation": "infra/runtime/v023/life-core.sqlite3 + synthetic Memos user",
        "synthetic_account": account["username"],
        "production_database_touched": False,
        "created": created,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "synthetic-gallery-seed.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database", default=str(RUNTIME / "life-core.sqlite3")
    )
    args = parser.parse_args()
    print(json.dumps(seed(guarded_database(args.database)), ensure_ascii=False, indent=2))
