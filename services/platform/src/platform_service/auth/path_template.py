"""Match request paths to FastAPI-style ``{param}`` path templates."""

from __future__ import annotations


def normalize_relative_path(request_path: str, api_root: str) -> str:
    """Strip ``api_root`` and return a leading-slash path (e.g. ``/admin/modules``)."""
    root = api_root.rstrip("/")
    if root and request_path.startswith(root):
        relative = request_path[len(root) :]
    else:
        relative = request_path
    if not relative.startswith("/"):
        relative = f"/{relative}"
    if relative != "/" and relative.endswith("/"):
        relative = relative.rstrip("/")
    return relative


def _is_param(segment: str) -> bool:
    return len(segment) >= 3 and segment.startswith("{") and segment.endswith("}")


def path_matches_template(path: str, template: str) -> bool:
    """True when ``path`` matches ``template`` segment-for-segment."""
    path_parts = path.strip("/").split("/") if path.strip("/") else []
    template_parts = template.strip("/").split("/") if template.strip("/") else []
    if len(path_parts) != len(template_parts):
        return False
    for path_seg, tmpl_seg in zip(path_parts, template_parts, strict=True):
        if _is_param(tmpl_seg):
            if not path_seg:
                return False
            continue
        if path_seg != tmpl_seg:
            return False
    return True


def _literal_score(template: str) -> tuple[int, int]:
    """Prefer more literal segments, then longer templates (FastAPI static-first)."""
    parts = template.strip("/").split("/") if template.strip("/") else []
    literal = sum(1 for part in parts if not _is_param(part))
    return (literal, len(parts))


def match_path_template(path: str, templates: list[str] | frozenset[str]) -> str | None:
    """Return the best-matching template for ``path``, or None if none match."""
    matches = [tmpl for tmpl in templates if path_matches_template(path, tmpl)]
    if not matches:
        return None
    return max(matches, key=_literal_score)
