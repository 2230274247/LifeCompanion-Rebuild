from __future__ import annotations

import sqlite3

import pytest

from test_v03_windows import build


def test_generation_key_index_rejects_duplicate_non_null_keys(tmp_path):
    _moments, _user, store, _memory = build(tmp_path)
    with store.connect() as db:
        indexes = {
            row["name"] for row in db.execute("PRAGMA index_list(moments)")
        }
        assert "idx_moment_generation_key" in indexes
        db.execute(
            """INSERT INTO moments
            (moment_id,user_id,window_start,window_end,timezone,slot,status,
             source_memory_ids,selection,caption,attempts,created_at,updated_at,
             generation_key)
            VALUES ('mom_key_one','owner','2026-11-04T00:00:00+00:00',
                '2026-11-04T01:00:00+00:00','Asia/Hong_Kong',0,'queued',
                '[]','[]','',0,'2026-11-04T00:00:00+00:00',
                '2026-11-04T00:00:00+00:00','generation-key-1')"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO moments
                (moment_id,user_id,window_start,window_end,timezone,slot,status,
                 source_memory_ids,selection,caption,attempts,created_at,updated_at,
                 generation_key)
                VALUES ('mom_key_two','owner','2026-11-04T01:00:00+00:00',
                    '2026-11-04T02:00:00+00:00','Asia/Hong_Kong',0,'queued',
                    '[]','[]','',0,'2026-11-04T00:00:00+00:00',
                    '2026-11-04T00:00:00+00:00','generation-key-1')"""
            )


def test_generation_key_index_allows_legacy_null_values(tmp_path):
    _moments, _user, store, _memory = build(tmp_path)
    with store.connect() as db:
        for suffix, hour in (("one", 1), ("two", 2)):
            db.execute(
                """INSERT INTO moments
                (moment_id,user_id,window_start,window_end,timezone,slot,status,
                 source_memory_ids,selection,caption,attempts,created_at,updated_at)
                VALUES (?,?,'2026-11-04T0?:00:00+00:00',
                    '2026-11-04T0?:00:00+00:00','Asia/Hong_Kong',0,'queued',
                    '[]','[]','',0,'2026-11-04T00:00:00+00:00',
                    '2026-11-04T00:00:00+00:00')""".replace("0?", str(hour)),
                (f"mom_legacy_{suffix}", "legacy-owner"),
            )
