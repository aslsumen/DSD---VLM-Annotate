"""Dataset export endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_db, get_project_or_404, settings_dep, storage_dep
from ..errors import ApiError
from ..models import DatasetExport, JobStatus, ProcessingJob
from ..schemas import ExportCreate, ExportCreated, ExportOut, JobOut
from ..services.pipeline import enqueue_export_job
from ..services.storage import LocalStorage
from .files import range_file_response

router = APIRouter(tags=["exports"])


def _export_out(export: DatasetExport, storage: LocalStorage) -> ExportOut:
    out = ExportOut.model_validate(export)
    out.has_file = bool(export.storage_key and storage.exists(export.storage_key))
    return out


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(
    project_id: int,
    payload: ExportCreate,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
    settings: Settings = Depends(settings_dep),
) -> ExportCreated:
    project = get_project_or_404(session, project_id)
    export, job = enqueue_export_job(
        session,
        project=project,
        include_unreviewed=payload.include_unreviewed,
        max_attempts=settings.worker_max_attempts,
    )
    session.commit()
    session.refresh(export)
    session.refresh(job)
    return ExportCreated(export=_export_out(export, storage), job=JobOut.model_validate(job))


@router.get("/projects/{project_id}/exports", response_model=list[ExportOut])
def list_exports(
    project_id: int,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> list[ExportOut]:
    get_project_or_404(session, project_id)
    exports = session.scalars(
        select(DatasetExport)
        .where(DatasetExport.project_id == project_id)
        .order_by(DatasetExport.id.desc())
    )
    return [_export_out(export, storage) for export in exports]


@router.get("/exports/{export_id}", response_model=ExportOut)
def get_export(
    export_id: int,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> ExportOut:
    export = session.get(DatasetExport, export_id)
    if export is None:
        raise ApiError(404, "EXPORT_NOT_FOUND", f"export {export_id} does not exist")
    return _export_out(export, storage)


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_export(
    export_id: int,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    export = session.get(DatasetExport, export_id)
    if export is None:
        raise ApiError(404, "EXPORT_NOT_FOUND", f"export {export_id} does not exist")
    if export.status == "running":
        raise ApiError(409, "EXPORT_RUNNING", "a running export cannot be deleted")
    key = export.storage_key
    job = session.scalar(select(ProcessingJob).where(ProcessingJob.export_id == export.id))
    if job is not None:
        session.delete(job)
    session.delete(export)
    session.commit()
    if key:
        storage.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: int,
    request: Request,
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    export = session.get(DatasetExport, export_id)
    if export is None:
        raise ApiError(404, "EXPORT_NOT_FOUND", f"export {export_id} does not exist")
    if export.status != "ready" or not export.storage_key:
        raise ApiError(
            409,
            "EXPORT_NOT_READY",
            "the export is not ready for download",
            {"status": export.status.value},
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return range_file_response(
        storage.path_for(export.storage_key),
        request,
        media_type="application/zip",
        filename=f"vlm-annotate-project-{export.project_id}-{stamp}.zip",
        attachment=True,
    )


__all__ = ["JobStatus", "router"]
