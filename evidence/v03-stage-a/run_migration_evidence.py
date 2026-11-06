"""Create isolated evidence for the legacy-to-V0.3 schema migration and rollback."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import hashlib
import html
import json
import shutil
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "life-core"))
sys.path.insert(0, str(ROOT / "services" / "life-core" / "tests"))

from app.config import Settings
from app.memory import Candidate, MemoryService
from app.moments import MomentSettings, Moments
from app.moment_windows import LEGACY_ENDS
from app.store import Store


STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUTPUT = ROOT / "evidence" / "v03-stage-a" / "migration" / STAMP
OUTPUT.mkdir(parents=True, exist_ok=False)
DB_PATH = OUTPUT / "stage-a-migration.sqlite3"


def settings(database_path: Path, *, v03: bool) -> Settings:
    return Settings(
        database_path=database_path,
        internal_token="synthetic-internal",
        jwt_secret="synthetic-jwt",
        jwt_refresh_secret="synthetic-refresh",
        memos_base_url="http://memos.invalid",
        memos_api_token="",
        timezone="Asia/Hong_Kong",
        allowed_origins=(),
        moment_windows_v03=v03,
        moment_scheduler_external=True,
        moment_workers_enabled=False,
        moment_image_generation_enabled=False,
    )


def snapshot(store: Store) -> dict:
    tables = (
        "moments",
        "recollection_candidates",
        "moment_settings",
        "moment_schedule_state",
        "moment_policy_history",
        "moment_migration_conflicts",
        "schema_migrations",
    )
    result = {}
    with store.connect() as db:
        for table in tables:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                result[table] = None
                continue
            result[table] = {
                "columns": [dict(row) for row in db.execute(f"PRAGMA table_info({table})")],
                "indexes": [
                    dict(row) for row in db.execute(f"PRAGMA index_list({table})")
                ],
            }
    return result


def create_legacy_moment_schema(store: Store) -> None:
    """Create the exact pre-V0.3 moments subset without instantiating new Moments."""
    with store.connect() as db:
        db.executescript(
            """
            CREATE TABLE moment_settings (
                user_id TEXT PRIMARY KEY, config TEXT NOT NULL,
                enabled_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE moments (
                moment_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                window_start TEXT NOT NULL, window_end TEXT NOT NULL,
                timezone TEXT NOT NULL, slot INTEGER NOT NULL,
                status TEXT NOT NULL, source_memory_ids TEXT NOT NULL,
                selection TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '',
                image BLOB, mime TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(user_id,window_start,window_end)
            );
            CREATE TABLE moment_exclusions (
                user_id TEXT NOT NULL, memory_id TEXT NOT NULL,
                excluded INTEGER NOT NULL, PRIMARY KEY(user_id,memory_id)
            );
            CREATE UNIQUE INDEX idx_moment_window ON moments(user_id,window_end);
            CREATE TABLE recollection_candidates (
                window_id TEXT NOT NULL, user_id TEXT NOT NULL,
                memory_id TEXT NOT NULL, source_revision INTEGER NOT NULL,
                input_hash TEXT NOT NULL, source_message_ids TEXT NOT NULL,
                dimensions TEXT, score REAL, eligible INTEGER NOT NULL DEFAULT 0,
                reason_code TEXT NOT NULL, model_reason_code TEXT,
                selected INTEGER NOT NULL DEFAULT 0, version TEXT NOT NULL,
                PRIMARY KEY(window_id,memory_id)
            );
            """
        )


legacy = settings(DB_PATH, v03=False)
upgraded = settings(DB_PATH, v03=True)
store = Store(DB_PATH)
store.initialize()
memory = MemoryService(store, legacy)
memory.initialize()
create_legacy_moment_schema(store)
user = store.bootstrap_user(
    librechat_user_id="migration-user",
    memos_user_id="users/migration",
    memos_username="migration",
    display_name="Migration Synthetic",
    memory_consent=True,
    image_consent=True,
)
when = datetime.fromisoformat("2026-11-03T12:00:00+08:00").astimezone(timezone.utc)
event = store.create_event(
    user_id=user["life_user_id"],
    source_type="chat",
    source_message_ids=["legacy-message"],
    conversation_id="legacy-chat",
    occurred_at=when.isoformat(),
    title="旧版合成回忆",
    summary="旧版合成回忆，仅用于迁移证据。",
    confidence=.95,
    consent_state="granted",
    status="published",
    idempotency_key="migration:legacy-message",
)
candidate = Candidate(
    candidate_type="life_event",
    canonical_text="旧版合成回忆，仅用于迁移证据。",
    evidence_quote="旧版合成回忆，仅用于迁移证据。",
    occurred_state="occurred",
    confidence=.95,
    sensitivity="ordinary",
    image_candidate=True,
)
item = memory.save(
    user["life_user_id"],
    candidate,
    "synthetic:legacy-message",
    "legacy-message",
    "legacy-chat",
    candidate.canonical_text,
    when,
    event["event_id"],
)
with store.connect() as db:
    db.execute(
        """INSERT INTO moment_settings(user_id,config,enabled_at,updated_at)
        VALUES (?,?,?,?)""",
        (
            user["life_user_id"],
            json.dumps(MomentSettings(
                enabled=True, timezone="Asia/Hong_Kong", ends=list(LEGACY_ENDS)
            ).model_dump()),
            when.isoformat(),
            when.isoformat(),
        ),
    )
    db.execute(
        """INSERT INTO moments
        (moment_id,user_id,window_start,window_end,timezone,slot,status,
         source_memory_ids,selection,caption,attempts,error_code,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "mom_legacy_synthetic",
            user["life_user_id"],
            "2026-11-03T04:00:00+00:00",
            "2026-11-03T08:00:00+00:00",
            "Asia/Hong_Kong",
            0,
            "generated",
            json.dumps([item["memory_id"]]),
            "[]",
            "旧版文字回忆保留",
            1,
            None,
            when.isoformat(),
            when.isoformat(),
        ),
    )

before_schema = snapshot(store)
legacy_backup = OUTPUT / "legacy-before.sqlite3"
shutil.copy2(DB_PATH, legacy_backup)
with store.connect() as db:
    before_row = dict(db.execute(
        "SELECT * FROM moments WHERE moment_id='mom_legacy_synthetic'"
    ).fetchone())

with patch("app.moments.utc_now", return_value="2026-11-03T00:00:00+00:00"):
    migrated_moments = Moments(store, upgraded, memory)
after_first = snapshot(store)
with store.connect() as db:
    after_first_rows = db.execute("SELECT count(*) FROM moments").fetchone()[0]
    migration_rows_first = [
        dict(row) for row in db.execute("SELECT * FROM schema_migrations ORDER BY name")
    ]
    upgraded_config = migrated_moments.config(user["life_user_id"])
    coverage_audits = [
        dict(row) for row in db.execute(
            """SELECT actor,old_values,new_values FROM permission_audit
            WHERE user_id=? AND actor='v03_night_coverage_migration'""",
            (user["life_user_id"],),
        )
    ]
    coverage_history = [
        dict(row) for row in db.execute(
            """SELECT timezone,ends_json,policy_version,effective_at_utc
            FROM moment_policy_history WHERE user_id=?""",
            (user["life_user_id"],),
        )
    ]

Moments(store, upgraded, memory)
after_second = snapshot(store)
with store.connect() as db:
    after_second_rows = db.execute("SELECT count(*) FROM moments").fetchone()[0]
    migration_rows_second = [
        dict(row) for row in db.execute("SELECT * FROM schema_migrations ORDER BY name")
    ]
    migrated_row = dict(db.execute(
        "SELECT * FROM moments WHERE moment_id='mom_legacy_synthetic'"
    ).fetchone())

v03_backup = OUTPUT / "v03-after.sqlite3"
shutil.copy2(DB_PATH, v03_backup)

rolled_back = Moments(store, legacy, memory)
config_after_rollback = rolled_back.config(user["life_user_id"])
with store.connect() as db:
    rollback_row = dict(db.execute(
        "SELECT * FROM moments WHERE moment_id='mom_legacy_synthetic'"
    ).fetchone())
    rolled_back_indexes = {
        row["name"] for row in db.execute("PRAGMA index_list(moments)")
    }

preserved_fields = (
    "moment_id",
    "user_id",
    "window_start",
    "window_end",
    "timezone",
    "slot",
    "status",
    "source_memory_ids",
    "selection",
    "caption",
    "attempts",
    "error_code",
    "created_at",
    "updated_at",
)
assert before_schema["moments"]["columns"]
assert {"local_date", "review_json", "late_checked_at"} == {
    column["name"] for column in after_first["moments"]["columns"]
} & {"local_date", "review_json", "late_checked_at"}
assert after_first == after_second
assert {name: before_row[name] for name in preserved_fields} == {
    name: migrated_row[name] for name in preserved_fields
}
assert after_first_rows == after_second_rows == 1
assert len(migration_rows_first) == len(migration_rows_second) == 1
assert upgraded_config["ends"] == ["11:00", "17:00", "24:00"]
assert len(coverage_audits) == 1
assert json.loads(coverage_audits[0]["old_values"])["ends"][-1] == "23:00"
assert json.loads(coverage_audits[0]["new_values"])["ends"][-1] == "24:00"
assert len(coverage_history) == 1
assert json.loads(coverage_history[0]["ends_json"])[-1] == "24:00"
assert config_after_rollback["enabled"] is True
assert {name: before_row[name] for name in preserved_fields} == {
    name: rollback_row[name] for name in preserved_fields
}
assert "idx_moment_business_key" in rolled_back_indexes
with sqlite3.connect(legacy_backup) as db:
    backup_columns = {
        row[1] for row in db.execute("PRAGMA table_info(moments)")
    }
assert "local_date" not in backup_columns

result = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "mode": "SYNTHETIC_SQLITE_ONLY",
    "database": str(DB_PATH),
    "database_sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest(),
    "legacy_backup": str(legacy_backup),
    "legacy_backup_sha256": hashlib.sha256(legacy_backup.read_bytes()).hexdigest(),
    "v03_backup": str(v03_backup),
    "v03_backup_sha256": hashlib.sha256(v03_backup.read_bytes()).hexdigest(),
    "schema_before": before_schema,
    "schema_after": after_first,
    "schema_after_second_migration": after_second,
    "migration_rows": {
        "first": migration_rows_first,
        "second": migration_rows_second,
    },
    "row_counts": {
        "before": 1,
        "after_first": after_first_rows,
        "after_second": after_second_rows,
    },
    "night_coverage_migration": {
        "effective_ends": upgraded_config["ends"],
        "audit": coverage_audits,
        "policy_history": coverage_history,
    },
    "legacy_row_before": before_row,
    "legacy_row_after": migrated_row,
    "rollback": {
        "mode": "FEATURE_FLAG_OFF_NO_DROP",
        "config_enabled": config_after_rollback["enabled"],
        "row": rollback_row,
        "business_key_index_present": "idx_moment_business_key" in rolled_back_indexes,
    },
}
(OUTPUT / "migration-evidence.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)

document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V0.3 阶段 A 迁移与回滚证据</title>
<style>
body{{margin:0;background:#f4f0e5;color:#14251f;font:16px/1.55 Georgia,"Noto Serif SC",serif}}
main{{max-width:1000px;margin:auto;padding:48px 24px}}h1{{font-size:clamp(32px,6vw,64px);line-height:1}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:28px 0}}
.grid div{{border-top:3px solid #146b4a;padding-top:10px}}.grid b{{display:block;font-size:22px}}
pre{{background:#14251f;color:#e8eadf;padding:18px;overflow:auto;font:12px/1.5 Consolas,monospace}}
.note{{border-left:4px solid #a64b2a;padding-left:14px}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<p>STAGE A · SYNTHETIC MIGRATION EVIDENCE</p>
<h1>旧库增量迁移与特性关闭回滚</h1>
<section class="grid"><div><span>旧数据行</span><b>保留</b></div>
<div><span>二次迁移</span><b>幂等</b></div><div><span>回滚方式</span><b>关闭 V0.3</b></div></section>
<p class="note">本页只使用合成的 SQLite。没有连接或迁移生产/原始用户数据库，也没有生图 API 调用。</p>
<h2>Schema 前后</h2>
<pre>{html.escape(json.dumps({
    "before": [c["name"] for c in before_schema["moments"]["columns"]],
    "after": [c["name"] for c in after_first["moments"]["columns"]],
}, ensure_ascii=False, indent=2))}</pre>
<h2>迁移记录</h2>
<pre>{html.escape(json.dumps(migration_rows_second, ensure_ascii=False, indent=2))}</pre>
<h2>保留字段</h2>
<pre>{html.escape(json.dumps({name: migrated_row[name] for name in preserved_fields},
    ensure_ascii=False, indent=2))}</pre>
<p>DATABASE {html.escape(str(DB_PATH))}<br>SHA256 {result["database_sha256"]}</p>
</main></body></html>"""
(OUTPUT / "migration-evidence.html").write_text(document, encoding="utf-8")

print(json.dumps({
    "output": str(OUTPUT),
    "schema_before_columns": len(before_schema["moments"]["columns"]),
    "schema_after_columns": len(after_first["moments"]["columns"]),
    "rows_after_second_migration": after_second_rows,
    "rollback_enabled": config_after_rollback["enabled"],
}, ensure_ascii=False))
