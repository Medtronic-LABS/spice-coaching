"""Deterministic prose for dashboard module demand summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from mc_contracts.dashboard import DigitalHelpModuleUsageItem
from mc_contracts.localized import LocalizedString

from platform_service.services.module_creation_suggestion_classifier import (
    SUGGESTION_KIND_MATCHED_DRAFT,
    SUGGESTION_KIND_PROPOSED_TOPIC,
)


@dataclass(frozen=True)
class AggregatedCreationDemand:
    suggestion_kind: str
    display_title: str
    matched_module_id: UUID | None
    question_count: int
    request_count: int
    evidence_count: int


def _display_title_from_localized(title: LocalizedString | None, *, fallback: str = "Untitled module") -> str:
    if not title:
        return fallback
    for key in ("en", "bn"):
        value = title.get(key)
        if value and value.strip():
            return value.strip()
    for value in title.values():
        if value and str(value).strip():
            return str(value).strip()
    return fallback


def _format_date_range(from_date: date, to_date: date) -> str:
    if from_date == to_date:
        return from_date.isoformat()
    return f"{from_date.isoformat()} to {to_date.isoformat()}"


def _format_usage_item(item: DigitalHelpModuleUsageItem) -> str:
    title = _display_title_from_localized(item.title)
    parts: list[str] = []
    if item.digital_help_count:
        parts.append(f"{item.digital_help_count} digital-help")
    if item.module_requested_count:
        label = "request" if item.module_requested_count == 1 else "requests"
        parts.append(f"{item.module_requested_count} {label}")
    if not parts:
        return title
    return f"{title} ({', '.join(parts)})"


def _format_creation_item(item: AggregatedCreationDemand) -> str:
    if item.suggestion_kind == SUGGESTION_KIND_MATCHED_DRAFT:
        prefix = "Finish draft"
    elif item.suggestion_kind == SUGGESTION_KIND_PROPOSED_TOPIC:
        prefix = "Create"
    else:
        prefix = "Add"

    detail_parts: list[str] = []
    if item.request_count:
        label = "request" if item.request_count == 1 else "requests"
        detail_parts.append(f"{item.request_count} {label}")
    if item.question_count:
        label = "question" if item.question_count == 1 else "questions"
        detail_parts.append(f"{item.question_count} {label}")
    if not detail_parts:
        detail_parts.append(f"{item.evidence_count} evidence")
    return f"{prefix} {item.display_title} ({', '.join(detail_parts)})"


def build_module_demand_text_summary(
    *,
    from_date: date,
    to_date: date,
    usage_modules: list[DigitalHelpModuleUsageItem],
    creation_demand: list[AggregatedCreationDemand],
) -> str:
    """Build a short narrative summary from ranked usage and creation demand."""
    date_label = _format_date_range(from_date, to_date)
    has_usage = bool(usage_modules)
    has_creation = bool(creation_demand)

    if not has_usage and not has_creation:
        return f"No module usage or creation demand was recorded for your team between {date_label}."

    paragraphs: list[str] = []
    if has_usage:
        formatted = "; ".join(_format_usage_item(item) for item in usage_modules)
        paragraphs.append(f"Between {date_label}, CHWs in your scope used digital help most on: {formatted}.")
    if has_creation:
        formatted = "; ".join(_format_creation_item(item) for item in creation_demand)
        paragraphs.append(f"Unattributed demand suggests modules to add or finish: {formatted}.")
    return " ".join(paragraphs)
