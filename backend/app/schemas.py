"""Typed API schemas (request/response contracts).

These models are the single source of truth for the HTTP contract documented in
docs/API_CONTRACTS.md.  Timestamps are always *source-video-relative seconds*
with a half-open interval ``[start_seconds, end_seconds)``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    ClipStatus,
    ExportFormat,
    ExportStatus,
    JobKind,
    JobStatus,
    SearchStatus,
    SearchVideoStatus,
    UserRole,
    Verdict,
    VideoStatus,
)

# --------------------------------------------------------------------------- #
# Projects and actions
# --------------------------------------------------------------------------- #


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def _strip(self) -> ProjectCreate:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name must not be blank")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class ActionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=3, max_length=5000)

    @model_validator(mode="after")
    def _strip(self) -> ActionCreate:
        self.name = self.name.strip()
        self.description = self.description.strip()
        if not self.name or not self.description:
            raise ValueError("name and description are required")
        return self


class ActionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=5000)


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Videos
# --------------------------------------------------------------------------- #


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    dataset_id: int | None
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    fps: float | None
    status: VideoStatus
    error_message: str | None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


class JobCreate(BaseModel):
    """Body for POST /videos/{id}/jobs."""

    action_id: int
    adapter: str | None = Field(default=None, max_length=100)
    params: dict[str, object] = Field(default_factory=dict)


class BatchJobCreate(BaseModel):
    """Body for POST /projects/{id}/actions/{id}/jobs (one job per video)."""

    video_ids: list[int] | None = None  # None = every ready video in the project
    adapter: str | None = Field(default=None, max_length=100)
    params: dict[str, object] = Field(default_factory=dict)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: JobKind
    status: JobStatus
    project_id: int | None
    video_id: int | None
    action_id: int | None
    export_id: int | None
    progress: float
    attempts: int
    max_attempts: int
    adapter_name: str | None
    adapter_version: str | None
    error_code: str | None
    error_message: str | None
    available_at: datetime
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# --------------------------------------------------------------------------- #
# Candidates and annotations
# --------------------------------------------------------------------------- #


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verdict: Verdict
    corrected_start_seconds: float | None
    corrected_end_seconds: float | None
    note: str
    reviewer: str
    created_at: datetime
    updated_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    search_id: int | None
    video_id: int
    action_id: int | None
    start_seconds: float
    end_seconds: float
    preview_start_seconds: float
    preview_end_seconds: float
    rank: int
    score: float
    model_notes: str
    clip_status: ClipStatus
    clip_error: str | None
    review_state: Literal["unreviewed", "reviewed"]
    annotation: AnnotationOut | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_orm_review_state(cls, value: object) -> object:
        # `review_state` is a Python property on the ORM model.
        return value


class AnnotationUpsert(BaseModel):
    verdict: Verdict
    corrected_start_seconds: float | None = Field(default=None, ge=0)
    corrected_end_seconds: float | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=2000)
    reviewer: str = Field(default="anonymous", max_length=100)

    @model_validator(mode="after")
    def _boundaries_together(self) -> AnnotationUpsert:
        if (self.corrected_start_seconds is None) != (self.corrected_end_seconds is None):
            raise ValueError(
                "corrected_start_seconds and corrected_end_seconds must be set together"
            )
        if (
            self.corrected_start_seconds is not None
            and self.corrected_end_seconds is not None
            and self.corrected_end_seconds <= self.corrected_start_seconds
        ):
            raise ValueError("corrected_end_seconds must be greater than corrected_start_seconds")
        return self


# --------------------------------------------------------------------------- #
# Exports and statistics
# --------------------------------------------------------------------------- #


class ExportCreate(BaseModel):
    include_unreviewed: bool = False
    format: ExportFormat = ExportFormat.zip


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    format: ExportFormat
    status: ExportStatus
    include_unreviewed: bool
    item_count: int
    size_bytes: int | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    has_file: bool = False


class ExportCreated(BaseModel):
    export: ExportOut
    job: JobOut


class ProjectStats(BaseModel):
    videos_total: int
    videos_ready: int
    candidates_total: int
    reviewed_total: int
    true_positive_total: int
    false_positive_total: int
    unreviewed_total: int
    jobs_running: int
    jobs_failed: int
    exports_ready: int


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str
    environment: str
    database: str
    adapter: str


class ErrorOut(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None


# --------------------------------------------------------------------------- #
# Identity and access (Sprint 3)
# --------------------------------------------------------------------------- #


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: UserRole = UserRole.annotator


class InvitationCreated(BaseModel):
    id: int
    email: str
    role: UserRole
    expires_at: datetime
    # Returned once because no mail transport exists yet; the client must deliver it.
    token: str


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class DatasetMemberAdd(BaseModel):
    user_id: int | None = None
    email: str | None = Field(default=None, max_length=320)


class DatasetMemberOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: UserRole
    created_at: datetime


# --------------------------------------------------------------------------- #
# Searches (Sprint 3)
# --------------------------------------------------------------------------- #


class SearchCreate(BaseModel):
    """Body for POST /datasets/{dataset_id}/searches."""

    prompt: str = Field(min_length=1, max_length=5000)
    title: str | None = Field(default=None, max_length=200)
    video_ids: list[int] | None = Field(
        default=None, min_length=1
    )  # None = every ready video in the dataset
    adapter_name: str | None = Field(default=None, max_length=100)
    params: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _strip(self) -> SearchCreate:
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("prompt must not be blank")
        if self.title is not None:
            self.title = self.title.strip() or None
        return self


class SearchVideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    search_id: int
    video_id: int
    job_id: int | None
    status: SearchVideoStatus
    error_message: str | None


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    prompt: str
    title: str | None
    status: SearchStatus
    created_by_id: int | None
    created_at: datetime
    finished_at: datetime | None
    error_message: str | None
    total_videos: int = 0
    queued_videos: int = 0
    running_videos: int = 0
    done_videos: int = 0
    failed_videos: int = 0


class SearchDetailOut(SearchOut):
    videos: list[SearchVideoOut] = []

