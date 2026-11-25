"""Candidate review endpoints: queue, annotation upsert, clip playback."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..deps import get_db, get_project_or_404, storage_dep
from ..errors import ApiError
from ..models import Annotation, Candidate, Verdict, Video
from ..schemas import AnnotationOut, AnnotationUpsert, CandidateOut
from ..services.storage import LocalStorage
from ..validation import validate_interval
from .files import range_file_response

router = APIRouter(tags=["candidates"])


def _candidate_or_404(session: Session, candidate_id: int) -> Candidate:
    candidate = session.scalar(
        select(Candidate)
        .options(selectinload(Candidate.annotation))
        .where(Candidate.id == candidate_id)
    )
    if candidate is None:
        raise ApiError(404, "CANDIDATE_NOT_FOUND", f"candidate {candidate_id} does not exist")
    return candidate


@router.get("/projects/{project_id}/candidates", response_model=list[CandidateOut])
def list_project_candidates(
    project_id: int,
    session: Session = Depends(get_db),
    video_id: int | None = Query(default=None),
    action_id: int | None = Query(default=None),
    review_state: Literal["unreviewed", "reviewed"] | None = Query(default=None),
    verdict: Verdict | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[Candidate]:
    get_project_or_404(session, project_id)
    statement = (
        select(Candidate)
        .join(Video, Candidate.video_id == Video.id)
        .options(selectinload(Candidate.annotation))
        .where(Video.project_id == project_id)
    )
    if video_id is not None:
        statement = statement.where(Candidate.video_id == video_id)
    if action_id is not None:
        statement = statement.where(Candidate.action_id == action_id)
    # ``annotations`` is joined at most once: joining it a second time for the
    # verdict filter emits the table twice and makes every column reference
    # ambiguous, so ``review_state`` + ``verdict`` together used to fail.
    if review_state == "unreviewed":
        statement = statement.outerjoin(
            Annotation, Annotation.candidate_id == Candidate.id
        ).where(Annotation.id.is_(None))
    elif review_state == "reviewed" or verdict is not None:
        statement = statement.join(Annotation, Annotation.candidate_id == Candidate.id)
    if verdict is not None:
        statement = statement.where(Annotation.verdict == verdict)
    statement = statement.order_by(Video.id, Candidate.start_seconds, Candidate.rank).limit(limit)
    return list(session.scalars(statement))


@router.get("/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate(candidate_id: int, session: Session = Depends(get_db)) -> Candidate:
    return _candidate_or_404(session, candidate_id)


@router.put("/candidates/{candidate_id}/annotation", response_model=CandidateOut)
def upsert_annotation(
    candidate_id: int,
    payload: AnnotationUpsert,
    session: Session = Depends(get_db),
) -> Candidate:
    candidate = _candidate_or_404(session, candidate_id)
    video = session.get(Video, candidate.video_id)
    if video is None:
        raise ApiError(409, "VIDEO_MISSING", "the candidate's video no longer exists")

    if payload.corrected_start_seconds is not None:
        assert payload.corrected_end_seconds is not None  # guaranteed by schema validator
        try:
            start, end = validate_interval(
                payload.corrected_start_seconds,
                payload.corrected_end_seconds,
                video.duration_seconds,
            )
        except ValueError as exc:
            raise ApiError(422, "INVALID_CORRECTED_INTERVAL", str(exc)) from exc
    else:
        start, end = None, None

    annotation = candidate.annotation
    if annotation is None:
        annotation = Annotation(candidate_id=candidate.id, verdict=payload.verdict)
        session.add(annotation)
    annotation.verdict = payload.verdict
    annotation.corrected_start_seconds = start
    annotation.corrected_end_seconds = end
    annotation.note = payload.note.strip()
    annotation.reviewer = payload.reviewer.strip() or "anonymous"
    session.commit()
    session.refresh(candidate)
    return candidate


@router.delete("/candidates/{candidate_id}/annotation", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(candidate_id: int, session: Session = Depends(get_db)) -> Response:
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.annotation is not None:
        session.delete(candidate.annotation)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates/{candidate_id}/clip")
def candidate_clip(
    candidate_id: int,
    request: Request,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    candidate = _candidate_or_404(session, candidate_id)
    if not candidate.clip_storage_key:
        raise ApiError(
            404,
            "CLIP_NOT_AVAILABLE",
            "no preview clip has been generated for this candidate",
            {"clip_status": candidate.clip_status.value, "error": candidate.clip_error},
        )
    return range_file_response(
        storage.path_for(candidate.clip_storage_key),
        request,
        media_type="video/mp4",
        filename=f"candidate-{candidate.id}.mp4",
    )


__all__ = ["AnnotationOut", "router"]
