"""Boundary tests for ``object_name_from_reference`` on a provider store.

Pure unit tests; the storage client is not contacted for reference normalisation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from platform_service.objectstore.boto_store import BotoLinkSigner, BotoObjectStore

from tests.helpers.storage import storage_config


@pytest.fixture
def store() -> BotoObjectStore:
    client = MagicMock()
    return BotoObjectStore(
        storage_config(bucket="medtronics-storage"),
        client=client,
        link_signer=BotoLinkSigner(client, "access key"),
    )


def test_object_name_strips_configured_bucket_prefix(store: BotoObjectStore) -> None:
    assert store.object_name_from_reference("medtronics-storage/ingest/a.pdf") == "ingest/a.pdf"


def test_object_name_accepts_key_without_bucket(store: BotoObjectStore) -> None:
    assert store.object_name_from_reference("ingest/a.pdf") == "ingest/a.pdf"


def test_object_name_rejects_foreign_bucket_prefix(store: BotoObjectStore) -> None:
    with pytest.raises(ValueError, match="other-bucket"):
        store.object_name_from_reference("other-bucket/ingest/a.pdf")


def test_object_name_rejects_junk_first_segment(store: BotoObjectStore) -> None:
    with pytest.raises(ValueError, match="nope"):
        store.object_name_from_reference("nope/ingest/a.pdf")


def test_object_name_rejects_empty_reference(store: BotoObjectStore) -> None:
    with pytest.raises(ValueError, match="object_name is required"):
        store.object_name_from_reference("")


def test_object_name_rejects_path_traversal(store: BotoObjectStore) -> None:
    with pytest.raises(ValueError, match="unsafe path segment"):
        store.object_name_from_reference("ingest/../etc/passwd")


def test_object_name_normalises_leading_slash(store: BotoObjectStore) -> None:
    assert store.object_name_from_reference("/ingest/a.pdf") == "ingest/a.pdf"
