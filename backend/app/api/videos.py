"""Video upload, probing, streaming and processing-job creation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import DATASET_WRITE_ROLES, enforce_video_access
from ..adapters.registry import get_adapter
from ..config import Settings
from ..deps import (
    Principal,
    get_db,
    get_optional_principal,
    get_project_or_404,
    get_video_or_404,
    probe_dep,
    settings_dep,
    storage_dep,
)
from ..errors import ApiError
from ..models import ActionDefinition, Candidate, ProcessingJob, Video, VideoStatus
from ..schemas import JobCreate, JobOut, VideoOut
from ..services.media import MediaError, MediaProbe
from ..services.pipeline import (
    engine_job_key,
    enqueue_candidate_job,
    feature_cache_key,
    refresh_searches_for_video,
    settle_searches,
)
from ..services.storage import LocalStorage, StorageError
from ..services.storage_gc import flush_pending_deletions, record_deletions
from .files import range_file_response

router = APIRouter(tags=["videos"])

_MP4_EXTENSIONS = {".mp4", ".mov", ".m4v"}
_MATROSKA_EXTENSIONS = {".webm", ".mkv"}


def _sniff_container(header: bytes) -> str:
    """Cheap container sanity check on the first bytes of the upload."""
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "mp4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "matroska"
    return "unknown"


@router.post(
    "/projects/{project_id}/videos",
    response_model=VideoOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    project_id: int,
    file: UploadFile = File(..., description="Single-view RGB video (mp4/mov/m4v/webm/mkv)"),
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
    probe: MediaProbe = Depends(probe_dep),
    settings: Settings = Depends(settings_dep),
) -> Video:
    get_project_or_404(session, project_id)
    return await ingest_video(
        file,
        subdir=f"videos/{project_id}",
        project_id=project_id,
        dataset_id=None,
        session=session,
        storage=storage,
        probe=probe,
        settings=settings,
    )


async def ingest_video(
    file: UploadFile,
    *,
    subdir: str,
    project_id: int | None,
    dataset_id: int | None,
    session: Session,
    storage: LocalStorage,
    probe: MediaProbe,
    settings: Settings,
) -> Video:
    """Validate, store and probe one upload; attach it to a project or a dataset."""
    original_name = Path(file.filename or "upload").name
    extension = Path(original_name).suffix.lower()
    if extension not in settings.allowed_video_extensions:
        raise ApiError(
            415,
            "UNSUPPORTED_VIDEO_EXTENSION",
            f"'{extension or 'no extension'}' is not an accepted video container",
            {"allowed": settings.allowed_video_extensions},
        )
    if file.content_type and file.content_type not in settings.allowed_video_content_types:
        raise ApiError(
            415,
            "UNSUPPORTED_CONTENT_TYPE",
            f"content type '{file.content_type}' is not accepted",
            {"allowed": settings.allowed_video_content_types},
        )

    header = await file.read(16)
    await file.seek(0)
    container = _sniff_container(header)
    if container == "unknown":
        raise ApiError(
            415,
            "UNRECOGNISED_CONTAINER",
            "the uploaded bytes do not look like a supported video container",
        )
    expected = "mp4" if extension in _MP4_EXTENSIONS else "matroska"
    if container != expected:
        raise ApiError(
            415,
            "CONTAINER_MISMATCH",
            f"file extension {extension} does not match the detected {container} container",
        )

    try:
        stored = storage.save_stream(
            file.file,
            subdir=subdir,
            suffix=extension,
            max_bytes=settings.max_upload_bytes,
        )
    except StorageError as exc:
        if "exceeds" in str(exc):
            raise ApiError(
                413,
                "UPLOAD_TOO_LARGE",
                f"video exceeds the configured limit of {settings.max_upload_bytes} bytes",
                {"max_bytes": settings.max_upload_bytes},
            ) from exc
        raise ApiError(400, "STORAGE_ERROR", str(exc)) from exc

    try:
        metadata = probe.probe(storage.path_for(stored.key))
    except MediaError as exc:
        storage.delete(stored.key)
        raise ApiError(422, exc.code, exc.message) from exc

    if not (
        settings.min_video_duration_seconds
        <= metadata.duration_seconds
        <= settings.max_video_duration_seconds
    ):
        storage.delete(stored.key)
        raise ApiError(
            422,
            "VIDEO_DURATION_OUT_OF_RANGE",
            (
                f"video duration {metadata.duration_seconds:.1f}s is outside the accepted "
                f"range {settings.min_video_duration_seconds:.0f}-"
                f"{settings.max_video_duration_seconds:.0f}s"
            ),
            {
                "min_seconds": settings.min_video_duration_seconds,
                "max_seconds": settings.max_video_duration_seconds,
            },
        )

    video = Video(
        project_id=project_id,
        dataset_id=dataset_id,
        original_filename=original_name,
        storage_key=stored.key,
        content_type=file.content_type or "video/mp4",
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.sha256,
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        fps=metadata.fps,
        status=VideoStatus.ready,
    )
    session.add(video)
    try:
        session.commit()
    except Exception:
        storage.delete(stored.key)
        raise
    session.refresh(video)
    return video


@router.get("/projects/{project_id}/videos", response_model=list[VideoOut])
def list_videos(project_id: int, session: Session = Depends(get_db)) -> list[Video]:
    get_project_or_404(session, project_id)
    return list(
        session.scalars(
            select(Video).where(Video.project_id == project_id).order_by(Video.id.desc())
        )
    )


@router.get("/videos/{video_id}", response_model=VideoOut)
def get_video(
    video_id: int,
    principal: Principal = Depends(get_optional_principal),
    session: Session = Depends(get_db),
) -> Video:
    video = get_video_or_404(session, video_id)
    enforce_video_access(session, principal, video)
    return video


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    principal: Principal = Depends(get_optional_principal),
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    video = get_video_or_404(session, video_id)
    # Authorize before anything is touched: a denied delete must leave the row,
    # the stored file and the derived engine artefacts in place.
    enforce_video_access(session, principal, video, allowed_roles=DATASET_WRITE_ROLES)
    clip_keys = list(
        session.scalars(
            select(Candidate.clip_storage_key).where(
                Candidate.video_id == video_id, Candidate.clip_storage_key.is_not(None)
            )
        )
    )
    job_ids = list(session.scalars(select(ProcessingJob.id).where(ProcessingJob.video_id == video_id)))
    storage_key = video.storage_key
    # One transaction for the whole deletion: detach the video from its searches,
    # queue the storage cleanup, drop the Video row (which cascades to its jobs and
    # candidates), and settle each affected Search only after that commit.  Deriving
    # inside the same transaction would let a crash leave the video alive while its
    # search already claims to be finished with zero videos.
    #
    # The cleanup keys are queued *inside* that transaction on purpose.  Unlinking
    # after the commit leaves a window where a crash strands bytes that no row can
    # name again; queueing them first makes "the row is gone" imply "the cleanup is
    # still queued" for the next sweep.
    search_ids = refresh_searches_for_video(session, video_id, commit=False)
    keys = [storage_key, *filter(None, clip_keys)]
    record_deletions(session, keys=keys, reason="video")
    tree_keys = [*(engine_job_key(job_id) for job_id in job_ids), feature_cache_key(video_id)]
    record_deletions(session, keys=tree_keys, reason="video", is_tree=True)
    session.delete(video)
    session.commit()
    # Converge afterwards: a peer worker may be finishing another video of the
    # same search right now, and only a post-commit snapshot sees its row.
    settle_searches(session, search_ids)
    # Fast path: usually everything is already unreferenced, so the sweep that the
    # worker would do later is unnecessary.  A crash before this line is what the
    # queue exists for.
    flush_pending_deletions(session, storage, keys=[*keys, *tree_keys])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/videos/{video_id}/stream")
def stream_video(
    video_id: int,
    request: Request,
    principal: Principal = Depends(get_optional_principal),
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
) -> Response:
    video = get_video_or_404(session, video_id)
    enforce_video_access(session, principal, video)
    return range_file_response(
        storage.path_for(video.storage_key),
        request,
        media_type=video.content_type or "video/mp4",
        filename=video.original_filename,
    )


@router.post(
    "/videos/{video_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_processing_job(
    video_id: int,
    payload: JobCreate,
    principal: Principal = Depends(get_optional_principal),
    session: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100),
) -> ProcessingJob:
    video = get_video_or_404(session, video_id)
    enforce_video_access(session, principal, video, allowed_roles=DATASET_WRITE_ROLES)
    if video.dataset_id is not None:
        # Dataset work is launched through POST /datasets/{id}/searches, which
        # carries the free-text prompt.  Actions belong to projects, so there is
        # no action a dataset video could legally run.
        raise ApiError(
            409,
            "PROJECT_MISMATCH",
            "dataset videos are processed through a dataset search, not a project action",
        )
    action = session.get(ActionDefinition, payload.action_id)
    if action is None:
        raise ApiError(404, "ACTION_NOT_FOUND", f"action {payload.action_id} does not exist")
    if action.project_id != video.project_id:
        raise ApiError(409, "PROJECT_MISMATCH", "action and video belong to different projects")

    adapter = get_adapter(payload.adapter, settings)
    job = enqueue_candidate_job(
        session,
        video=video,
        action=action,
        adapter_name=adapter.name,
        params=payload.params,
        idempotency_key=idempotency_key,
        max_attempts=settings.worker_max_attempts,
    )
    session.commit()
    session.refresh(job)
    return job
