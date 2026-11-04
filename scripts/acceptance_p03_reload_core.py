"""Reload the verified isolated Core; never operate on another process or database."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

from acceptance_environment import ENVFILE, PYTHON, ROOT, dotenv
from verify_rebuild_workspace import verify


def shell(command):
    return subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", command],
        text=True, encoding="utf-8").strip()


def listener():
    value = json.loads(shell(
        "$ErrorActionPreference='Stop'; "
        "$p=Get-NetTCPConnection -LocalPort 8031 -State Listen; "
        "if (@($p).Count -ne 1 -or $p.LocalAddress -ne '127.0.0.1') { throw 'UNEXPECTED_LISTENER' }; "
        "Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.OwningProcess) | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"))
    script = str(ROOT / "scripts/acceptance_environment.py")
    assert f'"{script}" core' in value["CommandLine"], "WRONG_CORE_PROCESS"
    return value["ProcessId"]


def snapshot():
    config = dotenv(ENVFILE)
    database = ROOT / "infra/runtime/p00/life-core.sqlite3"
    assert database.resolve() == __import__("pathlib").Path(config["LIFE_DATABASE_PATH"]).resolve()
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        jobs = dict(db.execute("SELECT status,count(*) FROM memory_jobs GROUP BY status").fetchall())
        assert set(jobs) <= {"succeeded", "failed", "cancelled"}, "MODEL_WORK_PENDING"
        image_users = db.execute("SELECT count(*) FROM users WHERE image_consent=1").fetchone()[0]
        assert image_users == 0, "IMAGE_CONSENT_NEEDS_MANUAL_REVIEW"
        model_calls = db.execute("SELECT count(*) FROM memory_model_calls").fetchone()[0]
        revision = any(row[1] == "revision" for row in db.execute("PRAGMA table_info(reminders)"))
    return {"database": str(database.relative_to(ROOT)), "memory_jobs": jobs,
            "image_consent_users": image_users, "model_call_rows": model_calls,
            "reminder_revision_column": revision}


def main(report=None):
    identity = verify(ROOT)
    report = (report or ROOT / "evidence/p03/core-reload-business-workflow.json").resolve()
    assert report.is_relative_to((ROOT / "evidence").resolve()) and not report.exists()
    assert report.parent.is_dir() and report.suffix == ".json"
    before = snapshot()
    original = listener()
    config_digest = hashlib.sha256(ENVFILE.read_bytes()).digest()
    # PID comes only from the listener whose command line was checked above.
    shell(f"$ErrorActionPreference='Stop'; Stop-Process -Id {original}")
    launch = subprocess.check_output(
        [str(PYTHON), str(ROOT / "scripts/acceptance_environment.py"), "core-service"],
        cwd=ROOT, text=True, encoding="utf-8")
    new_pid = json.loads(launch)["core_pid"]
    deadline = time.monotonic() + 45
    healthy = False
    while time.monotonic() < deadline:
        try:
            response = httpx.get("http://127.0.0.1:8031/health", timeout=2, trust_env=False)
            healthy = response.status_code == 200
        except httpx.HTTPError:
            pass
        if healthy:
            break
        time.sleep(.25)
    assert healthy and listener() != original, "CORE_RELOAD_FAILED"
    after = snapshot()
    assert after["reminder_revision_column"]
    assert after["model_call_rows"] == before["model_call_rows"]
    assert hashlib.sha256(ENVFILE.read_bytes()).digest() == config_digest
    result = {"status": "PASS", "identity": identity, "previous_pid": original,
              "launched_pid": new_pid, "before": before, "after": after,
              "health_status": 200, "configuration_unchanged": True,
              "added_model_call_rows": after["model_call_rows"] - before["model_call_rows"],
              "scope": "isolated 8031 Core reload, not production or scheduler deployment"}
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    main(parser.parse_args().report)
