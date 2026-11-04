"""Real HTTP with explicit legacy-row fault injection; no image or model request."""
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx

from acceptance_p03_live import ROOT, load_settings, start, stop, utc_now
from verify_rebuild_workspace import verify


def main():
    verify(ROOT)
    database = ROOT / "infra/runtime/p04/privacy-6be8c1bc45c34d49/life.sqlite3"
    assert database.is_file() and database.resolve().is_relative_to((ROOT / "infra/runtime/p04").resolve())
    settings = replace(load_settings(), database_path=database, memory_llm_key="",
                       neo4j_uri="", memos_api_token="", vikunja_users={},
                       reminder_scheduler_external=True)
    account = json.loads((ROOT / "infra/runtime/p00/accounts.json").read_text(encoding="utf-8"))["a"]
    login = httpx.post("http://127.0.0.1:3091/api/auth/login",
                       json={"email": account["email"], "password": account["password"]}, timeout=20)
    login.raise_for_status()
    auth = {"Authorization": "Bearer " + login.json()["token"]}
    run_id = uuid.uuid4().hex[:16]
    skipped = "p04-skipped-injection-" + run_id
    result = {"status": "FAIL", "run_id": run_id, "started_at": utc_now(), "provider_calls": 0,
              "scope": "legacy cancelled text and empty skipped row fault injection; real HTTP/SQLite; no image asset or cloud request"}
    app, server, worker, client = start(settings)
    owner = identifier = None
    try:
        owner = app.state.store.get_user_by_librechat_id(account["librechat_user_id"])["life_user_id"]
        assert not app.state.store.get_user(owner)["image_consent"]
        with app.state.store.connect() as db:
            row = db.execute("SELECT * FROM moments WHERE user_id=? LIMIT 1", (owner,)).fetchone()
            identifier = row["moment_id"]
            db.execute("""UPDATE moments SET status='cancelled',caption='SYNTHETIC_LEGACY_RETAINED_TEXT',
                selection='[{"legacy":"synthetic"}]' WHERE moment_id=?""", (identifier,))
            end = (datetime.now(UTC) - timedelta(days=3)).isoformat()
            db.execute("""INSERT INTO moments
                (moment_id,user_id,window_start,window_end,timezone,slot,status,
                 source_memory_ids,selection,caption,created_at,updated_at)
                VALUES (?,?,?,?,?,0,'skipped','[]','[]','',?,?)""",
                (skipped,owner,end,end,"Asia/Hong_Kong",utc_now(),utc_now()))
        listing = client.get("/api/v1/moments", headers=auth)
        listing.raise_for_status()
        rows = listing.json()["moments"]
        assert all(item["caption"] != "SYNTHETIC_LEGACY_RETAINED_TEXT" for item in rows)
        assert skipped not in {item["moment_id"] for item in rows}
        detail = client.get(f"/api/v1/moments/{identifier}", headers=auth).json()["moment"]
        assert detail["status"] == "cancelled" and not detail["caption"] and not detail["selection"]
        assert detail["image_data"] is None
        client.patch("/api/v1/me/settings", headers=auth, json={"image_consent": False}).raise_for_status()
        with app.state.store.connect() as db:
            assert db.execute("SELECT status FROM moments WHERE moment_id=?", (skipped,)).fetchone()[0] == "skipped"
            row = db.execute("SELECT caption,selection,image FROM moments WHERE moment_id=?", (identifier,)).fetchone()
            assert tuple(row) == ("", "[]", None)
            calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        assert skipped not in {item["moment_id"] for item in client.get("/api/v1/moments", headers=auth).json()["moments"]}
        assert calls == 0
        result.update(status="PASS", legacy_payload_scrubbed=True,
                      skipped_row_not_published_after_revocation=True, model_call_rows=calls)
    finally:
        if owner:
            with app.state.store.connect() as db:
                db.execute("DELETE FROM moments WHERE moment_id=? AND user_id=?", (skipped,owner))
                if identifier:
                    db.execute("""UPDATE moments SET image=NULL,mime=NULL,caption='',selection='[]'
                        WHERE moment_id=? AND user_id=?""", (identifier,owner))
        stop(server, worker, client)
        result["ended_at"] = utc_now()
        (ROOT / f"evidence/p04/legacy-privacy-{run_id}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
