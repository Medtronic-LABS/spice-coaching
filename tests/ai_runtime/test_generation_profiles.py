"""Unit tests for ai-runtime GenerationType → GenerationProfile map."""

from __future__ import annotations

from types import SimpleNamespace

from ai_runtime.generation_profiles import GENERATION_PROFILES, resolve_local_profile
from mc_contracts.enums import GenerationType


def test_every_generation_type_has_a_profile() -> None:
    for generation_type in GenerationType:
        assert generation_type in GENERATION_PROFILES, f"{generation_type!r} missing from GENERATION_PROFILES"


def test_key_profile_budgets() -> None:
    assert GENERATION_PROFILES[GenerationType.MODULE_IDENTIFICATION].max_tokens == 12_000
    assert GENERATION_PROFILES[GenerationType.CANDIDATE_MERGE].max_tokens == 8192
    assert GENERATION_PROFILES[GenerationType.MODULE_PUBLISHED_MERGE].max_tokens == 4_000
    assert GENERATION_PROFILES[GenerationType.COACHING_RAG].max_tokens == 2048
    assert GENERATION_PROFILES[GenerationType.COACHING_CHAT_ROUTE].max_tokens == 512
    assert GENERATION_PROFILES[GenerationType.COACHING_CHAT_ROUTE].temperature == 0.1
    assert GENERATION_PROFILES[GenerationType.COACHING_LOCAL_CARD_RAG].max_tokens == 512
    assert GENERATION_PROFILES[GenerationType.COACHING_LOCAL_CARD_RAG].temperature == 0.0
    assert GENERATION_PROFILES[GenerationType.COACHING_LOCAL_CARD_CHAT_ROUTE].max_tokens == 128
    assert GENERATION_PROFILES[GenerationType.COACHING_LOCAL_CARD_CHAT_ROUTE].temperature == 0.0
    assert GENERATION_PROFILES[GenerationType.RAG_EVAL_JUDGE].temperature == 0.0


def test_resolve_local_profile_tightens_coaching_budgets() -> None:
    settings = SimpleNamespace(
        default_inference_model="gemini-2.5-flash",
        default_max_tokens=8192,
        default_temperature=0.2,
    )
    rag = resolve_local_profile(GenerationType.COACHING_RAG, settings)
    assert rag.max_tokens == 512
    assert rag.temperature == 0.0

    route = resolve_local_profile(GenerationType.COACHING_CHAT_ROUTE, settings)
    assert route.max_tokens == 128
    assert route.temperature == 0.0

    local_card_rag = resolve_local_profile(GenerationType.COACHING_LOCAL_CARD_RAG, settings)
    assert local_card_rag.max_tokens == 512
    assert local_card_rag.temperature == 0.0

    local_card_route = resolve_local_profile(GenerationType.COACHING_LOCAL_CARD_CHAT_ROUTE, settings)
    assert local_card_route.max_tokens == 128
    assert local_card_route.temperature == 0.0

    other = resolve_local_profile(GenerationType.CARD_DRAFTING, settings)
    assert other.max_tokens == GENERATION_PROFILES[GenerationType.CARD_DRAFTING].max_tokens
