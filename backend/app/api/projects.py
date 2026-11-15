"""Project and action-definition endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_db, get_project_or_404, storage_dep
from ..errors import ApiError
from ..models import (
    ActionDefinition,
    Annotation,
    Candidate,
    DatasetExport,
    ExportStatus,
    JobStatus,
    ProcessingJob,
    Project,
    Verdict,
    Video,
)
from ..schemas import (
    ActionCreate,
    ActionOut,
    ActionUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)
from ..services.storage import LocalStorage

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: Session = Depends(get_db)) -> Project:
    project = Project(name=payload.name, description=payload.description)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .order_by(Project.created_at.desc(), Project.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, session: Session = Depends(get_db)) -> Project:
    return get_project_or_404(session, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, payload: ProjectUpdate, session: Session = Depends(get_db)
) -> Project:
    project = get_project_or_404(session, project_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise ApiError(422, "INVALID_NAME", "project name must not be blank")
        project.name = name
    if payload.description is not None:
        project.description = payload.description
    session.commit()
    session.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    project = get_project_or_404(session, project_id)
    video_keys = list(
        session.scalars(select(Video.storage_key).where(Video.project_id == project_id))
    )
    clip_keys = list(
        session.scalars(
            select(Candidate.clip_storage_key)
            .join(Video, Candidate.video_id == Video.id)
            .where(Video.project_id == project_id, Candidate.clip_storage_key.is_not(None))
        )
    )
    export_keys = list(
        session.scalars(
            select(DatasetExport.storage_key).where(
                DatasetExport.project_id == project_id, DatasetExport.storage_key.is_not(None)
            )
        )
    )
    session.delete(project)
    session.commit()
    for key in [*video_keys, *clip_keys, *export_keys]:
        if key:
            storage.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/stats", response_model=ProjectStats)
def project_stats(project_id: int, session: Session = Depends(get_db)) -> ProjectStats:
    get_project_or_404(session, project_id)

    def scalar(statement: object) -> int:
        return int(session.scalar(statement) or 0)  # type: ignore[arg-type]

    def candidate_count(*conditions: object) -> int:
        statement = (
            select(func.count(Candidate.id))
            .join(Video, Candidate.video_id == Video.id)
            .where(Video.project_id == project_id)
        )
        for condition in conditions:
            statement = statement.where(condition)  # type: ignore[arg-type]
        return scalar(statement)

    reviewed_total = scalar(
        select(func.count(Annotation.id))
        .join(Candidate, Annotation.candidate_id == Candidate.id)
        .join(Video, Candidate.video_id == Video.id)
        .where(Video.project_id == project_id)
    )
    true_positive = scalar(
        select(func.count(Annotation.id))
        .join(Candidate, Annotation.candidate_id == Candidate.id)
        .join(Video, Candidate.video_id == Video.id)
        .where(Video.project_id == project_id, Annotation.verdict == Verdict.true_positive)
    )
    false_positive = scalar(
        select(func.count(Annotation.id))
        .join(Candidate, Annotation.candidate_id == Candidate.id)
        .join(Video, Candidate.video_id == Video.id)
        .where(Video.project_id == project_id, Annotation.verdict == Verdict.false_positive)
    )
    total_candidates = candidate_count()
    jobs_running = int(
        session.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.project_id == project_id,
                ProcessingJob.status.in_([JobStatus.queued, JobStatus.running]),
            )
        )
        or 0
    )
    jobs_failed = int(
        session.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.project_id == project_id, ProcessingJob.status == JobStatus.failed
            )
        )
        or 0
    )
    exports_ready = int(
        session.scalar(
            select(func.count(DatasetExport.id)).where(
                DatasetExport.project_id == project_id,
                DatasetExport.status == ExportStatus.ready,
            )
        )
        or 0
    )
    return ProjectStats(
        videos_total=int(
            session.scalar(select(func.count(Video.id)).where(Video.project_id == project_id)) or 0
        ),
        videos_ready=int(
            session.scalar(
                select(func.count(Video.id)).where(
                    Video.project_id == project_id, Video.status == "ready"
                )
            )
            or 0
        ),
        candidates_total=total_candidates,
        reviewed_total=reviewed_total,
        true_positive_total=true_positive,
        false_positive_total=false_positive,
        unreviewed_total=total_candidates - reviewed_total,
        jobs_running=jobs_running,
        jobs_failed=jobs_failed,
        exports_ready=exports_ready,
    )


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #


@router.post(
    "/projects/{project_id}/actions",
    response_model=ActionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_action(
    project_id: int, payload: ActionCreate, session: Session = Depends(get_db)
) -> ActionDefinition:
    get_project_or_404(session, project_id)
    duplicate = session.scalar(
        select(ActionDefinition).where(
            ActionDefinition.project_id == project_id, ActionDefinition.name == payload.name
        )
    )
    if duplicate is not None:
        raise ApiError(
            409,
            "ACTION_NAME_TAKEN",
            f"an action named '{payload.name}' already exists in this project",
            {"action_id": duplicate.id},
        )
    action = ActionDefinition(
        project_id=project_id, name=payload.name, description=payload.description
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


@router.get("/projects/{project_id}/actions", response_model=list[ActionOut])
def list_actions(project_id: int, session: Session = Depends(get_db)) -> list[ActionDefinition]:
    get_project_or_404(session, project_id)
    return list(
        session.scalars(
            select(ActionDefinition)
            .where(ActionDefinition.project_id == project_id)
            .order_by(ActionDefinition.id.asc())
        )
    )


@router.patch("/actions/{action_id}", response_model=ActionOut)
def update_action(
    action_id: int, payload: ActionUpdate, session: Session = Depends(get_db)
) -> ActionDefinition:
    action = session.get(ActionDefinition, action_id)
    if action is None:
        raise ApiError(404, "ACTION_NOT_FOUND", f"action {action_id} does not exist")
    if payload.name is not None:
        action.name = payload.name.strip()
    if payload.description is not None:
        action.description = payload.description
    session.commit()
    session.refresh(action)
    return action


@router.delete("/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action(action_id: int, session: Session = Depends(get_db)) -> Response:
    action = session.get(ActionDefinition, action_id)
    if action is None:
        raise ApiError(404, "ACTION_NOT_FOUND", f"action {action_id} does not exist")
    session.delete(action)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
