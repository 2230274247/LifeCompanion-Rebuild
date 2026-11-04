from apscheduler.schedulers.background import BackgroundScheduler

from app.reminder_scheduler import (
    MOMENT_SETTLEMENT_JOB_ID, RECONCILE_JOB_ID, create_scheduler,
)


def test_scheduler_jobstore_persists_independent_jobs_across_restart(tmp_path):
    path = tmp_path / "scheduler.sqlite3"
    first = create_scheduler(path, interval_seconds=60,
                             scheduler_class=BackgroundScheduler)
    assert first.get_job(RECONCILE_JOB_ID) is not None
    assert first.get_job(MOMENT_SETTLEMENT_JOB_ID) is not None
    first.start(paused=True)
    first.shutdown(wait=False)
    second = create_scheduler(path, interval_seconds=60,
                              scheduler_class=BackgroundScheduler)
    second.start(paused=True)
    jobs = second.get_jobs()
    assert {job.id for job in jobs} == {RECONCILE_JOB_ID, MOMENT_SETTLEMENT_JOB_ID}
    second.shutdown(wait=False)
    assert path.is_file() and path.stat().st_size > 0


def test_scheduler_rejects_unsafe_interval(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="INTERVAL_TOO_SHORT"):
        create_scheduler(tmp_path / "scheduler.sqlite3", interval_seconds=1)
