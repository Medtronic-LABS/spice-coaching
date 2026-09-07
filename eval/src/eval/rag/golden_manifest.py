"""Manifest-based golden dataset loading and compilation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast


def _sanitize_json_control_chars_in_strings(text: str) -> str:
    """Replace raw newlines inside JSON string literals with spaces."""
    result: list[str] = []
    in_string = False
    escape = False
    for char in text:
        if escape:
            result.append(char)
            escape = False
            continue
        if char == "\\" and in_string:
            result.append(char)
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
        if in_string and char in "\n\r":
            result.append(" ")
            continue
        result.append(char)
    return "".join(result)


def loads_golden_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_sanitize_json_control_chars_in_strings(text))


def load_json_array(path: Path) -> list[object]:
    raw = loads_golden_json(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Golden dataset must be a JSON array: {path}")
    return raw


def is_manifest_path(path: Path) -> bool:
    return path.name.endswith(".manifest.json")


def manifest_base_dir(path: Path) -> Path:
    return path.parent


def load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Golden manifest not found: {path}")
    raw = loads_golden_json(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Golden manifest must be a JSON object: {path}")
    records = raw.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError(f"Golden manifest must include a non-empty records list: {path}")
    return raw


def resolve_manifest_record_paths(path: Path) -> list[Path]:
    manifest = load_manifest(path)
    base_dir = manifest_base_dir(path)
    record_paths: list[Path] = []
    for entry in manifest["records"]:
        if not isinstance(entry, str):
            raise ValueError(f"Manifest record entries must be strings: {path}")
        record_path = (base_dir / entry).resolve()
        if not record_path.is_file():
            raise FileNotFoundError(f"Manifest record shard not found: {record_path}")
        record_paths.append(record_path)
    return record_paths


def load_manifest_records(path: Path) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    for record_path in resolve_manifest_record_paths(path):
        shard = load_json_array(record_path)
        for idx, item in enumerate(shard):
            if not isinstance(item, dict):
                raise ValueError(f"Record {idx} in {record_path} must be an object")
            merged.append(item)
    return merged


def compile_manifest(path: Path, *, output: Path | None = None) -> Path:
    manifest = load_manifest(path)
    compiled_name = str(manifest.get("compiled_output", "Golden_Dataset.json"))
    out_path = output or (manifest_base_dir(path) / compiled_name)
    records = load_manifest_records(path)
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def load_golden_source_array(path: Path) -> list[object]:
    if is_manifest_path(path):
        return cast(list[object], load_manifest_records(path))
    return load_json_array(path)
