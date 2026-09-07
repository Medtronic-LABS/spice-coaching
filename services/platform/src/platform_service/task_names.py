"""Celery task name constants.

Keep these in lockstep with ``name=`` on the wrappers in ``celery_tasks.py``
and with Beat schedule entries in ``celery_app.py``. Callers enqueue via
``celery_enqueue`` using these names so the API process never imports worker
modules.
"""

PROCESS_MODULE_EVENT = "platform.process_module_event"
PROCESS_TRAINING_REQUEST_EVENT = "platform.process_training_request_event"
PROCESS_VIDEO_PROGRESS_EVENT = "platform.process_video_progress_event"
GENERATE_MODULE_QUIZ = "platform.generate_module_quiz"
GENERATE_MODULE_CARD_SEARCH_METADATA_BATCH = "platform.generate_module_card_search_metadata_batch"
GENERATE_MODULE_SEARCH_METADATA = "platform.generate_module_search_metadata"
BIND_ASSESSMENT_TRIGGERS = "platform.bind_assessment_triggers"
GENERATE_MODULE_EMBEDDING = "platform.generate_module_embedding"
CLASSIFY_MODULE_GAPS = "platform.classify_module_gaps"
GENERATE_SOURCE_THUMBNAIL = "platform.generate_source_thumbnail"
RUN_INGEST_BATCH = "platform.run_ingest_batch"
RETRY_INGEST_PIPELINE = "platform.retry_ingest_pipeline"
RETRY_INGEST_CANDIDATE_MERGE = "platform.retry_ingest_candidate_merge"
DRAIN_TELEMETRY_BUFFER = "platform.drain_telemetry_buffer"
AGGREGATE_CHAT_FAQS = "platform.aggregate_chat_faqs"
REFRESH_MODULE_CREATION_SUGGESTIONS = "platform.refresh_module_creation_suggestions"
AGGREGATE_CHAT_FEEDBACK_SUMMARY = "platform.aggregate_chat_feedback_summary"
