#!/usr/bin/env -S uv run python
"""Enqueue the weekly chat FAQ aggregation Celery task.

Hands off to ``platform.aggregate_chat_faqs``, which queries ClickHouse for
``digital_help_used`` questions, clusters them via ai-runtime, synthesizes
bilingual FAQs, and replaces ``chat_frequent_question`` rows per tenant.

Prerequisites:

1. ``REDIS_URL`` so Celery can enqueue the task.
2. A Celery worker running with ``platform.aggregate_chat_faqs`` registered.
3. Worker env must have ``DATABASE_URL``, ClickHouse, and ai-runtime access.

Usage:
    uv run python bin/aggregate_chat_faqs.py [--dry-run]

Examples:
    # Print what would be enqueued
    uv run python bin/aggregate_chat_faqs.py --dry-run

    # Enqueue the job
    uv run python bin/aggregate_chat_faqs.py
"""

from __future__ import annotations

import argparse

from platform_service.celery_tasks import aggregate_chat_faqs_task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the task name without enqueueing",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run: would enqueue platform.aggregate_chat_faqs")
        return 0

    result = aggregate_chat_faqs_task.delay()
    print(f"Enqueued platform.aggregate_chat_faqs task_id={result.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
