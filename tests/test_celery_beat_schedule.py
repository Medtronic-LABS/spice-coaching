"""Celery Beat schedule invariants."""

from __future__ import annotations

from celery.schedules import crontab
from celery.signals import setup_logging as celery_setup_logging
from platform_service.celery_app import celery_app


def test_aggregate_chat_faqs_runs_weekly_sunday_02_utc() -> None:
    entry = celery_app.conf.beat_schedule["aggregate-chat-faqs"]
    assert entry["task"] == "platform.aggregate_chat_faqs"

    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.hour == {2}
    assert schedule.minute == {0}
    assert schedule.day_of_week == {0}


def test_aggregate_chat_feedback_summary_runs_weekly_sunday_03_utc() -> None:
    entry = celery_app.conf.beat_schedule["aggregate-chat-feedback-summary"]
    assert entry["task"] == "platform.aggregate_chat_feedback_summary"

    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.hour == {3}
    assert schedule.minute == {0}
    assert schedule.day_of_week == {0}


def test_worker_owns_logging_and_disables_stdout_redirect() -> None:
    assert celery_app.conf.worker_hijack_root_logger is False
    assert celery_app.conf.worker_redirect_stdouts is False
    assert celery_setup_logging.receivers
