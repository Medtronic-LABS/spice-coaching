"""Structured JSON logging — shared setup for all services."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal, TypeVar

from pythonjsonlogger.json import JsonFormatter

ACCESS_LOGGER_NAME = "mc.access"
AUDIT_LOGGER_NAME = "mc.audit"
SECURITY_LOGGER_NAME = "mc.security"

LogRole = Literal["http_platform", "http_ai", "worker"]

_NAMED_LOGGERS: tuple[str, ...] = (
    ACCESS_LOGGER_NAME,
    AUDIT_LOGGER_NAME,
    SECURITY_LOGGER_NAME,
)

_NAMED_LOG_TYPE_BY_LOGGER: dict[str, str] = {
    ACCESS_LOGGER_NAME: "access",
    AUDIT_LOGGER_NAME: "audit",
    SECURITY_LOGGER_NAME: "security",
}

_PRIMARY_LOG_TYPE_BY_ROLE: dict[str, str] = {
    "http_platform": "application",
    "http_ai": "ai-runtime",
    "worker": "worker",
}

# File types emitted for each process role (named types besides the primary).
_FILE_TYPES_BY_ROLE: dict[str, tuple[str, ...]] = {
    "http_platform": ("application", "access", "audit", "security", "error"),
    "http_ai": ("ai-runtime", "access", "security", "error"),
    "worker": ("worker", "error"),
}

_DEFAULT_MAX_BYTES = 50_000_000
_DEFAULT_BACKUP_COUNT = 10

_HandlerT = TypeVar("_HandlerT", bound=logging.Handler)


def get_access_logger() -> logging.Logger:
    return logging.getLogger(ACCESS_LOGGER_NAME)


def get_audit_logger() -> logging.Logger:
    return logging.getLogger(AUDIT_LOGGER_NAME)


def get_security_logger() -> logging.Logger:
    return logging.getLogger(SECURITY_LOGGER_NAME)


def reset_logging() -> None:
    """Drop handlers so ``setup_logging`` can run again (fork / tests)."""
    root = logging.getLogger()
    _close_and_clear(root)
    if hasattr(root, "_mc_configured"):
        delattr(root, "_mc_configured")
    for name in _NAMED_LOGGERS:
        named = logging.getLogger(name)
        _close_and_clear(named)
        named.propagate = True


def setup_logging(
    *,
    service_name: str = "microcoaching",
    log_level: str = "INFO",
    json_logs: bool = True,
    app_env: str = "development",
    log_dir: str | None = None,
    log_role: LogRole = "http_platform",
    log_max_bytes: int = _DEFAULT_MAX_BYTES,
    log_backup_count: int = _DEFAULT_BACKUP_COUNT,
    include_pid: bool = False,
) -> None:
    """Configure the root logger and typed named loggers once per process.

    Safe to call multiple times: the first call wins and subsequent calls are
    no-ops. Call :func:`reset_logging` first after a Celery fork. Always writes
    JSON (or text) to stdout. When ``log_dir`` is set, also writes size-rotated
    files per log type, suffixed by ``service_name``.
    """
    root = logging.getLogger()
    root.setLevel(log_level.upper())

    if getattr(root, "_mc_configured", False):
        return

    if log_role not in _PRIMARY_LOG_TYPE_BY_ROLE:
        raise ValueError(f"unknown log_role: {log_role!r}")

    resolved_dir = log_dir.strip() if isinstance(log_dir, str) else log_dir
    if not resolved_dir:
        resolved_dir = None

    primary_type = _PRIMARY_LOG_TYPE_BY_ROLE[log_role]
    file_types = _FILE_TYPES_BY_ROLE[log_role]

    # Prefer the real process streams. Celery (and similar) may replace
    # sys.stdout with a LoggingProxy; writing into that proxy from a
    # StreamHandler recurses and drops the record.
    stream = sys.__stdout__ if hasattr(sys, "__stdout__") and sys.__stdout__ else sys.stdout
    stdout = _build_handler(
        logging.StreamHandler(stream),
        json_logs=json_logs,
        service_name=service_name,
        app_env=app_env,
        log_type=primary_type,
    )
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(stdout)

    error_file_handler: logging.Handler | None = None
    if resolved_dir is not None:
        directory = Path(resolved_dir)
        directory.mkdir(parents=True, exist_ok=True)
        if primary_type in file_types:
            root.addHandler(
                _build_file_handler(
                    directory,
                    log_type=primary_type,
                    service_name=service_name,
                    include_pid=include_pid,
                    json_logs=json_logs,
                    app_env=app_env,
                    max_bytes=log_max_bytes,
                    backup_count=log_backup_count,
                )
            )
        if "error" in file_types:
            error_file_handler = _build_file_handler(
                directory,
                log_type="error",
                service_name=service_name,
                include_pid=include_pid,
                json_logs=json_logs,
                app_env=app_env,
                max_bytes=log_max_bytes,
                backup_count=log_backup_count,
            )
            error_file_handler.setLevel(logging.ERROR)
            root.addHandler(error_file_handler)

    for logger_name, log_type in _NAMED_LOG_TYPE_BY_LOGGER.items():
        named = logging.getLogger(logger_name)
        named.propagate = False
        named.setLevel(log_level.upper())
        _close_and_clear(named)
        named.addHandler(
            _build_handler(
                logging.StreamHandler(stream),
                json_logs=json_logs,
                service_name=service_name,
                app_env=app_env,
                log_type=log_type,
            )
        )
        if resolved_dir is not None and log_type in file_types:
            named.addHandler(
                _build_file_handler(
                    Path(resolved_dir),
                    log_type=log_type,
                    service_name=service_name,
                    include_pid=include_pid,
                    json_logs=json_logs,
                    app_env=app_env,
                    max_bytes=log_max_bytes,
                    backup_count=log_backup_count,
                )
            )
        if error_file_handler is not None:
            named.addHandler(error_file_handler)

    root._mc_configured = True  # type: ignore[attr-defined]


def _build_file_handler(
    directory: Path,
    *,
    log_type: str,
    service_name: str,
    include_pid: bool,
    json_logs: bool,
    app_env: str,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    path = directory / _log_filename(log_type, service_name, include_pid)
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    return _build_handler(
        handler,
        json_logs=json_logs,
        service_name=service_name,
        app_env=app_env,
        log_type=log_type,
    )


def _build_handler(
    handler: _HandlerT,
    *,
    json_logs: bool,
    service_name: str,
    app_env: str,
    log_type: str,
) -> _HandlerT:
    handler.setFormatter(_build_formatter(json_logs, service_name, app_env, log_type))
    return handler


def _build_formatter(
    json_logs: bool,
    service_name: str,
    app_env: str,
    log_type: str,
) -> logging.Formatter:
    if json_logs:
        return JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            static_fields={
                "service": service_name,
                "env": app_env,
                "log_type": log_type,
            },
        )
    return logging.Formatter(
        f"%(asctime)s %(levelname)s %(name)s [{log_type}] %(message)s",
    )


def _log_filename(log_type: str, service_name: str, include_pid: bool) -> str:
    safe_service = service_name.replace("/", "-").replace(os.sep, "-")
    if include_pid:
        return f"{log_type}.{safe_service}.{os.getpid()}.log"
    return f"{log_type}.{safe_service}.log"


def _close_and_clear(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
