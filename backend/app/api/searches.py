"""Search fan-out and read endpoints (Sprint 3, S3-06)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
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


def _aggregate(session: Session, search: Search) -> SearchOut:
    rows = list(
        session.scalars(
            select(SearchVideo).where(SearchVideo.search_id == search.id)
        )
    )
    counts = {
        "total_videos": len(rows),
        "queued_videos": sum(1 for r in rows if r.status == SearchVideoStatus.queued),
        "running_videos": sum(1 for r in rows if r.status == SearchVideoStatus.running),
        "done_videos": sum(1 for r in rows if r.status == SearchVideoStatus.done),
        "failed_videos": sum(1 for r in rows if r.status == SearchVideoStatus.failed),
    }
    out = SearchOut.model_validate(search)
    for key, value in counts.items():
        setattr(out, key, value)
    return out


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
) -> SearchDetailOut:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", f"dataset {dataset_id} does not exist")
    _require_access(session, principal, dataset)

    adapter = get_adapter(payload.adapter_name, settings)

    # Resolve ready videos in the dataset, optionally filtered to the requested list.
    stmt = select(Video).where(
        Video.dataset_id == dataset_id, Video.status == VideoStatus.ready
    )
    if payload.video_ids:
        videos = list(session.scalars(stmt.where(Video.id.in_(payload.video_ids))))
        found = {video.id for video in videos}
        missing = [vid for vid in payload.video_ids if vid not in found]
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
    )
    session.add(search)
    session.flush()

    search_videos: list[SearchVideo] = []
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
            search_videos.append(
                SearchVideo(
                    search_id=search.id,
                    video_id=video.id,
                    job_id=job.id,
                    status=SearchVideoStatus.queued,
                )
            )
        session.add_all(search_videos)
    session.commit()
    session.refresh(search)

    out = SearchDetailOut.model_validate(search)
    agg = _aggregate(session, search)
    for key in ("total_videos", "queued_videos", "running_videos", "done_videos", "failed_videos"):
        setattr(out, key, getattr(agg, key))
    out.videos = [SearchVideoOut.model_validate(sv) for sv in search_videos]
    return out


@router.get("/searches/{search_id}", response_model=SearchDetailOut)
def get_search(
    search_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> SearchDetailOut:
    search = _search_or_404(session, search_id)
    _require_search_access(session, principal, search)
    agg = _aggregate(session, search)
    out = SearchDetailOut.model_validate(search)
    for key in ("total_videos", "queued_videos", "running_videos", "done_videos", "failed_videos"):
        setattr(out, key, getattr(agg, key))
    out.videos = [
        SearchVideoOut.model_validate(sv)
        for sv in session.scalars(
            select(SearchVideo)
            .where(SearchVideo.search_id == search.id)
            .order_by(SearchVideo.video_id)
        )
    ]
    return out


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
    if review_state == "unreviewed":
        statement = statement.outerjoin(Annotation, Annotation.candidate_id == Candidate.id).where(
            Annotation.id.is_(None)
        )
    elif review_state == "reviewed":
        statement = statement.join(Annotation, Annotation.candidate_id == Candidate.id)
    if verdict is not None:
        statement = statement.join(Annotation, Annotation.candidate_id == Candidate.id).where(
            Annotation.verdict == verdict
        )
    statement = statement.order_by(Candidate.video_id, Candidate.start_seconds, Candidate.rank).limit(limit)
    return list(session.scalars(statement))
