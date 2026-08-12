-- Idempotent squashed snapshot of Alembic head (schema + seeds).
-- Target DB: PostgreSQL (UUID/JSONB/arrays/range + pgvector).
-- Safe to re-run on an empty or already-bootstrapped database via CREATE IF NOT EXISTS
-- and seed ON CONFLICT. Live environments use Alembic; this file is a docs reference.
-- Seed tenant_id uses DEFAULT_TENANT_ID = 0.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────────────────────────────────────
-- Source layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS source_document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
  title text NOT NULL,
  description text NULL,
  source_type text NOT NULL,
  primary_language text NOT NULL,
  content_domain text NOT NULL DEFAULT 'clinical',
  version_label text NULL,
  publication_date date NULL,
  original_storage_path text NOT NULL,
  thumbnail_storage_path text NULL,
  content_sha256 text NULL,
  original_filename text NULL,
  uploaded_by text NULL,
  outline_method text NULL,
  outline_jsonb jsonb NULL,
  extraction_calibration_jsonb jsonb NULL,
  sync_published_visible boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'ingesting',
  tenant_id bigint NOT NULL,
  uploaded_date timestamptz NOT NULL DEFAULT now(),
  ingested_at timestamptz NOT NULL DEFAULT now(),
  ingested_by uuid NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_source_document_content_sha256_ingested
  ON source_document (content_sha256)
  WHERE status = 'ingested' AND content_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_source_document_tenant_id
  ON source_document (tenant_id);

CREATE TABLE IF NOT EXISTS source_page (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  start_ms integer NULL,
  end_ms integer NULL,
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

CREATE TABLE IF NOT EXISTS ingest_batch (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL DEFAULT 'queued',
  assessment_mode text NOT NULL DEFAULT 'with_quiz',
  ingestion_instructions text NULL,
  cards_per_module integer NULL,
  quizzes_per_module integer NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  error_jsonb jsonb NULL,
  triggered_by uuid NULL
);

CREATE INDEX IF NOT EXISTS ix_ingest_batch_tenant_id
  ON ingest_batch (tenant_id);

CREATE TABLE IF NOT EXISTS ingestion_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  ingest_batch_id uuid NULL REFERENCES ingest_batch(id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  status text NOT NULL DEFAULT 'running',
  error_jsonb jsonb NULL,
  triggered_by uuid NULL
);

CREATE INDEX IF NOT EXISTS ix_ingestion_run_ingest_batch_id
  ON ingestion_run (ingest_batch_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_run_active_per_source
  ON ingestion_run (source_document_id)
  WHERE status IN ('queued', 'running')
    AND COALESCE(error_jsonb->>'type', '') != 'cross_source_fusion';

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
  error_code text NULL,
  error_message text NULL,
  error_jsonb jsonb NULL
);

CREATE TABLE IF NOT EXISTS llm_call_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id bigint NOT NULL,
  input_hash text NOT NULL,
  model text NOT NULL,
  prompt_template_id uuid NULL,
  response_jsonb jsonb NOT NULL,
  token_usage_jsonb jsonb NULL,
  cached_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_llm_call_cache_tenant_hash UNIQUE (tenant_id, input_hash)
);

CREATE INDEX IF NOT EXISTS ix_llm_call_cache_tenant_id
  ON llm_call_cache (tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Audit / provenance
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS file_upload (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket_name text NOT NULL,
  object_key text NOT NULL,
  storage_path text NOT NULL,
  original_filename text NOT NULL,
  content_sha256 text NOT NULL,
  content_type text NULL,
  size_bytes bigint NOT NULL,
  uploaded_by text NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_file_upload_object UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS ix_file_upload_storage_path ON file_upload (storage_path);
CREATE INDEX IF NOT EXISTS ix_file_upload_bucket_content_sha256
  ON file_upload (bucket_name, content_sha256);
CREATE INDEX IF NOT EXISTS ix_file_upload_tenant_id
  ON file_upload (tenant_id);

CREATE TABLE IF NOT EXISTS attribution_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type text NOT NULL,
  source_document_id uuid NULL,
  module_id uuid NULL,
  actor text NOT NULL,
  payload_jsonb jsonb NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_attribution_event_source_document
  ON attribution_event (source_document_id);
CREATE INDEX IF NOT EXISTS ix_attribution_event_event_type
  ON attribution_event (event_type);
CREATE INDEX IF NOT EXISTS ix_attribution_event_tenant_id
  ON attribution_event (tenant_id);

CREATE TABLE IF NOT EXISTS module_candidate_draft (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid NOT NULL REFERENCES ingestion_run(id) ON DELETE CASCADE,
  proposed_title text NOT NULL,
  domain text NULL,
  behavioural_gap_code text NULL,
  scope_summary text NOT NULL DEFAULT '',
  description_localized jsonb NULL,
  source_provenance_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_chunk_ids jsonb NULL,
  estimated_card_count integer NOT NULL DEFAULT 0,
  estimated_quiz_count integer NOT NULL DEFAULT 0,
  clinical_review_notes text NULL,
  proposed_module_type text NOT NULL DEFAULT 'refresher',
  previous_practice_summary text NULL,
  current_practice_summary text NULL,
  rationale_summary text NULL,
  ingestion_instruction_rationale text NULL,
  quality_flags_jsonb jsonb NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_module_candidate_draft_tenant_id
  ON module_candidate_draft (tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Module layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS module_family (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_code text NOT NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NULL,
  current_published_module_id uuid NULL,
  CONSTRAINT uq_module_family_tenant_code UNIQUE (tenant_id, module_code)
);

CREATE INDEX IF NOT EXISTS ix_module_family_tenant_id
  ON module_family (tenant_id);

-- NOTE: The ORM model does not declare a SQL-level FK for module_family_id.
-- This script intentionally mirrors Alembic (no FK).
CREATE TABLE IF NOT EXISTS module (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_family_id uuid NOT NULL,
  version integer NOT NULL DEFAULT 1,
  title_localized jsonb NOT NULL,
  description_localized jsonb NULL,
  domain text NOT NULL,
  sub_domain text NULL,
  module_type text NOT NULL DEFAULT 'refresher',
  tenant_id bigint NOT NULL,
  primary_gap_id uuid NULL,
  estimated_minutes integer NOT NULL DEFAULT 10,
  difficulty_level text NOT NULL DEFAULT 'moderate',
  source_document_ids uuid[] NULL,
  thumbnail_storage_path text NULL,
  urgent_publish boolean NOT NULL DEFAULT false,
  chatbot_faqs_only boolean NOT NULL DEFAULT false,
  module_json jsonb NULL,
  embedding vector NULL,
  visibility_window tstzrange NULL,
  pass_threshold_override double precision NULL,
  quality_flags_jsonb jsonb NULL,
  search_metadata_jsonb jsonb NULL,
  clinically_reviewed boolean NOT NULL DEFAULT false,
  clinically_reviewed_at timestamptz NULL,
  clinically_reviewed_by uuid NULL,
  lifecycle_status text NOT NULL DEFAULT 'draft',
  published_at timestamptz NULL,
  first_activated_at timestamptz NULL,
  last_deactivated_at timestamptz NULL,
  last_reactivated_at timestamptz NULL,
  deactivated_by uuid NULL,
  reactivated_by uuid NULL,
  deprecated_at timestamptz NULL,
  supersedes_module_id uuid NULL,
  merge_secondary_module_id uuid NULL,
  merge_primary_module_id uuid NULL,
  merge_source_module_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_family_version UNIQUE (module_family_id, version)
);

CREATE INDEX IF NOT EXISTS ix_module_tenant_id
  ON module (tenant_id);

CREATE TABLE IF NOT EXISTS module_quiz_question (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NULL REFERENCES module(id) ON DELETE CASCADE,
  question_order integer NULL,
  question_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
  question_version integer NOT NULL DEFAULT 1,
  case_setup_localized jsonb NULL,
  question_localized jsonb NOT NULL,
  question_type text NOT NULL DEFAULT 'single_select',
  options_localized jsonb NOT NULL,
  correct_indices integer[] NOT NULL,
  explanation_localized jsonb NULL,
  primary_card_family_id uuid NULL,
  source_block_ids uuid[] NULL,
  difficulty text NOT NULL DEFAULT 'moderate',
  distractor_critique_jsonb jsonb NULL,
  field_flags_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_quiz_family_version UNIQUE (question_family_id, question_version)
);

CREATE INDEX IF NOT EXISTS ix_module_quiz_question_module_id ON module_quiz_question (module_id);

CREATE TABLE IF NOT EXISTS module_card (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  card_order integer NOT NULL,
  card_family_id uuid NOT NULL DEFAULT gen_random_uuid(),
  card_version integer NOT NULL DEFAULT 1,
  title_localized jsonb NOT NULL,
  body_localized jsonb NULL,
  previous_practice_localized jsonb NULL,
  current_practice_localized jsonb NULL,
  rationale_for_change_localized jsonb NULL,
  next_action_localized jsonb NULL,
  thresholds_jsonb jsonb NULL,
  source_block_ids uuid[] NULL,
  figure_ref_block_id uuid NULL,
  search_metadata_jsonb jsonb NULL,
  attachments_jsonb jsonb NULL,
  field_flags_jsonb jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_card_family_version UNIQUE (card_family_id, card_version)
);

CREATE INDEX IF NOT EXISTS ix_module_card_module_id ON module_card (module_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Gap + badge + assignment layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS behavioural_gap (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  gap_code text NOT NULL UNIQUE,
  description text NOT NULL,
  domain text NOT NULL,
  severity_default text NOT NULL DEFAULT 'moderate',
  detection_rule_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active',
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_behavioural_gap_tenant_id
  ON behavioural_gap (tenant_id);

CREATE TABLE IF NOT EXISTS badge (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  domain text NOT NULL,
  image_storage_path text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  sequence integer NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by text NULL,
  updated_by text NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_badge_name_active
  ON badge (name)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_badge_domain ON badge (domain);
CREATE INDEX IF NOT EXISTS ix_badge_status ON badge (status);
CREATE INDEX IF NOT EXISTS ix_badge_tenant_id ON badge (tenant_id);

CREATE TABLE IF NOT EXISTS badge_module (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  badge_id uuid NOT NULL REFERENCES badge(id) ON DELETE CASCADE,
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  CONSTRAINT uq_badge_module_pair UNIQUE (badge_id, module_id)
);

CREATE INDEX IF NOT EXISTS ix_badge_module_badge_id ON badge_module (badge_id);
CREATE INDEX IF NOT EXISTS ix_badge_module_module_id ON badge_module (module_id);

CREATE TABLE IF NOT EXISTS chw_badge (
  chw_id bigint NOT NULL,
  badge_id uuid NOT NULL REFERENCES badge(id) ON DELETE CASCADE,
  earned_at timestamptz NOT NULL DEFAULT now(),
  tenant_id bigint NOT NULL,
  CONSTRAINT pk_chw_badge PRIMARY KEY (chw_id, badge_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_badge_chw_id ON chw_badge (chw_id);
CREATE INDEX IF NOT EXISTS ix_chw_badge_badge_id ON chw_badge (badge_id);
CREATE INDEX IF NOT EXISTS ix_chw_badge_tenant_id ON chw_badge (tenant_id);

CREATE TABLE IF NOT EXISTS module_behavioural_gap (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  behavioural_gap_id uuid NOT NULL REFERENCES behavioural_gap(id) ON DELETE CASCADE,
  is_primary boolean NOT NULL DEFAULT false,
  CONSTRAINT uq_module_behavioural_gap_pair UNIQUE (module_id, behavioural_gap_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_module_behavioural_gap_one_primary
  ON module_behavioural_gap (module_id)
  WHERE is_primary;

CREATE INDEX IF NOT EXISTS ix_module_behavioural_gap_module_id
  ON module_behavioural_gap (module_id);

CREATE INDEX IF NOT EXISTS ix_module_behavioural_gap_behavioural_gap_id
  ON module_behavioural_gap (behavioural_gap_id);

CREATE TABLE IF NOT EXISTS chw_behavioural_gap_state (
  chw_id bigint NOT NULL,
  behavioural_gap_id uuid NOT NULL REFERENCES behavioural_gap(id) ON DELETE CASCADE,
  tenant_id bigint NOT NULL,
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

CREATE INDEX IF NOT EXISTS ix_chw_behavioural_gap_state_tenant_id
  ON chw_behavioural_gap_state (tenant_id);

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
  tenant_id bigint NOT NULL,
  CONSTRAINT pk_chw_module_completion PRIMARY KEY (chw_id, module_family_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_module_completion_tenant_id
  ON chw_module_completion (tenant_id);

CREATE TABLE IF NOT EXISTS module_assignment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  tenant_id bigint NOT NULL,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  assigned_by bigint NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_module_assignment_user UNIQUE (module_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_module_assignment_tenant_id
  ON module_assignment (tenant_id);
CREATE INDEX IF NOT EXISTS ix_module_assignment_user_id
  ON module_assignment (user_id);

CREATE TABLE IF NOT EXISTS chw_video_assignment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  assignment_type varchar(50) NOT NULL,
  tenant_id bigint NOT NULL,
  user_id bigint NULL,
  upazila varchar(100) NULL,
  assigned_by bigint NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_video_assignment_user UNIQUE (source_document_id, user_id),
  CONSTRAINT uq_video_assignment_upazila UNIQUE (source_document_id, upazila)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_video_assignment_tenant
  ON chw_video_assignment (source_document_id, tenant_id)
  WHERE assignment_type = 'group';

CREATE INDEX IF NOT EXISTS ix_chw_video_assignment_tenant_id
  ON chw_video_assignment (tenant_id);
CREATE INDEX IF NOT EXISTS ix_chw_video_assignment_user_id
  ON chw_video_assignment (user_id);
CREATE INDEX IF NOT EXISTS ix_chw_video_assignment_upazila
  ON chw_video_assignment (upazila);

CREATE TABLE IF NOT EXISTS chw_video_progress (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chw_id bigint NOT NULL,
  source_document_id uuid NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
  last_position_ms bigint NOT NULL DEFAULT 0,
  percent_watched double precision NOT NULL DEFAULT 0,
  completed boolean NOT NULL DEFAULT false,
  last_watched_at timestamptz NOT NULL DEFAULT now(),
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_video_progress_chw_video UNIQUE (chw_id, source_document_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_video_progress_chw_id
  ON chw_video_progress (chw_id);
CREATE INDEX IF NOT EXISTS ix_chw_video_progress_source_document_id
  ON chw_video_progress (source_document_id);
CREATE INDEX IF NOT EXISTS ix_chw_video_progress_tenant_id
  ON chw_video_progress (tenant_id);

CREATE TABLE IF NOT EXISTS chw_module_quiz_progress (
  chw_id bigint NOT NULL,
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  quiz_id uuid NOT NULL REFERENCES module_quiz_question(id) ON DELETE CASCADE,
  first_correct_at timestamptz NOT NULL DEFAULT now(),
  tenant_id bigint NOT NULL,
  CONSTRAINT pk_chw_module_quiz_progress PRIMARY KEY (chw_id, module_id, quiz_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_module_quiz_progress_chw_module
  ON chw_module_quiz_progress (chw_id, module_id);
CREATE INDEX IF NOT EXISTS ix_chw_module_quiz_progress_tenant_id
  ON chw_module_quiz_progress (tenant_id);

CREATE TABLE IF NOT EXISTS chw_quiz_question_state (
  chw_id bigint NOT NULL,
  quiz_id uuid NOT NULL REFERENCES module_quiz_question(id) ON DELETE CASCADE,
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  tenant_id bigint NOT NULL,
  failed_attempts_count integer NOT NULL DEFAULT 0,
  last_failed_attempt_at timestamptz NULL,
  first_attempt_at timestamptz NULL,
  last_attempt_at timestamptz NULL,
  escalated_to_supervisor boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active',
  updated_at timestamptz NULL,
  CONSTRAINT pk_chw_quiz_question_state PRIMARY KEY (chw_id, quiz_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_quiz_question_state_chw_module
  ON chw_quiz_question_state (chw_id, module_id);
CREATE INDEX IF NOT EXISTS ix_chw_quiz_question_state_tenant_id
  ON chw_quiz_question_state (tenant_id);

CREATE TABLE IF NOT EXISTS chw_learning_point_event (
  event_id uuid NOT NULL,
  chw_id bigint NOT NULL,
  points integer NOT NULL,
  awarded_at timestamptz NOT NULL,
  tenant_id bigint NOT NULL,
  CONSTRAINT pk_chw_learning_point_event PRIMARY KEY (event_id)
);

CREATE INDEX IF NOT EXISTS ix_chw_learning_point_event_chw_id ON chw_learning_point_event (chw_id);
CREATE INDEX IF NOT EXISTS ix_chw_learning_point_event_tenant_id
  ON chw_learning_point_event (tenant_id);

CREATE TABLE IF NOT EXISTS chw_gap_telemetry_event (
  event_id uuid PRIMARY KEY,
  chw_id bigint NOT NULL,
  event_type text NOT NULL,
  processed_at timestamptz NOT NULL,
  tenant_id bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_chw_gap_telemetry_event_tenant_id
  ON chw_gap_telemetry_event (tenant_id);

CREATE TABLE IF NOT EXISTS trigger_definition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger_kind text NOT NULL,
  trigger_code text NOT NULL UNIQUE,
  description text NULL,
  predicate_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  predicate_schema_version integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'active',
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_trigger_definition_tenant_id
  ON trigger_definition (tenant_id);

CREATE TABLE IF NOT EXISTS module_trigger_binding (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  trigger_definition_id uuid NOT NULL REFERENCES trigger_definition(id) ON DELETE CASCADE,
  relationship text NOT NULL DEFAULT 'primary',
  priority_weight integer NOT NULL DEFAULT 10,
  notes text NULL,
  CONSTRAINT uq_module_trigger_binding_pair UNIQUE (module_id, trigger_definition_id)
);

CREATE TABLE IF NOT EXISTS module_lifecycle_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid NULL,
  reason text NULL
);

CREATE INDEX IF NOT EXISTS ix_module_lifecycle_event_module_occurred
  ON module_lifecycle_event (module_id, occurred_at);

-- ──────────────────────────────────────────────────────────────────────────────
-- Chatbot / demand / creation suggestion layer
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chat_frequent_question (
  id uuid PRIMARY KEY,
  tenant_id bigint NOT NULL,
  question_localized jsonb NOT NULL,
  normalized_question text NOT NULL,
  occurrence_count integer NOT NULL,
  rank integer NOT NULL,
  last_seen_at timestamptz NULL,
  computed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_chat_faq_tenant_question UNIQUE (tenant_id, normalized_question)
);

CREATE INDEX IF NOT EXISTS ix_chat_frequent_question_tenant_id
  ON chat_frequent_question (tenant_id);
CREATE INDEX IF NOT EXISTS ix_chat_faq_tenant_rank
  ON chat_frequent_question (tenant_id, rank);
CREATE INDEX IF NOT EXISTS ix_chat_faq_tenant_updated
  ON chat_frequent_question (tenant_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_feedback_summary (
  id uuid PRIMARY KEY,
  tenant_id bigint NOT NULL,
  payload_json jsonb NOT NULL,
  generated_at timestamptz NOT NULL,
  computed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_chat_feedback_summary_tenant
  ON chat_feedback_summary (tenant_id);
CREATE INDEX IF NOT EXISTS ix_chat_feedback_summary_tenant_id
  ON chat_feedback_summary (tenant_id);

CREATE TABLE IF NOT EXISTS module_creation_suggestion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id bigint NOT NULL,
  suggestion_date date NOT NULL,
  suggestion_kind text NOT NULL,
  matched_module_id uuid NULL REFERENCES module(id) ON DELETE SET NULL,
  proposed_topic text NULL,
  display_title text NOT NULL,
  rationale text NULL,
  question_count integer NOT NULL DEFAULT 0,
  request_count integer NOT NULL DEFAULT 0,
  evidence_count integer NOT NULL DEFAULT 0,
  rank integer NOT NULL,
  computed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_module_creation_suggestion_tenant_id
  ON module_creation_suggestion (tenant_id);
CREATE INDEX IF NOT EXISTS ix_module_creation_suggestion_tenant_date
  ON module_creation_suggestion (tenant_id, suggestion_date);
CREATE INDEX IF NOT EXISTS ix_module_creation_suggestion_date
  ON module_creation_suggestion (suggestion_date);
CREATE INDEX IF NOT EXISTS ix_module_creation_suggestion_matched_module
  ON module_creation_suggestion (matched_module_id);

CREATE TABLE IF NOT EXISTS module_creation_suggestion_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suggestion_id uuid NOT NULL REFERENCES module_creation_suggestion(id) ON DELETE CASCADE,
  source text NOT NULL,
  text text NOT NULL,
  normalized_text text NOT NULL,
  occurrence_count integer NOT NULL DEFAULT 1,
  last_seen_at timestamptz NULL,
  sample_event_id text NULL,
  sample_chw_id bigint NULL
);

CREATE INDEX IF NOT EXISTS ix_module_creation_suggestion_evidence_suggestion
  ON module_creation_suggestion_evidence (suggestion_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- CHW training request
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chw_training_request (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chw_id bigint NOT NULL,
  module_id uuid NULL REFERENCES module(id) ON DELETE RESTRICT,
  requested_module_name text NULL,
  reason text NULL,
  submitted_at timestamptz NOT NULL,
  tenant_id bigint NOT NULL,
  reviewed_by text NULL,
  reviewed_at timestamptz NULL,
  reviewer_notes text NULL
);

CREATE INDEX IF NOT EXISTS ix_chw_training_request_chw_id
  ON chw_training_request (chw_id);
CREATE INDEX IF NOT EXISTS ix_chw_training_request_module_id
  ON chw_training_request (module_id);
CREATE INDEX IF NOT EXISTS ix_chw_training_request_tenant_id
  ON chw_training_request (tenant_id);
CREATE INDEX IF NOT EXISTS ix_chw_training_request_tenant_submitted
  ON chw_training_request (tenant_id, submitted_at);

-- ──────────────────────────────────────────────────────────────────────────────
-- District / users hierarchy (0059; role PROGRAM_MANAGER → PO in 0066)
-- AM → PO → SK; ck_users_role allows AREA_MANAGER | PO | SHASTIYA_KORMI
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS district (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  updated_by text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_district_tenant_id ON district (tenant_id);

CREATE TABLE IF NOT EXISTS upazila (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  district_id bigint NOT NULL REFERENCES district(id) ON DELETE CASCADE,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  updated_by text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_upazila_tenant_id ON upazila (tenant_id);
CREATE INDEX IF NOT EXISTS ix_upazila_district_id ON upazila (district_id);

CREATE TABLE IF NOT EXISTS users (
  id bigint PRIMARY KEY,
  name text NOT NULL,
  role text NOT NULL,
  parent_id bigint NULL REFERENCES users(id) ON DELETE CASCADE,
  district_id bigint NOT NULL REFERENCES district(id) ON DELETE CASCADE,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  updated_by text NOT NULL,
  CONSTRAINT ck_users_role CHECK (
    role IN ('AREA_MANAGER', 'PO', 'SHASTIYA_KORMI')
  ),
  CONSTRAINT ck_users_parent_nullability CHECK (
    (role = 'AREA_MANAGER' AND parent_id IS NULL) OR
    (role <> 'AREA_MANAGER' AND parent_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users (tenant_id);
CREATE INDEX IF NOT EXISTS ix_users_district_id ON users (district_id);
CREATE INDEX IF NOT EXISTS ix_users_parent_id ON users (parent_id);
CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);

CREATE TABLE IF NOT EXISTS user_upazila (
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  upazila_id bigint NOT NULL REFERENCES upazila(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, upazila_id)
);

CREATE INDEX IF NOT EXISTS ix_user_upazila_user_id ON user_upazila (user_id);
CREATE INDEX IF NOT EXISTS ix_user_upazila_upazila_id ON user_upazila (upazila_id);

CREATE OR REPLACE FUNCTION enforce_users_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_role text;
    parent_district_id bigint;
    parent_tenant_id bigint;
    district_tenant_id bigint;
    expected_parent_role text;
BEGIN
    SELECT d.tenant_id INTO district_tenant_id
    FROM district d
    WHERE d.id = NEW.district_id;

    IF district_tenant_id IS NULL THEN
        RAISE EXCEPTION 'hierarchy_parent_invalid: district % not found', NEW.district_id;
    END IF;

    IF district_tenant_id <> NEW.tenant_id THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: user tenant_id % does not match district tenant_id %',
            NEW.tenant_id, district_tenant_id;
    END IF;

    IF NEW.role = 'AREA_MANAGER' THEN
        IF NEW.parent_id IS NOT NULL THEN
            RAISE EXCEPTION
                'hierarchy_parent_invalid: AREA_MANAGER must have parent_id NULL';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.parent_id IS NULL THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: role % requires a parent_id', NEW.role;
    END IF;

    SELECT u.role, u.district_id, u.tenant_id
    INTO parent_role, parent_district_id, parent_tenant_id
    FROM users u
    WHERE u.id = NEW.parent_id;

    IF parent_role IS NULL THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: parent user % not found', NEW.parent_id;
    END IF;

    IF parent_district_id <> NEW.district_id THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: parent district_id % does not match child district_id %',
            parent_district_id, NEW.district_id;
    END IF;

    IF parent_tenant_id <> NEW.tenant_id THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: parent tenant_id % does not match child tenant_id %',
            parent_tenant_id, NEW.tenant_id;
    END IF;

    IF NEW.role = 'PO' THEN
        expected_parent_role := 'AREA_MANAGER';
    ELSIF NEW.role = 'SHASTIYA_KORMI' THEN
        expected_parent_role := 'PO';
    ELSE
        RAISE EXCEPTION 'hierarchy_role_mismatch: unsupported role %', NEW.role;
    END IF;

    IF parent_role <> expected_parent_role THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: role % requires parent role %, got %',
            NEW.role, expected_parent_role, parent_role;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_hierarchy ON users;
CREATE TRIGGER trg_users_hierarchy
BEFORE INSERT OR UPDATE OF role, parent_id, district_id, tenant_id
ON users
FOR EACH ROW
EXECUTE FUNCTION enforce_users_hierarchy();

-- ──────────────────────────────────────────────────────────────────────────────
-- Config
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS config_threshold (
  id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  key text NOT NULL,
  value_json jsonb NOT NULL,
  title text NULL,
  description text NULL,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_config_threshold_tenant_key UNIQUE (tenant_id, key)
);

CREATE INDEX IF NOT EXISTS ix_config_threshold_tenant_id
  ON config_threshold (tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Prompt templates
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prompt_template (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id bigint NOT NULL,
  template_id text NOT NULL,
  version integer NOT NULL,
  variant_key text NULL,
  generation_type text NOT NULL,
  system_prompt_template text NOT NULL,
  human_message_template text NOT NULL,
  required_variables jsonb NOT NULL,
  title text NULL,
  description text NULL,
  change_notes text NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_prompt_template_tenant_id_variant_version
    UNIQUE (tenant_id, template_id, variant_key, version)
);

CREATE INDEX IF NOT EXISTS ix_prompt_template_template_id
  ON prompt_template (template_id);
CREATE INDEX IF NOT EXISTS ix_prompt_template_active_lookup
  ON prompt_template (template_id, variant_key, status);
CREATE INDEX IF NOT EXISTS ix_prompt_template_tenant_id
  ON prompt_template (tenant_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Alembic version tracking (revision 0064)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alembic_version (
  version_num varchar(32) NOT NULL,
  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('0064')
ON CONFLICT (version_num) DO UPDATE SET version_num = EXCLUDED.version_num;


-- Learning-points config_threshold seed (migration 0005)
-- plus quiz_reattempt_validity_days (0036)
-- ──────────────────────────────────────────────────────────────────────────────

INSERT INTO config_threshold (tenant_id, version, key, value_json, title, description) VALUES
  (0, 1, 'learning_points_module_delivered', '5'::jsonb,
   'Learning Points: Module Delivered',
   'CHW learning points awarded per module_delivered telemetry event'),
  (0, 1, 'learning_points_module_card_viewed', '10'::jsonb,
   'Learning Points: Module Card Viewed',
   'CHW learning points awarded per module_card_viewed telemetry event'),
  (0, 1, 'learning_points_module_quiz_attempted_base', '15'::jsonb,
   'Learning Points: Quiz Attempted (Base)',
   'Base CHW learning points for module_quiz_attempted (correct outcome)'),
  (0, 1, 'learning_points_module_quiz_score_multiplier', '15'::jsonb,
   'Learning Points: Quiz Score Multiplier',
   'Quiz score bonus multiplier: floor(quiz_score_pct [0–1] * this) added to base'),
  (0, 1, 'learning_points_module_completed', '20'::jsonb,
   'Learning Points: Module Completed',
   'CHW learning points awarded per module_completed telemetry event'),
  (0, 1, 'learning_points_spice_action_observed', '3'::jsonb,
   'Learning Points: Spice Action Observed',
   'CHW learning points awarded per spice_action_observed telemetry event'),
  (0, 1, 'quiz_reattempt_validity_days', '7'::jsonb,
   'Quiz Reattempt Validity (Days)',
   'Configure the number of days from the module assignment date during which users can reattempt a quiz. Users are always allowed their first quiz attempt, even if this period has expired. After the first attempt, reattempts are permitted only until the configured validity period ends.')
ON CONFLICT ON CONSTRAINT uq_config_threshold_tenant_key DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────
-- Referral behavioural_gap seed (seed/behavioural_gaps_referral.json; migration 0014)
-- ──────────────────────────────────────────────────────────────────────────────

INSERT INTO behavioural_gap (tenant_id, gap_code, description, domain, severity_default, detection_rule_jsonb, status)
VALUES
  (0, 'referral_iccm_danger_signs', 'CHW did not follow ICCM general danger signs referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["General Danger Signs"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["General Danger Signs"]}]},"metadata":{"tier":"referred_reason","values":["General Danger Signs"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_iccm_respiratory', 'CHW did not follow ICCM respiratory referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Pneumonia","Cough"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Pneumonia","Cough"]}]},"metadata":{"tier":"referred_reason","values":["Pneumonia","Cough"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_iccm_fever_malaria', 'CHW did not follow ICCM fever/malaria referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Fever","Malaria"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Fever","Malaria"]}]},"metadata":{"tier":"referred_reason","values":["Fever","Malaria"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_iccm_diarrhoea', 'CHW did not follow ICCM diarrhoea referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Diarrhoea"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Diarrhoea"]}]},"metadata":{"tier":"referred_reason","values":["Diarrhoea"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_iccm_malnutrition', 'CHW did not follow ICCM malnutrition referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["MUAC"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["MUAC"]}]},"metadata":{"tier":"referred_reason","values":["MUAC"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_iccm_other_symptoms', 'CHW did not follow ICCM other-symptoms referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Symptoms"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Symptoms"]}]},"metadata":{"tier":"referred_reason","values":["Symptoms"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_rmnch_anc_high_risk', 'CHW did not follow ANC high-risk referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["High risk pregnant woman"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]}]},"metadata":{"tier":"referred_reason","values":["High risk pregnant woman"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_rmnch_anc_care_gaps', 'CHW did not follow ANC care-gap referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Gaps in ANC"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in ANC"]}]},"metadata":{"tier":"referred_reason","values":["Gaps in ANC"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_rmnch_pnc_mother_high_risk', 'CHW did not follow PNC mother high-risk referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["High risk mother"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]}]},"metadata":{"tier":"referred_reason","values":["High risk mother"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_rmnch_pnc_care_gaps', 'CHW did not follow PNC care-gap referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Gaps in PNC"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in PNC"]}]},"metadata":{"tier":"referred_reason","values":["Gaps in PNC"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_rmnch_childhood_visit', 'CHW did not follow childhood visit referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Childhood Visit Signs"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Childhood Visit Signs"]}]},"metadata":{"tier":"referred_reason","values":["Childhood Visit Signs"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_tb_symptoms', 'CHW did not follow TB symptoms referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["TB Symptoms"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["TB Symptoms"]}]},"metadata":{"tier":"referred_reason","values":["TB Symptoms"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_cbs', 'CHW did not follow CBS referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["CBS Referral"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["CBS Referral"]}]},"metadata":{"tier":"referred_reason","values":["CBS Referral"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_ncd_cardiometabolic', 'CHW did not follow NCD cardiometabolic referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["NCD","High BP","High BG"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["NCD","High BP","High BG"]}]},"metadata":{"tier":"referred_reason","values":["NCD","High BP","High BG"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_ncd_mental_health', 'CHW did not follow NCD mental-health referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Mental Health","Suicidal Ideation"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Mental Health","Suicidal Ideation"]}]},"metadata":{"tier":"referred_reason","values":["Mental Health","Suicidal Ideation"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_ncd_substance', 'CHW did not follow NCD substance-use referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Substance Abuse"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Substance Abuse"]}]},"metadata":{"tier":"referred_reason","values":["Substance Abuse"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_ncd_hiv_pregnancy', 'CHW did not follow NCD HIV/pregnancy-symptom referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["HIV","Pregnancy Symptoms"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["HIV","Pregnancy Symptoms"]}]},"metadata":{"tier":"referred_reason","values":["HIV","Pregnancy Symptoms"],"mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_family_planning_consult', 'CHW did not follow family planning consult recommendation after pregnancy outcome.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.referredReason","values":["Family Planning Consult"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Family Planning Consult"]}]},"metadata":{"tier":"referred_reason","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_anc_emergency_obstetric', 'CHW deviated from ANC emergency (obstetric) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["Suspected Pre-eclampsia","Abnormal fundal height","Urinary Bilirubin present"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["Suspected Pre-eclampsia","Abnormal fundal height","Urinary Bilirubin present"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"obstetric","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_emergency_acute', 'CHW deviated from ANC emergency (acute) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["High Fever","Abnormal Pulse","Abnormal weight gain"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["High Fever","Abnormal Pulse","Abnormal weight gain"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"acute","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_emergency_severe_anemia', 'CHW deviated from ANC emergency (severe_anemia) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["Severe Anemia"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["Severe Anemia"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"severe_anemia","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_emergency_chronic_untreated', 'CHW deviated from ANC emergency (chronic_untreated) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["PW not on treatment for existing chronic illnesses"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.URGENT","values":["PW not on treatment for existing chronic illnesses"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"chronic_untreated","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_non_emergency_demographic', 'CHW deviated from ANC non-emergency (demographic) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["High risk PW due to age/birth spacing"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["High risk PW due to age/birth spacing"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"demographic","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_non_emergency_anemia', 'CHW deviated from ANC non-emergency (anemia) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Moderate Anemia","Mild Anemia"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Moderate Anemia","Mild Anemia"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"anemia","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_non_emergency_diabetes', 'CHW deviated from ANC non-emergency (diabetes) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Suspected/Existing Case of Diabetes"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Suspected/Existing Case of Diabetes"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"diabetes","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_non_emergency_chronic_treated', 'CHW deviated from ANC non-emergency (chronic_treated) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["PW with existing chronic illnesses with treatment"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["PW with existing chronic illnesses with treatment"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"chronic_treated","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_non_emergency_other', 'CHW deviated from ANC non-emergency (other) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Mild Fever","H/O Preg related medical complications","Other Danger Signs"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman.NON_URGENT","values":["Mild Fever","H/O Preg related medical complications","Other Danger Signs"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk pregnant woman"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"other","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_anc_gap_supplementation', 'CHW deviated from ANC care-gap (supplementation) recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["Inadequate /Non consumption IFA","Inadequate /Non consumption Calcium","TT vaccination incomplete"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["Inadequate /Non consumption IFA","Inadequate /Non consumption Calcium","TT vaccination incomplete"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in ANC"]}]}]},"metadata":{"tier":"anc_gap","group":"supplementation","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_anc_gap_visit_cadence', 'CHW deviated from ANC care-gap (visit_cadence) recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["USG not done >36 weeks","ANC with Doctor not done >36 weeks","Less than 3 ANCs completed at end of 36 weeks"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["USG not done >36 weeks","ANC with Doctor not done >36 weeks","Less than 3 ANCs completed at end of 36 weeks"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in ANC"]}]}]},"metadata":{"tier":"anc_gap","group":"visit_cadence","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_anc_gap_delivery_plan', 'CHW deviated from ANC care-gap (delivery_plan) recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["Facility not identified for institutional delivery","Planned for Home Delivery"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.anc.summary.gapsInAnc","values":["Facility not identified for institutional delivery","Planned for Home Delivery"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in ANC"]}]}]},"metadata":{"tier":"anc_gap","group":"delivery_plan","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_pnc_emergency_bleeding_infection', 'CHW deviated from PNC emergency (bleeding_infection) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["Heavy bleeding","Foul-smelling discharge","Severe abdominal pain","Perineum tear / Discharge from wound area"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["Heavy bleeding","Foul-smelling discharge","Severe abdominal pain","Perineum tear / Discharge from wound area"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"bleeding_infection","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_emergency_neurological', 'CHW deviated from PNC emergency (neurological) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["Severe headache/visual issues/convulsions"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["Severe headache/visual issues/convulsions"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"neurological","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_emergency_hypertensive', 'CHW deviated from PNC emergency (hypertensive) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High BP","Not on treatment for HTN or Pre-eclampsia /Eclampsia","Edema","Urine Albumin"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High BP","Not on treatment for HTN or Pre-eclampsia /Eclampsia","Edema","Urine Albumin"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"hypertensive","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_emergency_metabolic', 'CHW deviated from PNC emergency (metabolic) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High Blood sugar","Known DM/GDM patient not on treatment","Suspected Jaundice"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High Blood sugar","Known DM/GDM patient not on treatment","Suspected Jaundice"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"metabolic","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_emergency_acute', 'CHW deviated from PNC emergency (acute) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High Fever","Abnormal Pulse","Severe Anemia"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.URGENT","values":["High Fever","Abnormal Pulse","Severe Anemia"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"acute","referral_type":"emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_non_emergency_anemia', 'CHW deviated from PNC non-emergency (anemia) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["Moderate Anemia","Mild Anemia"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["Moderate Anemia","Mild Anemia"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"anemia","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_non_emergency_breast', 'CHW deviated from PNC non-emergency (breast) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["Cracked nipples / painful / swollen breasts with or without fever"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["Cracked nipples / painful / swollen breasts with or without fever"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"breast","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_non_emergency_chronic_treated', 'CHW deviated from PNC non-emergency (chronic_treated) referral recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["On treatment for HTN or Pre-eclampsia / Eclampsia","On treatment for DM/GDM","Fever","Other Danger Signs"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.motherRisks.NON_URGENT","values":["On treatment for HTN or Pre-eclampsia / Eclampsia","On treatment for DM/GDM","Fever","Other Danger Signs"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["High risk mother"]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]}]},"metadata":{"tier":"subcondition","group":"chronic_treated","referral_type":"non_emergency","mismatch_kind":"reason_or_urgency"}}'::jsonb, 'active'),
  (0, 'referral_pnc_gap_supplementation', 'CHW deviated from PNC supplementation care-gap recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"array_contains_substring","path":"recommended.assessmentDetails.pncMother.pncGaps","value":"Supplementation"},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"array_contains_substring","path":"recommended.assessmentDetails.pncMother.pncGaps","value":"Supplementation"},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in PNC"]}]}]},"metadata":{"tier":"pnc_gap","group":"supplementation","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_pnc_gap_contraception', 'CHW deviated from PNC contraception care-gap recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.pncGaps","values":["Not using postpartum contraception"]},{"op":"or","conditions":[{"op":"and","conditions":[{"op":"contains_any","path":"recommended.assessmentDetails.pncMother.pncGaps","values":["Not using postpartum contraception"]},{"op":"missed_referral"}]},{"op":"mismatch_contains_any","recommended_path":"recommended.referredReason","actual_path":"actual.referralReasons","values":["Gaps in PNC"]}]}]},"metadata":{"tier":"pnc_gap","group":"contraception","mismatch_kind":"missed_or_wrong_reason"}}'::jsonb, 'active'),
  (0, 'referral_type_emergency', 'CHW did not follow emergency (urgent) referral classification recommended by the rule engine.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"or","conditions":[{"op":"map_key_nonempty","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman","key":"URGENT"},{"op":"map_key_nonempty","path":"recommended.assessmentDetails.pncMother.motherRisks","key":"URGENT"}]},{"op":"mismatch_urgency","recommended_urgency":"URGENT","actual_path":"actual.isUrgent"}]},"metadata":{"tier":"referral_type","referral_type":"emergency","mismatch_kind":"urgency"}}'::jsonb, 'active'),
  (0, 'referral_type_non_emergency', 'CHW did not follow non-emergency referral classification recommended by the rule engine.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"or","conditions":[{"op":"map_key_nonempty","path":"recommended.assessmentDetails.anc.summary.highRiskPregnantWoman","key":"NON_URGENT"},{"op":"map_key_nonempty","path":"recommended.assessmentDetails.pncMother.motherRisks","key":"NON_URGENT"}]},{"op":"mismatch_urgency","recommended_urgency":"NON_URGENT","actual_path":"actual.isUrgent"}]},"metadata":{"tier":"referral_type","referral_type":"non_emergency","mismatch_kind":"urgency"}}'::jsonb, 'active'),
  (0, 'referral_location_upazila', 'CHW did not follow Upazila Health Complex destination recommended by the rule engine.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"or","conditions":[{"op":"eq","path":"recommended.referralFacilityType","value":"Upazila Health Complex"},{"op":"eq","path":"recommended.assessmentDetails.referralFacilityType","value":"Upazila Health Complex"}]},{"op":"or","conditions":[{"op":"missed_referral"},{"op":"mismatch_eq","recommended_path":"recommended.referralFacilityType","actual_path":"actual.destinationTier"},{"op":"mismatch_eq","recommended_path":"recommended.assessmentDetails.referralFacilityType","actual_path":"actual.destinationTier"}]}]},"metadata":{"tier":"location","destination":"upazila","mismatch_kind":"wrong_destination"}}'::jsonb, 'active'),
  (0, 'referral_location_community_clinic', 'CHW did not follow Community Clinic destination recommended by the rule engine.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"or","conditions":[{"op":"eq","path":"recommended.referralFacilityType","value":"Community Clinic"},{"op":"eq","path":"recommended.assessmentDetails.referralFacilityType","value":"Community Clinic"}]},{"op":"or","conditions":[{"op":"missed_referral"},{"op":"mismatch_eq","recommended_path":"recommended.referralFacilityType","actual_path":"actual.destinationTier"},{"op":"mismatch_eq","recommended_path":"recommended.assessmentDetails.referralFacilityType","actual_path":"actual.destinationTier"}]}]},"metadata":{"tier":"location","destination":"community_clinic","mismatch_kind":"wrong_destination"}}'::jsonb, 'active'),
  (0, 'referral_location_facility_selected', 'CHW did not follow rule-engine referral facility/site recommendation.', 'referral', 'high', '{"schema_version":1,"evaluator":"spice_referral_compliance","when":{"op":"and","conditions":[{"op":"or","conditions":[{"op":"exists","path":"recommended.assessmentDetails.anc.summary.referralFacility"},{"op":"exists","path":"recommended.assessmentDetails.pncMother.referralFacility"}]},{"op":"or","conditions":[{"op":"missed_referral"},{"op":"and","conditions":[{"op":"exists","path":"recommended.assessmentDetails.anc.summary.referralFacility"},{"op":"mismatch_eq","recommended_path":"recommended.assessmentDetails.anc.summary.referralFacility","actual_path":"actual.referredSiteId"}]},{"op":"and","conditions":[{"op":"exists","path":"recommended.assessmentDetails.pncMother.referralFacility"},{"op":"mismatch_eq","recommended_path":"recommended.assessmentDetails.pncMother.referralFacility","actual_path":"actual.referredSiteId"}]}]}]},"metadata":{"tier":"location","destination":"facility_selected","mismatch_kind":"wrong_site"}}'::jsonb, 'active')
ON CONFLICT (gap_code) DO UPDATE SET
  description = EXCLUDED.description,
  domain = EXCLUDED.domain,
  severity_default = EXCLUDED.severity_default,
  detection_rule_jsonb = EXCLUDED.detection_rule_jsonb,
  status = 'active',
  updated_at = now();

-- ──────────────────────────────────────────────────────────────────────────────
-- Assessment-due trigger_definition seed (seed/assessment_due_triggers.json; migration 0026)
-- ──────────────────────────────────────────────────────────────────────────────

INSERT INTO trigger_definition (tenant_id, trigger_kind, trigger_code, description, predicate_jsonb, predicate_schema_version, status)
VALUES
  (0, 'workflow_event', 'wf:assessment_due:anc', 'Patients due for antenatal care visit', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"anc","match":{"encounter_type_any":["ANC"],"reason_any":[],"diagnosis_any":["ANC"],"patient_status_any":["anc"],"reason_display_any":["ANC Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["ANC"],"encounter_program_any":["RMNCH"],"is_pregnant":true,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:anemia', 'Anemia follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"anemia","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["ANEMIA"],"patient_status_any":["anemia"],"reason_display_any":["Anemia"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:cbs', 'CBS escalation follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"cbs","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["cbs"],"reason_display_any":["CBS"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:child_health', 'Under-five child health visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"child_health","match":{"encounter_type_any":["CHILDHOOD_VISIT","PNC_CHILD","PNC_NEONATE","UNDER_FIVE_YEARS","UNDER_TWO_MONTHS"],"reason_any":[],"diagnosis_any":["PNC_NEONATE","UNDER_FIVE_YEARS","UNDER_TWO_MONTHS"],"patient_status_any":["child_health"],"reason_display_any":["Childhood Visit Signs","PNC Neonate Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["CHILDHOOD_VISIT","PNC_CHILD","PNC_NEONATE"],"encounter_program_any":["CHILDHOOD_VISIT"],"is_pregnant":null,"max_age":5,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:childhood_visit', 'Childhood wellness visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"childhood_visit","match":{"encounter_type_any":["CHILDHOOD_VISIT"],"reason_any":[],"diagnosis_any":[],"patient_status_any":["childhood_visit"],"reason_display_any":["Childhood Visit Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["CHILDHOOD_VISIT"],"encounter_program_any":["CHILDHOOD_VISIT","RMNCH"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:cough', 'Cough follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"cough","match":{"encounter_type_any":[],"reason_any":["COUGH"],"diagnosis_any":[],"patient_status_any":["cough"],"reason_display_any":["Cough"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:diarrhea', 'Diarrhoea follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"diarrhea","match":{"encounter_type_any":["DIARRHEA"],"reason_any":["DIARRHEA","DIARRHOEA"],"diagnosis_any":["DIARRHEA","DIARRHOEA"],"patient_status_any":["diarrhea"],"reason_display_any":["Diarrhoea","Dysentry (Bloody Diarrhoea)","Watery diarrhoea / Dysentery"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:ear_problem', 'Ear problem follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"ear_problem","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["EARPROBLEM","EAR_PROBLEM"],"patient_status_any":["ear_problem"],"reason_display_any":["Ear Problem"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:fever', 'Fever follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"fever","match":{"encounter_type_any":[],"reason_any":["FEVER"],"diagnosis_any":[],"patient_status_any":["fever"],"reason_display_any":["Fever"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:general_danger_signs', 'General danger signs follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"general_danger_signs","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["general_danger_signs"],"reason_display_any":["General Danger Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:hiv_aids', 'HIV/AIDS follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"hiv_aids","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["HIVAIDS","HIVINFECTION","HIV_AIDS"],"patient_status_any":["hiv_aids"],"reason_display_any":["HIV Infection","HIV/AIDS"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:iccm', 'ICCM community follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"iccm","match":{"encounter_type_any":["DIARRHEA","ICCM","MALARIA","OTHER_SYMPTOMS","PNEUMONIA","UNDER_FIVE_YEARS","UNDER_TWO_MONTHS"],"reason_any":["COUGH","DIARRHEA","DIARRHOEA","FEVER","MALARIA","MUAC","PNEUMONIA","SYMPTOMS"],"diagnosis_any":["ANEMIA","EARPROBLEM","EAR_PROBLEM","HIVAIDS","HIVINFECTION","HIV_AIDS","JAUNDICE","MODERATEMALNUTRITION","MODERATE_MALNUTRITION","MUAC","OTHER_SYMPTOMS","SEVEREMALARIA","SEVEREMALNUTRITION","SEVERE_MALARIA","SEVERE_MALNUTRITION","UNCOMPLICATEDMALARIA","UNCOMPLICATED_MALARIA","UNDER_FIVE_YEARS","UNDER_TWO_MONTHS"],"patient_status_any":["iccm"],"reason_display_any":[],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:jaundice', 'Jaundice follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"jaundice","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["JAUNDICE"],"patient_status_any":["jaundice"],"reason_display_any":["Jaundice"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:malaria', 'Malaria follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"malaria","match":{"encounter_type_any":["MALARIA"],"reason_any":["MALARIA"],"diagnosis_any":["MALARIA","SEVEREMALARIA","SEVERE_MALARIA","UNCOMPLICATEDMALARIA","UNCOMPLICATED_MALARIA"],"patient_status_any":["malaria"],"reason_display_any":["Malaria","Uncomplicated Malaria"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:maternal_health', 'Maternal health follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"maternal_health","match":{"encounter_type_any":["ANC","PNC_MOTHER"],"reason_any":[],"diagnosis_any":["ANC","PNC"],"patient_status_any":["maternal_health"],"reason_display_any":["ANC Signs","Gaps in PNC","High Risk Mother","PNC Mother Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["ANC","PNC_MOTHER"],"encounter_program_any":["RMNCH"],"is_pregnant":true,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:miscarriage', 'Miscarriage follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"miscarriage","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["miscarriage"],"reason_display_any":["Miscarriage"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:moderate_malnutrition', 'Moderate malnutrition follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"moderate_malnutrition","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["MODERATEMALNUTRITION","MODERATE_MALNUTRITION"],"patient_status_any":["moderate_malnutrition"],"reason_display_any":["Moderate Malnutrition"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:muac', 'MUAC malnutrition follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"muac","match":{"encounter_type_any":[],"reason_any":["MUAC"],"diagnosis_any":["MUAC"],"patient_status_any":["muac"],"reason_display_any":["MUAC"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:ncd', 'NCD follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"ncd","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["ncd"],"reason_display_any":["NCD","NCDSymptoms"],"appointment_type_any":[],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:neonatal', 'Neonatal follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"neonatal","match":{"encounter_type_any":["PNC_NEONATE","UNDER_TWO_MONTHS"],"reason_any":[],"diagnosis_any":["PNC_NEONATE","UNDER_TWO_MONTHS"],"patient_status_any":["neonatal"],"reason_display_any":[],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["PNC_NEONATE"],"encounter_program_any":[],"is_pregnant":null,"max_age":0,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:on_treatment', 'On-treatment household visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"on_treatment","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["on_treatment"],"reason_display_any":["On Treatment","OnTreatment"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:other_symptoms', 'Other symptoms ICCM follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"other_symptoms","match":{"encounter_type_any":["OTHER_SYMPTOMS"],"reason_any":["SYMPTOMS"],"diagnosis_any":["OTHER_SYMPTOMS"],"patient_status_any":["other_symptoms"],"reason_display_any":["Symptoms","TB Symptoms"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:pnc_child', 'Postnatal child visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"pnc_child","match":{"encounter_type_any":["PNC_CHILD"],"reason_any":[],"diagnosis_any":[],"patient_status_any":["pnc_child"],"reason_display_any":["Childhood Visit Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["PNC_CHILD"],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:pnc_mother', 'Postnatal mother visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"pnc_mother","match":{"encounter_type_any":["PNC_MOTHER"],"reason_any":[],"diagnosis_any":["PNC"],"patient_status_any":["pnc_mother"],"reason_display_any":["Gaps in PNC","PNC Mother Signs","PNC Visit"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["PNC_MOTHER"],"encounter_program_any":["RMNCH"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:pnc_neonate', 'Neonatal postnatal visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"pnc_neonate","match":{"encounter_type_any":["PNC_NEONATE"],"reason_any":[],"diagnosis_any":["PNC_NEONATE"],"patient_status_any":["pnc_neonate"],"reason_display_any":["PNC Neonate Signs"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":["PNC_NEONATE"],"encounter_program_any":["RMNCH"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:pneumonia', 'Pneumonia follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"pneumonia","match":{"encounter_type_any":["PNEUMONIA"],"reason_any":["COUGH","PNEUMONIA"],"diagnosis_any":["PNEUMONIA"],"patient_status_any":["pneumonia"],"reason_display_any":["Cough or Difficult Breathing","Pneumonia","Pneumonia / Fever"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":["ICCM"],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:recovered', 'Recovered patient follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"recovered","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["recovered"],"reason_display_any":["Recovered"],"appointment_type_any":[],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:referred', 'Referred patient follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"referred","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["referred"],"reason_display_any":["Referred"],"appointment_type_any":["REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:respiratory', 'Respiratory illness follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"respiratory","match":{"encounter_type_any":["PNEUMONIA"],"reason_any":["COUGH","PNEUMONIA"],"diagnosis_any":["PNEUMONIA"],"patient_status_any":["respiratory"],"reason_display_any":[],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:severe_malaria', 'Severe malaria follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"severe_malaria","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["SEVEREMALARIA","SEVERE_MALARIA"],"patient_status_any":["severe_malaria"],"reason_display_any":["Severe Malaria"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:severe_malnutrition', 'Severe malnutrition follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"severe_malnutrition","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["SEVEREMALNUTRITION","SEVERE_MALNUTRITION"],"patient_status_any":["severe_malnutrition"],"reason_display_any":["Severe Malnutrition"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:symptoms', 'Unspecified symptoms follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"symptoms","match":{"encounter_type_any":[],"reason_any":["SYMPTOMS"],"diagnosis_any":[],"patient_status_any":["symptoms"],"reason_display_any":["Symptoms"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:tb_symptoms', 'TB symptoms follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"tb_symptoms","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":[],"patient_status_any":["tb_symptoms"],"reason_display_any":["TB Symptoms"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:under_five_years', 'Under-five-years ICCM visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"under_five_years","match":{"encounter_type_any":["UNDER_FIVE_YEARS"],"reason_any":[],"diagnosis_any":["UNDER_FIVE_YEARS"],"patient_status_any":["under_five_years"],"reason_display_any":[],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:under_two_months', 'Under-two-months ICCM visit due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"under_two_months","match":{"encounter_type_any":["UNDER_TWO_MONTHS"],"reason_any":[],"diagnosis_any":["UNDER_TWO_MONTHS"],"patient_status_any":["under_two_months"],"reason_display_any":[],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active'),
  (0, 'workflow_event', 'wf:assessment_due:worsened', 'Worsened condition follow-up due today', '{"spice_event_code":"assessment_due","filter_predicate":{"assessment_topic":"worsened","match":{"encounter_type_any":[],"reason_any":[],"diagnosis_any":["WORSENED"],"patient_status_any":["worsened"],"reason_display_any":["Worsened"],"appointment_type_any":["HH_VISIT","MEDICAL_REVIEW","REFERRED"],"encounter_name_any":[],"encounter_program_any":[],"is_pregnant":null,"max_age":null,"min_age":null}}}'::jsonb, 1, 'active')
ON CONFLICT (trigger_code) DO UPDATE SET
  description = EXCLUDED.description,
  predicate_jsonb = EXCLUDED.predicate_jsonb,
  status = 'active',
  updated_at = now();

-- ──────────────────────────────────────────────────────────────────────────────
-- Prompt template seed (seed/prompt_templates.json; migrations 0044/0053)
-- ──────────────────────────────────────────────────────────────────────────────

INSERT INTO prompt_template (
  id, tenant_id, template_id, version, variant_key, generation_type,
  system_prompt_template, human_message_template, required_variables,
  title, description, change_notes, status
) VALUES
  ('172e2106-68be-5362-aac7-de2f5b4535b7'::uuid, 0, 'cross-source-fuser', 1, NULL, 'cross_source_fusion', 'You are pairing already-extracted training-module candidates from MULTIPLE
source documents that train the SAME community health worker (CHW).

Each candidate has a title, a scope summary, and a `source_document_id`
identifying which source document it came from. Different source documents
typically cover the SAME CHW activity from DIFFERENT angles:

- A clinical training manual covers WHY and WHEN — decision criteria,
  danger signs, BP thresholds, danger-sign synthesis, referral rationale.
- A digital workflow manual covers HOW — which app screen, which field,
  which button, what the app does next.

Your task: identify candidate GROUPS where two or more candidates from
DIFFERENT source documents cover the SAME CHW behavioural unit.

What "same behavioural unit" means:
- Same patient population + same CHW activity (e.g., pre-eclampsia detection
  during ANC; postpartum danger-sign recognition; family-planning counselling)
- The clinical reasoning and the app workflow are halves of one learnable
  unit for the CHW. Pushing only the clinical half (no app context) or only
  the app half (no clinical reasoning) gives the CHW half the answer.

What is NOT a fusion group:
- Two candidates from the SAME source_document_id (those are intra-source
  duplicates, not cross-source fusions; do not merge them here)
- Two candidates whose topics are merely adjacent or share a domain
  (e.g., "Hypertension management" and "Diabetes management" — both NCDs
   but different CHW behavioural units; KEEP SEPARATE)
- Generic skill candidates that don''t pair with a specific clinical/workflow
  counterpart (e.g., "Communication skills" stays alone unless paired with
  a workflow about a specific app communication feature)

Strict rules:
1. A candidate appears in AT MOST ONE fusion group.
2. Every fusion group MUST contain candidates from AT LEAST TWO DIFFERENT
   source_document_id values. A "group" of all-same-source candidates is
   invalid — leave them as-is.
3. Most candidates will NOT be in any fusion group. That is expected and
   correct. Single-source candidates are first-class outputs of this
   pipeline; fusion is for cases where the cross-source pairing is
   genuinely tight.
4. Bias toward LEAVING candidates UNPAIRED. False fusions degrade reviewer
   experience more than missed fusions.

For each fusion group, produce:
- candidate_ids: the list of candidate IDs being merged (≥2, from ≥2 distinct
  source documents)
- merged_title: a concise English title that captures the unified CHW unit
  (e.g., "Pre-eclampsia detection and digital referral" — combines clinical
  threshold + app referral workflow)
- merged_scope_summary: 3-5 sentences describing what the fused module
  teaches, drawing from BOTH the clinical reasoning AND the app workflow
- pairing_rationale: 1-2 sentences explaining why these candidates pair
  (what makes them the same CHW behavioural unit)

Return STRICT JSON with this top-level shape:
{
  "fusion_groups": [
    {
      "candidate_ids": ["uuid-1", "uuid-2"],
      "merged_title": "...",
      "merged_scope_summary": "...",
      "pairing_rationale": "..."
    },
    ...
  ]
}

If no candidates pair across sources, return `{"fusion_groups": []}`.
Do not include markdown fences or commentary. Only the JSON object.
', '{candidates_json}', '["candidates_json"]'::jsonb, 'Cross-source fuser', 'Stage 2b candidate pairing across source documents', 'Initial seed from Python prompt modules', 'active'),
  ('c9e89e55-7d1d-5fc2-8240-518e65e2ae46'::uuid, 0, 'gap-classification', 1, NULL, 'module_gap_classification', 'You classify community-health-worker (CHW) training modules against a fixed
registry of referral-domain compliance gaps. Each registry entry describes a
referral practice failure detected at visit time (e.g. missed referral, wrong
destination, incorrect urgency). The module''s primary teaching gap is already
assigned separately; you are selecting secondary referral associations only.

Rules:
- Select ONLY gap_codes from the supplied registry. Do not invent codes.
- Multi-label: return every registry gap that genuinely applies to what the
  module teaches or corrects. Return an empty list when no registry gap fits.
- Do NOT select codes starting with `module_primary_gap_` (those are
  module-specific primary gaps, not registry entries).
- Prefer precision over recall: include a gap only when the module content
  clearly addresses that failure pattern.
- At most {max_associations} associated_gap_codes.

Return STRICT JSON with this shape:
{{
  "associated_gap_codes": ["gap_code_from_registry", ...],
  "rationale": "1-3 sentences for clinical reviewers explaining the mapping"
}}

Do not include markdown fences or commentary. Only the JSON object.
', '## BEHAVIOURAL GAP REGISTRY ##
{registry_gaps_json}

## MODULE TO CLASSIFY ##
{module_payload_json}', '["max_associations", "registry_gaps_json", "module_payload_json"]'::jsonb, 'Gap classification', 'Post-publish behavioural gap registry mapping', 'Initial seed from Python prompt modules', 'active'),
  ('ba51da65-3dc9-58f4-b81e-26a45b1c2be9'::uuid, 0, 'assessment-topic-classification', 1, NULL, 'module_assessment_topic_classification', 'You classify community-health-worker (CHW) training modules against a fixed
registry of assessment-due patient condition topics. These topics correspond to
patients due for follow-up visits today (RMNCH, ICCM, child health).

Rules:
- Select ONLY assessment_topic keys from the supplied allow-list. Do not invent keys.
- Multi-label: return every topic that genuinely applies to what the module teaches.
  Return an empty list when no topic fits.
- Prefer precision over recall: include a topic only when module content clearly
  addresses that clinical follow-up condition.
- Choose exactly one primary_topic from assessment_topics (the best single match).
- At most {max_topics} assessment_topics.

Return STRICT JSON with this shape:
{{
  "assessment_topics": ["topic_key_from_allow_list", ...],
  "primary_topic": "one_of_assessment_topics",
  "rationale": "1-3 sentences for clinical reviewers explaining the mapping"
}}

Do not include markdown fences or commentary. Only the JSON object.


Allowed topics: {allowed_topics_line}', '## ALLOWED ASSESSMENT TOPICS ##
{allowed_topics_json}

## SEARCH METADATA ##
{search_metadata_json}

## MODULE TO CLASSIFY ##
{module_payload_json}', '["max_topics", "allowed_topics_line", "allowed_topics_json", "search_metadata_json", "module_payload_json"]'::jsonb, 'Assessment topic classification', 'Post-publish assessment-due topic mapping', 'Initial seed from Python prompt modules', 'active'),
  ('e3482599-f455-548b-9e8f-36031319aadb'::uuid, 0, 'chat-faq-synthesis', 1, NULL, 'chat_faq_synthesis', 'You generate FAQ suggestion chips for a community-health-worker (CHW) field chat
experience in {deployment_region_context}. You receive clusters of real questions
CHWs typed in the app. Each cluster groups paraphrases of the same underlying
clinical topic.

Rules:
- Produce exactly {target_count} FAQ items (or fewer only if fewer clusters were provided).
- For each item, write one natural question in the `question` map — phrasing a CHW
  might tap as a suggestion chip ({primary_locale_label} required).
- Base wording only on themes present in the cluster members; do not invent clinical
  facts, thresholds, or protocols not implied by the inputs.
- Deduplicate overlapping topics across clusters.
- Set source_cluster_index to the cluster index from the input (0-based).

Return STRICT JSON with this shape:
{{
  "faqs": [
    {{
{question_field_schema}
      "source_cluster_index": 0
    }}
  ]
}}

Do not include markdown fences or commentary. Only the JSON object.
', '## CLUSTERED CHW QUESTIONS ##
{clusters_json}', '["target_count", "deployment_region_context", "primary_locale_label", "question_field_schema", "clusters_json"]'::jsonb, 'Chat FAQ synthesis', 'Nightly FAQ chip generation from clustered questions', 'Initial seed from Python prompt modules', 'active'),
  ('a1f10a87-6887-5091-b4d6-18f7750f2bf2'::uuid, 0, 'chat-feedback-summary', 1, NULL, 'chat_feedback_summary', 'You analyze community-health-worker (CHW) chat feedback for a coaching platform.

You receive:
- Counts of new positive and negative feedback events in the current incremental window.
- Sampled events with the CHW''s question (`question`), user comment (`feedback`),
  excerpt of the chat answer (`answer_excerpt`), and `inference_mode`.
- Optionally, a previous cumulative summary to merge forward.

Rules:
- Produce an updated cumulative summary that incorporates both the previous summary (if any)
  and the new events in this window.
- Split findings by inference mode:
  - Online: `inference_mode` is "online" (RAG responses).
  - Offline: edge, cached, on-device, or any non-online mode.
- For each mode, highlight what went well and what could be improved:
  - `positive_online_themes` / `positive_offline_themes`: what is working well.
  - `negative_online_recommendations` / `negative_offline_recommendations`: concrete,
    actionable improvements.
- Use `question` and `feedback` together to understand context; do not ignore the question.
- Base recommendations only on evidence in the inputs; do not invent modules, protocols, or facts.
- Keep each item concise (one sentence). Limit to at most 8 items per list.
- `llm_summary` should be 3-6 sentences covering positive and negative trends for both modes.

Return STRICT JSON with this shape:
{
  "llm_summary": "...",
  "positive_online_themes": ["..."],
  "positive_offline_themes": ["..."],
  "negative_online_recommendations": ["..."],
  "negative_offline_recommendations": ["..."]
}

Do not include markdown fences or commentary. Only the JSON object.
', '## CHAT FEEDBACK EVENTS ##
{payload_json}', '["payload_json"]'::jsonb, 'Chat feedback summary', 'Weekly cumulative chat feedback digest', 'Initial seed from Python prompt modules', 'active'),
  ('b7c4e91a-2f8d-5a1e-9c3b-6d0e4f8a1b2c'::uuid, 0, 'module-creation-suggestion', 1, NULL, 'module_creation_suggestion', 'You help coaching-platform content admins decide which training modules to create next.
You receive:
1) A catalog of EXISTING DRAFT modules (id + title) for this tenant.
2) Deduped CHW chatbot questions that had no module_id.
3) Deduped free-text module request names that had no module_id.

Task: group the evidence into suggested modules.

Rules:
- Prefer matching evidence to an existing draft when the topic clearly fits. Use ONLY draft ids from the catalog.
- When no draft fits, propose a concise new topic name (English) under proposed_topic.
- Each suggestion must be either matched_module_id OR proposed_topic (not both).
- Attach evidence via the provided keys (evidence_question_keys / evidence_request_keys).
- Prefer precision: do not force weak matches onto drafts.
- At most {max_suggestions} suggestions, ranked by evidence volume (most demand first).
- Return STRICT JSON only.

Output shape:
{{
  "suggestions": [
    {{
      "matched_module_id": "uuid-from-catalog-or-null",
      "proposed_topic": "new topic or null",
      "rationale": "1-2 sentences",
      "evidence_question_keys": ["normalized_key", ...],
      "evidence_request_keys": ["normalized_key", ...]
    }}
  ]
}}
', '## SUGGESTION DATE (UTC) ##
{suggestion_date}

## DRAFT MODULE CATALOG ##
{draft_catalog_json}

## DEDUPED CHAT QUESTIONS ##
{questions_json}

## DEDUPED FREE-TEXT MODULE REQUESTS ##
{requests_json}', '["max_suggestions", "suggestion_date", "draft_catalog_json", "questions_json", "requests_json"]'::jsonb, 'Module creation suggestion', 'Daily mapping of unattributed demand to draft modules or new topics', 'Initial seed for module creation suggestions job', 'active'),
  ('5ca253ca-abc0-529b-8df4-65dda09b76d8'::uuid, 0, 'search-metadata', 1, NULL, 'module_search_metadata', 'You generate search metadata for community-health-worker (CHW) training modules
in {deployment_region_context}. The metadata helps health workers find the right
module when they type natural clinical questions or keywords — not just when
they know the exact module title.

Given a drafted module (title, description, domain, and card summaries), produce
lexical enrichment plus structured tags.

Rules:
- keywords: short terms, abbreviations, and clinical vocabulary
  (≤ {max_keywords}).
- search_phrases: natural-language questions or scenarios a CHW might type
  (≤ {max_search_phrases}). Include symptom-duration patterns, threshold questions,
  and referral scenarios when relevant.
- synonyms: map abbreviations to expanded forms in the deployment primary language
  (e.g. "ARI" → expanded form in that language). Abbrev keys may be Latin acronyms
  (≤ {max_synonyms}).
- topic_tags: broad topical labels in the deployment primary language using snake_case
  (e.g. respiratory, child_health) (≤ {max_tags}).
- clinical_conditions: specific conditions or syndromes the module addresses, in the
  deployment primary language (≤ {max_tags}).
- audience: always "chw_field_worker".
- rationale: one sentence for clinical reviewers explaining the metadata choices.

Return STRICT JSON with this shape:
{{
  "schema_version": 1,
{keywords_field_schema}
{search_phrases_field_schema}
{synonyms_field_schema}
{topic_tags_field_schema}
{clinical_conditions_field_schema}
  "audience": "chw_field_worker",
  "rationale": "..."
}}

Do not include markdown fences or commentary. Only the JSON object.
', '## MODULE TO INDEX ##
{module_payload_json}', '["deployment_region_context", "max_keywords", "max_search_phrases", "max_synonyms", "max_tags", "keywords_field_schema", "search_phrases_field_schema", "synonyms_field_schema", "topic_tags_field_schema", "clinical_conditions_field_schema", "module_payload_json"]'::jsonb, 'Module search metadata', 'Post-publish module retrieval metadata', 'Initial seed from Python prompt modules', 'active'),
  ('984ed71c-e912-5e66-9ee9-610716cde093'::uuid, 0, 'card-search-metadata', 1, NULL, 'card_search_metadata', 'You generate search metadata for ALL cards in a community-health-worker (CHW)
training module in {deployment_region_context}. The metadata helps health workers
find each specific card when they type natural clinical questions or keywords.

Given module context plus an array of cards (title, body, practice fields),
produce lexical enrichment for every card, scoped only to what each card covers.

Rules (apply per card):
- retrieval_hints: short natural-language search scenarios a CHW might type to
  find this card (≤ {max_retrieval_hints}). Include symptom-duration patterns
  and threshold questions when relevant.
- keywords: short terms, abbreviations, and clinical vocabulary from or implied
  by the card (≤ {max_keywords}).
- synonyms: map abbreviations to expanded forms in the deployment primary language
  (e.g. "ARI" → expanded form in that language). Abbrev keys may be Latin acronyms
  (≤ {max_synonyms} entries).
- questions: explicit FAQ-style questions this card answers
  (≤ {max_questions}). Distinct from retrieval hints — full questions, not fragments.

Return STRICT JSON with this shape:
{{
  "schema_version": 1,
  "cards": [
    {{
      "card_index": 0,
{retrieval_hints_field_schema}
{keywords_field_schema}
{synonyms_field_schema}
{questions_field_schema}
    }}
  ]
}}

Include one entry per input card. Each entry MUST include the matching card_index.
Do not include markdown fences or commentary. Only the JSON object.
', '## MODULE CONTEXT ##
{module_context_json}

## CARDS TO INDEX ##
{cards_json}', '["deployment_region_context", "max_retrieval_hints", "max_keywords", "max_synonyms", "max_questions", "retrieval_hints_field_schema", "keywords_field_schema", "synonyms_field_schema", "questions_field_schema", "module_context_json", "cards_json"]'::jsonb, 'Card search metadata', 'Post-publish per-card retrieval metadata', 'Initial seed from Python prompt modules', 'active'),
  ('9ded2f24-5d4a-5efe-837f-ad9283fac4a3'::uuid, 0, 'published-module-merger', 1, NULL, 'module_published_merge', 'You merge a NEWLY DRAFTED training module with at most ONE EXISTING module
(published or draft — not retired) only when they are substantively the SAME
training unit with majority overlapping card content.

A behavioural unit is ONE actionable topic the CHW must internalise (e.g.
"Correct ANC referral by risk category", not "all of ANC").

When to match (ALL must hold):
- The existing module and new candidate teach the same CHW behavioural unit.
- A MAJORITY of the existing module''s cards cover the same substantive teaching
  points as cards in the new set (compare titles and bodies, not just domain).
- Overall card-body content overlap is HIGH across both sets — not keyword overlap
  or shared domain alone.
- If the existing module has semantically similar content overall to the new candidate, then match.
- If the existing module can be considered a subset of the new candidate in a way they are semantically similar, then match.
- If the existing module and the new candidate prescribes similar content, then match.

When NOT to match:
- Same domain but different topics (e.g. hypertension management vs diabetes).
- Only one or a minority of existing cards align with the new cards.
- You are uncertain — prefer NO match.
- These cards for a module are to be learnt by the CHW, so if the level of granularity is different, then do not match.

Rules:
1. Pick AT MOST ONE `matched_module_id` from the existing-modules list, or null if
   none meet the criteria above.
2. When matched: produce `merged_cards` combining BOTH card sets.
   - On overlapping topic/content, prefer the NEW candidate''s card text.
   - Keep unique cards from the existing module that the new set does not
     replace.
   - Respect card count bounds: minimum {card_min_count}, maximum {card_max_count}.
3. When NOT matched: set `matched_module_id` to null and set `merged_cards`
   to the new candidate''s cards unchanged (copy them exactly).
4. Do NOT invent clinical content. Preserve source_block_ids from inputs.
5. All card text must be in the deployment primary locale ({primary_locale_label}).
6. In `match_rationale`, briefly estimate overlap (e.g. "4/5 existing cards align").

Return STRICT JSON with this shape:
{{
  "matched_module_id": "uuid-string or null",
  "match_rationale": "1-3 sentences explaining match or why no match",
  "merged_cards": [
    {{
{title_field_schema}
{body_field_schema}
{next_action_field_schema}
{previous_practice_field_schema}
{current_practice_field_schema}
{rationale_field_schema}
      "source_block_ids": ["uuid", ...],
      "thresholds": {{}} or null,
      "figure_ref_block_id": "uuid or null"
    }}
  ]
}}

Do not include markdown fences or commentary. Only the JSON object.
', '## NEW CANDIDATE ##
{candidate_json}

## NEW CARDS ##
{new_cards_json}

## EXISTING MODULES (pick at most one match) ##
{existing_modules_json}', '["card_min_count", "card_max_count", "primary_locale_label", "title_field_schema", "body_field_schema", "next_action_field_schema", "previous_practice_field_schema", "current_practice_field_schema", "rationale_field_schema", "candidate_json", "new_cards_json", "existing_modules_json"]'::jsonb, 'Published module merger', 'Stage 2-draft merge with existing published modules', 'Initial seed from Python prompt modules', 'active'),
  ('d76f84ed-e5a3-56bf-ba1d-27daac09d885'::uuid, 0, 'module-identifier', 1, NULL, 'module_identification', 'You are drafting BEHAVIOURAL TOPIC modules for community health workers (CHWs)
in {deployment_region_context}.

A module covers ONE actionable behavioural topic the CHW must internalise correctly. Examples:
- "Correct ANC referral by risk category"
- "Recognising postpartum danger signs"
- "Hypertension identification and management" (when the source has a dedicated HTN chapter)
- "Dengue fever recognition, prevention, and referral"
- "Effective communication and counselling skills" (when the source has a dedicated chapter)
- "BRAC field activities and follow-up workflow" (when the source has an operational chapter)
- "SPICE form submission failure recovery"

GROUPING RULES — do NOT over-fragment, do NOT under-emit:

1. Do NOT create modules per individual test, vital sign, lab value, or
   measurement threshold (e.g. don''t make separate modules for "BP measurement",
   "Hb measurement", "blood-glucose threshold"). Group related measurements
   into a parent procedural unit (e.g. "Performing antenatal physical and
   pathological examinations").

2. DO create a standalone module per NAMED DISEASE or DEDICATED CHAPTER
   the source treats as its own learning unit. If the source corpus has a
   chapter on Hypertension, Diabetes, Tuberculosis, Malaria, Cancer, Dengue,
   Diarrhoea, ARI/Pneumonia, etc., emit a dedicated module for it — even
   when the chapter overlaps with an adjacent screening or measurement
   chapter. The CHW''s ongoing-management knowledge for the disease is
   distinct from the one-shot screening procedure.

3. DO create a module for non-clinical CHW skill chapters: communication,
   counselling skills, field activities, reporting workflow, safeguarding.
   These are CHW practice topics even though they are not disease-management.
   Don''t deprioritise them just because they aren''t clinical.

4. DO NOT propose modules from annexures, appendices, or reference
   sections. Forms, checklists, reporting templates, consent forms, and
   reference tables (e.g. "Healthcare Services by Facility Level") are
   JOB AIDS — the CHW fills them out or looks at them on the job, not
   topics they internalise through training. Detection cues:
   - Page or section heading begins with {annexure_terms}
     or similar.
   - Content is dominated by blank fields, tick-box rows, signature
     lines, or columnar reference data the user fills in or looks up.
   The training-content equivalent (e.g. "How to fill the NCD reporting
   form" as a procedural lesson) IS a valid module — the line is between
   the form itself (job aid) and the procedure of using it (trainable).

DO NOT invent topics. Only group and label content present in the source corpus.

For `domain`, pick the single best topical label for admin filtering — the
disease, program area, or skill the module primarily teaches (e.g. ANC module
→ "anc", hypertension chapter → "hypertension", digital app workflow →
"digital"). Do NOT default every candidate to the same value.

{ingestion_guidance_section}{cardinality_guidance_section}
You are receiving:
1. Document outline — section structure with page ranges
2. Already-published modules — DO NOT duplicate
3. Per-page corpus content — markdown text + content_block_ids

Content-domain branching:
{content_domain_branch_instructions}

CITATION FORMAT — READ CAREFULLY:

The CORPUS section below uses SHORT TOKENS to identify documents, pages,
and content blocks instead of full UUIDs. You will see headers like:

    ### source_document_id=d1 content_domain=...
    #### source_page_id=p47 page_number=12
    [content_block_id=b231 block_type=paragraph]

In your `source_provenance` output, use the SAME short tokens — `d1`,
`p47`, `b231` — exactly as they appear. DO NOT invent UUIDs. DO NOT
expand the tokens. Copy them character-for-character.

For EACH candidate module, return a JSON object with these fields:
{{
  "proposed_title": "string — short topic title in the deployment primary locale",
  "scope_summary": "string — one paragraph, ~3-5 sentences",
{description_field_schema}
  "source_provenance": [
    {{
      "source_document_id": "short token like ''d1'' (NOT a UUID)",
      "source_page_id": "short token like ''p47'' (NOT a UUID)",
      "content_block_ids": ["short token like ''b231''", "..."]
    }},
    ...
  ],
  "estimated_card_count": integer ({card_count_schema}),
  "estimated_quiz_count": integer ({quiz_count_schema}),
  "proposed_module_type": "refresher" | "content_update" | "digital_proficiency" | "initial_training",
  "domain": "string — snake_case program topic bucket for admin filtering; prefer a specific label from the corpus (e.g. dengue, pneumonia) when the source has a dedicated chapter, otherwise use the closest common domain when one fits: {module_domain_catalog}. Use snake_case; do not invent unrelated domains.",
  "clinical_review_notes": "string — what the reviewer should validate",
{ingestion_rationale_field}  {content_update_fields}
}}

Return STRICT JSON. The output must be a single JSON object with this top-level shape:
{{
  "candidates": [
    {{ ... candidate object ... }},
    ...
  ]
}}

Do not include markdown fences or commentary. Only the JSON object.
', '{head_json}

## CORPUS ##
{corpus_body}

{tail_json}{ingestion_suffix}', '["deployment_region_context", "annexure_terms", "ingestion_guidance_section", "cardinality_guidance_section", "content_domain_branch_instructions", "description_field_schema", "card_count_schema", "quiz_count_schema", "module_domain_catalog", "ingestion_rationale_field", "content_update_fields", "head_json", "corpus_body", "tail_json", "ingestion_suffix"]'::jsonb, 'Module identifier', 'Stage 2 module candidate identification', 'Initial seed from Python prompt modules', 'active'),
  ('fdd08d0c-30a4-5334-979c-d6661432f8b9'::uuid, 0, 'card-drafter', 1, NULL, 'card_drafting', 'You are drafting learning cards for community health workers (CHWs)
in {deployment_region_context}.

GROUND RULES (apply to every card):
- Each card covers ONE focused sub-topic. Do NOT cram multiple unrelated points
  into one card.
- Card content must come from the cited content_blocks below. Do NOT invent
  clinical content. If a sub-topic has no source coverage, drop the card.
- Write card text as plain sentences. Do NOT use markdown formatting (no headings
  like `##`, no bullet lists, no tables, no blockquotes, no code fences).
- Content ({primary_locale_label} — keys under title / body / etc.) must use the
  EXACT vocabulary and tone of the cited blocks in that language where available
  — these are the training-manual phrasings the CHW already learned. Do NOT
  colloquialise. (Prose and terminology only; symbol/range notation follows the
  verbalization rules below.)
{symbol_verbalization_rules}
- Maximum {card_max_count} cards. If the candidate''s scope produces more, pick
  the {card_max_count} most-important sub-topics.
- Minimum {card_min_count} cards. If you cannot draft that many from the cited
  blocks, return {{"insufficient_for_drafting": "<reason_code>"}} where reason_code
  is one of: no_actionable_content | single_concept_only | no_quiz_anchors.

CROSS-SOURCE COVERAGE (only when blocks span multiple sources):
Each cited block is tagged with its `source` label (e.g. `source=d1`,
`source=d2`). When the cited blocks span MULTIPLE source labels — meaning
this is a FUSED candidate that combines content from a clinical training
manual + a digital workflow guide (or two related sources) — your card
set MUST collectively cite blocks from EVERY source label present.
Specifically:
- At least one card per source label must include at least one
  `source_block_ids` entry from that source.
- The fused candidate exists because the clinical reasoning and the app
  workflow are halves of one CHW learning unit. Cards drawing only from
  one source defeat the purpose and produce a misleading module shape
  (fused title, single-source cards).
- If a source has only 1-2 cited blocks (an under-represented half), you
  must still produce at least one card grounded in those blocks even
  though the larger source has more material. Do NOT silently drop the
  smaller source.
- When all cited blocks are from a single source, this rule is a no-op
  and existing single-source drafting behaviour applies unchanged.

{module_type_rules}

OUTPUT SHAPE (strict JSON, no markdown fences, no commentary):
{{
  "cards": [
    {{
      "card_order": int (1-indexed),
{title_field_schema}
{body_field_schema}
      "thresholds": [
        {{"label": "BP threshold", "value": "140/90 mmHg"}},
        ...
      ] (optional, for clinical thresholds; preserve digits verbatim, verbalize symbols),
      "figure_ref_block_id": "uuid string or null (cite a content_block of block_type=figure)",
      "source_block_ids": ["uuid string", ...] (every block that informed this card)
    }},
    ...
  ]
}}

If you cannot meet the minimum card count, return:
{{ "insufficient_for_drafting": "<reason_code>" }}

Only ONE of `cards` or `insufficient_for_drafting` should be populated.
', '{head_json}
{cited_blocks_body}', '["deployment_region_context", "primary_locale_label", "card_min_count", "card_max_count", "symbol_verbalization_rules", "module_type_rules", "title_field_schema", "body_field_schema", "head_json", "cited_blocks_body"]'::jsonb, 'Card drafter', 'Stage D bilingual card drafting', 'Initial seed from Python prompt modules', 'active'),
  ('86af8d7e-326a-5ca1-b9b5-4deca46e0525'::uuid, 0, 'vision', 1, NULL, 'vision_extraction', 'You are an expert assistant tasked with describing pages of a clinical training document for retrieval.
A page image may contain text (paragraphs, headings), tables, figures, charts, or diagrams.

Instructions:
1. Return any text paragraphs verbatim — do NOT translate or paraphrase.
2. Return tables in markdown format.
3. For figures, charts, or diagrams: describe content clearly (title, axes, labels, key data points).
4. Do not use lead-in phrases like "The image shows" or "This page contains".
5. Output plain text / markdown suitable for downstream clinical scenario extraction.
6. Preserve the source language exactly (Bangla stays Bangla, English stays English).
7. Mark headings with Markdown syntax. Heading rules are STRICT:
   - At most ONE `#` per page. Use `#` ONLY when the page introduces a new chapter
     (typically the first page of a chapter where the chapter title is the largest text).
     If the page is a continuation of an ongoing chapter, do NOT use `#` at all.
   - Use `##` for section headings within a chapter (e.g. "পাঠ শিরোনাম", "উদ্দেশ্য",
     "প্রক্রিয়া"), `###` for subsection headings.
   - Numbered list items (e.g. "1. Fundal height", "14. Edema"), bulleted list items,
     glossary terms, definition list entries, and table headers are NEVER headings —
     even when bold or visually prominent. They are list items, definition entries,
     or table content. Body paragraphs have no marker.
8. Never use HTML tags (`<b>`, `<ul>`, `<li>`, etc.). Use markdown only:
   `**bold**`, `- bullets`, `1. numbered items`.
', 'Describe this page following the instructions above.', '[]'::jsonb, 'Vision extraction', 'Stage A vision fallback page extraction', 'Initial seed from Python prompt modules', 'active'),
  ('bab63684-d261-5a7b-a377-8b0e55b3bced'::uuid, 0, 'quiz-generation', 1, NULL, 'quiz_drafting', 'You write scenario-based quiz questions for community health workers (CHWs)
in {deployment_region_context}, using locale-keyed maps for all translatable fields.
The questions are delivered by a low-spec mobile app — they cannot use rich
media, only text.

Rules:
- One quiz item per question_index. Do NOT cluster sub-questions.
- Each question references content present in the supplied module cards.
  Do not invent facts.
- Single-select questions only (no multi-select, no ordering).
- 4 options per question. Exactly one is correct.
- Distractors must be plausibly wrong — content the CHW could reasonably
  pick if they had not internalised the card. No silly distractors.
- All translatable fields use the deployment primary locale ({primary_locale}).
- Explanations must stand alone: explain why the correct answer is correct in
  clinical prose. Do NOT mention card numbers, card titles, or phrases like
  "see Card N" / "কার্ড N". The `primary_card_index` field records which card
  the question tests — do not echo it in `explanation`.

Return STRICT JSON. The output must be a single object with this shape:
{{
  "questions": [
    {{
{case_setup_field_schema}
{question_field_schema}
{options_field_schema}
      "correct_index": integer (0-3),
{explanation_field_schema}
      "primary_card_index": integer (1-based card number this question tests),
      "difficulty": "easy" | "moderate" | "hard"
    }},
    ...
  ]
}}

Do not include markdown fences or commentary. Only the JSON object.', 'Module title: {module_title}
Module domain: {domain}
Estimated quiz size: {quiz_size} questions

## CARDS ##
{cards_block}
', '["deployment_region_context", "primary_locale", "case_setup_field_schema", "question_field_schema", "options_field_schema", "explanation_field_schema", "module_title", "domain", "quiz_size", "cards_block"]'::jsonb, 'Quiz generation', 'Post-publish scenario-based quiz generation', 'Initial seed from Python prompt modules', 'active'),
  ('721183d1-b6c3-583f-b2be-a1392b305a91'::uuid, 0, 'coaching-rag', 1, NULL, 'coaching_rag', 'You are a clinical / CHW training assistant. Answer ONLY using the MODULE_BLOCK excerpts. If the context is insufficient, say so explicitly. Respond with a single JSON object, no markdown fences, keys:
- "answer": string (primary language: {lang_label})
- "cited_module_ids": array of UUID strings — only modules you relied on from the MODULE_BLOCK headers
- "suggested_questions": array of 3–5 strings — follow-up questions a CHW might ask next; each MUST be fully answerable solely from the CARD_CONTENT inside the MODULE_BLOCK excerpts (not general medical knowledge or content absent from the excerpts); do not repeat or lightly rephrase the current user question; primary language: {lang_label}; return fewer items or [] if context is insufficient
- "confidence": optional string "high"|"medium"|"low"
', 'USER_QUESTION ({lang}):
{question}

RETRIEVAL_CONTEXT:
{context}
Return JSON only.', '["lang_label", "lang", "question", "context"]'::jsonb, 'Coaching RAG', 'Live coaching Q&A over retrieved module blocks', 'Initial seed from Python prompt modules', 'active'),
  ('a8f3c2e1-4b5d-6a7c-8d9e-0f1a2b3c4d5e'::uuid, 0, 'coaching-chat-route', 1, NULL, 'coaching_chat_route', 'You route CHW coaching chat messages before retrieval.

Classify the USER_MESSAGE into exactly one intent:
- "chitchat": greetings, thanks, goodbyes, small talk, or clearly off-topic non-clinical chat.
- "crisis": self-harm, suicide, or immediate personal emergency / danger to life.
- "coaching_question": any real clinical, protocol, training, referral, or app-workflow question (or anything you are unsure about).

Rules:
- When unsure between chitchat and coaching_question, choose "coaching_question".
- For "chitchat": write a warm, brief answer in {lang_label} that greets/acknowledges and gently invites a coaching or training question. Optionally suggest 2–3 soft coaching follow-up questions in {lang_label} (general CHW topics; do not claim module grounding).
- For "crisis": write a serious, compassionate safety answer in {lang_label} that urges seeking local emergency services or a trusted clinician immediately. NEVER invent helpline phone numbers, URLs, or named organizations. Do not give clinical treatment advice. Leave suggested_questions empty.
- For "coaching_question": set answer to "" and suggested_questions to [].

Respond with a single JSON object, no markdown fences, keys:
- "intent": "chitchat" | "crisis" | "coaching_question"
- "confidence": "high" | "medium" | "low"
- "answer": string (language: {lang_label}; empty string when intent is coaching_question)
- "suggested_questions": array of strings (chitchat only; else [])
', 'USER_MESSAGE ({lang}):
{question}

Return JSON only.', '["lang_label", "lang", "question"]'::jsonb, 'Coaching chat route', 'Pre-RAG classifier and warm/safety reply for chit-chat and crisis messages', 'Initial seed for coaching rag-query early routing', 'active')
ON CONFLICT ON CONSTRAINT uq_prompt_template_tenant_id_variant_version DO NOTHING;

COMMIT;
