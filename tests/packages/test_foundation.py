"""Unit tests for mc_foundation shared helpers."""

from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from mc_foundation.logging import (
    get_access_logger,
    get_audit_logger,
    get_security_logger,
    reset_logging,
    setup_logging,
)
from mc_foundation.request_middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient


async def _ok(_request: Request) -> Response:
    return Response("ok", media_type="text/plain")


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    reset_logging()
    yield
    reset_logging()


def _capture_named(logger_name: str) -> list[logging.LogRecord]:
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.addHandler(_ListHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return records


def _flush_all() -> None:
    loggers = [logging.getLogger(), get_access_logger(), get_audit_logger(), get_security_logger()]
    for logger in loggers:
        for handler in logger.handlers:
            handler.flush()


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class TestSetupLogging:
    def test_second_call_is_idempotent(self) -> None:
        setup_logging(service_name="test-a", log_level="INFO", json_logs=False, app_env="test")
        handler_count = len(logging.getLogger().handlers)
        setup_logging(service_name="test-b", log_level="DEBUG", json_logs=True, app_env="prod")
        assert len(logging.getLogger().handlers) == handler_count

    def test_log_dir_writes_typed_json_files(self, tmp_path: Path) -> None:
        setup_logging(
            service_name="platform-api",
            log_level="INFO",
            json_logs=True,
            app_env="test",
            log_dir=str(tmp_path),
            log_role="http_platform",
            log_max_bytes=1024,
            log_backup_count=3,
        )
        logging.getLogger("platform_service.example").info("hello-app")
        get_access_logger().info("hello-access")
        get_audit_logger().info("hello-audit")
        get_security_logger().warning("hello-security")
        logging.getLogger("platform_service.example").error("hello-error")
        _flush_all()

        expected = {
            "application.platform-api.log",
            "access.platform-api.log",
            "audit.platform-api.log",
            "security.platform-api.log",
            "error.platform-api.log",
        }
        assert expected <= {path.name for path in tmp_path.iterdir()}

        app_line = _read_json_lines(tmp_path / "application.platform-api.log")[0]
        assert app_line["log_type"] == "application"
        assert app_line["service"] == "platform-api"
        assert app_line["message"] == "hello-app"

        access_line = _read_json_lines(tmp_path / "access.platform-api.log")[0]
        assert access_line["log_type"] == "access"
        assert access_line["message"] == "hello-access"

        error_lines = _read_json_lines(tmp_path / "error.platform-api.log")
        assert any(line["message"] == "hello-error" for line in error_lines)
        app_errors = _read_json_lines(tmp_path / "application.platform-api.log")
        assert any(line["message"] == "hello-error" for line in app_errors)

        rotating = [
            handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler)
        ]
        assert rotating
        assert all(handler.maxBytes == 1024 for handler in rotating)
        assert all(handler.backupCount == 3 for handler in rotating)

    def test_include_pid_suffixes_worker_filenames(self, tmp_path: Path) -> None:
        setup_logging(
            service_name="platform-celery-worker",
            json_logs=True,
            app_env="test",
            log_dir=str(tmp_path),
            log_role="worker",
            include_pid=True,
        )
        logging.getLogger("platform_service.celery_tasks").info("worker-hello")
        _flush_all()
        pid = os.getpid()
        worker_file = tmp_path / f"worker.platform-celery-worker.{pid}.log"
        error_file = tmp_path / f"error.platform-celery-worker.{pid}.log"
        assert worker_file.exists()
        assert error_file.exists()
        line = _read_json_lines(worker_file)[0]
        assert line["log_type"] == "worker"
        assert line["message"] == "worker-hello"

    def test_ai_runtime_role_uses_ai_runtime_filename(self, tmp_path: Path) -> None:
        setup_logging(
            service_name="ai-runtime",
            json_logs=True,
            app_env="test",
            log_dir=str(tmp_path),
            log_role="http_ai",
        )
        logging.getLogger("ai_runtime.example").info("runtime-hello")
        _flush_all()
        names = {path.name for path in tmp_path.iterdir()}
        assert "ai-runtime.ai-runtime.log" in names
        assert "application.ai-runtime.log" not in names

    def test_unknown_log_role_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown log_role"):
            setup_logging(log_role="not-a-role")  # type: ignore[arg-type]

    def test_reset_logging_allows_reconfigure(self, tmp_path: Path) -> None:
        setup_logging(service_name="first", log_dir=str(tmp_path), json_logs=True)
        reset_logging()
        setup_logging(
            service_name="second",
            log_dir=str(tmp_path),
            json_logs=True,
            log_role="worker",
        )
        logging.getLogger("x").info("after-reset")
        _flush_all()
        assert (tmp_path / "worker.second.log").exists()

    def test_survives_stdout_replaced_with_logging_proxy(self, tmp_path: Path) -> None:
        """Celery redirects sys.stdout to LoggingProxy; handlers must not follow it."""

        class _DroppingProxy:
            """Minimal stand-in for celery.utils.log.LoggingProxy recurse drop."""

            def __init__(self) -> None:
                self.writes = 0

            def write(self, data: str) -> int:
                self.writes += 1
                return 0

            def flush(self) -> None:
                return None

        proxy = _DroppingProxy()
        original = sys.stdout
        sys.stdout = proxy  # type: ignore[assignment]
        try:
            setup_logging(
                service_name="platform-celery-worker",
                json_logs=True,
                app_env="test",
                log_dir=str(tmp_path),
                log_role="worker",
            )
            logging.getLogger("platform_service.workers.ingest_worker").info(
                "Running pipeline for source_document_id=probe"
            )
            _flush_all()
        finally:
            sys.stdout = original

        worker_file = tmp_path / "worker.platform-celery-worker.log"
        assert worker_file.exists()
        line = _read_json_lines(worker_file)[0]
        assert "Running pipeline" in str(line["message"])
        # StreamHandler must target sys.__stdout__, not the proxy.
        assert proxy.writes == 0


class TestRequestIdMiddleware:
    def test_echoes_request_id_header(self) -> None:
        app = Starlette(
            routes=[Route("/", _ok)],
            middleware=[Middleware(RequestIdMiddleware)],
        )
        client = TestClient(app)
        response = client.get("/", headers={REQUEST_ID_HEADER: "req-abc-123"})
        assert response.headers[REQUEST_ID_HEADER] == "req-abc-123"

    def test_generates_request_id_when_missing(self) -> None:
        app = Starlette(
            routes=[Route("/", _ok)],
            middleware=[Middleware(RequestIdMiddleware)],
        )
        client = TestClient(app)
        response = client.get("/")
        assert REQUEST_ID_HEADER in response.headers
        assert response.headers[REQUEST_ID_HEADER]

    def test_access_log_skips_health_and_ready(self) -> None:
        records = _capture_named("mc.access")
        app = Starlette(
            routes=[
                Route("/health", _ok),
                Route("/ready", _ok),
                Route("/medtronics-api/ready", _ok),
                Route("/admin/modules", _ok),
            ],
            middleware=[Middleware(RequestIdMiddleware)],
        )
        client = TestClient(app)
        client.get("/health")
        client.get("/ready")
        client.get("/medtronics-api/ready")
        client.get("/admin/modules?token=secret")
        assert [record.path for record in records] == ["/admin/modules"]
        record = records[0]
        assert record.method == "GET"
        assert record.status == 200
        assert "?" not in str(record.path)
        assert "token" not in record.getMessage()

    def test_access_log_includes_user_id_when_present(self) -> None:
        records = _capture_named("mc.access")

        class _User:
            id = 42

        class _SetUserMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
                request.state.spice_user = _User()
                return await call_next(request)

        app = Starlette(
            routes=[Route("/admin/modules", _ok)],
            middleware=[
                Middleware(_SetUserMiddleware),
                Middleware(RequestIdMiddleware, service_name="platform-api"),
            ],
        )
        client = TestClient(app)
        client.get("/admin/modules")
        assert len(records) == 1
        assert records[0].user_id == 42
        assert records[0].service == "platform-api"
