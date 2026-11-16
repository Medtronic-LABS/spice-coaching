"""The per-provider rules of ``StorageConfig.from_settings``."""

from __future__ import annotations

import pytest
from platform_service.objectstore.config import (
    GCS_DEFAULT_ENDPOINT,
    LEGACY_ENV_RENAMES,
    StorageConfig,
    StorageConfigError,
    StorageProvider,
    describe_legacy,
    legacy_env_names,
)

from tests.helpers.storage import storage_settings

NO_ENV: dict[str, str] = {}


def _config(**settings: object) -> StorageConfig:
    return StorageConfig.from_settings(storage_settings(**settings), environ=NO_ENV)


def _minio(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "storage_provider": "minio",
        "storage_bucket": "dev-bucket",
        "storage_endpoint": "http://minio:9000",
        "storage_access_key": "k",
        "storage_secret_key": "s",
    }
    base.update(overrides)
    return base


# ─── provider and bucket ────────────────────────────────────────────────────


def test_provider_is_required() -> None:
    with pytest.raises(StorageConfigError, match="MICROCOACHING_STORAGE_PROVIDER is required"):
        _config(storage_bucket="b")


def test_missing_provider_lists_leftover_pre_rename_variables() -> None:
    environ = {"object_storage_backend": "minio", "OBJECT_STORAGE_AUTH": "gcp", "PATH": "/bin"}
    with pytest.raises(StorageConfigError) as raised:
        StorageConfig.from_settings(storage_settings(), environ=environ)
    message = str(raised.value)
    assert "OBJECT_STORAGE_BACKEND -> MICROCOACHING_STORAGE_PROVIDER" in message
    assert "OBJECT_STORAGE_AUTH (remove; no longer used)" in message
    assert "PATH" not in message


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(StorageConfigError, match="must be one of: minio, s3, gcs"):
        _config(storage_provider="azure", storage_bucket="b")


def test_provider_is_case_insensitive() -> None:
    assert _config(storage_provider=" GCS ", storage_bucket="b").provider is StorageProvider.GCS


def test_bucket_is_required() -> None:
    with pytest.raises(StorageConfigError, match="MICROCOACHING_STORAGE_BUCKET is required"):
        _config(storage_provider="gcs")


# ─── keys ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("provider", ["minio", "s3", "gcs"])
@pytest.mark.parametrize("keys", [("k", ""), ("", "s")])
def test_half_a_key_pair_is_rejected(provider: str, keys: tuple[str, str]) -> None:
    settings = _minio(storage_provider=provider, storage_access_key=keys[0], storage_secret_key=keys[1])
    with pytest.raises(StorageConfigError, match="must be set together"):
        _config(**settings)


def test_keys_never_appear_in_repr_or_description() -> None:
    config = _config(**_minio(storage_access_key="example-key", storage_secret_key="example-secret"))
    for text in (repr(config), config.describe()):
        assert "example-key" not in text
        assert "example-secret" not in text
    assert "auth=access key" in config.describe()


# ─── minio ──────────────────────────────────────────────────────────────────


def test_minio_valid() -> None:
    config = _config(**_minio(storage_create_bucket=True))
    assert config.provider is StorageProvider.MINIO
    assert config.endpoint == "http://minio:9000"
    assert config.region == "us-east-1"
    assert config.create_bucket is True
    assert config.has_keys


def test_minio_requires_endpoint() -> None:
    with pytest.raises(StorageConfigError, match="ENDPOINT is required when .*PROVIDER=minio"):
        _config(**_minio(storage_endpoint=None))


def test_minio_requires_keys() -> None:
    with pytest.raises(StorageConfigError, match="are required when .*PROVIDER=minio"):
        _config(**_minio(storage_access_key="", storage_secret_key=""))


# ─── s3 ─────────────────────────────────────────────────────────────────────


def test_s3_needs_only_a_bucket() -> None:
    config = _config(storage_provider="s3", storage_bucket="b", storage_region="ap-south-1")
    assert config.endpoint is None
    assert config.region == "ap-south-1"
    assert not config.has_keys
    assert "auth=attached workload identity" in config.describe()


def test_s3_rejects_create_bucket() -> None:
    with pytest.raises(StorageConfigError, match="CREATE_BUCKET is only allowed with .*PROVIDER=minio"):
        _config(storage_provider="s3", storage_bucket="b", storage_create_bucket=True)


# ─── gcs ────────────────────────────────────────────────────────────────────


def test_gcs_needs_only_a_bucket_and_uses_the_attached_identity() -> None:
    config = _config(storage_provider="gcs", storage_bucket="b")
    assert config.endpoint == GCS_DEFAULT_ENDPOINT
    assert not config.has_keys
    assert config.public_endpoint is None


def test_gcs_with_a_key_pair() -> None:
    config = _config(
        storage_provider="gcs", storage_bucket="b", storage_access_key="k", storage_secret_key="s"
    )
    assert config.has_keys


def test_gcs_rejects_create_bucket() -> None:
    with pytest.raises(StorageConfigError, match="CREATE_BUCKET is only allowed"):
        _config(storage_provider="gcs", storage_bucket="b", storage_create_bucket=True)


def test_gcs_public_endpoint_needs_a_key_pair() -> None:
    settings = {
        "storage_provider": "gcs",
        "storage_bucket": "b",
        "storage_public_endpoint": "files.example.org",
    }
    with pytest.raises(StorageConfigError, match="PUBLIC_ENDPOINT needs a key pair"):
        _config(**settings)
    config = _config(**settings, storage_access_key="k", storage_secret_key="s")
    assert config.public_endpoint == "https://files.example.org"


def test_gcs_attached_identity_refuses_a_plain_http_endpoint() -> None:
    """The workload's bearer token must never travel over plain HTTP."""
    settings = {
        "storage_provider": "gcs",
        "storage_bucket": "b",
        "storage_endpoint": "http://gcs-emulator:4443",
    }
    with pytest.raises(StorageConfigError, match="must be an https googleapis.com host"):
        _config(**settings)
    # With a key pair nothing bearer-like is sent, so an emulator over HTTP is allowed.
    assert (
        _config(**settings, storage_access_key="k", storage_secret_key="s").endpoint
        == "http://gcs-emulator:4443"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://files.example.org",
        "https://storage.googleapis.com.example.org",
        "http://storage.googleapis.com",
    ],
)
def test_gcs_attached_identity_only_talks_to_google(endpoint: str) -> None:
    """A typo or a hostile endpoint must not receive the workload's token."""
    with pytest.raises(StorageConfigError, match="must be an https googleapis.com host"):
        _config(storage_provider="gcs", storage_bucket="b", storage_endpoint=endpoint)


@pytest.mark.parametrize(
    "endpoint", ["storage.googleapis.com", "https://storage.me-central2.rep.googleapis.com"]
)
def test_gcs_attached_identity_accepts_google_hosts(endpoint: str) -> None:
    config = _config(storage_provider="gcs", storage_bucket="b", storage_endpoint=endpoint)
    assert config.endpoint_is_google_https


# ─── endpoints ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("storage.googleapis.com", "https://storage.googleapis.com"),
        ("https://storage.googleapis.com/", "https://storage.googleapis.com"),
        ("http://minio:9000", "http://minio:9000"),
        ("  ", None),
    ],
)
def test_endpoint_is_normalised_and_bare_hosts_mean_https(raw: str, expected: str | None) -> None:
    config = _config(storage_provider="s3", storage_bucket="b", storage_endpoint=raw)
    assert config.endpoint == expected


@pytest.mark.parametrize(
    "raw", ["https://host/some/path", "ftp://host", "https://", "https://user:pass@host"]
)
def test_bad_endpoint_names_the_variable(raw: str) -> None:
    with pytest.raises(StorageConfigError, match="MICROCOACHING_STORAGE_ENDPOINT"):
        _config(storage_provider="s3", storage_bucket="b", storage_endpoint=raw)


# ─── deployed environments ──────────────────────────────────────────────────


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_local_development_keys_are_rejected_when_deployed(app_env: str) -> None:
    with pytest.raises(StorageConfigError, match="local development"):
        _config(
            **_minio(
                app_env=app_env, storage_access_key="microcoaching", storage_secret_key="microcoaching123"
            )
        )


def test_local_development_keys_are_fine_locally() -> None:
    assert _config(
        **_minio(storage_access_key="microcoaching", storage_secret_key="microcoaching123")
    ).has_keys


def test_keyless_gcs_passes_in_production() -> None:
    assert (
        _config(app_env="production", storage_provider="gcs", storage_bucket="b").provider
        is StorageProvider.GCS
    )


# ─── pre-rename variables ───────────────────────────────────────────────────


def test_legacy_names_are_found_case_insensitively() -> None:
    environ = {"object_storage_bucket_name": "b", "OBJECT_STORAGE_SECURE": "true", "HOME": "/root"}
    assert legacy_env_names(environ) == ["OBJECT_STORAGE_BUCKET_NAME", "OBJECT_STORAGE_SECURE"]
    assert legacy_env_names({}) == []


def test_every_legacy_name_has_a_hint() -> None:
    hints = describe_legacy(sorted(LEGACY_ENV_RENAMES))
    for name, replacement in LEGACY_ENV_RENAMES.items():
        assert name in hints
        assert not replacement or replacement.startswith("MICROCOACHING_STORAGE_")
