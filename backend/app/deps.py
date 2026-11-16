"""Shared FastAPI dependencies and lookups."""

from __future__ import annotations

import secrets

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .errors import ApiError
from .models import ProcessingJob, Project, Video
from .services.media import FFmpegClipExtractor, FFmpegMediaProbe
from .services.storage import LocalStorage


def settings_dep() -> Settings:
    return get_settings()


def storage_dep(request: Request) -> LocalStorage:
    return request.app.state.storage  # type: ignore[no-any-return]


def probe_dep(request: Request) -> FFmpegMediaProbe:
    return request.app.state.probe  # type: ignore[no-any-return]


def extractor_dep(request: Request) -> FFmpegClipExtractor:
    return request.app.state.extractor  # type: ignore[no-any-return]


def require_token(request: Request, settings: Settings = Depends(settings_dep)) -> None:
    """Bearer-token guard.  Disabled when VLM_API_TOKEN is unset (local dev)."""
    expected = settings.api_token
    if not expected:
        return
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
        raise ApiError(
            401,
            "UNAUTHENTICATED",
            "a valid bearer token is required",
            {"hint": "send Authorization: Bearer <VLM_API_TOKEN>"},
        )


def get_project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"project {project_id} does not exist")
    return project


def get_video_or_404(session: Session, video_id: int) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise ApiError(404, "VIDEO_NOT_FOUND", f"video {video_id} does not exist")
    return video


def get_job_or_404(session: Session, job_id: int) -> ProcessingJob:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", f"job {job_id} does not exist")
    return job


__all__ = [
    "extractor_dep",
    "get_db",
    "get_job_or_404",
    "get_project_or_404",
    "get_video_or_404",
    "probe_dep",
    "require_token",
    "settings_dep",
    "storage_dep",
]
