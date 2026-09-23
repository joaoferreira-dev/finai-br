from datetime import datetime, timedelta, timezone
import logging

import pytest
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobSubmissionEvent,
)
from apscheduler.executors import base as executor_base
from apscheduler.schedulers.base import BaseScheduler

import main


@pytest.fixture
def scheduler(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "run_daily_cycle", lambda: calls.append("daily-cycle"))
    monkeypatch.setattr(main, "send_latest_report", lambda: calls.append("send-report"))
    instance = main.create_scheduler()
    # Initialize the real job defaults and listeners without running the blocking loop.
    BaseScheduler.start(instance, paused=True)
    yield instance, calls
    BaseScheduler.shutdown(instance)


def execute_late_job(monkeypatch, scheduler, job_id, delay):
    scheduled_at = datetime(2026, 9, 22, 21, tzinfo=timezone.utc)

    class ExecutorClock:
        @staticmethod
        def now(tz):
            return (scheduled_at + timedelta(seconds=delay)).astimezone(tz)

    monkeypatch.setattr(executor_base, "datetime", ExecutorClock)
    events = executor_base.run_job(
        scheduler.get_job(job_id), "default", [scheduled_at], "test.scheduler"
    )
    for event in events:
        scheduler._dispatch_event(event)
    return events


@pytest.mark.parametrize("job_id", ["daily-cycle", "send-report"])
@pytest.mark.parametrize("delay", [1.530672, 299])
def test_brief_host_delay_still_executes_job(monkeypatch, scheduler, job_id, delay):
    instance, calls = scheduler
    events = execute_late_job(monkeypatch, instance, job_id, delay)
    assert calls == [job_id]
    assert [event.code for event in events] == [EVENT_JOB_EXECUTED]


def test_expired_job_is_skipped_and_logged_as_error(monkeypatch, scheduler, caplog):
    instance, calls = scheduler
    with caplog.at_level(logging.INFO, logger="main"):
        events = execute_late_job(monkeypatch, instance, "daily-cycle", 301)
    assert calls == []
    assert [event.code for event in events] == [EVENT_JOB_MISSED]
    assert "daily-cycle" in caplog.text
    assert "2026-09-22T18:00:00-03:00" in caplog.text
    assert "tolerância de 300s" in caplog.text
    assert "finalizou com sucesso" not in caplog.text
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_overlapping_run_is_logged_as_error(scheduler, caplog):
    instance, _ = scheduler
    event = JobSubmissionEvent(
        EVENT_JOB_MAX_INSTANCES, "daily-cycle", "default",
        [datetime(2026, 9, 22, 21, tzinfo=timezone.utc)],
    )
    with caplog.at_level(logging.ERROR, logger="main"):
        instance._dispatch_event(event)
    assert "execução anterior ainda ativa" in caplog.text


@pytest.mark.parametrize("job_id,utc_hour", [("daily-cycle", 21), ("send-report", 11)])
def test_weekday_jobs_use_sao_paulo_time(scheduler, job_id, utc_hour):
    instance, _ = scheduler
    job = instance.get_job(job_id)
    tuesday = datetime(2026, 9, 22, tzinfo=timezone.utc)
    saturday = datetime(2026, 9, 26, tzinfo=timezone.utc)
    assert job.trigger.get_next_fire_time(None, tuesday).astimezone(timezone.utc) == (
        tuesday.replace(hour=utc_hour)
    )
    assert job.trigger.get_next_fire_time(None, saturday).astimezone(timezone.utc) == (
        datetime(2026, 9, 28, utc_hour, tzinfo=timezone.utc)
    )
    assert job.coalesce is True
    assert job.max_instances == 1
