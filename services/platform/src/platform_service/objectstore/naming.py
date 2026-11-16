"""Pure helpers for object keys, metadata, endpoints and download headers (no storage SDK)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

from mc_foundation.objectstore import safe_basename

_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_ASCII_EXT = re.compile(r"^[A-Za-z0-9]{1,10}$")
NOT_FOUND_CODES = frozenset({"404", "NoSuchBucket", "NoSuchKey", "NotFound", "404 Not Found"})


def ascii_safe_object_basename(name: str) -> str:
    """Basename safe for S3 object keys and SigV4 HTTP headers (ASCII only)."""
    base = safe_basename(name)
    stem, dot, ext = base.rpartition(".")
    if not stem or not dot or not _ASCII_EXT.fullmatch(ext):
        stem, ext = base, ""
    else:
        ext = f".{ext}"

    normalised = unicodedata.normalize("NFKD", stem)
    ascii_stem = normalised.encode("ascii", "ignore").decode("ascii")
    ascii_stem = _UNSAFE_KEY_CHARS.sub("_", ascii_stem).strip("._") or "file"
    ascii_ext = ext.encode("ascii", "ignore").decode("ascii")
    ascii_ext = re.sub(r"[^A-Za-z0-9.]", "", ascii_ext)
    return f"{ascii_stem}{ascii_ext}"


def ascii_safe_object_key(object_name: str) -> str:
    """Keep path prefixes; ASCII-sanitise only the final key segment."""
    parts = object_name.split("/")
    parts[-1] = ascii_safe_object_basename(parts[-1])
    return "/".join(parts)


def ascii_safe_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Percent-encode non-ASCII metadata values (S3 user metadata is ASCII-only)."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        text = str(value)
        try:
            text.encode("ascii")
        except UnicodeEncodeError:
            text = quote(text, safe="")
        out[str(key)] = text
    return out


def endpoint_url(endpoint: str | None) -> str | None:
    """Normalise a storage endpoint to ``scheme://host[:port]``; ``None`` when empty.

    A bare host means HTTPS. Plain HTTP (a local MinIO) must be spelled out as ``http://``.
    """
    raw = (endpoint or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"endpoint scheme must be http or https, got {parsed.scheme!r}")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("endpoint must not include a path")
    if not parsed.hostname:
        raise ValueError("endpoint is invalid")
    if parsed.username or parsed.password:
        raise ValueError("endpoint must not contain credentials")
    return f"{parsed.scheme}://{parsed.netloc}"


def content_disposition_for(object_name: str, *, inline: bool, download_filename: str | None = None) -> str:
    filename = (download_filename or PurePosixPath(object_name).name).strip()
    if not filename:
        filename = PurePosixPath(object_name).name
    disp = "inline" if inline else "attachment"
    try:
        filename.encode("ascii")
    except UnicodeEncodeError:
        return f"{disp}; filename*=UTF-8''{quote(filename)}"
    return f'{disp}; filename="{filename}"'


def inline_default_for_content_type(content_type: str) -> bool:
    if content_type == "application/pdf":
        return True
    return content_type.startswith(("image/", "video/", "audio/"))
