"""``create_object_store`` picks the store from the provider setting."""

from __future__ import annotations

import pytest
from platform_service.config import Settings
from platform_service.objectstore import gcp_identity
from platform_service.objectstore.config import StorageConfigError
from platform_service.objectstore.factory import announce_object_store, create_object_store
from platform_service.objectstore.gcs_store import GcsObjectStore
from platform_service.objectstore.minio_store import MinioObjectStore
from platform_service.objectstore.s3_store import S3ObjectStore
from pydantic_settings import SettingsConfigDict

LEGACY = ("OBJECT_STORAGE_BACKEND", "OBJECT_STORAGE_BUCKET_NAME", "OBJECT_STORAGE_AUTH")


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Settings, "model_config", SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore")
    )
    for name in LEGACY:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gcp_identity.GcpMetadataToken, "__call__", lambda self: "token-from-sa")


def _settings(**storage: object) -> Settings:
    return Settings(**{f"microcoaching_storage_{name}": value for name, value in storage.items()})


@pytest.mark.parametrize(
    ("storage", "expected"),
    [
        (
            {"provider": "minio", "endpoint": "http://minio:9000", "access_key": "k", "secret_key": "s"},
            MinioObjectStore,
        ),
        ({"provider": "s3"}, S3ObjectStore),
        ({"provider": "gcs"}, GcsObjectStore),
        ({"provider": "gcs", "access_key": "k", "secret_key": "s"}, GcsObjectStore),
    ],
)
def test_provider_selects_the_store(storage: dict[str, object], expected: type) -> None:
    store = create_object_store(settings=_settings(bucket="bucket", **storage))
    assert type(store) is expected
    assert store.bucket_name == "bucket"
    assert store.allowed_prefixes == frozenset(
        {"uploads", "source-documents", "media", "ingest", "module-thumbnails"}
    )
    store.close()


def test_building_a_store_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    """Services build a store per instance; only the start-up paths announce it."""
    with caplog.at_level("INFO"):
        create_object_store(settings=_settings(provider="gcs", bucket="bucket")).close()
    assert caplog.text == ""


def test_announcement_has_no_credentials(caplog: pytest.LogCaptureFixture) -> None:
    storage = {
        "provider": "gcs",
        "bucket": "bucket",
        "access_key": "example-access-key",
        "secret_key": "example-secret-key",
    }
    store = create_object_store(settings=_settings(**storage))
    with caplog.at_level("INFO"):
        announce_object_store(store)
    assert "object storage ready: provider=gcs bucket=bucket" in caplog.text
    assert "links=HMAC key" in caplog.text
    assert "example-access-key" not in caplog.text
    assert "example-secret-key" not in caplog.text
    store.close()


def test_unconfigured_storage_fails_naming_the_setting() -> None:
    with pytest.raises(StorageConfigError, match="MICROCOACHING_STORAGE_PROVIDER is required"):
        create_object_store(settings=_settings())


def test_only_pre_rename_variables_fails_and_names_each_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard cut: the old names are not read, and the error says what to rename."""
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "minio")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET_NAME", "bucket")
    monkeypatch.setenv("OBJECT_STORAGE_AUTH", "gcp")
    with pytest.raises(StorageConfigError) as raised:
        create_object_store(settings=Settings())
    message = str(raised.value)
    assert "OBJECT_STORAGE_BACKEND -> MICROCOACHING_STORAGE_PROVIDER" in message
    assert "OBJECT_STORAGE_BUCKET_NAME -> MICROCOACHING_STORAGE_BUCKET" in message
    assert "OBJECT_STORAGE_AUTH (remove; no longer used)" in message


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_deployed_env_with_only_pre_rename_variables_still_gets_the_rename_hints(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    """Settings must load so that the storage error, with its hints, is the one the operator sees."""
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "minio")
    settings = Settings(
        app_env=app_env,
        database_password="secure-password",
        ai_runtime_token="prod-token",
        spice_auth_enabled=True,
        cors_allow_origins="https://app.example.com",
    )
    with pytest.raises(StorageConfigError, match="OBJECT_STORAGE_BACKEND -> MICROCOACHING_STORAGE_PROVIDER"):
        create_object_store(settings=settings)


def test_leftover_pre_rename_variables_are_ignored_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """During a rollout both sets exist; the new names win and the old ones are reported."""
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "minio")
    store = create_object_store(settings=_settings(provider="gcs", bucket="bucket"))
    assert type(store) is GcsObjectStore
    with caplog.at_level("WARNING"):
        announce_object_store(store)
    assert "OBJECT_STORAGE_BACKEND -> MICROCOACHING_STORAGE_PROVIDER" in caplog.text
    store.close()
