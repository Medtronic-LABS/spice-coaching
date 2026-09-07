"""Admin dashboard module endpoints.

See `docs/content-administration/ingest-pipeline.md`. Ingestion run list/detail lives in
``ingestion_runs``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from mc_contracts.enums import ContentDomain
from mc_contracts.errors import ErrorCode
from mc_contracts.modules import (
    ModuleCreateRequest,
    ModuleDetail,
    ModuleEditRequest,
    ModuleLifecycleActionRequest,
    ModuleLifecycleStatePayload,
    ModuleListResponse,
)
from mc_foundation.objectstore import ObjectStore
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.api.query_params import normalize_csv_query_values, normalize_int_csv_query_values
from platform_service.auth.spice_user import get_selected_tenant_id, resolve_spice_user_id
from platform_service.config import Settings, get_settings
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.module import Module
from platform_service.db.module_availability import VALID_LIFECYCLE_STATUSES
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.db.repositories.module_gap_repository import (
    ModuleGapLinkError,
    ModuleGapRepository,
)
from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleLifecycleError,
    ModuleLifecycleRepository,
    ModuleLifecycleState,
)
from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleNotFoundError as LifecycleModuleNotFoundError,
)
from platform_service.db.repositories.module_read_repository import (
    DEFAULT_MODULE_SORT_BY,
    DEFAULT_MODULE_SORT_DIR,
    MODULE_SORT_DIRS,
    MODULE_SORT_KEYS,
)
from platform_service.db.repositories.module_repository import (
    ModuleNotFoundError,
    ModuleRepository,
    ModuleVersionConflictError,
)
from platform_service.db.validators import ValidationError
from platform_service.deps import get_db, get_object_storage_client
from platform_service.module_domains import catalog_domain_label
from platform_service.services.attribution_audit import record_attribution_event
from platform_service.services.dashboard_hierarchy import resolve_users_by_geography_ids
from platform_service.services.module_attachment_validator import validate_module_attachments
from platform_service.services.module_card_body_validator import validate_module_card_bodies
from platform_service.services.module_card_service import (
    ModuleCardService,
    extract_cards_from_module_json,
    module_json_shell,
)
from platform_service.services.module_edit_equality import (
    edit_content_matches,
    is_complete_edit_snapshot,
    resolve_edit_request_quiz,
)
from platform_service.services.module_presenter import (
    card_payload,
    cards_with_source_pages,
    get_card_counts,
    get_quiz_counts,
    quiz_payload,
    source_documents_for_module,
    summary_from_module,
    visibility_window_bounds,
)
from platform_service.services.module_publish_enrichment import ModulePublishEnrichmentError
from platform_service.services.module_publish_service import ModulePublishService
from platform_service.services.module_quiz_service import ModuleQuizService
from platform_service.services.module_retire_service import ModuleRetireService
from platform_service.services.module_thumbnail_service import validate_module_thumbnail_storage_path

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])
logger = logging.getLogger(__name__)


@router.post("/modules", status_code=201)
async def create_new_module(
    request: Request,
    body: ModuleCreateRequest,
    session: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Manually create a new module family and initial draft module version."""
    module_json = body.module_json
    cards_data: list[dict[str, Any]] = []
    if module_json is not None:
        try:
            module_json = validate_module_card_bodies(module_json)
            module_json = await validate_module_attachments(
                module_json,
                settings=settings,
                storage=storage,
            )
            cards_data = extract_cards_from_module_json(module_json)
            module_json = module_json_shell(module_json)
        except ValidationError as exc:
            raise AppError(exc.code, exc.message, status=400) from exc

    repo = ModuleRepository(session)
    try:
        new_module = await repo.create_module(
            title=body.title,
            description=body.description,
            domain=body.domain,
            sub_domain=body.sub_domain,
            module_type=body.module_type,
            estimated_minutes=body.estimated_minutes,
            difficulty_level=body.difficulty_level,
            module_json=module_json,
            created_by_user_id=resolve_spice_user_id(request),
            behavioural_gap_ids=body.behavioural_gap_ids,
            primary_gap_id=body.primary_gap_id,
            chatbot_faqs_only=body.chatbot_faqs_only,
            content_domain=body.content_domain.value,
            tenant_id=get_selected_tenant_id(request),
        )
    except ValueError as exc:
        raise AppError(ErrorCode.BAD_REQUEST.value, str(exc), status=400) from exc
    except ModuleGapLinkError as exc:
        raise AppError(ErrorCode.GAP_LINK_ERROR.value, exc.message, status=400) from exc

    if cards_data:
        await ModuleCardService(session).append_cards(new_module.id, cards_data)

    quiz_data = body.quiz
    if quiz_data is None and body.module_json is not None:
        quiz_data = body.module_json.get("quiz")

    if quiz_data is not None:
        await ModuleQuizService(session).append_questions(new_module.id, quiz_data)

    await session.commit()
    return {
        "id": str(new_module.id),
        "module_family_id": str(new_module.module_family_id),
        "version": new_module.version,
    }


@router.get("/modules", response_model=ModuleListResponse)
async def list_modules(
    request: Request,
    status: str | None = Query(
        None,
        description=(
            "draft | published | retired | deactivated | review_pending — "
            "omit for All (retired excluded; deactivated + review_pending included)"
        ),
    ),
    clinically_reviewed: bool | None = Query(None),
    has_visibility_window: bool | None = Query(None),
    has_quality_flags: bool | None = Query(
        None,
        description="true → only modules with non-empty quality_flags_jsonb (the 'needs attention' view)",
    ),
    domain: str | None = Query(None, description="Domain filter (module.domain)"),
    content_domain: list[str] | None = Query(
        None,
        description=(
            "Optional filter on module.content_domain; repeat and/or comma-separate: "
            "clinical | digital | operational "
            "(e.g. content_domain=digital&content_domain=operational or content_domain=clinical,digital)"
        ),
    ),
    chatbot_faqs_only: bool | None = Query(
        None,
        description=(
            "Optional exact match on module.chatbot_faqs_only. "
            "Pass false to exclude Chatbot FAQ-only modules (e.g. badge assignable lists)."
        ),
    ),
    source_document_id: UUID | None = Query(
        default=None,
        description="Optional filter: only modules linked to this source_document_id",
    ),
    created_by: list[str] | None = Query(
        None,
        description=(
            "Optional filter by creator hierarchy user id(s); repeat and/or comma-separate "
            "(e.g. created_by=101&created_by=102 or created_by=101,102)"
        ),
    ),
    division_id: list[str] | None = Query(
        None,
        description=(
            "Optional filter by assignee geography: division id(s); "
            "repeat and/or comma-separate (OR within; AND with district_id/upazila_id)"
        ),
    ),
    district_id: list[str] | None = Query(
        None,
        description=(
            "Optional filter by assignee geography: district id(s); "
            "repeat and/or comma-separate (OR within; AND with division_id/upazila_id)"
        ),
    ),
    upazila_id: list[str] | None = Query(
        None,
        description=(
            "Optional filter by assignee geography: upazila id(s); "
            "repeat and/or comma-separate (OR within; AND with division_id/district_id)"
        ),
    ),
    created_from: datetime | None = Query(
        None, description="Inclusive Created Date range start (module.created_at)."
    ),
    created_to: datetime | None = Query(
        None, description="Inclusive Created Date range end (module.created_at)."
    ),
    published_from: datetime | None = Query(
        None, description="Inclusive Published Date range start (module.published_at)."
    ),
    published_to: datetime | None = Query(
        None, description="Inclusive Published Date range end (module.published_at)."
    ),
    activated_from: datetime | None = Query(
        None,
        description="Inclusive Activated Date range start (module.activated_at).",
    ),
    activated_to: datetime | None = Query(
        None,
        description="Inclusive Activated Date range end (module.activated_at).",
    ),
    deactivated_from: datetime | None = Query(
        None, description="Inclusive Deactivated Date range start (module.deactivated_at)."
    ),
    deactivated_to: datetime | None = Query(
        None, description="Inclusive Deactivated Date range end (module.deactivated_at)."
    ),
    q: str | None = Query(None, description="full-text query against title + description"),
    latest_version_only: bool = Query(
        True,
        description="When true (default), collapse to one row per module_family showing the highest-version row that matches filters. Set false to see every version.",
    ),
    sort_by: str = Query(
        DEFAULT_MODULE_SORT_BY,
        description=(
            "created_at | updated_at | published_at | activated_at | deactivated_at | "
            "title | domain | lifecycle_status"
        ),
    ),
    sort_dir: str = Query(
        DEFAULT_MODULE_SORT_DIR,
        description="asc | desc",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> ModuleListResponse:
    for date_from, date_to, from_name, to_name in (
        (created_from, created_to, "created_from", "created_to"),
        (published_from, published_to, "published_from", "published_to"),
        (activated_from, activated_to, "activated_from", "activated_to"),
        (deactivated_from, deactivated_to, "deactivated_from", "deactivated_to"),
    ):
        if date_from is not None and date_to is not None and date_from > date_to:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                f"{from_name} must be on or before {to_name}",
                status=422,
            )
    if status is not None and status not in VALID_LIFECYCLE_STATUSES:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"status must be one of: {', '.join(sorted(VALID_LIFECYCLE_STATUSES))}",
            status=422,
        )
    created_by_raw = normalize_csv_query_values(created_by)
    created_by_ids: list[int] | None = None
    if created_by_raw is not None:
        created_by_ids = []
        invalid_created_by: list[str] = []
        for token in created_by_raw:
            try:
                created_by_ids.append(int(token))
            except ValueError:
                invalid_created_by.append(token)
        if invalid_created_by:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                f"created_by must be integer user id(s); got invalid: {', '.join(invalid_created_by)}",
                status=422,
            )
    content_domain_raw = normalize_csv_query_values(content_domain)
    content_domains: list[str] | None = None
    if content_domain_raw is not None:
        allowed = frozenset(e.value for e in ContentDomain)
        invalid_domains = [token for token in content_domain_raw if token not in allowed]
        if invalid_domains:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                f"content_domain must be one of: {', '.join(sorted(allowed))}; "
                f"got invalid: {', '.join(invalid_domains)}",
                status=422,
            )
        content_domains = content_domain_raw
    division_ids = normalize_int_csv_query_values(division_id, param_name="division_id")
    district_ids = normalize_int_csv_query_values(district_id, param_name="district_id")
    upazila_ids = normalize_int_csv_query_values(upazila_id, param_name="upazila_id")
    if sort_by not in MODULE_SORT_KEYS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_by must be one of: {', '.join(sorted(MODULE_SORT_KEYS))}",
            status=422,
        )
    if sort_dir not in MODULE_SORT_DIRS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_dir must be one of: {', '.join(sorted(MODULE_SORT_DIRS))}",
            status=422,
        )
    effective_tenant = get_selected_tenant_id(request)
    assigned_to_user_ids = await resolve_users_by_geography_ids(
        session,
        tenant_id=effective_tenant,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    repo = ModuleRepository(session)
    list_filters = {
        "status": status,
        "clinically_reviewed": clinically_reviewed,
        "has_visibility_window": has_visibility_window,
        "has_quality_flags": has_quality_flags,
        "domain": domain,
        "content_domains": content_domains,
        "chatbot_faqs_only": chatbot_faqs_only,
        "source_document_id": source_document_id,
        "created_from": created_from,
        "created_to": created_to,
        "published_from": published_from,
        "published_to": published_to,
        "activated_from": activated_from,
        "activated_to": activated_to,
        "deactivated_from": deactivated_from,
        "deactivated_to": deactivated_to,
        "full_text_query": q,
        "latest_version_only": latest_version_only,
        "tenant_id": effective_tenant,
        "created_by_ids": created_by_ids,
        "assigned_to_user_ids": assigned_to_user_ids,
    }
    total_modules = await repo.count_modules(**list_filters)
    modules = await repo.list_modules(
        **list_filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    quiz_counts = await get_quiz_counts(session, [m.id for m in modules])
    card_counts = await get_card_counts(session, [m.id for m in modules])
    creator_ids = {m.created_by for m in modules if m.created_by is not None}
    publisher_ids = {m.published_by for m in modules if m.published_by is not None}
    deactivated_ids = {m.deactivated_by for m in modules if m.deactivated_by is not None}
    activated_ids = {m.activated_by for m in modules if m.activated_by is not None}
    retired_ids = {m.retired_by for m in modules if m.retired_by is not None}
    users_by_id = await HierarchyRepository(session).get_users_by_ids(
        list(creator_ids | publisher_ids | deactivated_ids | activated_ids | retired_ids)
    )
    summaries = [
        await summary_from_module(
            m,
            card_count=card_counts.get(m.id, 0),
            quiz_count=quiz_counts.get(m.id, 0),
            storage=storage,
            users_by_id=users_by_id,
        )
        for m in modules
    ]
    total_pages = (total_modules + limit - 1) // limit if total_modules > 0 else 0
    return ModuleListResponse(
        modules=summaries,
        total_modules=total_modules,
        total_pages=total_pages,
        limit=limit,
        offset=offset,
    )


@router.get("/modules/domains", response_model=list[str])
async def list_module_domains(
    request: Request,
    status: str | None = Query(
        None,
        description=(
            "draft | published | retired | deactivated | review_pending — "
            "omit for All (retired excluded; deactivated + review_pending included)"
        ),
    ),
    latest_version_only: bool = Query(
        True,
        description="When true (default), one domain per module family (highest version).",
    ),
    q: str | None = Query(
        None,
        description="Optional case-insensitive substring filter on domain.",
    ),
    session: AsyncSession = Depends(get_db),
) -> list[str]:
    """Distinct ``module.domain`` values for admin filter dropdowns."""
    if status is not None and status not in VALID_LIFECYCLE_STATUSES:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"status must be one of: {', '.join(sorted(VALID_LIFECYCLE_STATUSES))}",
            status=422,
        )
    effective_tenant = get_selected_tenant_id(request)
    repo = ModuleRepository(session)
    return await repo.list_module_domains(
        status=status,
        latest_version_only=latest_version_only,
        tenant_id=effective_tenant,
        q=q,
    )


@router.get("/modules/{module_id}", response_model=ModuleDetail)
async def get_module(
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> ModuleDetail:
    repo = ModuleRepository(session)
    module = await repo.get_module(module_id)
    if module is None:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, "module not found", status=404)
    quiz = await repo.list_quiz_questions(module_id)
    card_rows = await repo.list_cards(module_id)
    module_payload = module.module_json or {}
    source_documents = await source_documents_for_module(session, module, storage)
    presigned_by_doc = {ref.source_document_id: ref.presigned_url for ref in source_documents}
    presigned_expires_by_doc = {
        ref.source_document_id: ref.presigned_expires_seconds for ref in source_documents
    }
    cards = await cards_with_source_pages(
        session,
        card_payload(card_rows),
        storage=storage,
        presigned_by_doc=presigned_by_doc,
        presigned_expires_by_doc=presigned_expires_by_doc,
    )
    module_attachments = list(module_payload.get("attachments", []))
    user_ids: list[int] = []
    if module.created_by is not None:
        user_ids.append(module.created_by)
    if module.published_by is not None and module.published_by not in user_ids:
        user_ids.append(module.published_by)
    if module.deactivated_by is not None and module.deactivated_by not in user_ids:
        user_ids.append(module.deactivated_by)
    if module.activated_by is not None and module.activated_by not in user_ids:
        user_ids.append(module.activated_by)
    if module.retired_by is not None and module.retired_by not in user_ids:
        user_ids.append(module.retired_by)
    users_by_id: dict[int, HierarchyUser] = {}
    if user_ids:
        users_by_id = await HierarchyRepository(session).get_users_by_ids(user_ids)
    summary = await summary_from_module(
        module,
        card_count=len(cards),
        quiz_count=len(quiz),
        storage=storage,
        users_by_id=users_by_id,
    )
    window_lower, window_upper = visibility_window_bounds(module)
    gap_repo = ModuleGapRepository(session)
    behavioural_gap_ids = await gap_repo.get_gap_ids(module_id)
    return ModuleDetail(
        **summary.model_dump(),
        cards=cards,
        attachments=module_attachments,
        quiz=quiz_payload(quiz),
        sub_domain=module.sub_domain,
        difficulty_level=module.difficulty_level,
        pass_threshold_override=module.pass_threshold_override,
        visibility_window_lower=window_lower,
        visibility_window_upper=window_upper,
        source_documents=source_documents,
        primary_gap_id=module.primary_gap_id,
        behavioural_gap_ids=behavioural_gap_ids,
    )


@router.put("/modules/{module_id}")
async def edit_module(
    module_id: UUID,
    body: ModuleEditRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    repo = ModuleRepository(session)
    cards_data: list[dict[str, Any]] | None = None
    module_json = body.module_json
    if module_json is not None:
        try:
            module_json = validate_module_card_bodies(module_json)
            module_json = await validate_module_attachments(
                module_json,
                settings=settings,
                storage=storage,
            )
            cards_data = extract_cards_from_module_json(module_json)
            module_json = module_json_shell(module_json)
        except ValidationError as exc:
            raise AppError(exc.code, exc.message, status=400) from exc

    thumbnail_kw: dict[str, str | None] = {}
    if "thumbnail_storage_path" in body.model_fields_set:
        try:
            thumbnail_kw["thumbnail_storage_path"] = await validate_module_thumbnail_storage_path(
                body.thumbnail_storage_path,
                settings=settings,
                storage=storage,
            )
        except ValidationError as exc:
            raise AppError(exc.code, exc.message, status=400) from exc

    def _edit_response(module: Module) -> dict[str, Any]:
        return {
            "id": str(module.id),
            "module_family_id": str(module.module_family_id),
            "version": module.version,
            "supersedes_module_id": str(module.supersedes_module_id) if module.supersedes_module_id else None,
        }

    try:
        current = await repo.get_editable_module_tip(
            module_id,
            expected_version=body.expected_version,
        )
        chatbot_faqs_only_changed = (
            "chatbot_faqs_only" in body.model_fields_set
            and body.chatbot_faqs_only is not None
            and body.chatbot_faqs_only != current.chatbot_faqs_only
        )
        content_domain_changed = (
            "content_domain" in body.model_fields_set
            and body.content_domain is not None
            and body.content_domain.value != current.content_domain
        )
        next_domain: str | None = None
        if "domain" in body.model_fields_set:
            next_domain = catalog_domain_label(body.domain)
            if next_domain is None:
                raise AppError(
                    ErrorCode.BAD_REQUEST.value,
                    "domain is required",
                    status=400,
                )
        domain_changed = next_domain is not None and next_domain != current.domain
        estimated_minutes_changed = (
            "estimated_minutes" in body.model_fields_set
            and body.estimated_minutes is not None
            and body.estimated_minutes != current.estimated_minutes
        )
        if (
            is_complete_edit_snapshot(body)
            and "thumbnail_storage_path" in thumbnail_kw
            and not chatbot_faqs_only_changed
            and not content_domain_changed
            and not domain_changed
            and not estimated_minutes_changed
            and edit_content_matches(
                request_title=body.title,
                request_description=body.description,
                request_module_json_shell=module_json,
                request_cards=cards_data or [],
                request_quiz=resolve_edit_request_quiz(body),
                request_thumbnail_storage_path=thumbnail_kw["thumbnail_storage_path"],
                module=current,
                current_cards=card_payload(await repo.list_cards(current.id)),
                current_quiz=quiz_payload(await repo.list_quiz_questions(current.id)),
            )
        ):
            return _edit_response(current)

        edit_kwargs: dict[str, Any] = {}
        if "chatbot_faqs_only" in body.model_fields_set:
            edit_kwargs["chatbot_faqs_only"] = body.chatbot_faqs_only
        if "content_domain" in body.model_fields_set:
            edit_kwargs["content_domain"] = (
                body.content_domain.value if body.content_domain is not None else None
            )
        if next_domain is not None:
            edit_kwargs["domain"] = next_domain
        if "estimated_minutes" in body.model_fields_set and body.estimated_minutes is not None:
            edit_kwargs["estimated_minutes"] = body.estimated_minutes

        new_module = await repo.edit_module(
            module_id,
            expected_version=body.expected_version,
            title=body.title,
            description=body.description,
            module_json=module_json,
            created_by_user_id=resolve_spice_user_id(request),
            **thumbnail_kw,
            **edit_kwargs,
        )

        if body.behavioural_gap_ids is not None:
            if new_module.chatbot_faqs_only and body.behavioural_gap_ids:
                raise AppError(
                    ErrorCode.BAD_REQUEST.value,
                    "chatbot_faqs_only modules cannot be linked to behavioural gaps",
                    status=400,
                )
            gap_repo = ModuleGapRepository(session)
            primary = body.primary_gap_id
            if primary is None and body.behavioural_gap_ids:
                prior = await session.get(Module, module_id)
                primary = prior.primary_gap_id if prior is not None else None
                if primary is None or primary not in body.behavioural_gap_ids:
                    primary = body.behavioural_gap_ids[0]
            try:
                await gap_repo.replace_links(
                    new_module.id,
                    gap_ids=body.behavioural_gap_ids,
                    primary_gap_id=primary if body.behavioural_gap_ids else None,
                )
            except ModuleGapLinkError as exc:
                raise AppError(ErrorCode.GAP_LINK_ERROR.value, exc.message, status=400) from exc

        quiz_data = resolve_edit_request_quiz(body)
        if quiz_data is not None:
            await ModuleQuizService(session).append_questions(new_module.id, quiz_data)

        if cards_data is not None:
            await ModuleCardService(session).append_cards(new_module.id, cards_data)
        elif module_json is None:
            prior_cards = card_payload(await repo.list_cards(module_id))
            if prior_cards:
                await ModuleCardService(session).append_cards(new_module.id, prior_cards)

    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except ModuleVersionConflictError as exc:
        raise AppError(
            ErrorCode.MODULE_VERSION_CONFLICT.value,
            "module has been modified; refetch and retry",
            status=409,
            extensions={
                "expected_version": exc.expected_version,
                "current_version": exc.current_version,
                "latest_module_id": str(exc.latest_module_id),
            },
        ) from exc
    await session.commit()
    return _edit_response(new_module)


@router.post("/modules/{module_id}/publish")
async def publish_module(
    request: Request,
    module_id: UUID,
    body: ModuleLifecycleActionRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark a module version as published."""
    service = ModulePublishService(session)
    action = body or ModuleLifecycleActionRequest()
    try:
        state = await service.publish(
            module_id,
            actor_id=action.actor_id,
            published_by_user_id=resolve_spice_user_id(request),
            reason=action.reason,
        )
    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except ModuleLifecycleError as exc:
        raise AppError(ErrorCode.MODULE_LIFECYCLE_ERROR.value, exc.message, status=409) from exc
    except ModulePublishEnrichmentError as exc:
        raise AppError(exc.error_code.value, exc.message, status=502) from exc

    await session.commit()
    return {
        "id": str(state.module_id),
        "module_family_id": str(state.module_family_id),
        "lifecycle_status": state.lifecycle_status,
        "activated_at": state.activated_at,
    }


def _lifecycle_state_payload(state: ModuleLifecycleState) -> ModuleLifecycleStatePayload:
    return ModuleLifecycleStatePayload(
        module_id=state.module_id,
        module_family_id=state.module_family_id,
        lifecycle_status=state.lifecycle_status,
        activated_at=state.activated_at,
        deactivated_at=state.deactivated_at,
    )


@router.post("/modules/{module_id}/deactivate", response_model=ModuleLifecycleStatePayload)
async def deactivate_module(
    request: Request,
    module_id: UUID,
    body: ModuleLifecycleActionRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleLifecycleStatePayload:
    repo = ModuleLifecycleRepository(session)
    action = body or ModuleLifecycleActionRequest()
    try:
        state = await repo.deactivate(
            module_id,
            actor_id=action.actor_id,
            deactivated_by_user_id=resolve_spice_user_id(request),
            reason=action.reason,
        )
    except LifecycleModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except ModuleLifecycleError as exc:
        raise AppError(ErrorCode.MODULE_LIFECYCLE_ERROR.value, exc.message, status=409) from exc
    logger.info(
        "module_deactivated module_id=%s family_id=%s actor_id=%s",
        module_id,
        state.module_family_id,
        action.actor_id,
    )
    await record_attribution_event(
        session,
        event_type="module_deactivated",
        actor=str(action.actor_id) if action.actor_id else "admin",
        module_id=module_id,
        payload={"module_family_id": str(state.module_family_id), "reason": action.reason},
    )
    await session.commit()
    return _lifecycle_state_payload(state)


@router.post("/modules/{module_id}/reactivate", response_model=ModuleLifecycleStatePayload)
async def reactivate_module(
    request: Request,
    module_id: UUID,
    body: ModuleLifecycleActionRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleLifecycleStatePayload:
    repo = ModuleLifecycleRepository(session)
    action = body or ModuleLifecycleActionRequest()
    try:
        state = await repo.reactivate(
            module_id,
            actor_id=action.actor_id,
            activated_by_user_id=resolve_spice_user_id(request),
            reason=action.reason,
        )
    except LifecycleModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except ModuleLifecycleError as exc:
        raise AppError(ErrorCode.MODULE_LIFECYCLE_ERROR.value, exc.message, status=409) from exc
    logger.info(
        "module_reactivated module_id=%s family_id=%s actor_id=%s",
        module_id,
        state.module_family_id,
        action.actor_id,
    )
    await record_attribution_event(
        session,
        event_type="module_reactivated",
        actor=str(action.actor_id) if action.actor_id else "admin",
        module_id=module_id,
        payload={"module_family_id": str(state.module_family_id), "reason": action.reason},
    )
    await session.commit()
    return _lifecycle_state_payload(state)


@router.delete("/modules/{module_id}")
async def retire_module(
    request: Request,
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ModuleRetireService(session)
    try:
        module = await service.retire(
            module_id,
            retired_by_user_id=resolve_spice_user_id(request),
        )
    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    await session.commit()
    return {
        "id": str(module.id),
        "lifecycle_status": module.lifecycle_status,
        "retired_at": module.retired_at,
    }
