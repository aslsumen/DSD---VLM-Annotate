"""Shared FastAPI dependencies and lookups."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .errors import ApiError
from .models import ProcessingJob, Project, User, UserRole, UserSession, Video, utcnow
from .security import hash_token
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


@dataclass(frozen=True)
class Principal:
    """The caller identity for one request.

    ``user is None`` only in development when authentication is disabled: the
    caller is then treated as a synthetic administrator so the demo keeps
    working without accounts.
    """

    user: User | None
    role: UserRole
    is_authenticated: bool


def _bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_principal(
    request: Request,
    session: Session = Depends(get_db),
) -> Principal:
    settings: Settings = request.app.state.settings
    token = _bearer_token(request)

    if token:
        record = session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        now = utcnow()
        if (
            record is not None
            and record.revoked_at is None
            and record.expires_at > now
        ):
            user = session.get(User, record.user_id)
            if user is not None and user.is_active:
                if record.last_seen_at < now - timedelta(seconds=60):
                    record.last_seen_at = now
                    session.commit()
                return Principal(user=user, role=user.role, is_authenticated=True)
        raise ApiError(
            401,
            "INVALID_SESSION",
            "the session token is invalid, revoked or expired",
            {"hint": "sign in again to obtain a new token"},
        )

    if settings.auth_required:
        raise ApiError(
            401,
            "UNAUTHENTICATED",
            "sign-in is required for this endpoint",
            {"hint": "POST /api/v1/auth/login and send Authorization: Bearer <token>"},
        )
    return Principal(user=None, role=UserRole.administrator, is_authenticated=False)


def require_roles(*allowed: UserRole):
    """Dependency factory: administrator always passes, others must be listed."""

    allowed_set = frozenset(allowed)

    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role == UserRole.administrator or principal.role in allowed_set:
            return principal
        raise ApiError(
            403,
            "FORBIDDEN",
            "your role is not allowed to perform this action",
            {"required_roles": sorted(role.value for role in allowed_set)},
        )

    return _dependency


def require_authenticated(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    if not principal.is_authenticated or principal.user is None:
        raise ApiError(401, "UNAUTHENTICATED", "sign-in is required for this endpoint")
    return principal


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


def get_optional_principal(
    request: Request,
    session: Session = Depends(get_db),
) -> Principal:
    """Like :func:`get_current_principal` but never answers ``401`` itself.

    The shared legacy routes (``/videos/{id}``, ``/jobs/*``, ``/candidates/*``)
    serve both project-owned rows, which were never authenticated, and
    dataset-owned rows, which must be.  Refusing anonymous callers here would
    break the project routes whenever ``VLM_AUTH_REQUIRED`` is on, so this
    variant returns an anonymous principal instead and lets the per-row guard
    decide: project rows stay open, dataset rows refuse it (``401`` for an
    anonymous caller, ``404`` for a signed-in stranger).

    A *presented* token is still validated — an invalid or expired one raises
    ``401`` rather than silently degrading to anonymous.
    """
    settings: Settings = request.app.state.settings
    token = _bearer_token(request)

    if token:
        return get_current_principal(request, session)

    if settings.auth_required:
        return Principal(user=None, role=UserRole.annotator, is_authenticated=False)
    return Principal(user=None, role=UserRole.administrator, is_authenticated=False)


__all__ = [
    "Principal",
    "extractor_dep",
    "get_current_principal",
    "get_db",
    "get_job_or_404",
    "get_optional_principal",
    "get_project_or_404",
    "get_video_or_404",
    "probe_dep",
    "require_authenticated",
    "require_roles",
    "require_token",
    "settings_dep",
    "storage_dep",
]
