"""Shared FastAPI query-parameter normalization helpers."""

from __future__ import annotations

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError


def normalize_csv_query_values(raw: list[str] | None) -> list[str] | None:
    """Accept repeated params and/or comma-separated values; dedupe, preserve order."""
    if not raw:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        for part in item.split(","):
            token = part.strip()
            if token and token not in seen:
                seen.add(token)
                out.append(token)
    return out or None


def normalize_int_csv_query_values(
    raw: list[str] | None,
    *,
    param_name: str,
) -> list[int] | None:
    """Parse repeated/comma-separated integer query values; 422 on invalid tokens."""
    tokens = normalize_csv_query_values(raw)
    if tokens is None:
        return None
    out: list[int] = []
    invalid: list[str] = []
    for token in tokens:
        try:
            out.append(int(token))
        except ValueError:
            invalid.append(token)
    if invalid:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"{param_name} must be integer id(s); got invalid: {', '.join(invalid)}",
            status=422,
        )
    return out
