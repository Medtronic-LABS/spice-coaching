-- Standalone schema for SQLAlchemy models in:
-- services/platform/src/platform_service/db/models/
--
-- Target DB: PostgreSQL (uses UUID/JSONB/arrays/range + pgvector).
-- Safe to run on an empty database. Does not include migrations or triggers.

BEGIN;

-- Needed for gen_random_uuid() defaults (convenient for standalone SQL).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Needed for the Module.embedding column.
CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────────────────────────────────────
-- Source layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS source_document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
  title text NOT NULL,
  source_type text NOT NULL,
  primary_language text NOT NULL DEFAULT 'bn',
  authority_kind text NOT NULL DEFAULT 'official_training',
  authority_label text NOT NULL,
  version_label text NULL,
  publication_date date NULL,
  original_storage_path text NOT NULL,
  outline_method text NULL,
  outline_jsonb jsonb NULL,
  extraction_calibration_jsonb jsonb NULL,
  status text NOT NULL DEFAULT 'ingesting',
  ingested_at timestamptz NOT NULL DEFAULT now(),
  ingested_by uuid NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_page (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  page_image_path text NULL,
  markdown_content text NOT NULL DEFAULT '',
  extraction_method text NOT NULL DEFAULT 'text',
  extraction_quality_score double precision NOT NULL DEFAULT 0.0,
  text_extraction_alt text NULL,
  language_detected text NULL,
  metadata_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_source_page_doc_page UNIQUE (source_document_id, page_number)
);

CREATE TABLE IF NOT EXISTS content_block (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_page_id uuid NOT NULL REFERENCES source_page(id) ON DELETE CASCADE,
  block_order integer NOT NULL,
  block_type text NOT NULL,
  content_text text NOT NULL,
  content_language text NULL,
  heading_path_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  status text NOT NULL DEFAULT 'running',
  error_jsonb jsonb NULL,
  triggered_by uuid NULL
);

CREATE TABLE IF NOT EXISTS ingestion_run_step (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid NOT NULL REFERENCES ingestion_run(id) ON DELETE CASCADE,
  stage text NOT NULL,
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  status text NOT NULL DEFAULT 'pending',
  input_summary_jsonb jsonb NULL,
  output_summary_jsonb jsonb NULL,
  llm_call_id uuid NULL,
  error_jsonb jsonb NULL
);

CREATE TABLE IF NOT EXISTS llm_call_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_hash text NOT NULL UNIQUE,
  model text NOT NULL,
  prompt_template_id uuid NULL,
  response_jsonb jsonb NOT NULL,
  token_usage_jsonb jsonb NULL,
  cached_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module_candidate_draft (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid NOT NULL REFERENCES ingestion_run(id) ON DELETE CASCADE,
  proposed_title text NOT NULL,
  behavioural_gap_code text NULL,
  scope_summary text NOT NULL DEFAULT '',
  source_provenance_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  estimated_card_count integer NOT NULL DEFAULT 0,
  estimated_quiz_count integer NOT NULL DEFAULT 0,
  clinical_review_notes text NULL,
  proposed_module_type text NOT NULL DEFAULT 'refresher',
  previous_practice_summary text NULL,
  current_practice_summary text NULL,
  rationale_summary text NULL,
  quality_flags_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ──────────────────────────────────────────────────────────────────────────────
-- Module layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS module_family (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_code text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NULL,
  current_published_module_id uuid NULL
);

-- NOTE: The ORM model does not declare a SQL-level FK for module_family_id.
-- This script intentionally mirrors that (so it stays in lockstep with models).
CREATE TABLE IF NOT EXISTS module (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_family_id uuid NOT NULL,
  version integer NOT NULL DEFAULT 1,
  title_en text NULL,
  title_bn text NOT NULL,
  description_en text NULL,
  description_bn text NULL,
  domain text NOT NULL,
  sub_domain text NULL,
  module_type text NOT NULL DEFAULT 'refresher',
  tenant_id uuid NULL,
  primary_gap_id uuid NULL,
  estimated_minutes integer NOT NULL DEFAULT 10,
  difficulty_level text NOT NULL DEFAULT 'moderate',
  source_document_ids uuid[] NULL,
  urgent_publish boolean NOT NULL DEFAULT false,
  module_json jsonb NULL,
  embedding vector NULL,
  visibility_window tstzrange NULL,
  pass_threshold_override double precision NULL,
  quality_flags_jsonb jsonb NULL,
  clinically_reviewed boolean NOT NULL DEFAULT false,
  clinically_reviewed_at timestamptz NULL,
  clinically_reviewed_by uuid NULL,
  lifecycle_status text NOT NULL DEFAULT 'draft',
  published_at timestamptz NULL,
  deprecated_at timestamptz NULL,
  supersedes_module_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_family_version UNIQUE (module_family_id, version)
);

CREATE TABLE IF NOT EXISTS module_quiz_question (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NULL REFERENCES module(id) ON DELETE CASCADE,
  question_order integer NULL,
  question_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
  question_version integer NOT NULL DEFAULT 1,
  case_setup_en text NULL,
  case_setup_bn text NULL,
  question_en text NULL,
  question_bn text NOT NULL,
  question_type text NOT NULL DEFAULT 'single_select',
  options_en jsonb NULL,
  options_bn jsonb NOT NULL DEFAULT '[]'::jsonb,
  correct_indices integer[] NOT NULL,
  explanation_en text NULL,
  explanation_bn text NULL,
  primary_card_family_id uuid NULL,
  source_block_ids uuid[] NULL,
  difficulty text NOT NULL DEFAULT 'moderate',
  distractor_critique_jsonb jsonb NULL,
  field_flags_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_quiz_family_version UNIQUE (question_family_id, question_version)
);

CREATE INDEX IF NOT EXISTS ix_module_quiz_question_module_id ON module_quiz_question (module_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Gap + trigger layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS behavioural_gap (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  gap_code text NOT NULL UNIQUE,
  description text NOT NULL,
  domain text NOT NULL,
  severity_default text NOT NULL DEFAULT 'moderate',
  detection_rule_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active',
  tenant_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chw_behavioural_gap_state (
  chw_id bigint NOT NULL,
  behavioural_gap_id uuid NOT NULL REFERENCES behavioural_gap(id) ON DELETE CASCADE,
  tenant_id uuid NULL,
  severity_current text NOT NULL DEFAULT 'moderate',
  first_observed_at timestamptz NULL,
  last_observed_at timestamptz NULL,
  last_reinforced_at timestamptz NULL,
  occurrence_count integer NOT NULL DEFAULT 0,
  failed_attempts_count integer NOT NULL DEFAULT 0,
  last_failed_attempt_at timestamptz NULL,
  escalated_to_supervisor boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active',
  updated_at timestamptz NULL,
  CONSTRAINT pk_chw_behavioural_gap_state PRIMARY KEY (chw_id, behavioural_gap_id)
);

CREATE TABLE IF NOT EXISTS chw_module_completion (
  chw_id bigint NOT NULL,
  module_family_id uuid NOT NULL REFERENCES module_family(id) ON DELETE CASCADE,
  latest_completed_module_id uuid NULL,
  latest_attempt_module_id uuid NULL,
  completed_at timestamptz NULL,
  latest_attempt_at timestamptz NULL,
  latest_quiz_score double precision NULL,
  latest_attempt_passed boolean NOT NULL DEFAULT false,
  attempts_since_last_pass integer NOT NULL DEFAULT 0,
  reinforcement_due_at timestamptz NULL,
  tenant_id uuid NULL,
  CONSTRAINT pk_chw_module_completion PRIMARY KEY (chw_id, module_family_id)
);

CREATE TABLE IF NOT EXISTS chw_learning_point_event (
  event_id uuid NOT NULL,
  chw_id bigint NOT NULL,
  points integer NOT NULL,
  awarded_at timestamptz NOT NULL,
  tenant_id uuid NULL,
  CONSTRAINT pk_chw_learning_point_event PRIMARY KEY (event_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_learning_point_event_chw_id ON chw_learning_point_event (chw_id);

CREATE TABLE IF NOT EXISTS trigger_definition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger_kind text NOT NULL,
  trigger_code text NOT NULL UNIQUE,
  description text NULL,
  predicate_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  predicate_schema_version integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'active',
  tenant_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module_trigger_binding (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_family_id uuid NOT NULL REFERENCES module_family(id) ON DELETE CASCADE,
  trigger_definition_id uuid NOT NULL REFERENCES trigger_definition(id) ON DELETE CASCADE,
  relationship text NOT NULL DEFAULT 'primary',
  priority_weight integer NOT NULL DEFAULT 10,
  notes text NULL,
  CONSTRAINT uq_module_trigger_binding_pair UNIQUE (module_family_id, trigger_definition_id)
);

-- ──────────────────────────────────────────────────────────────────────────────
-- Config
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS config_threshold (
  id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  key text NOT NULL UNIQUE,
  value_json jsonb NOT NULL,
  description text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;

