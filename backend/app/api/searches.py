"""Search fan-out and read endpoints (Sprint 3, S3-06)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
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
from ..services.pipeline import enqueue_candidate_job
from .datasets import _require_access

router = APIRouter(tags=["searches"])


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


def _replay_matches(
    session: Session,
    existing: Search,
    dataset_id: int,
    prompt: str,
    requested_ids: list[int] | None,
) -> bool:
    """True when a stored search was created by the same request payload.

    ``requested_ids`` is ``None`` when the caller omitted ``video_ids`` ("every
    ready video"), in which case the resolved set is not part of the request and
    is ignored -- otherwise uploading one more video would turn a legitimate
    replay into a conflict.
    """
    if existing.dataset_id != dataset_id or existing.prompt != prompt:
        return False
    if requested_ids is None:
        return True
    return _video_ids_for(session, existing.id) == sorted(set(requested_ids))


def _replay_or_conflict(
    session: Session,
    existing: Search,
    dataset_id: int,
    prompt: str,
    requested_ids: list[int] | None,
) -> SearchDetailOut:
    """Return the original search, or 409 if the key was reused for another request."""
    if not _replay_matches(session, existing, dataset_id, prompt, requested_ids):
        raise ApiError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "this Idempotency-Key was already used with a different request",
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

    # Replay: a double click must return the original search, not fan out again.
    # Checked before resolving the adapter and the videos, so a repeat still
    # returns the original search after a video was deleted or an adapter was
    # removed from the configuration.
    if key is not None:
        existing = session.scalar(select(Search).where(Search.idempotency_key == key))
        if existing is not None:
            return _replay_or_conflict(
                session, existing, dataset_id, payload.prompt, requested_ids
            )

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
        return _replay_or_conflict(
            session, existing, dataset_id, payload.prompt, requested_ids
        )

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
