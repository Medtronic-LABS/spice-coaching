"""Celery application configuration for platform_service.

Redis is used as the broker. We intentionally do not configure a Celery result
backend — task outcomes are observable via the rows the workers write (e.g.
`module.lifecycle_status`, `ingestion_run_step.status`). Polling a result
backend on top of that is duplication.

Task registry: `celery_tasks.py` (the `include` argument below). Beat schedule
entries are added per-task as they come online (e.g. embedding/quiz post-publish
workers). The post-publish jobs are event-triggered, not scheduled, so the beat
schedule is empty by default.
"""

from __future__ import annotations

import asyncio
import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import (
    beat_init,
    worker_init,
    worker_process_init,
    worker_process_shutdown,
)
from celery.signals import (
    setup_logging as celery_setup_logging,
)
from mc_foundation.logging import reset_logging, setup_logging

from platform_service.config import get_settings
from platform_service.db.base import dispose_all_engines, reset_engine_caches
from platform_service.deps import shutdown_clients

logger = logging.getLogger(__name__)


def create_celery_app() -> Celery:
    settings = get_settings()

    app = Celery(
        "platform_service",
        broker=settings.redis_url,
        include=["platform_service.celery_tasks"],
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        enable_utc=True,
        timezone="UTC",
        task_track_started=True,
        # Own logging via the setup_logging signal below. Leaving Celery's
        # defaults on lets it redirect sys.stdout to LoggingProxy; our
        # StreamHandler then writes into that proxy and messages are dropped
        # by recurse protection — so app logger.info inside tasks vanishes
        # while Celery's own "task received" lines (bound to sys.__stderr__)
        # still appear.
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
        beat_schedule={
            "drain-telemetry-buffer": {
                "task": "platform.drain_telemetry_buffer",
                "schedule": float(settings.telemetry_buffer_drain_interval_seconds),
            },
            "aggregate-chat-faqs": {
                "task": "platform.aggregate_chat_faqs",
                "schedule": crontab(
                    hour=settings.chat_faq_weekly_hour_utc,
                    minute=0,
                    day_of_week=settings.chat_faq_weekly_day_of_week,
                ),
            },
            "aggregate-chat-feedback-summary": {
                "task": "platform.aggregate_chat_feedback_summary",
                "schedule": crontab(
                    hour=settings.chat_feedback_summary_weekly_hour_utc,
                    minute=0,
                    day_of_week=settings.chat_feedback_summary_weekly_day_of_week,
                ),
            },
            "refresh-module-creation-suggestions": {
                "task": "platform.refresh_module_creation_suggestions",
                "schedule": crontab(
                    hour=settings.module_creation_suggestions_daily_hour_utc,
                    minute=0,
                ),
            },
        },
    )

    return app


celery_app = create_celery_app()


def _configure_worker_logging(*, include_pid: bool) -> None:
    settings = get_settings()
    setup_logging(
        service_name=settings.log_service_name or settings.app_name,
        log_level=settings.log_level,
        json_logs=settings.log_json,
        app_env=settings.app_env,
        log_dir=settings.log_dir,
        log_role="worker",
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
        include_pid=include_pid,
    )


@celery_setup_logging.connect
def _on_celery_setup_logging(**_kwargs: object) -> None:
    """Claim logging so Celery skips its root/handler/stdout-redirect setup."""
    reset_logging()
    _configure_worker_logging(include_pid=False)


@worker_init.connect
def _on_worker_init(**_kwargs: object) -> None:
    # setup_logging signal usually already configured us; re-apply if needed.
    if not getattr(logging.getLogger(), "_mc_configured", False):
        _configure_worker_logging(include_pid=False)


@beat_init.connect
def _on_beat_init(**_kwargs: object) -> None:
    if not getattr(logging.getLogger(), "_mc_configured", False):
        _configure_worker_logging(include_pid=False)


@worker_process_init.connect
def _on_worker_process_init(**_kwargs: object) -> None:
    """Post-fork: reopen log files, dispose inherited SQLAlchemy pools, reset engine caches."""
    reset_logging()
    _configure_worker_logging(include_pid=True)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(dispose_all_engines())
    finally:
        loop.close()
    reset_engine_caches()
    logger.debug("Celery worker process init: engine pools disposed and caches reset")


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**_kwargs: object) -> None:
    """Release httpx pools and DB engines before the worker child exits."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(shutdown_clients())
    finally:
        loop.close()
    logger.debug("Celery worker process shutdown: shared clients closed")
