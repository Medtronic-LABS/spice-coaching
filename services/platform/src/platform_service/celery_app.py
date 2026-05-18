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

from celery import Celery

from platform_service.config import get_settings


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
    )

    return app


celery_app = create_celery_app()
