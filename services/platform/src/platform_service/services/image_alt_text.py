"""Helpers for source_image.alt_text quality, clipping, and LLM parse."""

import json
import re

from platform_service.services.llm_text_utils import strip_code_fence

_PLACEHOLDER_ALT_RE = re.compile(
    r"^(?:picture|image|graphic|photo|slide|figure)\s*\d*$",
    re.IGNORECASE,
)
_VISIBLE_BLOCK_RE = re.compile(
    r"VISIBLE_TEXT:\s*(.*?)(?=DESCRIPTION:|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_BLOCK_RE = re.compile(
    r"DESCRIPTION:\s*(.*)\Z",
    re.IGNORECASE | re.DOTALL,
)
_JSON_TEXT_KEYS = ("alt_text", "text", "content", "markdown")
_IMAGE_ALT_MAX_CHARS = 1000


def is_usable_image_alt(text: str | None) -> bool:
    """True when alt is non-empty and not a generic Office shape name."""
    if text is None:
        return False
    cleaned = " ".join(text.split())
    if not cleaned:
        return False
    return _PLACEHOLDER_ALT_RE.fullmatch(cleaned) is None


def clip_image_alt_text(text: str | None, *, max_chars: int = _IMAGE_ALT_MAX_CHARS) -> str | None:
    if text is None:
        return None
    cleaned = "\n".join(line.strip() for line in text.strip().splitlines() if line.strip())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _join_visible_and_description(visible: str | None, description: str | None) -> str:
    parts: list[str] = []
    if visible is not None:
        vis = visible.strip()
        if vis:
            parts.append(vis)
    if description is not None:
        desc = description.strip()
        if desc:
            parts.append(desc)
    return "\n".join(parts).strip()


def _from_json_object(obj: dict[str, object]) -> str | None:
    visible = obj.get("visible_text")
    if not isinstance(visible, str):
        visible = obj.get("VISIBLE_TEXT")
    description = obj.get("description")
    if not isinstance(description, str):
        description = obj.get("DESCRIPTION")
    visible_s = visible if isinstance(visible, str) else None
    description_s = description if isinstance(description, str) else None
    combined = _join_visible_and_description(visible_s, description_s)
    if combined:
        return combined
    for key in _JSON_TEXT_KEYS:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            if parts:
                return "\n".join(parts)
    return None


def parse_image_text_response(raw: str) -> str:
    """Turn an LLM figure-text response into a single alt_text candidate.

    Does not run page-markdown heading normalization.
    """
    s = strip_code_fence(raw).strip()
    if not s:
        return ""
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            from_json = _from_json_object(obj)
            if from_json:
                return from_json
    if re.search(r"VISIBLE_TEXT:|DESCRIPTION:", s, re.IGNORECASE):
        visible_match = _VISIBLE_BLOCK_RE.search(s)
        description_match = _DESCRIPTION_BLOCK_RE.search(s)
        visible = visible_match.group(1) if visible_match else None
        description = description_match.group(1) if description_match else None
        combined = _join_visible_and_description(visible, description)
        if combined:
            return combined
        return ""
    return s
