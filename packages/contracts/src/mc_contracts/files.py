"""Admin file upload API contracts — ``POST /admin/files``, ``GET /admin/files/presigned-url``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    bucket_name: str
    object_name: str
    storage_path: str
    content_type: str
    size_bytes: int = Field(ge=0)
    original_filename: str = Field(description="Client-provided basename at upload time")
    reused_existing: bool = False


class PresignedUrlResponse(BaseModel):
    url: str
    bucket_name: str
    object_name: str
    expires_seconds: int
