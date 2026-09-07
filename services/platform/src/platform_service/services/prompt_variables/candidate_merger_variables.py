"""Variable builders for batch candidate-merge prompt."""

import json
from typing import Any

from platform_service.services.prompts.module_topic_definition import MODULE_TOPIC_DEFINITION


def build_candidate_merger_variables(
    *,
    candidates: list[dict[str, Any]],
    annexure_terms: str,
) -> dict[str, str]:
    payload = {
        "candidates": [
            {
                "id": str(c.get("id")),
                "source_document_id": str(c.get("source_document_id")),
                "chunk_ids": list(c.get("chunk_ids") or []),
                "title": c.get("proposed_title", ""),
                "scope_summary": c.get("scope_summary", ""),
                "proposed_module_type": c.get("proposed_module_type", ""),
                "domain": c.get("domain") or "",
                "excerpt": c.get("excerpt") or "",
            }
            for c in candidates
        ]
    }
    return {
        "module_topic_definition": MODULE_TOPIC_DEFINITION.format(annexure_terms=annexure_terms),
        "candidates_json": json.dumps(payload, ensure_ascii=False, indent=2),
    }
