from __future__ import annotations

import logging
import os
from pathlib import Path

from acceptance_environment import ROOT, environment
from verify_rebuild_workspace import verify

verify(ROOT)
environment()

from app.reminder_scheduler import create_scheduler

os.environ.setdefault("LIFE_CORE_URL", "http://127.0.0.1:8031")
os.environ.setdefault("LIFE_REMINDER_SCHEDULER_DB", str(
    Path(__file__).resolve().parents[1] / "infra/runtime/p00/reminder-scheduler.sqlite3"))
if not os.environ.get("LIFE_INTERNAL_TOKEN"):
    raise RuntimeError("REMINDER_SCHEDULER_TOKEN_REQUIRED")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
scheduler = create_scheduler(Path(os.environ["LIFE_REMINDER_SCHEDULER_DB"]))
logging.info("Starting independent APScheduler reminder service; database path is isolated.")
scheduler.start()
