"""Platform vector-store adapters (pgvector today; more backends later)."""

from platform_service.vectorstore.factory import get_vector_store
from platform_service.vectorstore.pgvector_store import (
    CARDS_LOCAL_COLLECTION,
    MODULES_COLLECTION,
    MODULES_LOCAL_COLLECTION,
    PgVectorStore,
)

__all__ = [
    "CARDS_LOCAL_COLLECTION",
    "MODULES_COLLECTION",
    "MODULES_LOCAL_COLLECTION",
    "PgVectorStore",
    "get_vector_store",
]
