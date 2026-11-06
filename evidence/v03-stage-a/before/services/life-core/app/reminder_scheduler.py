from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)
RECONCILE_JOB_ID = "reminder-notification-reconciliation"


def reconcile_reminders():
    base_url = os.environ.get("LIFE_CORE_URL", "http://127.0.0.1:8031").rstrip("/")
    token = os.environ.get("LIFE_INTERNAL_TOKEN", "")
    if not token:
        raise RuntimeError("REMINDER_SCHEDULER_TOKEN_REQUIRED")
    response = httpx.post(
        f"{base_url}/internal/v1/reminders/reconcile",
        headers={"X-Internal-Token": token},
        timeout=20,
    )
    response.raise_for_status()
    logger.info("Reminder reconciliation completed: %s", response.json().get("status"))


def create_scheduler(database_path: Path, *, callback=reconcile_reminders,
                     interval_seconds: int = 15,
                     scheduler_class=BlockingScheduler) -> BlockingScheduler:
    if interval_seconds < 5:
        raise ValueError("REMINDER_SCHEDULER_INTERVAL_TOO_SHORT")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    jobstore_url = "sqlite:///" + database_path.resolve().as_posix()
    scheduler = scheduler_class(
        jobstores={"default": SQLAlchemyJobStore(url=jobstore_url)},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        timezone="UTC",
    )
    scheduler.add_job(
        callback, "interval", seconds=interval_seconds, id=RECONCILE_JOB_ID,
        replace_existing=True,
    )
    return scheduler
