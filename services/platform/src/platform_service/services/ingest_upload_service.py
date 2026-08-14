"""Ingest upload orchestration — object-storage staging, provenance, source_document creation.

Owns ``POST /admin/ingest/upload``. API routes validate HTTP form params;
this service handles bytes + DB rows with ``status='uploaded'``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from fastapi import UploadFile
from mc_contracts.enums import AssessmentMode, ContentDomain
from mc_contracts.errors import ErrorCode
from mc_foundation.objectstore import (
    ObjectStorageError,
    ObjectStore,
    StoredObject,
    safe_basename,
)
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.file_upload_repository import FileUploadRepository
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.attribution_audit import record_attribution_event
from platform_service.services.file_digest import sha256_hex_file
from platform_service.services.ingest_errors import IngestValidationError
from platform_service.services.media_duration import MediaDurationError, probe_media_duration_ms
from platform_service.services.upload_provenance import (
    build_upload_metadata,
    record_file_upload,
)

logger = logging.getLogger(__name__)

_SOURCE_TYPE_BY_SUFFIX = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".docx": "docx",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".webm": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
}
_ACCEPTED_SUFFIXES = frozenset(_SOURCE_TYPE_BY_SUFFIX)
_MEDIA_SOURCE_TYPES = frozenset({"audio", "video"})
_UPLOAD_CHUNK_BYTES = 1024 * 1024
MAX_INGEST_FILES = 10
_ALLOWED_CONTENT_DOMAINS = frozenset(e.value for e in ContentDomain)
_ALLOWED_ASSESSMENT_MODES = frozenset(e.value for e in AssessmentMode)
_DEFAULT_CONTENT_DOMAIN = ContentDomain.CLINICAL.value


@dataclass(frozen=True)
class IngestedSourceResult:
    """One source_document reference used when queueing the ingest pipeline."""

    source_document_id: uuid.UUID
    title: str
    source_type: str
    stored_path: str
    content_domain: str


@dataclass(frozen=True)
class IngestUploadParams:
    """Upload context: string actor for file_upload audit; numeric id for source_document."""

    actor: str
    uploaded_by_user_id: int | None = None
    tenant_id: int = 0


@dataclass(frozen=True)
class DuplicateIngestConflict:
    """One file skipped because matching content is already ingested."""

    filename: str
    title: str
    content_sha256: str
    existing_source_documents: tuple[SourceDocument, ...]


_DUPLICATE_CONTENT_MESSAGE = (
    "One or more files match already-uploaded or already-ingested content; set override to re-upload."
)


@dataclass(frozen=True)
class _StagedIngestUpload:
    """Local staging artifact before object-storage / DB writes."""

    staging_path: Path
    content_sha256: str
    original_filename: str
    source_type: str
    title: str
    description: str | None
    override_duplicate: bool
    content_domain: str


class IngestUploadService:
    """Upload files to object storage and create uploaded source_document rows."""

    def __init__(
        self,
        db: AsyncSession,
        storage: ObjectStore | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._storage = storage
        self._settings = settings or get_settings()

    @staticmethod
    def source_type_from_suffix(suffix: str) -> str:
        return _SOURCE_TYPE_BY_SUFFIX[suffix]

    def media_upload_limit_bytes(self) -> int:
        """Return the configured max bytes for ingest audio/video uploads."""
        return self._settings.ingest_media_max_upload_bytes

    @staticmethod
    def validate_file_count(files: list[UploadFile]) -> None:
        if not files:
            raise IngestValidationError("at least one file is required")
        if len(files) > MAX_INGEST_FILES:
            raise IngestValidationError(
                f"at most {MAX_INGEST_FILES} files per request; got {len(files)}",
            )

    @staticmethod
    def validate_content_domain(content_domain: str) -> None:
        if content_domain not in _ALLOWED_CONTENT_DOMAINS:
            raise IngestValidationError(
                f"invalid content_domain {content_domain!r}; "
                f"must be one of: {sorted(_ALLOWED_CONTENT_DOMAINS)}",
            )

    @staticmethod
    def validate_assessment_mode(assessment_mode: str) -> None:
        if assessment_mode not in _ALLOWED_ASSESSMENT_MODES:
            raise IngestValidationError(
                f"invalid assessment_mode {assessment_mode!r}; "
                f"must be one of: {sorted(_ALLOWED_ASSESSMENT_MODES)}",
            )

    def validate_cardinality_targets(
        self,
        *,
        target_cards_per_module: int | None,
        target_quizzes_per_module: int | None,
    ) -> None:
        """Validate optional fixed card/quiz counts against deployment bounds."""
        if target_cards_per_module is not None:
            lo = self._settings.card_min_count
            hi = self._settings.card_max_count
            if not (lo <= target_cards_per_module <= hi):
                raise IngestValidationError(
                    f"cards_per_module must be between {lo} and {hi} (inclusive); "
                    f"got {target_cards_per_module}",
                    status_code=422,
                )
        if target_quizzes_per_module is not None:
            lo = self._settings.quiz_min_questions
            hi = self._settings.quiz_max_questions
            if not (lo <= target_quizzes_per_module <= hi):
                raise IngestValidationError(
                    f"quizzes_per_module must be between {lo} and {hi} (inclusive); "
                    f"got {target_quizzes_per_module}",
                    status_code=422,
                )

    @staticmethod
    def resolve_titles_for_files(titles_json: str | None, files: list[UploadFile]) -> list[str]:
        """Map each upload to a title: explicit JSON array or filename stem."""
        if not files:
            raise IngestValidationError("at least one file is required")
        if titles_json is None:
            resolved: list[str] = []
            for upload in files:
                if not upload.filename:
                    raise IngestValidationError(
                        "filename is required",
                        code=ErrorCode.FILENAME_REQUIRED.value,
                    )
                stem = Path(safe_basename(upload.filename)).stem
                if not stem:
                    raise IngestValidationError(
                        f"cannot derive title from filename {upload.filename!r}",
                    )
                resolved.append(stem)
            return resolved
        try:
            parsed = json.loads(titles_json)
        except json.JSONDecodeError as exc:
            raise IngestValidationError("titles must be valid JSON") from exc
        if not isinstance(parsed, list):
            raise IngestValidationError("titles must be a JSON array")
        if len(parsed) != len(files):
            raise IngestValidationError(
                f"titles must have {len(files)} entries (one per file); got {len(parsed)}",
            )
        resolved = []
        for index, entry in enumerate(parsed):
            if not isinstance(entry, str) or not entry.strip():
                raise IngestValidationError(
                    f"titles[{index}] must be a non-empty string",
                )
            resolved.append(entry.strip())
        return resolved

    @staticmethod
    def resolve_descriptions_for_files(
        descriptions_json: str | None,
        files: list[UploadFile],
    ) -> list[str | None]:
        """Map each upload to an optional description (default null when omitted)."""
        if not files:
            raise IngestValidationError("at least one file is required")
        if descriptions_json is None:
            return [None] * len(files)
        try:
            parsed = json.loads(descriptions_json)
        except json.JSONDecodeError as exc:
            raise IngestValidationError("descriptions must be valid JSON") from exc
        if not isinstance(parsed, list):
            raise IngestValidationError("descriptions must be a JSON array")
        if len(parsed) != len(files):
            raise IngestValidationError(
                f"descriptions must have {len(files)} entries (one per file); got {len(parsed)}",
            )
        resolved: list[str | None] = []
        for index, entry in enumerate(parsed):
            if entry is None:
                resolved.append(None)
                continue
            if not isinstance(entry, str):
                raise IngestValidationError(
                    f"descriptions[{index}] must be a string or null",
                )
            text = entry.strip()
            resolved.append(text or None)
        return resolved

    @staticmethod
    def resolve_override_duplicates_for_files(
        override_json: str | None,
        files: list[UploadFile],
    ) -> list[bool]:
        """Map each upload to an override flag (default false when omitted)."""
        if not files:
            raise IngestValidationError("at least one file is required")
        if override_json is None:
            return [False] * len(files)
        try:
            parsed = json.loads(override_json)
        except json.JSONDecodeError as exc:
            raise IngestValidationError("override_duplicates must be valid JSON") from exc
        if not isinstance(parsed, list):
            raise IngestValidationError("override_duplicates must be a JSON array")
        if len(parsed) != len(files):
            raise IngestValidationError(
                f"override_duplicates must have {len(files)} entries (one per file); got {len(parsed)}",
            )
        resolved: list[bool] = []
        for index, entry in enumerate(parsed):
            if not isinstance(entry, bool):
                raise IngestValidationError(
                    f"override_duplicates[{index}] must be a boolean",
                )
            resolved.append(entry)
        return resolved

    @staticmethod
    def resolve_override_duplicates_for_ids(
        override_flags: list[bool] | None,
        source_document_ids: list[uuid.UUID],
    ) -> list[bool]:
        """Map each source_document_id to an override flag (default false when omitted)."""
        if not source_document_ids:
            raise IngestValidationError("at least one source_document_id is required")
        if override_flags is None:
            return [False] * len(source_document_ids)
        if len(override_flags) != len(source_document_ids):
            raise IngestValidationError(
                f"override_duplicates must have {len(source_document_ids)} entries "
                f"(one per source_document_id); got {len(override_flags)}",
            )
        return list(override_flags)

    @staticmethod
    def resolve_content_domains_for_files(
        content_domains_json: str | None,
        files: list[UploadFile],
    ) -> list[str]:
        """Map each upload to a content_domain (default clinical when omitted/null/empty)."""
        if not files:
            raise IngestValidationError("at least one file is required")
        if content_domains_json is None:
            return [_DEFAULT_CONTENT_DOMAIN] * len(files)
        try:
            parsed = json.loads(content_domains_json)
        except json.JSONDecodeError as exc:
            raise IngestValidationError("content_domains must be valid JSON") from exc
        if not isinstance(parsed, list):
            raise IngestValidationError("content_domains must be a JSON array")
        if len(parsed) != len(files):
            raise IngestValidationError(
                f"content_domains must have {len(files)} entries (one per file); got {len(parsed)}",
            )
        resolved: list[str] = []
        for index, entry in enumerate(parsed):
            if entry is None:
                resolved.append(_DEFAULT_CONTENT_DOMAIN)
                continue
            if not isinstance(entry, str):
                raise IngestValidationError(
                    f"content_domains[{index}] must be a string or null",
                )
            domain = entry.strip()
            if not domain:
                resolved.append(_DEFAULT_CONTENT_DOMAIN)
                continue
            IngestUploadService.validate_content_domain(domain)
            resolved.append(domain)
        return resolved

    @staticmethod
    def duplicate_conflict_payload(conflict: DuplicateIngestConflict) -> dict[str, Any]:
        return {
            "filename": conflict.filename,
            "title": conflict.title,
            "content_sha256": conflict.content_sha256,
            "existing_source_documents": [
                {
                    "source_document_id": str(doc.id),
                    "title": doc.title,
                    "original_filename": doc.original_filename,
                    "ingested_at": doc.ingested_at.isoformat(),
                    "status": doc.status,
                }
                for doc in conflict.existing_source_documents
            ],
        }

    @staticmethod
    def duplicate_content_error(
        conflicts: list[DuplicateIngestConflict],
        *,
        message: str = _DUPLICATE_CONTENT_MESSAGE,
    ) -> AppError:
        return AppError(
            ErrorCode.DUPLICATE_CONTENT.value,
            message,
            status=409,
            extensions={
                "conflicts": [IngestUploadService.duplicate_conflict_payload(c) for c in conflicts],
            },
        )

    @staticmethod
    def source_type_for_upload(file: UploadFile) -> str:
        if not file.filename:
            raise IngestValidationError(
                "filename is required",
                code=ErrorCode.FILENAME_REQUIRED.value,
            )
        suffix = Path(file.filename).suffix.lower()
        if suffix not in _ACCEPTED_SUFFIXES:
            raise IngestValidationError(
                f"unsupported file type {suffix!r}; accepted: {sorted(_ACCEPTED_SUFFIXES)}",
            )
        return IngestUploadService.source_type_from_suffix(suffix)

    async def upload_files(
        self,
        *,
        files: list[UploadFile],
        titles: list[str],
        descriptions: list[str | None],
        params: IngestUploadParams,
        override_flags: list[bool],
        content_domains: list[str],
    ) -> list[IngestedSourceResult]:
        """Stage all files, reject conflicts atomically, then write storage + DB rows."""
        if self._storage is None:
            raise RuntimeError("IngestUploadService requires object storage for uploads")

        staged: list[_StagedIngestUpload] = []
        try:
            for upload, doc_title, description, override_duplicate, content_domain in zip(
                files,
                titles,
                descriptions,
                override_flags,
                content_domains,
                strict=True,
            ):
                source_type = self.source_type_for_upload(upload)
                staging_path, content_sha256, original_filename = await self._stage_and_digest_upload(
                    upload,
                    source_type=source_type,
                )
                staged.append(
                    _StagedIngestUpload(
                        staging_path=staging_path,
                        content_sha256=content_sha256,
                        original_filename=original_filename,
                        source_type=source_type,
                        title=doc_title,
                        description=description,
                        override_duplicate=override_duplicate,
                        content_domain=content_domain,
                    )
                )

            self._reject_within_batch_duplicate_digests(staged)
            conflicts = await self._collect_duplicate_conflicts(staged, tenant_id=params.tenant_id)
            if conflicts:
                raise self.duplicate_content_error(conflicts)

            results: list[IngestedSourceResult] = []
            for item in staged:
                results.append(await self._persist_staged_upload(item, params=params))
            return results
        finally:
            for item in staged:
                item.staging_path.unlink(missing_ok=True)

    @staticmethod
    def _reject_within_batch_duplicate_digests(staged: list[_StagedIngestUpload]) -> None:
        seen: dict[str, str] = {}
        for item in staged:
            prior = seen.get(item.content_sha256)
            if prior is not None:
                raise IngestValidationError(
                    (
                        f"duplicate file content in the same request "
                        f"({prior!r} and {item.original_filename!r}); "
                        "remove duplicates from the upload and retry"
                    ),
                    status_code=422,
                )
            seen[item.content_sha256] = item.original_filename

    async def _collect_duplicate_conflicts(
        self,
        staged: list[_StagedIngestUpload],
        *,
        tenant_id: int,
    ) -> list[DuplicateIngestConflict]:
        source_repo = SourceRepository(self._db)
        conflicts: list[DuplicateIngestConflict] = []
        for item in staged:
            if item.override_duplicate:
                continue
            existing = await source_repo.list_duplicate_candidates_by_content_sha256(
                item.content_sha256,
                tenant_id=tenant_id,
            )
            if existing:
                conflicts.append(
                    DuplicateIngestConflict(
                        filename=item.original_filename,
                        title=item.title,
                        content_sha256=item.content_sha256,
                        existing_source_documents=tuple(existing),
                    )
                )
        return conflicts

    async def _persist_staged_upload(
        self,
        item: _StagedIngestUpload,
        *,
        params: IngestUploadParams,
    ) -> IngestedSourceResult:
        source_repo = SourceRepository(self._db)
        try:
            stored = await self._put_staged_upload_to_object_storage(
                item.staging_path,
                original_filename=item.original_filename,
            )
        except ObjectStorageError:
            logger.exception("Ingest object storage upload failed for %s", item.original_filename)
            raise IngestValidationError(
                "object storage upload failed",
                status_code=502,
                code=ErrorCode.OBJECT_STORAGE_ERROR.value,
            ) from None

        storage_path = stored.storage_path
        duration_ms = await anyio.to_thread.run_sync(
            duration_ms_for_staged_upload,
            item.staging_path,
            item.source_type,
        )
        await record_file_upload(
            file_upload_repo=FileUploadRepository(self._db),
            bucket_name=stored.bucket_name,
            object_key=stored.object_name,
            storage_path=storage_path,
            original_filename=item.original_filename,
            content_sha256=item.content_sha256,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            uploaded_by=params.actor,
            tenant_id=params.tenant_id,
        )

        doc = await source_repo.create_source_document(
            title=item.title,
            source_type=item.source_type,
            primary_language=self._settings.deployment_primary_locale,
            content_domain=item.content_domain,
            original_storage_path=storage_path,
            content_sha256=item.content_sha256,
            original_filename=item.original_filename,
            uploaded_by=params.uploaded_by_user_id,
            description=item.description,
            duration_ms=duration_ms,
            sync_published_visible=False,
            status="uploaded",
            tenant_id=params.tenant_id,
        )
        await record_attribution_event(
            self._db,
            event_type="ingest_uploaded",
            actor=params.actor,
            source_document_id=doc.id,
            payload={
                "stored_path": storage_path,
                "source_type": item.source_type,
                "content_domain": item.content_domain,
            },
        )
        return IngestedSourceResult(
            source_document_id=doc.id,
            title=doc.title,
            source_type=doc.source_type,
            stored_path=storage_path,
            content_domain=doc.content_domain,
        )

    async def _stage_and_digest_upload(
        self,
        file: UploadFile,
        *,
        source_type: str,
    ) -> tuple[Path, str, str]:
        """Stream multipart body to a staging file and return path + sha256 + safe name."""
        staging_dir = Path(self._settings.upload_dir) / "ingest_staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_path = staging_dir / f".ingest-{uuid.uuid4()}.part"
        max_media_bytes = self.media_upload_limit_bytes()
        await stream_upload_to_path(
            file,
            staging_path,
            source_type=source_type,
            max_media_bytes=max_media_bytes,
        )
        safe = safe_basename(file.filename or "")
        digest = sha256_hex_file(staging_path)
        return staging_path, digest, safe

    async def _put_staged_upload_to_object_storage(
        self,
        staging_path: Path,
        *,
        original_filename: str,
    ) -> StoredObject:
        """Upload a staged file to object storage under the ``ingest/`` prefix."""
        object_name = f"ingest/{uuid.uuid4()}_{original_filename}"
        content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
        digest = sha256_hex_file(staging_path)
        return await self._storage.put_object_from_local_file(
            object_name=object_name,
            local_path=staging_path,
            content_type=content_type,
            metadata=build_upload_metadata(content_sha256=digest, original_filename=original_filename),
        )


def duration_ms_for_staged_upload(staging_path: Path, source_type: str) -> int | None:
    """Probe audio/video duration; return None for documents or on probe failure."""
    if source_type not in _MEDIA_SOURCE_TYPES:
        return None
    try:
        duration_ms = probe_media_duration_ms(staging_path)
    except MediaDurationError:
        logger.warning(
            "Failed to probe media duration for %s; storing duration_ms=null",
            staging_path.name,
            exc_info=True,
        )
        return None
    if duration_ms <= 0:
        logger.warning(
            "Non-positive media duration for %s (%sms); storing duration_ms=null",
            staging_path.name,
            duration_ms,
        )
        return None
    return duration_ms


def _append_bytes_to_path(dest: Path, chunk: bytes, first: bool) -> None:
    mode = "wb" if first else "ab"
    with dest.open(mode) as fh:
        fh.write(chunk)


async def stream_upload_to_path(
    file: UploadFile,
    dest: Path,
    *,
    source_type: str,
    max_media_bytes: int,
) -> None:
    """Stream multipart upload to ``dest``, enforcing the media payload cap."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    bytes_seen = 0
    first = True
    try:
        while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
            bytes_seen += len(chunk)
            if source_type in _MEDIA_SOURCE_TYPES and bytes_seen > max_media_bytes:
                raise IngestValidationError(
                    f"media upload exceeds {max_media_bytes} bytes",
                    status_code=413,
                    code=ErrorCode.PAYLOAD_TOO_LARGE.value,
                )
            await anyio.to_thread.run_sync(lambda c=chunk, f=first: _append_bytes_to_path(dest, c, first=f))
            first = False
    except IngestValidationError:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise
