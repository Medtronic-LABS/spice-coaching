"""Map DB storage references to sync-facing object names."""

from __future__ import annotations

from mc_foundation.objectstore import looks_like_object_storage_storage_path


def sync_object_name(ref: str | None, *, bucket_name: str) -> str | None:
    """Return an object key for sync payloads, or ``None`` when not syncable.

    - ``{bucket_name}/{object_key}`` → ``object_key``
    - Absolute filesystem paths → ``None``
    - Blank / ``None`` → ``None``
    - Already-relative object keys → returned as-is
    """
    if ref is None:
        return None
    clean = str(ref).strip()
    if not clean:
        return None
    if clean.startswith("/") or clean.startswith("~"):
        return None
    # Windows-style absolute path (e.g. C:\\...)
    if len(clean) >= 3 and clean[1] == ":" and clean[2] in ("/", "\\"):
        return None
    if looks_like_object_storage_storage_path(clean, bucket_name=bucket_name):
        return clean[len(bucket_name) + 1 :]
    return clean


def is_batch_presign_object_name(ref: str, *, bucket_name: str) -> bool:
    """True when ``ref`` is acceptable input for ``POST /sync/presigned-urls``.

    Object names only: reject blank, filesystem paths, and full ``bucket/key`` refs.
    """
    clean = str(ref).strip()
    if not clean:
        return False
    if clean.startswith("/") or clean.startswith("~"):
        return False
    if len(clean) >= 3 and clean[1] == ":" and clean[2] in ("/", "\\"):
        return False
    if looks_like_object_storage_storage_path(clean, bucket_name=bucket_name):
        return False
    return True
