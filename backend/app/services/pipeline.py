"""Job orchestration: enqueue, claim, execute candidate proposals and exports."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import logging
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..adapters import (
    AdapterError,
    AdapterUnavailable,
    JobInterrupted,
    ProposalRequest,
    VLMAdapter,
)
from ..config import Settings
from ..errors import ApiError
from ..models import (
    ActionDefinition,
    Annotation,
    Candidate,
    ClipStatus,
    DatasetExport,
    ExportStatus,
    JobKind,
    JobStatus,
    ProcessingJob,
    Project,
    Search,
    SearchStatus,
    SearchVideo,
    SearchVideoStatus,
    Video,
    VideoStatus,
)
from ..validation import clamp_to_duration, preview_window
from .media import ClipExtractor, MediaError, MediaProbe
from .storage import LocalStorage, StorageError

logger = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------- #
# Enqueue
# --------------------------------------------------------------------------- #


def engine_job_key(job_id: int) -> str:
    return f"engine/job-{job_id}"


def feature_cache_key(video_id: int) -> str:
    return f"engine/features/video-{video_id}"


def remove_engine_files(
    storage: LocalStorage, job_ids: Iterable[int] = (), video_ids: Iterable[int] = ()
) -> None:
    """Remove engine work dirs (per job) and visual-feature dirs (per video); missing is fine."""
    keys = [*map(engine_job_key, job_ids), *map(feature_cache_key, video_ids)]
    for key in keys:
        with contextlib.suppress(StorageError, OSError):
            shutil.rmtree(storage.path_for(key), ignore_errors=True)


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue_candidate_job(
    session: Session,
    *,
    video: Video,
    action: ActionDefinition | None,
    adapter_name: str,
    params: dict[str, Any],
    idempotency_key: str | None,
    max_attempts: int,
) -> ProcessingJob:
    if action is not None and video.project_id != action.project_id:
        raise ApiError(409, "PROJECT_MISMATCH", "video and action belong to different projects")
    if video.status != VideoStatus.ready or not video.duration_seconds:
        raise ApiError(
            409,
            "VIDEO_NOT_READY",
            "video must be probed successfully before a processing job can start",
        )
    if idempotency_key:
        existing = session.scalar(
            select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
    job = ProcessingJob(
        kind=JobKind.candidate_proposal,
        status=JobStatus.queued,
        project_id=video.project_id,
        video_id=video.id,
        action_id=action.id if action is not None else None,
        adapter_name=adapter_name,
        params_json=json.dumps(params, sort_keys=True),
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
        available_at=_now(),
    )
    session.add(job)
    session.flush()
    return job


def enqueue_export_job(
    session: Session,
    *,
    project: Project,
    include_unreviewed: bool,
    max_attempts: int,
) -> tuple[DatasetExport, ProcessingJob]:
    candidate_count = (
        session.scalar(
            select(func.count(Candidate.id))
            .join(Video, Candidate.video_id == Video.id)
            .where(Video.project_id == project.id)
        )
        or 0
    )
    if candidate_count == 0:
        raise ApiError(409, "EMPTY_PROJECT", "this project has no candidates to export")

    reviewed_count = (
        session.scalar(
            select(func.count(Annotation.id))
            .join(Candidate, Annotation.candidate_id == Candidate.id)
            .join(Video, Candidate.video_id == Video.id)
            .where(Video.project_id == project.id)
        )
        or 0
    )
    if reviewed_count == 0 and not include_unreviewed:
        raise ApiError(
            409,
            "NO_REVIEWED_CANDIDATES",
            "no reviewed candidates yet; review some or set include_unreviewed=true "
            "to export an explicitly unlabelled snapshot",
        )

    export = DatasetExport(
        project_id=project.id,
        include_unreviewed=include_unreviewed,
        status=ExportStatus.queued,
    )
    session.add(export)
    session.flush()
    job = ProcessingJob(
        kind=JobKind.dataset_export,
        status=JobStatus.queued,
        project_id=project.id,
        export_id=export.id,
        max_attempts=max_attempts,
        available_at=_now(),
    )
    session.add(job)
    session.flush()
    return export, job


# --------------------------------------------------------------------------- #
# Claim
# --------------------------------------------------------------------------- #


def claim_next_job(session: Session, now: datetime | None = None) -> ProcessingJob | None:
    """Atomically move one due job from queued to running.

    The conditional UPDATE is the concurrency guard: two workers racing on the
    same row produce a rowcount of 0 for the loser.  On PostgreSQL this can be
    upgraded to ``SELECT ... FOR UPDATE SKIP LOCKED``.
    """
    moment = now or _now()
    job_id = session.scalar(
        select(ProcessingJob.id)
        .where(
            ProcessingJob.status == JobStatus.queued,
            ProcessingJob.available_at <= moment,
        )
        .order_by(ProcessingJob.available_at, ProcessingJob.id)
        .limit(1)
    )
    if job_id is None:
        return None
    result = session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id, ProcessingJob.status == JobStatus.queued)
        .values(
            status=JobStatus.running,
            started_at=moment,
            updated_at=moment,
            attempts=ProcessingJob.attempts + 1,
        )
    )
    session.commit()
    if result.rowcount != 1:
        return None
    return session.get(ProcessingJob, job_id)


# --------------------------------------------------------------------------- #
# Lease: a worker owns a job while status == running AND attempts == the value it
# claimed with (the fencing token).  Liveness is ProcessingJob.updated_at, touched by
# every progress commit and by the worker's heartbeat thread.  updated_at uses the
# worker's clock, so several worker hosts need synchronized clocks (NTP).
# --------------------------------------------------------------------------- #


def _owned(job_id: int, attempts: int) -> tuple[Any, ...]:
    return (
        ProcessingJob.id == job_id,
        ProcessingJob.status == JobStatus.running,
        ProcessingJob.attempts == attempts,
    )


def heartbeat(session: Session, job_id: int, attempts: int) -> bool:
    """Touch updated_at if this worker still owns the job.  False means it no longer does."""
    result = session.execute(
        update(ProcessingJob)
        .where(*_owned(job_id, attempts))
        .values(updated_at=_now())
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount == 1


def _fence(session: Session, job: ProcessingJob) -> None:
    """Assert ownership and take the row/write lock for the caller's upcoming commit.

    Deliberately does not commit: the caller's ORM writes and commit share this transaction,
    so the ownership check and the writes are atomic (SQLite write lock, Postgres row lock).
    """
    # Read the identity before anything else: once the row is gone (job canceled,
    # reclaimed, or deleted with its action/video) the rollback expires the ORM
    # object and reading job.id afterwards would raise ObjectDeletedError.
    job_id, attempts = job.id, job.attempts
    result = session.execute(
        update(ProcessingJob)
        .where(*_owned(job_id, attempts))
        .values(updated_at=_now())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise JobInterrupted(f"job {job_id} is no longer owned by this worker")


def _fail_export(session: Session, export_id: int | None, message: str) -> None:
    export = session.get(DatasetExport, export_id) if export_id else None
    if export is not None:
        export.status = ExportStatus.failed
        export.error_message = message[:2000]


def reap_stale_jobs(
    session: Session, stale_after_seconds: float, now: datetime | None = None
) -> int:
    """Requeue (or fail, when attempts are exhausted) running jobs whose worker went silent."""
    moment = now or _now()
    cutoff = moment - timedelta(seconds=stale_after_seconds)
    stale = session.scalars(
        select(ProcessingJob).where(
            ProcessingJob.status == JobStatus.running, ProcessingJob.updated_at < cutoff
        )
    ).all()
    reaped = 0
    for job in stale:
        exhausted = job.attempts >= job.max_attempts
        message = "worker stopped heart-beating; " + (
            "attempts exhausted" if exhausted else "requeued"
        )
        values: dict[str, Any] = {
            "error_code": "WORKER_LOST",
            "error_message": message,
            "updated_at": moment,
        }
        if exhausted:
            values.update(status=JobStatus.failed, finished_at=moment)
        else:
            values.update(status=JobStatus.queued, available_at=moment, progress=0.0)
        # Re-checking status/updated_at/attempts keeps two reapers (or a late heartbeat) from
        # double-acting on the same job.
        result = session.execute(
            update(ProcessingJob)
            .where(*_owned(job.id, job.attempts), ProcessingJob.updated_at < cutoff)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            if exhausted and job.kind == JobKind.dataset_export:
                _fail_export(session, job.export_id, message)
            # The bulk UPDATE ran with synchronize_session=False, so the ORM
            # instance is stale. Paint the new state in memory, then mirror it on
            # the SearchVideo row (a requeued job goes back to queued, not failed).
            job.status = JobStatus.failed if exhausted else JobStatus.queued
            job.error_message = message
            sv = _search_video_for_job(session, job)
            search_id = None
            if sv is not None:
                sv.status = (
                    SearchVideoStatus.failed if exhausted else SearchVideoStatus.queued
                )
                sv.error_message = message if exhausted else None
                search_id = sv.search_id
            reaped += 1
            logger.warning("job %s: %s", job.id, message)
        else:
            search_id = None
        session.commit()
        if search_id is not None:
            # Commit first, then derive: a worker may be finishing another video
            # of the same search right now, and an in-transaction derivation would
            # not see that row.
            _settle_search_status(session, search_id)
    return reaped


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


def execute_job(
    session: Session,
    job_id: int,
    *,
    storage: LocalStorage,
    probe: MediaProbe,
    extractor: ClipExtractor,
    adapter: VLMAdapter | None,
    settings: Settings,
) -> ProcessingJob:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", "job disappeared before execution")
    # Fence *before* the first child write.  A job canceled or reclaimed between
    # the claim and this point already had its SearchVideo settled by the
    # canceller or the reaper; painting "running" here without checking ownership
    # would resurrect that row and hang its search in ``running`` for good.
    try:
        _fence(session, job)
        search_video = _search_video_for_job(session, job)
        search_id = None
        if search_video is not None:
            search_video.status = SearchVideoStatus.running
            search_video.error_message = None
            search_id = search_video.search_id
        session.commit()
        if search_id is not None:
            # Derive after the commit so a peer finishing another video of the
            # same search is visible here.
            _settle_search_status(session, search_id)
    except JobInterrupted:
        session.rollback()
        logger.info(
            "job %s no longer owned by this worker (canceled or reclaimed); not started",
            job_id,
        )
        return job
    try:
        try:
            if job.kind == JobKind.candidate_proposal:
                if adapter is None:
                    raise AdapterUnavailable("no adapter resolved for this job")
                _run_candidate_job(
                    session,
                    job,
                    storage=storage,
                    probe=probe,
                    extractor=extractor,
                    adapter=adapter,
                    settings=settings,
                )
            elif job.kind == JobKind.dataset_export:
                _run_export_job(session, job, storage=storage, settings=settings)
            else:  # pragma: no cover - enum guard
                raise ApiError(500, "UNKNOWN_JOB_KIND", f"unknown job kind {job.kind}")
            # Job and child row land in the SAME transaction: a crash between the
            # two would otherwise leave a succeeded job whose SearchVideo is still
            # "running", i.e. a search that never finishes.
            _finish(session, job, JobStatus.succeeded, commit=False)
            search_video = _search_video_for_job(session, job)
            if search_video is not None:
                search_video.status = SearchVideoStatus.done
                search_video.error_message = None
            session.commit()
            if search_video is not None:
                # Derive the aggregate only now that this row is visible to peers.
                _settle_search_status(session, search_video.search_id)
        except JobInterrupted:
            raise  # must not reach the generic handler below
        except (AdapterError, MediaError, StorageError) as exc:
            _record_failure(
                session,
                job,
                exc.code,
                exc,
                settings=settings,
                retryable=getattr(exc, "retryable", True),
                commit=False,
            )
            _commit_with_search_video(session, job)
        except ApiError as exc:
            _record_failure(
                session, job, exc.code, exc, settings=settings, retryable=False, commit=False
            )
            _commit_with_search_video(session, job)
        except SQLAlchemyError as exc:
            # A statement failure (foreign key, constraint, disk) leaves the
            # session unusable: every later statement raises PendingRollbackError,
            # so the job kept its "running" status and the search never settled.
            # Roll back first, then re-read the row to see whether we still own it.
            job_id, attempts = job.id, job.attempts
            logger.warning(
                "job %s hit a database error; rolling back and failing it",
                job_id,
                exc_info=exc,
            )
            session.rollback()
            current = session.get(ProcessingJob, job_id)
            if (
                current is None
                or current.status != JobStatus.running
                or current.attempts != attempts
            ):
                # Deleted (its video went away) or taken over by another worker.
                return current if current is not None else job
            _record_failure(
                session,
                current,
                "JOB_FAILED",
                exc,
                settings=settings,
                retryable=True,
                commit=False,
            )
            _commit_with_search_video(session, current)
            return current
        except Exception as exc:
            logger.exception("unexpected job failure", extra={"job_id": job_id})
            _record_failure(
                session, job, "JOB_FAILED", exc, settings=settings, retryable=True, commit=False
            )
            _commit_with_search_video(session, job)
    except JobInterrupted:
        # Also reached from inside _record_failure.  Leave the row to its new owner/canceler.
        session.rollback()
        logger.info(
            "job %s no longer owned by this worker (canceled or reclaimed); result dropped",
            job_id,
        )
    return job


def _set_progress(session: Session, job: ProcessingJob, value: float) -> None:
    _fence(session, job)
    job.progress = round(min(1.0, max(0.0, value)), 3)
    job.updated_at = _now()
    session.commit()


def _run_candidate_job(
    session: Session,
    job: ProcessingJob,
    *,
    storage: LocalStorage,
    probe: MediaProbe,
    extractor: ClipExtractor,
    adapter: VLMAdapter,
    settings: Settings,
) -> None:
    video = session.get(Video, job.video_id) if job.video_id else None
    action = session.get(ActionDefinition, job.action_id) if job.action_id else None
    if video is None:
        raise ApiError(409, "JOB_PRECONDITION_FAILED", "video no longer exists")
    # Search-driven jobs (action is None) carry their prompt on the parent Search
    # linked through SearchVideo.job_id.
    search_video: SearchVideo | None = None
    search: Search | None = None
    if action is None:
        search_video = session.scalar(
            select(SearchVideo).where(SearchVideo.job_id == job.id)
        )
        search = (
            session.get(Search, search_video.search_id)
            if search_video is not None
            else None
        )
        if search is None:
            raise ApiError(
                409, "JOB_PRECONDITION_FAILED", "search no longer exists for this job"
            )
        action_text = search.prompt
    else:
        action_text = action.description
    if not video.duration_seconds:
        metadata = probe.probe(storage.path_for(video.storage_key))
        video.duration_seconds = metadata.duration_seconds
        video.width = metadata.width
        video.height = metadata.height
        video.fps = metadata.fps
        video.status = VideoStatus.ready

    duration = float(video.duration_seconds)
    job.adapter_version = adapter.version
    _set_progress(session, job, 0.05)

    job_id, video_id = job.id, video.id
    request = ProposalRequest(
        video_path=storage.path_for(video.storage_key),
        duration_seconds=duration,
        action_text=action_text,
        max_candidates=settings.max_candidates_per_job,
        min_duration_seconds=settings.candidate_min_duration_seconds,
        max_duration_seconds=settings.candidate_max_duration_seconds,
        params=json.loads(job.params_json or "{}"),
        # Stable per job id so a resumable engine can pick up where a failed attempt stopped.
        work_dir=storage.path_for(engine_job_key(job_id)),
        feature_cache_dir=storage.path_for(feature_cache_key(video_id)),
        progress=lambda fraction: _set_progress(session, job, 0.05 + 0.30 * fraction),
    )
    try:
        proposals = adapter.propose(request)
    finally:
        # A running adapter can write files after the API has removed the video and its directories.
        if not request.video_path.is_file():
            remove_engine_files(storage, [job_id], [video_id])
    # Exhaustive adapters report every occurrence they find; none means "does not occur".
    exhaustive = getattr(adapter, "exhaustive", False)
    if not proposals and not exhaustive:
        raise AdapterError("adapter returned zero candidate intervals")

    # Retries must be idempotent: clear any partial rows from a previous attempt.
    session.execute(delete(Candidate).where(Candidate.job_id == job.id))
    session.flush()
    _set_progress(session, job, 0.35)

    if exhaustive:  # keep everything, likely ones first for reviewers
        ordered = sorted(proposals, key=lambda p: (-p.score, p.start_seconds))
    else:
        ordered = sorted(proposals, key=lambda p: (p.start_seconds, p.end_seconds))
        ordered = ordered[: settings.max_candidates_per_job]
    created: list[Candidate] = []
    for rank, proposal in enumerate(ordered, start=1):
        start, end = clamp_to_duration(
            min(proposal.start_seconds, duration),
            min(proposal.end_seconds, duration),
            duration,
            min_duration=max(0.5, settings.candidate_min_duration_seconds / 2),
        )
        notes = proposal.notes
        if abs(start - proposal.start_seconds) > 1e-6 or abs(end - proposal.end_seconds) > 1e-6:
            notes = (
                f"{notes} [clamped from {proposal.start_seconds:.3f}-{proposal.end_seconds:.3f}s]"
            ).strip()
        try:
            preview_start, preview_end = preview_window(
                start,
                end,
                duration,
                padding=settings.clip_padding_seconds,
                max_length=settings.clip_max_duration_seconds,
            )
        except ValueError:
            preview_start, preview_end = start, end
        candidate = Candidate(
            job_id=job.id,
            search_id=search.id if search is not None else None,
            video_id=video.id,
            action_id=action.id if action is not None else None,
            start_seconds=start,
            end_seconds=end,
            preview_start_seconds=preview_start,
            preview_end_seconds=preview_end,
            rank=rank,
            score=round(float(proposal.score), 4),
            model_notes=notes or "",
            clip_status=ClipStatus.pending,
        )
        session.add(candidate)
        created.append(candidate)
    session.flush()
    _set_progress(session, job, 0.55)

    failures = 0
    for index, candidate in enumerate(created, start=1):
        # Fence *before* writing the clip.  The old order extracted first and
        # fenced only at the bottom of the loop, so a job whose video was deleted
        # while the extractor was paused still wrote its file — a file no row
        # referenced, because the delete had already collected the candidates.
        _set_progress(session, job, 0.55 + 0.4 * (index - 1) / len(created))
        clip_key = f"clips/{candidate.id}-{round(candidate.preview_start_seconds, 3)}-{round(candidate.preview_end_seconds, 3)}.mp4"
        clip_key = clip_key.replace(":", "")
        try:
            destination = storage.path_for(clip_key)
            extractor.extract(
                storage.path_for(video.storage_key),
                destination,
                candidate.preview_start_seconds,
                candidate.preview_end_seconds,
            )
            still_ours = session.scalar(
                select(func.count(Candidate.id)).where(Candidate.id == candidate.id)
            )
            if not still_ours:
                # The video went away while the extractor ran: drop the bytes it
                # just wrote instead of leaving an unreferenced clip behind.
                storage.delete(clip_key)
                raise JobInterrupted(
                    "the video was deleted while its preview clip was extracted"
                )
            candidate.clip_storage_key = clip_key
            candidate.clip_status = ClipStatus.ready
        except (MediaError, StorageError) as exc:
            failures += 1
            candidate.clip_status = ClipStatus.failed
            candidate.clip_error = f"{exc.code}: {exc}"
            logger.warning("clip extraction failed for candidate %s: %s", candidate.id, exc)
        _set_progress(session, job, 0.55 + 0.4 * index / len(created))

    if failures:
        job.error_code = "CLIP_EXTRACTION_PARTIAL"
        job.error_message = (
            f"{failures}/{len(created)} preview clips could not be extracted; "
            "candidates remain reviewable with the source video player."
        )
    else:
        job.error_code = None
        job.error_message = None


def _run_export_job(
    session: Session, job: ProcessingJob, *, storage: LocalStorage, settings: Settings
) -> None:
    export = session.get(DatasetExport, job.export_id) if job.export_id else None
    if export is None:
        raise ApiError(409, "JOB_PRECONDITION_FAILED", "export record no longer exists")
    project = session.get(Project, export.project_id)
    if project is None:
        raise ApiError(409, "JOB_PRECONDITION_FAILED", "project no longer exists")

    export.status = ExportStatus.running
    _set_progress(session, job, 0.1)

    rows = session.execute(
        select(Candidate, Annotation, Video, ActionDefinition, ProcessingJob)
        .join(Video, Candidate.video_id == Video.id)
        .join(ProcessingJob, Candidate.job_id == ProcessingJob.id)
        .outerjoin(ActionDefinition, Candidate.action_id == ActionDefinition.id)
        .outerjoin(Annotation, Annotation.candidate_id == Candidate.id)
        .where(Video.project_id == project.id)
        .order_by(Video.id, Candidate.start_seconds, Candidate.rank)
    ).all()

    clip_keys = {candidate.id: candidate.clip_storage_key for candidate, *_ in rows}
    items: list[dict[str, Any]] = []
    for candidate, annotation, video, action, source_job in rows:
        if annotation is None and not export.include_unreviewed:
            continue
        corrected = None
        final_start, final_end = candidate.start_seconds, candidate.end_seconds
        if annotation and annotation.corrected_start_seconds is not None:
            corrected = {
                "start_seconds": annotation.corrected_start_seconds,
                "end_seconds": annotation.corrected_end_seconds,
            }
            final_start, final_end = (
                annotation.corrected_start_seconds,
                annotation.corrected_end_seconds,
            )
        clip_name = None
        if candidate.clip_storage_key and storage.exists(candidate.clip_storage_key):
            clip_name = f"clips/candidate_{candidate.id:05d}.mp4"
        items.append(
            {
                "candidate_id": candidate.id,
                "verdict": annotation.verdict.value if annotation else "unreviewed",
                "review_state": candidate.review_state,
                "video": {
                    "id": video.id,
                    "original_filename": video.original_filename,
                    "duration_seconds": video.duration_seconds,
                    "checksum_sha256": video.checksum_sha256,
                },
                "action": (
                    {
                        "id": action.id,
                        "name": action.name,
                        "description": action.description,
                    }
                    if action
                    else None
                ),
                "job": {
                    "id": source_job.id,
                    "adapter_name": source_job.adapter_name,
                    "adapter_version": source_job.adapter_version,
                },
                "proposal": {
                    "start_seconds": candidate.start_seconds,
                    "end_seconds": candidate.end_seconds,
                    "score": candidate.score,
                },
                "preview": {
                    "start_seconds": candidate.preview_start_seconds,
                    "end_seconds": candidate.preview_end_seconds,
                },
                "corrected": corrected,
                "final": {"start_seconds": final_start, "end_seconds": final_end},
                "clip": {
                    "file": clip_name,
                    "status": candidate.clip_status.value,
                },
                "note": annotation.note if annotation else "",
                "reviewer": annotation.reviewer if annotation else None,
                "reviewed_at": annotation.updated_at.isoformat() if annotation else None,
                "provenance": {
                    "adapter": source_job.adapter_name,
                    "adapter_version": source_job.adapter_version,
                    "mock": source_job.adapter_name == "mock",
                    "proposal_clamped": "clamped from" in candidate.model_notes,
                },
            }
        )

    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": _now().isoformat(),
        "project": {"id": project.id, "name": project.name},
        "units": "seconds, source-video-relative, half-open [start, end)",
        "include_unreviewed": export.include_unreviewed,
        "item_count": len(items),
        "items": items,
    }

    with tempfile.TemporaryDirectory(dir=storage.root) as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "dataset.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            archive.writestr("labels.csv", _labels_csv(items))
            archive.writestr("README.txt", _export_readme(project, items))
            for item in items:
                clip = item["clip"]["file"]
                if not clip:
                    continue
                source_key = clip_keys.get(item["candidate_id"])
                if source_key and storage.exists(source_key):
                    archive.write(storage.path_for(source_key), arcname=clip)
            _set_progress(session, job, 0.8)
        with archive_path.open("rb") as stream:
            stored = storage.save_stream(
                stream, subdir="exports", suffix=".zip", max_bytes=settings.max_export_bytes
            )

    export.storage_key = stored.key
    export.size_bytes = stored.size_bytes
    export.item_count = len(items)
    export.status = ExportStatus.ready
    export.finished_at = _now()
    _set_progress(session, job, 1.0)


def _labels_csv(items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "candidate_id",
            "verdict",
            "video_id",
            "video_filename",
            "action_name",
            "start_seconds",
            "end_seconds",
            "proposal_start_seconds",
            "proposal_end_seconds",
            "score",
            "clip_file",
            "reviewer",
            "reviewed_at",
            "note",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item["candidate_id"],
                item["verdict"],
                item["video"]["id"],
                item["video"]["original_filename"],
                (item["action"] or {}).get("name", ""),
                item["final"]["start_seconds"],
                item["final"]["end_seconds"],
                item["proposal"]["start_seconds"],
                item["proposal"]["end_seconds"],
                item["proposal"]["score"],
                item["clip"]["file"] or "",
                item["reviewer"] or "",
                item["reviewed_at"] or "",
                item["note"],
            ]
        )
    return buffer.getvalue()


def _export_readme(project: Project, items: list[dict[str, Any]]) -> str:
    mock_items = sum(1 for item in items if item["provenance"]["mock"])
    return (
        f"VLM Annotate dataset export — project #{project.id} {project.name}\n"
        f"schema_version={EXPORT_SCHEMA_VERSION}\n\n"
        "UNITS: all times are seconds relative to the SOURCE video, half-open [start, end).\n"
        "final.start_seconds/final.end_seconds use the human correction when present,\n"
        "otherwise the model proposal. proposal/preview/corrected are preserved separately.\n\n"
        "manifest.json  full provenance per item\n"
        "labels.csv     flat label table for training/evaluation scripts\n"
        "clips/         one H.264/AAC preview clip per item when extraction succeeded\n\n"
        f"Items: {len(items)}; items produced by the MOCK adapter: {mock_items}.\n"
        "Mock items are NOT model predictions and must be labelled as such in any report.\n"
    )


def _finish(
    session: Session, job: ProcessingJob, status: JobStatus, *, commit: bool = True
) -> None:
    _fence(session, job)
    job.status = status
    job.progress = 1.0
    job.finished_at = _now()
    job.updated_at = _now()
    if status == JobStatus.succeeded and job.kind == JobKind.candidate_proposal:
        job.error_code = job.error_code or None
    if commit:
        session.commit()


# --------------------------------------------------------------------------- #
# SearchVideo status synchronization and Search aggregation
# --------------------------------------------------------------------------- #


def _search_video_for_job(session: Session, job: ProcessingJob) -> SearchVideo | None:
    return session.scalar(select(SearchVideo).where(SearchVideo.job_id == job.id))


def _recompute_search_status(session: Session, search_id: int) -> Search | None:
    """Derive a Search's aggregated status from its SearchVideo rows.

    Rules (per the S3-06 plan):
    * queued  — every SearchVideo is queued
    * running — any SearchVideo is running, OR a mix of queued and done/failed
    * done    — every SearchVideo is done, or no rows remain -> finished_at set
    * failed  — every SearchVideo is failed        -> finished_at set
    * partial — none queued/running, >=1 done, >=1 failed -> finished_at set

    A Search with no SearchVideo rows has nothing left to wait for, so it is
    settled as ``done`` (this is the "every video of the search was deleted"
    case, which must not leave the search stuck in queued/running).

    This derives from whatever the session currently sees.  Callers that share
    a run with other workers must go through :func:`_settle_search_status`,
    which re-derives after committing so a concurrent completion cannot be
    missed.
    """
    search = session.get(Search, search_id)
    if search is None:
        return None
    rows = list(
        session.scalars(select(SearchVideo).where(SearchVideo.search_id == search_id))
    )
    if not rows:
        search.status = SearchStatus.done
        search.finished_at = search.finished_at or _now()
        search.error_message = None
        return search
    statuses = {row.status for row in rows}

    all_queued = all(row.status == SearchVideoStatus.queued for row in rows)
    any_running = SearchVideoStatus.running in statuses
    all_done = all(row.status == SearchVideoStatus.done for row in rows)
    all_failed = all(row.status == SearchVideoStatus.failed for row in rows)
    none_pending = (
        SearchVideoStatus.queued not in statuses
        and SearchVideoStatus.running not in statuses
    )
    has_done = SearchVideoStatus.done in statuses
    has_failed = SearchVideoStatus.failed in statuses

    if all_done:
        search.status, finished = SearchStatus.done, True
    elif all_failed:
        search.status, finished = SearchStatus.failed, True
    elif none_pending and has_done and has_failed:
        search.status, finished = SearchStatus.partial, True
    elif any_running:
        search.status, finished = SearchStatus.running, False
    elif all_queued:
        search.status, finished = SearchStatus.queued, False
    else:
        # mix of queued and done/failed with no running row
        search.status, finished = SearchStatus.running, False
    # Only stamp finished_at on the way into a terminal state; re-deriving an
    # already-finished search must not keep bumping the timestamp.
    if finished:
        search.finished_at = search.finished_at or _now()
    else:
        search.finished_at = None
    if search.status == SearchStatus.failed:
        search.error_message = next(
            (
                row.error_message
                for row in rows
                if row.status == SearchVideoStatus.failed and row.error_message
            ),
            None,
        )
    else:
        search.error_message = None
    return search


def _settle_search_status(
    session: Session, search_id: int, *, max_rounds: int = 3, commit: bool = True
) -> Search | None:
    """Persist the pending row change, then derive the Search status atomically.

    Two workers can finish the last two videos of the same search at the same
    time.  Each derives the aggregate from what *its own* transaction can see,
    so a worker that read the rows before its peer committed would compute
    ``running`` and could then overwrite the peer's ``done`` — leaving the
    search stuck in ``running`` forever, because nobody derives it again.

    The cure is to commit the SearchVideo row first and only then derive, and to
    keep re-deriving (dropping the stale snapshot with ``expire_all``) until the
    derived status stops changing.  Whoever commits last therefore always reads
    the rows the other worker already committed and settles on the terminal
    state.  See ``test_searches.py::test_concurrent_completion_settles_the_search``.

    ``commit=False`` is for callers that must keep the row change and the
    aggregate inside their *own* transaction (``DELETE /videos/{id}``): the
    search is then derived in place, without committing or expiring, so a
    failure rolls the delete and the derived status back together.
    """
    if not commit:
        return _recompute_search_status(session, search_id)
    session.commit()
    previous: SearchStatus | None = None
    search: Search | None = None
    for _ in range(max_rounds):
        session.expire_all()
        search = _recompute_search_status(session, search_id)
        if search is None:
            return None
        derived = search.status
        session.commit()
        if derived == previous:
            break
        previous = derived
    return search


def refresh_searches_for_video(
    session: Session, video_id: int, *, commit: bool = True
) -> list[int]:
    """Detach a video from its searches and re-derive each affected Search.

    Call this *before* deleting the Video row: it owns the SearchVideo rows that
    reference the video (the DB cascade would otherwise remove them silently and
    leave the parent Search stuck).  Returns the affected search ids.

    ``commit=False`` keeps the row removals and the derived statuses in the
    caller's transaction, so ``DELETE /videos/{id}`` can drop the video, its
    searches' rows and the settle in one commit — a crash in between must not
    leave the video alive while its search already claims to be finished.
    """
    rows = list(
        session.scalars(select(SearchVideo).where(SearchVideo.video_id == video_id))
    )
    search_ids = sorted({row.search_id for row in rows})
    for row in rows:
        session.delete(row)
    session.flush()
    for search_id in search_ids:
        # Commit the row removals, then derive — a worker may be finishing
        # another video of the same search right now.  With commit=False the
        # caller owns both steps and the aggregate is derived in place.
        _settle_search_status(session, search_id, commit=commit)
    return search_ids


def settle_searches(session: Session, search_ids: Iterable[int]) -> None:
    """Derive each Search from a snapshot that includes a peer's committed rows.

    Split out for callers that had to keep their own write atomic first — notably
    ``DELETE /videos/{id}``, which drops the video and its SearchVideo rows in one
    transaction and can only converge the aggregate afterwards.
    """
    for search_id in sorted(set(search_ids)):
        _settle_search_status(session, search_id)


def _repair_drifted_search_video(
    session: Session,
    *,
    row_id: int,
    row_status: SearchVideoStatus,
    job_id: int,
    job_status: JobStatus,
    wanted: SearchVideoStatus,
    message: str | None,
) -> bool:
    """Repaint one SearchVideo from its job, but only if both still look as read.

    The sweep reads a page of rows and writes them later, in one transaction, so a
    worker can finish one of those videos in between.  Applying the observation
    taken before the pause would put a ``done`` row — and, through the aggregate,
    a ``done`` Search — back to ``running``.  Re-asserting both observations
    inside the UPDATE closes that window: either the row is still the one we read
    and its job still holds the status that justified the repair, or the write
    does nothing and the next tick observes the newer state.

    Returns ``True`` when the repair was applied.
    """
    current_job_status = (
        select(ProcessingJob.status)
        .where(ProcessingJob.id == job_id)
        .scalar_subquery()
    )
    applied = session.execute(
        update(SearchVideo)
        .where(
            SearchVideo.id == row_id,
            SearchVideo.status == row_status,
            SearchVideo.job_id == job_id,
            current_job_status == job_status,
        )
        .values(status=wanted, error_message=message)
        .execution_options(synchronize_session=False)
    )
    return applied.rowcount == 1


def reconcile_search_state(session: Session) -> int:
    """Repair SearchVideo / Search rows that a crash left out of step with their job.

    Every write path now commits the job and its SearchVideo mirror together, so a
    mismatch should not arise going forward; this sweep exists for the rows written
    by older code and for anything a hard kill can still tear apart.  It is
    idempotent and cheap when there is nothing to repair, so the worker calls it on
    every tick alongside :func:`reap_stale_jobs`.

    Four classes of drift are repaired:

    * a SearchVideo whose job already finished (``succeeded``/``failed``/
      ``canceled``) or was requeued, but whose row still says something else — the
      row is repainted from the job, which is the source of truth;
    * a job that is still ``queued``/``running`` while its row claims a terminal
      state — the row is put back to ``queued``/``running``;
    * a Search left in ``queued``/``running`` although all of its videos already
      settled — the aggregate is re-derived;
    * a terminal Search (``done``/``failed``) that still has a ``queued``/
      ``running`` video — the aggregate is re-derived, because a terminal parent
      contradicts a child that is in flight.

    The repaint is a conditional UPDATE that re-asserts the job status and the row
    status observed before the sweep wrote, so a video that finished or was
    requeued while the sweep was paused is left for the next tick instead of being
    dragged back to the state this sweep read.  One residual window is accepted: an
    ABA on the job (``queued -> running -> queued`` by the reaper between read and
    write) can let the old observation through.  That is self-healing — the next
    tick sees the disagreement and repaints — and it can never lose a newer
    *finished* result, which is the failure this guard exists to prevent.

    Returns the number of rows changed — the SearchVideo rows repainted plus the
    Search rows whose aggregate actually moved — so 0 means the sweep found
    nothing to do.  A sweep that only settles a stale aggregate must not report
    0, or a caller would take a torn database for a clean one.
    """
    repaired = 0
    settled_searches: set[int] = set()

    expected = {
        JobStatus.succeeded: SearchVideoStatus.done,
        JobStatus.failed: SearchVideoStatus.failed,
        JobStatus.canceled: SearchVideoStatus.failed,
        JobStatus.running: SearchVideoStatus.running,
        JobStatus.queued: SearchVideoStatus.queued,
    }
    # Select only rows that already disagree, so an idle tick stays cheap.
    drift = or_(
        *[
            and_(ProcessingJob.status == job_status, SearchVideo.status != row_status)
            for job_status, row_status in expected.items()
        ]
    )
    rows = session.execute(
        select(SearchVideo, ProcessingJob)
        .join(ProcessingJob, SearchVideo.job_id == ProcessingJob.id)
        .where(SearchVideo.job_id.is_not(None), drift)
        .limit(200)
    ).all()
    for search_video, job in rows:
        wanted = expected[job.status]
        message = None
        if wanted == SearchVideoStatus.failed:
            message = job.error_message if job.status == JobStatus.failed else "Job canceled"
        # Capture scalars before writing: the ORM instances stay usable after the
        # bulk UPDATE (``expire_on_commit=False``) and must not be written again
        # from this stale read.
        row_id = search_video.id
        row_status = search_video.status
        job_id = job.id
        job_status = job.status
        search_id = search_video.search_id
        applied = _repair_drifted_search_video(
            session,
            row_id=row_id,
            row_status=row_status,
            job_id=job_id,
            job_status=job_status,
            wanted=wanted,
            message=message,
        )
        if not applied:
            # The job or the row moved on while this sweep was paused: the newer
            # state wins, so leave it alone and let the next tick re-observe.
            continue
        logger.warning(
            "reconciled search video %s: job %s is %s, row was %s",
            row_id,
            job_id,
            job_status.value,
            row_status.value,
        )
        settled_searches.add(search_id)
        repaired += 1

    # A Search is only "in progress" while one of its videos is.  Derive only the
    # searches whose rows have all settled but whose own status has not: deriving
    # genuinely running searches on every tick would churn the row for nothing.
    terminal_rows = session.execute(
        select(SearchVideo.search_id)
        .where(SearchVideo.status.in_((SearchVideoStatus.queued, SearchVideoStatus.running)))
        .distinct()
    ).all()
    still_busy = {row[0] for row in terminal_rows}
    unfinished = session.scalars(
        select(Search.id).where(
            Search.status.in_(
                (SearchStatus.queued, SearchStatus.running, SearchStatus.partial)
            )
        )
    ).all()
    for search_id in unfinished:
        if search_id not in still_busy:
            settled_searches.add(search_id)

    # The reverse contradiction: a terminal Search with a queued/running video.
    # ``retry_search`` commits the replacement job and the row before it settles the
    # aggregate, so a kill in between leaves ``failed`` on a search whose only video
    # is queued again -- and the loop above never looks at a terminal parent, so
    # without this the sweep would report 0 and the parent would stay failed.
    if still_busy:
        stale_terminal = session.scalars(
            select(Search.id).where(
                Search.status.in_((SearchStatus.done, SearchStatus.failed)),
                Search.id.in_(list(still_busy)),
            )
        ).all()
        settled_searches.update(stale_terminal)

    if not settled_searches:
        return repaired
    # Remember what each aggregate said before deriving: only a real change counts
    # as a repair, so a sweep that finds nothing still returns 0.
    before = {
        search.id: search.status
        for search in session.scalars(
            select(Search).where(Search.id.in_(list(settled_searches)))
        )
    }
    session.commit()
    for search_id in sorted(settled_searches):
        settled = _settle_search_status(session, search_id)
        if settled is not None and before.get(search_id) != settled.status:
            repaired += 1
    return repaired


def _commit_with_search_video(session: Session, job: ProcessingJob) -> None:
    """Commit the job's new state together with its SearchVideo mirror, then settle.

    The failure paths must not commit the job alone: a crash in between would
    leave a failed job whose SearchVideo still says "running", and nothing would
    ever recompute that search again.  Writing both rows in one transaction and
    only then deriving the aggregate keeps the three levels consistent.
    """
    job_id = job.id
    failed = job.status == JobStatus.failed
    sv = _search_video_for_job(session, job)
    search_id = None
    if sv is not None:
        sv.status = SearchVideoStatus.failed if failed else SearchVideoStatus.queued
        sv.error_message = job.error_message if failed else None
        search_id = sv.search_id
    session.commit()
    if search_id is not None:
        _settle_search_status(session, search_id)
    logger.debug("job %s mirrored onto search video %s", job_id, search_id)


def _record_failure(
    session: Session,
    job: ProcessingJob,
    code: str,
    exc: Exception,
    *,
    settings: Settings,
    retryable: bool,
    commit: bool = True,
) -> None:
    _fence(session, job)
    job.error_code = code
    job.error_message = str(exc)[:4000]
    job.updated_at = _now()
    if retryable and job.attempts < job.max_attempts:
        delay = settings.worker_retry_backoff_seconds * max(1, job.attempts)
        job.status = JobStatus.queued
        job.progress = 0.0
        job.available_at = _now() + timedelta(seconds=delay)
        logger.info("job %s requeued after %s: %s", job.id, code, exc)
    else:
        job.status = JobStatus.failed
        job.finished_at = _now()
        if job.kind == JobKind.dataset_export:
            _fail_export(session, job.export_id, str(exc))
    if commit:
        session.commit()


def fail_job_now(session: Session, job: ProcessingJob, code: str, message: str) -> ProcessingJob:
    """Non-retryable failure decided before execution starts (e.g. adapter missing).

    Fences first, like ``execute_job``: this runs *before* the job's first write,
    so a job canceled (or reclaimed) between the claim and this point must keep
    the state its canceller gave it.  Without the fence the preflight failure
    happily overwrote ``canceled`` with ``failed`` and mirrored that onto the
    SearchVideo, resurrecting a cancellation that had already settled the search
    as ``failed`` with reason "Job canceled".
    """
    job_id = job.id
    try:
        _fence(session, job)
    except JobInterrupted:
        session.rollback()
        logger.info("job %s no longer owned by this worker; not failing it", job_id)
        return job
    job.status = JobStatus.failed
    job.error_code = code
    job.error_message = message[:4000]
    job.finished_at = _now()
    job.updated_at = _now()
    if job.kind == JobKind.dataset_export:
        _fail_export(session, job.export_id, message)
    # Job row and SearchVideo mirror commit together, then the search is settled.
    _commit_with_search_video(session, job)
    return job


def retry_job(session: Session, job: ProcessingJob) -> ProcessingJob:
    # A search job (``action_id`` is NULL: it was enqueued by a search, not by an
    # action) is only runnable while its SearchVideo still points at it.  Once a
    # search retry has linked a replacement job, or the video/SearchVideo row is
    # gone, re-queueing this one could only ever produce a guaranteed failure --
    # ``_run_candidate_job`` would raise "search no longer exists for this job".
    if job.kind == JobKind.candidate_proposal and job.action_id is None:
        linked = session.scalar(select(SearchVideo.id).where(SearchVideo.job_id == job.id))
        if linked is None:
            raise ApiError(
                409,
                "JOB_SUPERSEDED",
                "this job was replaced by a newer run of its search",
            )
    if job.status not in (JobStatus.failed,):
        raise ApiError(409, "JOB_NOT_RETRYABLE", "only failed jobs can be retried")
    job.status = JobStatus.queued
    job.attempts = 0
    job.progress = 0.0
    job.error_code = None
    job.error_message = None
    job.finished_at = None
    job.available_at = _now()
    job.updated_at = _now()
    if job.export_id:
        export = session.get(DatasetExport, job.export_id)
        if export is not None:
            export.status = ExportStatus.queued
            export.error_message = None
    # The SearchVideo mirrors the job: back to queued, and the parent Search
    # leaves its terminal state (finished_at is cleared by the recompute).  Both
    # rows move in one transaction so a crash cannot split them.
    _commit_with_search_video(session, job)
    return job


def cancel_job(session: Session, job: ProcessingJob) -> ProcessingJob:
    """Cancel a queued or running job; a running worker notices at its next fence."""
    moment = _now()
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job.id,
            ProcessingJob.status.in_((JobStatus.queued, JobStatus.running)),
        )
        .values(status=JobStatus.canceled, finished_at=moment, updated_at=moment)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise ApiError(409, "JOB_NOT_CANCELABLE", "only queued or running jobs can be canceled")
    # The UPDATE used synchronize_session=False, so the ORM instance still holds
    # the pre-cancel state; mirror the new status in memory before syncing the
    # SearchVideo row in this same transaction.
    job.status = JobStatus.canceled
    job.finished_at = moment
    sv = _search_video_for_job(session, job)
    search_id = None
    if sv is not None:
        sv.status = SearchVideoStatus.failed
        sv.error_message = "Job canceled"
        search_id = sv.search_id
    if job.export_id:
        session.execute(
            update(DatasetExport)
            .where(
                DatasetExport.id == job.export_id,
                DatasetExport.status.in_((ExportStatus.queued, ExportStatus.running)),
            )
            .values(status=ExportStatus.failed, error_message="canceled")
            .execution_options(synchronize_session=False)
        )
    session.commit()
    if search_id is not None:
        # Derive only now: the SearchVideo row must be visible to peers first.
        _settle_search_status(session, search_id)
    session.refresh(job)
    return job


__all__ = [
    "cancel_job",
    "claim_next_job",
    "enqueue_candidate_job",
    "enqueue_export_job",
    "execute_job",
    "fail_job_now",
    "heartbeat",
    "reap_stale_jobs",
    "reconcile_search_state",
    "refresh_searches_for_video",
    "retry_job",
    "settle_searches",
]
