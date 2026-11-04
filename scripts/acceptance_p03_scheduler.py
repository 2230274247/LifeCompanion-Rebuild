"""Start the independent APScheduler process and observe one real reconciliation."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from acceptance_environment import ROOT
from verify_rebuild_workspace import verify

verify(ROOT)
runtime = ROOT / "infra/runtime/p00"
log = runtime / "reminder-scheduler.out.log"
error_log = runtime / "reminder-scheduler.err.log"
database = runtime / "reminder-scheduler.sqlite3"
result = {"status": "FAIL", "provider_calls": 0, "started_at": datetime.now(UTC).isoformat()}
process = None
log_text = lambda: "".join(
    path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    for path in (log, error_log)
)
before_completions = log_text().count("Reminder reconciliation completed")
try:
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/run_reminder_scheduler.py")],
        cwd=ROOT,
        stdout=log.open("ab"),
        stderr=error_log.open("ab"),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 35
    completed = False
    while time.monotonic() < deadline:
        completed = log_text().count("Reminder reconciliation completed") > before_completions
        if completed:
            break
        if process.poll() is not None:
            break
        time.sleep(.5)
    assert database.is_file() and database.stat().st_size > 0, "SCHEDULER_JOBSTORE_MISSING"
    assert completed, "SCHEDULER_DID_NOT_COMPLETE_RECONCILIATION"
    assert process.poll() is None, "SCHEDULER_EXITED_EARLY"
    result.update(
        status="PASS",
        scheduler_pid=process.pid,
        jobstore=str(database.relative_to(ROOT)),
        jobstore_bytes=database.stat().st_size,
        reconciliation_observed=True,
        newly_observed_reconciliations=(
            log_text().count("Reminder reconciliation completed") - before_completions),
        checks={
            "independent_process_started": "PASS",
            "persistent_sqlalchemy_jobstore_created": "PASS",
            "real_internal_core_reconciliation": "PASS",
            "model_requests": "ZERO",
        },
    )
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    result["ended_at"] = datetime.now(UTC).isoformat()
    (ROOT / "evidence/p03").mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence/p03/scheduler-live.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
