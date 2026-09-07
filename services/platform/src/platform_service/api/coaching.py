"""Coaching RAG — vector retrieval over published module embeddings + grounded answer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from mc_contracts.coaching import CoachingLocalRagRequest, CoachingRagRequest, CoachingRagResponse
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import get_selected_tenant_id
from platform_service.deps import get_ai_client, get_db, get_object_storage_client
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.coaching_rag_service import CoachingRagService

router = APIRouter(prefix="/coaching", tags=["coaching-rag"])


@router.post("/rag-query", response_model=CoachingRagResponse)
async def rag_query(
    request: Request,
    body: CoachingRagRequest,
    session: AsyncSession = Depends(get_db),
    ai: AIRuntimeClient = Depends(get_ai_client),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> CoachingRagResponse:
    """Embed ``question``, retrieve top similar **published** modules, generate a grounded answer."""
    tenant_id = get_selected_tenant_id(request)
    return await CoachingRagService(session, ai, storage).query(body, tenant_id=tenant_id)


@router.post("/local-rag-query", response_model=CoachingRagResponse)
async def local_rag_query(
    request: Request,
    body: CoachingLocalRagRequest,
    session: AsyncSession = Depends(get_db),
    ai: AIRuntimeClient = Depends(get_ai_client),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> CoachingRagResponse:
    """Embed via local models, retrieve top similar **published** cards, generate a grounded answer."""
    tenant_id = get_selected_tenant_id(request)
    return await CoachingRagService(session, ai, storage).local_query(body, tenant_id=tenant_id)
