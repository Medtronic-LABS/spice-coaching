"""SyncService.get_card_embeddings_bundle — published card embedding delta sync."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from platform_service.config import Settings
from platform_service.db.models.module import Module
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.services.module_card_service import (
    ModuleCardService,
    extract_cards_from_module_json,
    module_json_shell,
)
from platform_service.services.sync_service import SyncService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import _unit_basis_vector

pytestmark = [requires_db, pytest.mark.asyncio]


async def _make_published_module(
    session: AsyncSession,
    *,
    tenant_id: int = 1,
    module_json: dict[str, Any] | None = None,
    chatbot_faqs_only: bool = False,
    lifecycle_status: str = "published",
) -> Module:
    family = ModuleFamily(
        module_code=f"SYNC-EMB-{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        chatbot_faqs_only=chatbot_faqs_only,
    )
    session.add(family)
    await session.flush()
    if module_json is None:
        cards_data: list[dict[str, Any]] = []
        shell_json: dict[str, Any] | None = {}
    else:
        cards_data = extract_cards_from_module_json(module_json)
        shell_json = module_json_shell(module_json)
    module = Module(
        module_family_id=family.id,
        version=1,
        lifecycle_status=lifecycle_status,
        module_type="refresher",
        title_localized={"bn": "মডিউল"},
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
        module_json=shell_json,
        chatbot_faqs_only=chatbot_faqs_only,
        tenant_id=tenant_id,
    )
    session.add(module)
    await session.flush()
    if cards_data:
        await ModuleCardService(session).append_cards(module.id, cards_data)
        await session.flush()
    if lifecycle_status == "published":
        family.current_published_module_id = module.id
        await session.flush()
    return module


async def _set_card_embeddings(session: AsyncSession, module_id: Any) -> list[ModuleCard]:
    cards = list(
        (
            await session.execute(
                select(ModuleCard).where(ModuleCard.module_id == module_id).order_by(ModuleCard.card_order)
            )
        )
        .scalars()
        .all()
    )
    for index, card in enumerate(cards):
        card.local_embedding = _unit_basis_vector(index)
    await session.flush()
    return cards


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_returns_vectors_for_updated_published_module(
    db_session: AsyncSession,
) -> None:
    module = await _make_published_module(
        db_session,
        module_json={
            "cards": [
                {"title": {"bn": "C1"}, "body": {"bn": "B1"}, "source_block_ids": [str(uuid4())]},
                {"title": {"bn": "C2"}, "body": {"bn": "B2"}, "source_block_ids": [str(uuid4())]},
            ]
        },
    )
    cards = await _set_card_embeddings(db_session, module.id)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    bundle = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)

    assert bundle.embedding_dimension == Settings().embedding_dimension
    assert len(bundle.cards) == 2
    by_id = {row.card_id: row for row in bundle.cards}
    assert cards[0].id in by_id
    assert cards[1].id in by_id
    assert by_id[cards[0].id].module_id == module.id
    assert by_id[cards[0].id].card_family_id == cards[0].card_family_id
    assert by_id[cards[0].id].embedding == _unit_basis_vector(0)


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_omits_cards_without_embedding(
    db_session: AsyncSession,
) -> None:
    module = await _make_published_module(
        db_session,
        module_json={
            "cards": [
                {"title": {"bn": "C1"}, "body": {"bn": "B1"}, "source_block_ids": [str(uuid4())]},
                {"title": {"bn": "C2"}, "body": {"bn": "B2"}, "source_block_ids": [str(uuid4())]},
            ]
        },
    )
    cards = await _set_card_embeddings(db_session, module.id)
    cards[1].local_embedding = None
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    bundle = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)

    assert len(bundle.cards) == 1
    assert bundle.cards[0].card_id == cards[0].id


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_excludes_non_published_modules(
    db_session: AsyncSession,
) -> None:
    module = await _make_published_module(
        db_session,
        lifecycle_status="draft",
        module_json={
            "cards": [{"title": {"bn": "C1"}, "body": {"bn": "B1"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    await _set_card_embeddings(db_session, module.id)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    bundle = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)
    assert bundle.cards == []


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_excludes_chatbot_faq_modules(
    db_session: AsyncSession,
) -> None:
    module = await _make_published_module(
        db_session,
        chatbot_faqs_only=True,
        module_json={
            "cards": [{"title": {"bn": "FAQ"}, "body": {"bn": "Body"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    await _set_card_embeddings(db_session, module.id)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    bundle = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)
    assert bundle.cards == []


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_respects_since_delta(db_session: AsyncSession) -> None:
    module = await _make_published_module(
        db_session,
        module_json={
            "cards": [{"title": {"bn": "C1"}, "body": {"bn": "B1"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    await _set_card_embeddings(db_session, module.id)
    await db_session.commit()

    since = datetime.now(UTC) + timedelta(minutes=1)
    bundle = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)
    assert bundle.cards == []


@pytest.mark.asyncio
@requires_db
async def test_card_embeddings_bundle_tenant_scope(db_session: AsyncSession) -> None:
    module_a = await _make_published_module(
        db_session,
        tenant_id=1,
        module_json={
            "cards": [{"title": {"bn": "A"}, "body": {"bn": "A"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    module_b = await _make_published_module(
        db_session,
        tenant_id=2,
        module_json={
            "cards": [{"title": {"bn": "B"}, "body": {"bn": "B"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    cards_a = await _set_card_embeddings(db_session, module_a.id)
    cards_b = await _set_card_embeddings(db_session, module_b.id)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    tenant_a = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=1)
    tenant_b = await SyncService(db_session).get_card_embeddings_bundle(since=since, tenant_id=2)

    assert {row.card_id for row in tenant_a.cards} == {cards_a[0].id}
    assert {row.card_id for row in tenant_b.cards} == {cards_b[0].id}


@pytest.mark.asyncio
@requires_db
async def test_list_card_embeddings_for_sync_repository(db_session: AsyncSession) -> None:
    module = await _make_published_module(
        db_session,
        module_json={
            "cards": [{"title": {"bn": "C1"}, "body": {"bn": "B1"}, "source_block_ids": [str(uuid4())]}]
        },
    )
    cards = await _set_card_embeddings(db_session, module.id)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(days=1)
    rows = await ModuleRepository(db_session).list_card_embeddings_for_sync(since, tenant_id=1)
    assert len(rows) == 1
    assert rows[0].id == cards[0].id
