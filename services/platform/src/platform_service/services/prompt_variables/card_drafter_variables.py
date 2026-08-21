"""Variable builders for card drafter prompt."""

from __future__ import annotations

import json
from typing import Any

from mc_foundation.locale import locale_display_name

from platform_service.config import get_settings
from platform_service.services.card_image_assigner import (
    ImageCatalogEntry,
    render_catalog_for_prompt,
)
from platform_service.services.prompts.card_drafter_prompt import (
    _CONTENT_UPDATE_RULES,
    _DIGITAL_PROFICIENCY_RULES,
    _INITIAL_TRAINING_RULES,
    _REFRESHER_RULES,
)
from platform_service.services.prompts.symbol_verbalization import (
    render_locale_map_field_schema,
    render_symbol_verbalization_rules,
)


def _body_field_schema_for(module_type: str, *, primary_locale: str) -> str:
    if module_type == "content_update":
        lines = [
            render_locale_map_field_schema(
                "body",
                primary_locale=primary_locale,
                description="may be empty for content_update; delta fields carry the framing",
            ),
            render_locale_map_field_schema(
                "previous_practice",
                primary_locale=primary_locale,
                primary_required=True,
                description="REQUIRED for content_update",
            ),
            render_locale_map_field_schema(
                "current_practice",
                primary_locale=primary_locale,
                primary_required=True,
                description="REQUIRED for content_update",
            ),
            render_locale_map_field_schema(
                "rationale_for_change",
                primary_locale=primary_locale,
                primary_required=True,
                description="REQUIRED for content_update",
            ),
            render_locale_map_field_schema(
                "next_action",
                primary_locale=primary_locale,
            ),
        ]
        return "\n".join(lines)
    return render_locale_map_field_schema(
        "body",
        primary_locale=primary_locale,
        primary_required=True,
        description="REQUIRED for initial_training / refresher / digital_proficiency",
    )


def _module_type_rules_for(module_type: str, *, primary_locale: str) -> str:
    primary_label = locale_display_name(primary_locale)
    if module_type == "initial_training":
        return _INITIAL_TRAINING_RULES
    if module_type == "refresher":
        return _REFRESHER_RULES
    if module_type == "digital_proficiency":
        return _DIGITAL_PROFICIENCY_RULES
    if module_type == "content_update":
        return _CONTENT_UPDATE_RULES.format(primary_locale_label=primary_label)
    return _REFRESHER_RULES


def _image_assignment_rules(max_images_per_card: int) -> str:
    return (
        f"IMAGES (only when an ## AVAILABLE IMAGES ## section appears below):\n"
        f"- Attach relevant images to each card via "
        f'`"source_image_ids": ["img_N", ...]` using ONLY ids from the catalog.\n'
        f"- Maximum {max_images_per_card} image(s) per card. Omit the field when none are relevant.\n"
        f"- The same image id may appear on more than one card.\n"
        f"- Do NOT embed image markdown in body text."
    )


def build_card_drafter_variables(
    *,
    module_type: str,
    card_min_count: int,
    card_max_count: int,
    candidate: dict[str, Any],
    cited_blocks: list[dict[str, Any]],
    deployment_primary_locale: str | None = None,
    deployment_region_context: str | None = None,
    image_catalog: list[ImageCatalogEntry] | None = None,
    max_images_per_card: int = 5,
) -> dict[str, str]:
    settings = get_settings()
    primary_locale = deployment_primary_locale or settings.deployment_primary_locale
    region_context = deployment_region_context or settings.deployment_region_context
    primary_label = locale_display_name(primary_locale)

    module_rules = _module_type_rules_for(module_type, primary_locale=primary_locale)
    if module_type in ("initial_training", "refresher", "digital_proficiency"):
        module_rules = module_rules.format(
            card_min_count=card_min_count,
            card_max_count=card_max_count,
        )

    candidate_summary = {
        "proposed_title": candidate.get("proposed_title"),
        "scope_summary": candidate.get("scope_summary"),
        "proposed_module_type": candidate.get("proposed_module_type"),
        "estimated_card_count": candidate.get("estimated_card_count"),
        "previous_practice_summary": candidate.get("previous_practice_summary"),
        "current_practice_summary": candidate.get("current_practice_summary"),
        "rationale_summary": candidate.get("rationale_summary"),
    }
    head_json = json.dumps(
        {"candidate": {k: v for k, v in candidate_summary.items() if v is not None}},
        ensure_ascii=False,
        indent=2,
    )

    source_label: dict[str, str] = {}
    for blk in cited_blocks:
        sd = str(blk.get("source_document_id") or "unknown")
        if sd not in source_label:
            source_label[sd] = f"d{len(source_label) + 1}"

    body_lines = ["\n## CITED CONTENT BLOCKS ##"]
    if len(source_label) > 1:
        per_source_counts = {label: 0 for label in source_label.values()}
        for blk in cited_blocks:
            sd = str(blk.get("source_document_id") or "unknown")
            per_source_counts[source_label[sd]] += 1
        body_lines.append(
            f"\n[multi-source candidate: blocks span {len(source_label)} sources — "
            f"counts {per_source_counts}. Per the cross-source coverage rule, your "
            f"card set MUST cite blocks from each source label.]"
        )

    for blk in cited_blocks:
        sd = str(blk.get("source_document_id") or "unknown")
        body_lines.append(
            f"\n[content_block_id={blk['content_block_id']} "
            f"source={source_label[sd]} "
            f"block_type={blk['block_type']} "
            f"language={blk.get('content_language', 'unknown')}]\n{blk['content_text']}"
        )

    return {
        "deployment_region_context": region_context,
        "primary_locale_label": primary_label,
        "card_min_count": str(card_min_count),
        "card_max_count": str(card_max_count),
        "symbol_verbalization_rules": render_symbol_verbalization_rules(
            primary_locale=primary_locale,
        ),
        "module_type_rules": module_rules,
        "title_field_schema": render_locale_map_field_schema(
            "title",
            primary_locale=primary_locale,
            primary_required=True,
        ),
        "body_field_schema": _body_field_schema_for(module_type, primary_locale=primary_locale),
        "head_json": head_json,
        "cited_blocks_body": "\n".join(body_lines),
        "available_images_body": render_catalog_for_prompt(image_catalog or []),
        "image_assignment_rules": _image_assignment_rules(max_images_per_card),
    }
