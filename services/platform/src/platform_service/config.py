"""Platform service settings.

Per `docs/ARCHITECTURE_RESET.md`. Service code reads from `Settings`;
nothing reads `os.environ` directly. All thresholds and feature flags live
here so they are env-overridable and unit-testable.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from mc_foundation.config import BaseAppSettings
from pydantic_settings import SettingsConfigDict

AiCloudProvider = Literal["google", "openai"]


class Settings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "platform-api"

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/microcoaching"
    # Sourced from env in production. Default None so a missing env var
    # surfaces clearly at first DB connection rather than silently using
    # someone's stale local password.
    database_password: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    # ── ClickHouse ────────────────────────────────────────────
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "default"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    # ── AI Runtime (internal call) ────────────────────────────
    ai_runtime_base_url: str = "http://ai-runtime:8001"
    ai_runtime_timeout_seconds: float = 600.0
    # Service token sent in X-Internal-Token header.
    ai_runtime_token: str = "dev-internal-token"

    # ── Embedding ─────────────────────────────────────────────
    embedding_dimension: int = 768
    top_k: int = 5
    retrieval_require_validated: bool = False

    # ── Safety ────────────────────────────────────────────────
    # Comma-separated allowlist of referral destination strings the
    # coaching card may emit. Empty default; deployments override via
    # SPICE_REFERRAL_DESTINATIONS env var.
    spice_referral_destinations: str = ""

    @property
    def spice_referral_set(self) -> frozenset[str]:
        return frozenset(d.strip() for d in self.spice_referral_destinations.split(",") if d.strip())

    # ── Stage 1 — quality heuristic thresholds ──────────────────
    extraction_quality_text_empty_min_chars: int = 50
    # Native-script encoding integrity: pages with < this native-script
    # codepoint frequency AND > non_ascii_byte_max non-ASCII byte rate are
    # treated as legacy ANSI/Bijoy encoding and routed to vision fallback.
    # Applies to any language with a registered script in
    # `quality_heuristic._NATIVE_SCRIPT_RANGES` (bn / hi / mr / ta / te /
    # bn_en_mixed). Generalised from Bangla-only after the Hindi-Bijoy
    # ASHA Induction PDF bypassed the bn-only check and the identifier
    # silently dropped TB & FP modules.
    extraction_quality_native_codepoint_min: float = 0.40
    extraction_quality_non_ascii_byte_max: float = 0.25

    # ── Stage 1 — calibration ───────────────────────────────────
    extraction_calibration_sample_size: int = 10
    extraction_calibration_force_vision_threshold: float = 0.80
    extraction_calibration_skip_vision_threshold: float = 0.20

    # ── Stage 1 — vision recovery pass ──────────────────────────
    # After the main per-page loop, any page that raised during vision
    # extraction is retried in a recovery pass. The recovery pass waits
    # `stage_a_vision_recovery_initial_delay_s` first (lets the Vertex
    # per-minute quota window clear) and then retries each failed page
    # serially up to `stage_a_vision_recovery_max_retries` times. This
    # complements the in-call retry inside `prompt_executor` — the in-call
    # retry handles short bursts; this recovery pass handles sustained
    # quota windows that span the full main-loop duration.
    stage_a_vision_recovery_initial_delay_s: float = 60.0
    stage_a_vision_recovery_max_retries: int = 3
    # Tolerance: pages that remain vision_failed AFTER the recovery pass.
    # 0 = strict (any unrecovered page fails Stage 1). For the SK pilot
    # (small corpus, every chapter matters) keep at 0; raise for noisier
    # production volumes if individual page failures become acceptable.
    stage_a_vision_failed_tolerance: int = 0

    # ── Stage 2 — module identification ─────────────────────────
    # Advisory thresholds for the insufficient-source heuristic. The
    # heuristic flags a candidate when source provenance is below either
    # bound; per the architecture reset these flags are written onto the
    # candidate's quality_flags_jsonb but DO NOT reject the candidate.
    stage_c_insufficient_source_min_tokens: int = 50
    stage_c_insufficient_source_min_headings: int = 1
    # Default `module.domain` value when Stage 2's candidate doesn't carry
    # a domain. Override via DEFAULT_MODULE_DOMAIN env var.
    default_module_domain: str = "rmnch"
    # Output-token budget for the identification LLM call. Bumped from 32K
    # to 60K to give the LLM room to emit 25-30 candidates with full
    # provenance for one chunk's worth of corpus content. Override via
    # STAGE_C_MAX_OUTPUT_TOKENS env var.
    stage_c_max_output_tokens: int = 60_000
    # ── Stage 2 — token-budget chunker ──────────────────────────
    # Target tokens per chunk. Empirical data from Run 6 on the SK manual:
    # 35K finished in ~4 min, 40K and 68K both timed out at the 15-min
    # AI_RUNTIME_TIMEOUT_SECONDS ceiling. 25K is comfortably below the
    # 35K proven-safe ceiling and yields ~10 chunks for the SK manual,
    # each completing deterministically.
    stage_c_chunk_target_tokens: int = 25_000
    # Window (as a fraction of target) within which the chunker will look
    # for an outline section boundary to break at. 0.10 = ±10%. If no
    # boundary is found within the window, the chunker breaks at the
    # current page.
    stage_c_chunk_window_pct: float = 0.10
    # Trigram-Jaccard similarity threshold for cross-chunk near-duplicate
    # flagging. Candidates from different chunks with normalised-title
    # similarity ≥ this are tagged `cross_chunk_near_duplicate` for
    # reviewer attention. Same-title candidates are merged deterministically
    # (no LLM); near-similar titles are flagged but kept separate so the
    # reviewer makes the merge call. Lowered from 0.80 → 0.70 after the
    # Induction-Hindi run produced a substring-overlap STI pair scoring
    # 0.757 — just under the prior threshold. 0.70 still high enough to
    # avoid false positives on genuinely different topics.
    stage_c_cross_chunk_similarity_threshold: float = 0.70
    # How many per-chunk identification calls run in parallel. 2 is
    # conservative against Vertex per-project quota.
    stage_c_section_concurrency: int = 2

    # ── Stage 2-draft — bilingual card drafting ─────────────────
    # Cardinality bounds. Quiz bounds also apply to the post-publish quiz
    # generation worker.
    quiz_min_questions: int = 3
    quiz_max_questions: int = 10
    card_min_count: int = 3
    card_max_count: int = 7

    # ── Quiz pass / retrigger ───────────────────────────────────
    quiz_pass_threshold_default: float = 0.70
    quiz_periodic_refresh_days: int = 90
    quiz_failure_escalation_count: int = 3
    quiz_failure_escalation_window_days: int = 30

    # ── Trigger sensitivity ─────────────────────────────────────
    # Default gap-trigger occurrence threshold; per-module override via
    # trigger_definition.predicate_jsonb.
    gap_trigger_default_occurrences: int = 2
    gap_trigger_default_window_days: int = 14

    # ── Staging retention ───────────────────────────────────────
    staging_retention_days: int = 30

    upload_dir: str = "/tmp/microcoaching/uploads"

    # ── AI Runtime model selection ──────────────────────────────
    # Default provider matches docker-compose.yml. Override via env.
    ai_cloud_provider: str = "google"

    google_inference_model: str = "gemini-2.5-flash"
    google_identification_model: str = "gemini-2.5-pro"
    google_embedding_model: str = "text-embedding-005"
    google_vision_model: str = "gemini-2.5-flash"

    openai_inference_model: str = "gpt-4o-mini"
    openai_identification_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_vision_model: str = "gpt-4o-mini"

    @property
    def text_model(self) -> str:
        return (
            self.openai_inference_model if self.ai_cloud_provider == "openai" else self.google_inference_model
        )

    @property
    def identification_model(self) -> str:
        return (
            self.openai_identification_model
            if self.ai_cloud_provider == "openai"
            else self.google_identification_model
        )

    @property
    def embedding_model(self) -> str:
        return (
            self.openai_embedding_model if self.ai_cloud_provider == "openai" else self.google_embedding_model
        )

    @property
    def vision_model(self) -> str:
        return self.openai_vision_model if self.ai_cloud_provider == "openai" else self.google_vision_model


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Refuse to start in production with the dev default token.
    if settings.app_env == "production" and settings.ai_runtime_token == "dev-internal-token":
        raise RuntimeError(
            "Refusing to start: AI_RUNTIME_TOKEN is still the dev default. "
            "Set a real token."
        )
    return settings
