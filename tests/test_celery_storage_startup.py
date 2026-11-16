"""The Celery worker refuses to start with a bad storage configuration."""

from __future__ import annotations

import pytest
from platform_service import celery_app
from platform_service.config import Settings
from platform_service.objectstore import gcp_identity
from pydantic_settings import SettingsConfigDict


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Settings, "model_config", SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore")
    )
    for name in ("MICROCOACHING_STORAGE_PROVIDER", "MICROCOACHING_STORAGE_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    # The handler would otherwise install the service's own log handlers and bypass caplog.
    monkeypatch.setattr(celery_app, "_configure_worker_logging", lambda **kwargs: None)
    monkeypatch.setattr(celery_app.logger, "propagate", True)
    monkeypatch.setattr(gcp_identity.GcpMetadataToken, "__call__", lambda self: "token-from-sa")


def test_worker_exits_when_storage_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Celery swallows ordinary exceptions from signal handlers, so the handler must exit."""
    monkeypatch.setattr(celery_app, "get_settings", lambda: Settings())
    with caplog.at_level("CRITICAL"), pytest.raises(SystemExit) as raised:
        celery_app._on_worker_init()
    assert raised.value.code == 1
    assert "MICROCOACHING_STORAGE_PROVIDER is required" in caplog.text


def test_worker_logs_the_storage_line_when_configured(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(microcoaching_storage_provider="gcs", microcoaching_storage_bucket="bucket")
    monkeypatch.setattr(celery_app, "get_settings", lambda: settings)
    with caplog.at_level("INFO"):
        celery_app._on_worker_init()
    assert "object storage ready: provider=gcs bucket=bucket" in caplog.text
    assert "links=attached service account" in caplog.text
