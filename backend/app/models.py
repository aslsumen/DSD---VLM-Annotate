"""SQLAlchemy domain model for VLM Annotate.

Key invariants (see docs/DATABASE_SCHEMA.md):

* All media times are float seconds relative to the *source video*, half-open
  ``[start, end)``.
* A candidate stores three distinct boundaries: the model proposal, the padded
  preview window (used for clip extraction), and — on the annotation — the human
  correction.  They are never overwritten by each other.
* "Unreviewed" is the absence of an :class:`Annotation` row.  A binary verdict
  can only be ``true_positive`` or ``false_positive``, so an unreviewed
  candidate can never be silently exported as a negative.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on top of SQLite's naive storage."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class VideoStatus(enum.StrEnum):
    uploaded = "uploaded"
    ready = "ready"
    failed = "failed"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class JobKind(enum.StrEnum):
    candidate_proposal = "candidate_proposal"
    dataset_export = "dataset_export"


class ClipStatus(enum.StrEnum):
    pending = "pending"
    ready = "ready"
    failed = "failed"
    skipped = "skipped"


class Verdict(enum.StrEnum):
    true_positive = "true_positive"
    false_positive = "false_positive"


class ExportFormat(enum.StrEnum):
    zip = "zip"


class ExportStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    ready = "ready"
    failed = "failed"


class UserRole(enum.StrEnum):
    """Global roles (customer decision, 2026-11-09): never per-dataset."""

    administrator = "administrator"
    dataset_admin = "dataset_admin"
    annotator = "annotator"


class SearchStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    partial = "partial"
    failed = "failed"


class SearchVideoStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    actions: Mapped[list[ActionDefinition]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    videos: Mapped[list[Video]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class ActionDefinition(Base):
    """A natural-language description of the temporal action to look for."""

    __tablename__ = "action_definitions"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_action_project_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="actions")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VideoStatus] = mapped_column(
        _enum(VideoStatus, "video_status"), nullable=False, default=VideoStatus.uploaded
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="videos")
    jobs: Mapped[list[ProcessingJob]] = relationship(back_populates="video")

    __table_args__ = (CheckConstraint("size_bytes >= 0", name="ck_video_size_non_negative"),)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_job_idempotency_key"),
        Index("ix_jobs_claim", "status", "available_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind, "job_kind"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), nullable=False, default=JobStatus.queued
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("action_definitions.id", ondelete="SET NULL"), nullable=True
    )
    export_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_exports.id", ondelete="CASCADE"), nullable=True, unique=True
    )

    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    video: Mapped[Video | None] = relationship(back_populates="jobs")
    action: Mapped[ActionDefinition | None] = relationship()
    export: Mapped[DatasetExport | None] = relationship(back_populates="job")
    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "rank", name="uq_candidate_job_rank"),
        CheckConstraint("start_seconds >= 0", name="ck_candidate_start_non_negative"),
        CheckConstraint("end_seconds > start_seconds", name="ck_candidate_end_after_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[int] = mapped_column(
        ForeignKey("action_definitions.id", ondelete="SET NULL"), nullable=True
    )

    # Model proposal, source-video-relative seconds.
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    # Padded window actually cut for preview playback.
    preview_start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    preview_end_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    clip_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_status: Mapped[ClipStatus] = mapped_column(
        _enum(ClipStatus, "clip_status"), nullable=False, default=ClipStatus.pending
    )
    clip_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    job: Mapped[ProcessingJob] = relationship(back_populates="candidates")
    video: Mapped[Video] = relationship()
    action: Mapped[ActionDefinition | None] = relationship()
    annotation: Mapped[Annotation | None] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", uselist=False
    )

    @property
    def review_state(self) -> str:
        return "reviewed" if self.annotation is not None else "unreviewed"


class Annotation(Base):
    """A human decision.  Existence of the row means the candidate was reviewed."""

    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint(
            "verdict in ('true_positive', 'false_positive')", name="ck_verdict_allowed"
        ),
        CheckConstraint(
            "corrected_start_seconds is null or corrected_start_seconds >= 0",
            name="ck_annotation_corrected_start",
        ),
        CheckConstraint(
            "corrected_end_seconds is null or corrected_start_seconds is null "
            "or corrected_end_seconds > corrected_start_seconds",
            name="ck_annotation_corrected_end",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict, "verdict"), nullable=False)
    corrected_start_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_end_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False, default="anonymous")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    candidate: Mapped[Candidate] = relationship(back_populates="annotation")


class DatasetExport(Base):
    __tablename__ = "dataset_exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[ExportFormat] = mapped_column(
        _enum(ExportFormat, "export_format"), nullable=False, default=ExportFormat.zip
    )
    status: Mapped[ExportStatus] = mapped_column(
        _enum(ExportStatus, "export_status"), nullable=False, default=ExportStatus.queued
    )
    include_unreviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    job: Mapped[ProcessingJob | None] = relationship(back_populates="export", uselist=False)


# --------------------------------------------------------------------------- #
# Identity and access (Sprint 3)
# --------------------------------------------------------------------------- #


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), nullable=False, default=UserRole.annotator
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Invitation(Base):
    """Single-use, time-limited invitation; only the token hash is stored."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_invitation_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "invitation_role"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_session_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Dataset(Base):
    """A collection of videos owned by one or more Dataset Administrators."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class DatasetMembership(Base):
    """Which users may see and annotate a dataset (roles remain global)."""

    __tablename__ = "dataset_memberships"
    __table_args__ = (
        UniqueConstraint("dataset_id", "user_id", name="uq_dataset_membership"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Search(Base):
    """A prompt run against a dataset, split into one SearchVideo per video."""

    __tablename__ = "searches"
    __table_args__ = (
        Index("ix_searches_dataset_status", "dataset_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[SearchStatus] = mapped_column(
        _enum(SearchStatus, "search_status"), nullable=False, default=SearchStatus.queued
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SearchVideo(Base):
    """One video's slice of a :class:`Search`, tying it to a processing job."""

    __tablename__ = "search_videos"
    __table_args__ = (
        UniqueConstraint("search_id", "video_id", name="uq_search_video"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[SearchVideoStatus] = mapped_column(
        _enum(SearchVideoStatus, "search_video_status"),
        nullable=False,
        default=SearchVideoStatus.queued,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
