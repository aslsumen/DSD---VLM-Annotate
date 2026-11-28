"""Dataset ownership resolution and per-resource authorization.

The dataset routes created in Sprint 3 check membership themselves, but the
shared routes inherited from the single-project API serve the very same rows by
id: ``GET/DELETE /videos/{id}``, ``GET /videos/{id}/stream``,
``GET/POST /jobs/{id}/*`` and ``GET/PUT/DELETE /candidates/{id}/*`` returned a
dataset-owned row to any caller, because they only ever performed a primary-key
lookup.  These helpers close that hole.

Two rules keep the legacy surface intact:

* A row that belongs to no dataset (``video.dataset_id is None`` and
  ``job.project_id is not None``) keeps its historical behaviour: the project
  routes were never authenticated and are deliberately left alone.
* A row that belongs to a dataset is checked exactly like the dataset routes.

Callers pass the already-loaded row, so the guard runs *inside* the handler,
after the principal is resolved.  That ordering is deliberate: membership is
resolved first, so an outsider gets ``404`` and cannot tell whether the record
exists; the role check runs second, so a member lacking the role gets ``403``.
Binding ``require_roles`` as a route dependency cannot express this — FastAPI
runs dependencies before the body, so it would answer ``403`` to strangers.

These handlers take :func:`app.deps.get_optional_principal` rather than
``get_current_principal``, because the same routes also serve legacy project rows
that were never authenticated: a required dependency would answer ``401`` to
anonymous callers and break them.  The dataset boundary is therefore enforced
here instead, and an anonymous caller is rejected only once the row is known to
belong to a dataset (see :func:`_require_session_for_dataset`).  With
authentication switched off the principal is a synthetic administrator, which is
why development stays unauthenticated end to end.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import Principal
from .errors import ApiError
from .models import (
    Candidate,
    Dataset,
    DatasetMembership,
    ProcessingJob,
    Search,
    SearchVideo,
    UserRole,
    Video,
)

#: Roles allowed to change a dataset-owned resource.  ``administrator`` is not
#: listed because :func:`_require_membership_then_roles` lets it through first.
DATASET_WRITE_ROLES: tuple[UserRole, ...] = (UserRole.dataset_admin,)

__all__ = [
    "DATASET_WRITE_ROLES",
    "dataset_for_candidate",
    "dataset_for_job",
    "dataset_for_video",
    "enforce_candidate_access",
    "enforce_job_access",
    "enforce_video_access",
    "filter_visible_jobs",
    "is_dataset_member",
]


def is_dataset_member(session: Session, dataset_id: int, user_id: int | None) -> bool:
    """True when ``user_id`` holds a membership row for ``dataset_id``."""
    if user_id is None:
        return False
    return (
        session.scalar(
            select(DatasetMembership).where(
                DatasetMembership.dataset_id == dataset_id,
                DatasetMembership.user_id == user_id,
            )
        )
        is not None
    )


def _dataset_or_none(session: Session, dataset_id: int | None) -> Dataset | None:
    if dataset_id is None:
        return None
    return session.get(Dataset, dataset_id)


def dataset_for_video(session: Session, video: Video) -> Dataset | None:
    """The dataset owning ``video``, or ``None`` for a project-owned video."""
    return _dataset_or_none(session, video.dataset_id)


def dataset_for_job(session: Session, job: ProcessingJob) -> Dataset | None:
    """The dataset owning ``job``, resolved through video, search or candidate.

    A job carries no dataset column of its own, so ownership is derived from the
    row it points at.  ``video_id`` is tried first; then the ``search_videos``
    row and, failing that, a candidate it produced.  Deleting a video removes its
    jobs through the database cascade (``Video.jobs`` declares
    ``passive_deletes``), so a live job always still has one of these links; the
    remaining lookups cover jobs whose video was removed by an older build, when
    the ORM used to null the foreign key instead of cascading.
    """
    if job.video_id is not None:
        video = session.get(Video, job.video_id)
        if video is not None:
            dataset = _dataset_or_none(session, video.dataset_id)
            if dataset is not None:
                return dataset

    search_video = session.scalar(select(SearchVideo).where(SearchVideo.job_id == job.id))
    if search_video is not None:
        search = session.get(Search, search_video.search_id)
        if search is not None:
            dataset = _dataset_or_none(session, search.dataset_id)
            if dataset is not None:
                return dataset

    candidate = session.scalar(select(Candidate).where(Candidate.job_id == job.id))
    if candidate is not None:
        return dataset_for_candidate(session, candidate)
    return None


def dataset_for_candidate(session: Session, candidate: Candidate) -> Dataset | None:
    """The dataset owning ``candidate``: prefer the search, fall back to video."""
    if candidate.search_id is not None:
        search = session.get(Search, candidate.search_id)
        if search is not None:
            dataset = _dataset_or_none(session, search.dataset_id)
            if dataset is not None:
                return dataset
    video = session.get(Video, candidate.video_id)
    if video is None:
        return None
    return _dataset_or_none(session, video.dataset_id)


def _require_session_for_dataset(principal: Principal) -> None:
    """401 for anonymous callers when authentication is enforced.

    ``get_optional_principal`` deliberately does not raise, because the same
    dependency serves the legacy project routes, which must keep working without
    a token.  By the time a dataset-owned row is involved we *do* want the
    honest answer, and only this guard knows the row belongs to a dataset.

    With authentication switched off, the anonymous principal is a synthetic
    administrator (see :func:`app.deps.get_optional_principal`) and this is never
    reached; that is why development stays unauthenticated end to end.
    """
    if principal.user is None and not principal.is_authenticated:
        raise ApiError(
            401,
            "UNAUTHENTICATED",
            "this resource belongs to a dataset and requires a session token",
        )


def _require_membership_then_roles(
    session: Session,
    principal: Principal,
    dataset: Dataset,
    *,
    not_found_code: str,
    not_found_message: str,
    allowed_roles: Iterable[UserRole],
) -> None:
    """401 for anonymous, 404 to outsiders (hide existence), 403 for the rest."""
    if principal.role == UserRole.administrator:
        return
    _require_session_for_dataset(principal)
    user_id = principal.user.id if principal.user is not None else None
    if not is_dataset_member(session, dataset.id, user_id):
        raise ApiError(404, not_found_code, not_found_message)

    roles = frozenset(allowed_roles)
    if not roles:
        return  # any member may perform this operation
    if principal.role not in roles:
        raise ApiError(
            403,
            "FORBIDDEN",
            "your role is not allowed to perform this action",
            {"required_roles": sorted(role.value for role in roles)},
        )


def enforce_video_access(
    session: Session,
    principal: Principal,
    video: Video,
    *,
    allowed_roles: Iterable[UserRole] = (),
) -> None:
    """Authorize ``principal`` against a video served by a shared route."""
    dataset = dataset_for_video(session, video)
    if dataset is None:
        return
    _require_membership_then_roles(
        session,
        principal,
        dataset,
        not_found_code="VIDEO_NOT_FOUND",
        not_found_message=f"video {video.id} does not exist",
        allowed_roles=allowed_roles,
    )


def enforce_job_access(
    session: Session,
    principal: Principal,
    job: ProcessingJob,
    *,
    allowed_roles: Iterable[UserRole] = (),
) -> None:
    """Authorize ``principal`` against a job served by a shared route."""
    dataset = dataset_for_job(session, job)
    if dataset is None:
        if job.project_id is not None:
            return  # legacy project job, unchanged
        # Neither a project nor a resolvable dataset: a dataset search job whose
        # video was deleted.  Nobody outside the administrator can reason about
        # it, so fail closed instead of falling back to "no check".
        if principal.role == UserRole.administrator:
            return
        raise ApiError(404, "JOB_NOT_FOUND", f"job {job.id} does not exist")
    _require_membership_then_roles(
        session,
        principal,
        dataset,
        not_found_code="JOB_NOT_FOUND",
        not_found_message=f"job {job.id} does not exist",
        allowed_roles=allowed_roles,
    )


def enforce_candidate_access(
    session: Session,
    principal: Principal,
    candidate: Candidate,
    *,
    allowed_roles: Iterable[UserRole] = (),
) -> None:
    """Authorize ``principal`` against a candidate served by a shared route."""
    dataset = dataset_for_candidate(session, candidate)
    if dataset is None:
        return
    _require_membership_then_roles(
        session,
        principal,
        dataset,
        not_found_code="CANDIDATE_NOT_FOUND",
        not_found_message=f"candidate {candidate.id} does not exist",
        allowed_roles=allowed_roles,
    )


def filter_visible_jobs(
    session: Session,
    principal: Principal,
    jobs: Iterable[ProcessingJob],
) -> list[ProcessingJob]:
    """Drop dataset-owned jobs the caller may not see from a list response.

    A list endpoint cannot answer 404 per item, so it filters instead: an
    outsider simply does not get the row.  Legacy project jobs stay visible,
    matching the historical behaviour of ``GET /jobs``.
    """
    if principal.role == UserRole.administrator:
        return list(jobs)

    user_id = principal.user.id if principal.user is not None else None
    visible: list[ProcessingJob] = []
    for job in jobs:
        dataset = dataset_for_job(session, job)
        if dataset is None:
            if job.project_id is not None:
                visible.append(job)
            continue
        if is_dataset_member(session, dataset.id, user_id):
            visible.append(job)
    return visible
