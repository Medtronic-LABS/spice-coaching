"""Deterministic prose for dashboard module demand summaries."""

from __future__ import annotations

from datetime import date

from mc_contracts.dashboard import ModuleDemandPatternItem, ModuleDemandSummaryResponse

_MONTH_ABBREV = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_EN_DASH = "\u2013"
_TITLE = "Insights from Module Usage"

_BUCKET_ASSIGN = "assign"
_BUCKET_PUBLISH = "publish"
_BUCKET_CREATE = "create"

_TIE_RANK = {
    _BUCKET_ASSIGN: 0,
    _BUCKET_PUBLISH: 1,
    _BUCKET_CREATE: 2,
}

_LEGEND: dict[str, tuple[str, str]] = {
    _BUCKET_ASSIGN: (
        "Existing coverage",
        "Demand is concentrated around a few published modules",
    ),
    _BUCKET_PUBLISH: (
        "Ready to publish",
        "Some unanswered demand already has draft content",
    ),
    _BUCKET_CREATE: (
        "Content gaps",
        "Remaining demand represents opportunities for new modules",
    ),
}

_SCREENSHOT_ORDER = (_BUCKET_ASSIGN, _BUCKET_PUBLISH, _BUCKET_CREATE)
_SCREENSHOT_NARRATIVE = (
    "Most demand can be addressed with existing or draft content. "
    "Prioritize assigning high-demand published modules, publish matching drafts "
    "to close immediate gaps, and create new content only for topics with no existing coverage."
)


def _format_month_day(value: date, *, include_year: bool) -> str:
    month = _MONTH_ABBREV[value.month - 1]
    if include_year:
        return f"{month} {value.day}, {value.year}"
    return f"{month} {value.day}"


def _format_date_range(from_date: date, to_date: date) -> str:
    if from_date == to_date:
        return _format_month_day(from_date, include_year=True)
    if from_date.year != to_date.year:
        start = _format_month_day(from_date, include_year=True)
        end = _format_month_day(to_date, include_year=True)
        return f"{start}{_EN_DASH}{end}"
    if from_date.month == to_date.month:
        month = _MONTH_ABBREV[from_date.month - 1]
        return f"{month} {from_date.day}{_EN_DASH}{to_date.day}, {from_date.year}"
    start_month = _MONTH_ABBREV[from_date.month - 1]
    end_month = _MONTH_ABBREV[to_date.month - 1]
    return f"{start_month} {from_date.day}{_EN_DASH}{end_month} {to_date.day}, {from_date.year}"


def _ordered_buckets(
    assign_volume: int,
    publish_volume: int,
    create_volume: int,
) -> list[str]:
    scored = [
        (_BUCKET_ASSIGN, assign_volume),
        (_BUCKET_PUBLISH, publish_volume),
        (_BUCKET_CREATE, create_volume),
    ]
    present = [(name, volume) for name, volume in scored if volume > 0]
    present.sort(key=lambda item: (-item[1], _TIE_RANK[item[0]]))
    return [name for name, _ in present]


def _opening(ordered: list[str]) -> str:
    kinds = set(ordered)
    if ordered[0] == _BUCKET_CREATE:
        return "Most demand represents opportunities for new modules."
    if _BUCKET_ASSIGN in kinds and _BUCKET_PUBLISH in kinds:
        return "Most demand can be addressed with existing or draft content."
    if ordered[0] == _BUCKET_ASSIGN:
        return "Most demand can be addressed with existing published modules."
    return "Most demand can be addressed with draft content ready to publish."


def _clause(bucket: str, *, is_last: bool) -> str:
    if bucket == _BUCKET_ASSIGN:
        return "assigning high-demand published modules"
    if bucket == _BUCKET_PUBLISH:
        return "publishing matching drafts to close immediate gaps"
    if is_last:
        return "creating new content only for topics with no existing coverage"
    return "creating new modules for uncovered topics"


def _prioritize_sentence(ordered: list[str]) -> str:
    last_index = len(ordered) - 1
    clauses = [_clause(bucket, is_last=index == last_index) for index, bucket in enumerate(ordered)]
    if len(clauses) == 1:
        return f"Prioritize {clauses[0]}."
    if len(clauses) == 2:
        return f"Prioritize {clauses[0]} and {clauses[1]}."
    return f"Prioritize {clauses[0]}, {clauses[1]}, and {clauses[2]}."


def _narrative(ordered: list[str]) -> str:
    if tuple(ordered) == _SCREENSHOT_ORDER:
        return _SCREENSHOT_NARRATIVE
    return f"{_opening(ordered)} {_prioritize_sentence(ordered)}"


def _demand_pattern(ordered: list[str]) -> list[ModuleDemandPatternItem]:
    return [
        ModuleDemandPatternItem(
            bucket=bucket,
            title=_LEGEND[bucket][0],
            description=_LEGEND[bucket][1],
        )
        for bucket in ordered
    ]


def build_module_demand_summary(
    *,
    from_date: date,
    to_date: date,
    assign_volume: int,
    publish_volume: int,
    create_volume: int,
) -> ModuleDemandSummaryResponse:
    """Build a leverage-ordered executive summary from full category volumes."""
    date_label = _format_date_range(from_date, to_date)
    ordered = _ordered_buckets(assign_volume, publish_volume, create_volume)
    if not ordered:
        return ModuleDemandSummaryResponse(
            from_date=from_date,
            to_date=to_date,
            title=_TITLE,
            date_label=date_label,
            narrative=None,
            empty_message=f"No module demand for your team in {date_label}.",
            demand_pattern=[],
        )

    return ModuleDemandSummaryResponse(
        from_date=from_date,
        to_date=to_date,
        title=_TITLE,
        date_label=date_label,
        narrative=_narrative(ordered),
        empty_message=None,
        demand_pattern=_demand_pattern(ordered),
    )
