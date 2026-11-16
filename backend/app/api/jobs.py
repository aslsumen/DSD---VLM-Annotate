"""Processing-job endpoints: status, retry, cancel and candidate listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..deps import get_db, get_job_or_404, get_project_or_404
from ..models import Candidate, JobStatus, ProcessingJob
from ..schemas import CandidateOut, JobOut
from ..services.pipeline import cancel_job, retry_job

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    session: Session = Depends(get_db),
    project_id: int | None = Query(default=None),
    video_id: int | None = Query(default=None),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ProcessingJob]:
    statement = select(ProcessingJob).order_by(ProcessingJob.id.desc()).limit(limit)
    if project_id is not None:
        get_project_or_404(session, project_id)
        statement = statement.where(ProcessingJob.project_id == project_id)
    if video_id is not None:
        statement = statement.where(ProcessingJob.video_id == video_id)
    if status_filter is not None:
        statement = statement.where(ProcessingJob.status == status_filter)
    return list(session.scalars(statement))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_db)) -> ProcessingJob:
    return get_job_or_404(session, job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry(job_id: int, session: Session = Depends(get_db)) -> ProcessingJob:
    job = get_job_or_404(session, job_id)
    return retry_job(session, job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: int, session: Session = Depends(get_db)) -> ProcessingJob:
    job = get_job_or_404(session, job_id)
    return cancel_job(session, job)


@router.get("/jobs/{job_id}/candidates", response_model=list[CandidateOut])
def job_candidates(job_id: int, session: Session = Depends(get_db)) -> list[Candidate]:
    get_job_or_404(session, job_id)
    return list(
        session.scalars(
            select(Candidate)
            .options(selectinload(Candidate.annotation))
            .where(Candidate.job_id == job_id)
            .order_by(Candidate.rank.asc())
        )
    )
