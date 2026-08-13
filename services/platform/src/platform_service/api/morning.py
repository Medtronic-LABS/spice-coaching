"""Morning cards endpoint — CHW-facing morning module suggestions.

Canonical path:
  GET /morning/cards → MorningCardsResponse
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from mc_contracts.morning import MorningCardsResponse
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import require_spice_user
from platform_service.auth.spice_user import get_selected_tenant_id
from platform_service.config import get_settings
from platform_service.deps import get_db
from platform_service.services.morning_suggestion_service import MorningSuggestionService

router = APIRouter(prefix="/morning", tags=["morning"])


@router.get("/cards", response_model=MorningCardsResponse)
async def get_morning_cards(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MorningCardsResponse:
    if not get_settings().spice_auth_enabled:
        return MorningCardsResponse(items=[], total_points=0)

    user = require_spice_user(request)

    return await MorningSuggestionService(db).get_morning_cards(
        chw_id=user.id,
        tenant_id=get_selected_tenant_id(request),
    )
