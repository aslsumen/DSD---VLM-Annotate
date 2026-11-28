"""Search fan-out and read endpoints (Sprint 3, S3-06)."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..adapters.registry import get_adapter
from ..config import Settings
from ..deps import (
    Principal,
    get_current_principal,
    get_db,
    require_roles,
    settings_dep,
)
from ..errors import ApiError
from ..models import (
    Annotation,
    Candidate,
    Dataset,
    JobStatus,
    ProcessingJob,
    Search,
    SearchStatus,
    SearchVideo,
    SearchVideoStatus,
    UserRole,
    Verdict,
    Video,
    VideoStatus,
    utcnow,
)
from ..schemas import (
    CandidateOut,
    SearchCreate,
    SearchDetailOut,
    SearchOut,
    SearchVideoOut,
)
from ..services.pipeline import cancel_job, enqueue_candidate_job, settle_searches
from .datasets import _require_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["searches"])

#: Fields that define *what a search does*.  Two requests may share an
#: Idempotency-Key only if all of them match; ``title`` is deliberately absent
#: (presentation only) and so is the resolved video set (derived, not requested).
SCOPE_FIELDS: tuple[str, ...] = (
    "dataset_id",
    "prompt",
    "params",
    "adapter_name",
    "video_ids",
)


def _search_or_404(session: Session, search_id: int) -> Search:
    search = session.get(Search, search_id)
    if search is None:
        raise ApiError(404, "SEARCH_NOT_FOUND", f"search {search_id} does not exist")
    return search


def _require_search_access(session: Session, principal: Principal, search: Search) -> None:
    dataset = session.get(Dataset, search.dataset_id)
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", "the search's dataset no longer exists")
    _require_access(session, principal, dataset)


def _auto_title(prompt: str) -> str:
    """Short automatic title for long prompts: first 60 chars, trimmed cleanly."""
    trimmed = prompt.strip()
    if len(trimmed) <= 60:
        return trimmed
    head = trimmed[:60].rsplit(" ", 1)[0] if " " in trimmed[:60] else trimmed[:60]
    return head.rstrip(" ,;:") or head


def _aggregate_many(session: Session, search_ids: list[int]) -> dict[int, dict[str, int]]:
    """Per-search counts of SearchVideo statuses, in one query (no N+1)."""
    counts: dict[int, dict[str, int]] = {
        search_id: {
            "total_videos": 0,
            "queued_videos": 0,
            "running_videos": 0,
            "done_videos": 0,
            "failed_videos": 0,
        }
        for search_id in search_ids
    }
    if not search_ids:
        return counts
    rows = session.scalars(
        select(SearchVideo).where(SearchVideo.search_id.in_(search_ids))
    )
    field_by_status = {
        SearchVideoStatus.queued: "queued_videos",
        SearchVideoStatus.running: "running_videos",
        SearchVideoStatus.done: "done_videos",
        SearchVideoStatus.failed: "failed_videos",
    }
    for row in rows:
        bucket = counts.get(row.search_id)
        if bucket is None:  # pragma: no cover - guarded by the filter above
            continue
        bucket["total_videos"] += 1
        bucket[field_by_status[row.status]] += 1
    return counts


def _with_counts(search: Search, counts: dict[str, int]) -> SearchOut:
    out = SearchOut.model_validate(search)
    for key, value in counts.items():
        setattr(out, key, value)
    return out


def _aggregate(session: Session, search: Search) -> SearchOut:
    counts = _aggregate_many(session, [search.id])[search.id]
    return _with_counts(search, counts)


def _detail(session: Session, search: Search) -> SearchDetailOut:
    """Full search payload: aggregate counts plus one row per SearchVideo."""
    agg = _aggregate(session, search)
    out = SearchDetailOut(**agg.model_dump())
    out.videos = [
        SearchVideoOut.model_validate(sv)
        for sv in session.scalars(
            select(SearchVideo)
            .where(SearchVideo.search_id == search.id)
            .order_by(SearchVideo.video_id)
        )
    ]
    return out


def _video_ids_for(session: Session, search_id: int) -> list[int]:
    return sorted(
        session.scalars(
            select(SearchVideo.video_id).where(SearchVideo.search_id == search_id)
        )
    )


def _request_scope(
    dataset_id: int,
    prompt: str,
    params: dict[str, object],
    adapter_name: str | None,
    requested_ids: list[int] | None,
) -> dict[str, object]:
    """The fields that define *what a search does*, in canonical form.

    ``video_ids`` is ``None`` when the caller omitted it ("every ready video").
    That is a different request from any explicit subset, so ``None`` must not be
    normalised to a list here -- it only becomes a set on comparison.
    """
    return {
        "dataset_id": dataset_id,
        "prompt": prompt,
        "params": params,
        "adapter_name": adapter_name,
        "video_ids": None if requested_ids is None else sorted(set(requested_ids)),
    }


def _dump_scope(scope: dict[str, object]) -> str:
    """Serialise a scope deterministically, so equal requests store equal text."""
    return json.dumps(scope, sort_keys=True, separators=(",", ":"))


def _load_scope(raw: str | None) -> dict[str, object] | None:
    """Parse a stored scope, or ``None`` when the row predates the column."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):  # pragma: no cover - only a corrupt row
        logger.warning("unreadable request scope stored on a search: %r", raw)
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    return parsed


def _mismatched_fields(
    session: Session, existing: Search, wanted: dict[str, object]
) -> list[str]:
    """Names of the scope fields whose stored value differs from ``wanted``.

    An empty list means the stored search answers the same request, so the call
    is a replay.  Historical rows (stored before ``request_scope_json`` existed)
    have no snapshot; for those the old dataset + prompt comparison is used and
    the video scope is checked against the live rows as a best effort.
    """
    stored = _load_scope(existing.request_scope_json)
    if stored is None:
        logger.warning(
            "search %s has no stored request scope; falling back to its current rows",
            existing.id,
        )
        legacy: list[str] = []
        if existing.dataset_id != wanted["dataset_id"]:
            legacy.append("dataset_id")
        if existing.prompt != wanted["prompt"]:
            legacy.append("prompt")
        if legacy:
            return legacy
        requested_ids = wanted["video_ids"]
        if requested_ids is None:
            return []
        if _video_ids_for(session, existing.id) != list(requested_ids):
            legacy.append("video_ids")
        return legacy

    mismatches: list[str] = []
    for field in SCOPE_FIELDS:
        if stored.get(field) != wanted[field]:
            mismatches.append(field)
    return mismatches


def _replay_or_conflict(
    session: Session, existing: Search, wanted: dict[str, object]
) -> SearchDetailOut:
    """Return the original search, or 409 if the key was reused for another request."""
    mismatches = _mismatched_fields(session, existing, wanted)
    if mismatches:
        raise ApiError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "this Idempotency-Key was already used with a different request",
            {"mismatched_fields": mismatches},
        )
    return _detail(session, existing)


@router.post(
    "/datasets/{dataset_id}/searches",
    response_model=SearchDetailOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_search(
    dataset_id: int,
    payload: SearchCreate,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", max_length=100
    ),
) -> SearchDetailOut:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", f"dataset {dataset_id} does not exist")
    _require_access(session, principal, dataset)

    # None = "every ready video"; a list is compared on replay to detect a
    # different request reusing the same Idempotency-Key.
    requested_ids = (
        list(dict.fromkeys(payload.video_ids)) if payload.video_ids is not None else None
    )

    # A blank header means "no key", otherwise an all-space value would be stored
    # as "" and collide with the next blank one through the unique constraint.
    key = (idempotency_key.strip() or None) if idempotency_key else None

    # What this request asks for, captured before anything is resolved: a replay
    # must be judged on the request itself, not on rows that later change
    # (deleting a selected video used to break its own replay).  ``adapter_name``
    # is stored resolved, so omitting it and naming the same default adapter are
    # the same request.
    scope = _request_scope(
        dataset_id=dataset_id,
        prompt=payload.prompt,
        params=payload.params,
        adapter_name=payload.adapter_name or settings.vlm_adapter,
        requested_ids=requested_ids,
    )

    # Replay: a double click must return the original search, not fan out again.
    # Checked before resolving the adapter and the videos, so a repeat still
    # returns the original search after a video was deleted or an adapter was
    # removed from the configuration.
    if key is not None:
        existing = session.scalar(select(Search).where(Search.idempotency_key == key))
        if existing is not None:
            return _replay_or_conflict(session, existing, scope)

    adapter = get_adapter(payload.adapter_name, settings)

    # Resolve ready videos in the dataset, optionally filtered to the requested list.
    stmt = select(Video).where(
        Video.dataset_id == dataset_id, Video.status == VideoStatus.ready
    )
    if requested_ids is not None:
        videos = list(session.scalars(stmt.where(Video.id.in_(requested_ids))))
        found = {video.id for video in videos}
        missing = [vid for vid in requested_ids if vid not in found]
        if missing:
            raise ApiError(
                422,
                "VIDEOS_NOT_IN_DATASET",
                "some requested videos do not belong to this dataset or are not ready",
                {"missing": missing},
            )
    else:
        videos = list(session.scalars(stmt.order_by(Video.id)))

    search = Search(
        dataset_id=dataset_id,
        prompt=payload.prompt,
        title=(payload.title or _auto_title(payload.prompt)),
        status=SearchStatus.queued,
        created_by_id=principal.user.id if principal.user is not None else None,
        idempotency_key=key,
        request_scope_json=_dump_scope(scope),
    )
    session.add(search)
    try:
        session.flush()
    except IntegrityError:
        # Lost a race against a concurrent request with the same key.
        session.rollback()
        if key is None:  # pragma: no cover - the key column is the only unique field
            raise
        existing = session.scalar(select(Search).where(Search.idempotency_key == key))
        if existing is None:  # pragma: no cover - defensive
            raise
        return _replay_or_conflict(session, existing, scope)

    if not videos:
        search.status = SearchStatus.done
        search.finished_at = utcnow()
    else:
        for video in videos:
            job = enqueue_candidate_job(
                session,
                video=video,
                action=None,
                adapter_name=adapter.name,
                params=payload.params,
                idempotency_key=None,
                max_attempts=settings.worker_max_attempts,
            )
            session.add(
                SearchVideo(
                    search_id=search.id,
                    video_id=video.id,
                    job_id=job.id,
                    status=SearchVideoStatus.queued,
                )
            )
    session.commit()
    session.refresh(search)
    return _detail(session, search)


@router.get("/datasets/{dataset_id}/searches", response_model=list[SearchOut])
def list_searches(
    dataset_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
    status_filter: SearchStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SearchOut]:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", f"dataset {dataset_id} does not exist")
    _require_access(session, principal, dataset)

    stmt = select(Search).where(Search.dataset_id == dataset_id)
    if status_filter is not None:
        stmt = stmt.where(Search.status == status_filter)
    searches = list(
        session.scalars(
            stmt.order_by(Search.created_at.desc(), Search.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    counts = _aggregate_many(session, [search.id for search in searches])
    return [_with_counts(search, counts[search.id]) for search in searches]


@router.get("/searches/{search_id}", response_model=SearchDetailOut)
def get_search(
    search_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> SearchDetailOut:
    search = _search_or_404(session, search_id)
    _require_search_access(session, principal, search)
    return _detail(session, search)


@router.post(
    "/datasets/{dataset_id}/searches/{search_id}/cancel",
    response_model=SearchDetailOut,
)
def cancel_search(
    dataset_id: int,
    search_id: int,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
) -> SearchDetailOut:
    """Cancel every queued or running video of a search.

    The meaning is "make sure nothing is running here", so a search that is
    already settled is returned unchanged with 200 instead of failing: the
    frontend retries this on a flaky connection.  A video whose job finishes
    while this request is in flight is already settled too, so the resulting
    ``409 JOB_NOT_CANCELABLE`` from ``cancel_job`` is swallowed.
    """
    search = _search_or_404(session, search_id)
    if search.dataset_id != dataset_id:
        raise ApiError(404, "SEARCH_NOT_FOUND", f"search {search_id} does not exist")
    _require_search_access(session, principal, search)

    jobs = list(
        session.scalars(
            select(ProcessingJob).where(
                ProcessingJob.id.in_(
                    select(SearchVideo.job_id).where(SearchVideo.search_id == search_id)
                ),
                ProcessingJob.status.in_((JobStatus.queued, JobStatus.running)),
            )
        )
    )
    for job in jobs:
        # cancel_job repaints the SearchVideo mirror and settles the aggregate.
        # A worker may finish this job between the query above and the conditional
        # update inside cancel_job; that surfaces as JOB_NOT_CANCELABLE, which is
        # not an error here -- the video is simply already settled.
        try:
            cancel_job(session, job)
        except ApiError as exc:
            if exc.code != "JOB_NOT_CANCELABLE":
                raise
            session.rollback()
    session.refresh(search)
    return _detail(session, search)


@router.post(
    "/datasets/{dataset_id}/searches/{search_id}/retry",
    response_model=SearchDetailOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_search(
    dataset_id: int,
    search_id: int,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> SearchDetailOut:
    """Re-queue the failed videos of a search, leaving the finished ones alone.

    The restart of each video is a compare-and-swap on the row that was read:
    the ``SearchVideo`` only moves to the replacement job while it still points
    at the failed job this request saw.  Two retries released together therefore
    queue one replacement per video, and the loser of the race answers 202 with
    the restarted search instead of failing -- the caller asked for "make this
    run again", which is true.
    """
    search = _search_or_404(session, search_id)
    if search.dataset_id != dataset_id:
        raise ApiError(404, "SEARCH_NOT_FOUND", f"search {search_id} does not exist")
    _require_search_access(session, principal, search)

    scope = _load_scope(search.request_scope_json) or {}
    fallback_params = scope.get("params") if isinstance(scope.get("params"), dict) else {}
    fallback_adapter = scope.get("adapter_name")

    eligible = False
    rows = list(
        session.scalars(select(SearchVideo).where(SearchVideo.search_id == search_id))
    )
    for row in rows:
        job = session.get(ProcessingJob, row.job_id) if row.job_id else None
        if row.status != SearchVideoStatus.failed:
            continue
        if job is not None and job.status not in (JobStatus.failed,):
            continue
        video = session.get(Video, row.video_id)
        if video is None:
            # The video is gone; the row would only be re-created as a failure.
            continue
        adapter_name = (
            job.adapter_name
            if job is not None and job.adapter_name
            else (fallback_adapter or settings.vlm_adapter)
        )
        # Prefer the parameters the failed run actually used; fall back to the
        # ones recorded in the search scope for rows whose job is gone.
        if job is not None and job.params_json:
            params = json.loads(job.params_json)
        else:
            params = fallback_params
        # No idempotency key here: a deterministic key would make the loser of a
        # race reuse the winner's job, but two concurrent inserts of the same key
        # fail the unique constraint at flush time and poison the transaction.
        # The compare-and-swap below already guarantees one surviving job.
        eligible = True
        new_job = enqueue_candidate_job(
            session,
            video=video,
            action=None,
            adapter_name=adapter_name,
            params=params,
            idempotency_key=None,
            max_attempts=settings.worker_max_attempts,
        )
        # Compare-and-swap: only the request that still sees the failed job this
        # row pointed at when it was read may install the replacement.
        claimed = session.execute(
            update(SearchVideo)
            .where(
                SearchVideo.id == row.id,
                SearchVideo.job_id == row.job_id,
                SearchVideo.status == SearchVideoStatus.failed,
            )
            .values(
                job_id=new_job.id,
                status=SearchVideoStatus.queued,
                error_message=None,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            # A concurrent retry already replaced this video, so the job this
            # request queued is orphaned.  Delete it -- but only if nothing
            # points at it, so a future change to the enqueue key cannot make
            # this cleanup break the winner's link.
            referenced = session.scalar(
                select(SearchVideo.id).where(SearchVideo.job_id == new_job.id)
            )
            if referenced is None:
                session.delete(new_job)
            session.expire(row)
            continue

    if not eligible:
        session.rollback()
        raise ApiError(
            409,
            "SEARCH_NOT_RETRYABLE",
            "this search has no failed videos to retry",
        )

    # Everything that was failed has been restarted -- by this request or by a
    # concurrent one that won every swap.  Losing the race is not an error: the
    # caller asked for "make this run again", which is true, so both cases answer
    # 202 with the search as it is now.
    session.commit()
    # Derive the aggregate from the committed rows: the row statuses moved, and
    # in the lost-race case the sibling may not have settled the search yet, so
    # the stored column would still say ``partial``.
    settle_searches(session, [search_id])
    session.expire_all()
    search = _search_or_404(session, search_id)
    return _detail(session, search)


@router.get("/searches/{search_id}/candidates", response_model=list[CandidateOut])
def list_search_candidates(
    search_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
    review_state: Literal["unreviewed", "reviewed"] | None = Query(default=None),
    verdict: Verdict | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[Candidate]:
    search = _search_or_404(session, search_id)
    _require_search_access(session, principal, search)

    statement = (
        select(Candidate)
        .options(selectinload(Candidate.annotation))
        .where(Candidate.search_id == search_id)
    )
    # ``annotations`` is joined at most once: joining it a second time for the
    # verdict filter emits the table twice and makes every column reference
    # ambiguous ("two filters together -> 500").
    if review_state == "unreviewed":
        statement = statement.outerjoin(
            Annotation, Annotation.candidate_id == Candidate.id
        ).where(Annotation.id.is_(None))
    elif review_state == "reviewed" or verdict is not None:
        statement = statement.join(Annotation, Annotation.candidate_id == Candidate.id)
    if verdict is not None:
        statement = statement.where(Annotation.verdict == verdict)
    statement = statement.order_by(Candidate.video_id, Candidate.start_seconds, Candidate.rank).limit(limit)
    return list(session.scalars(statement))
