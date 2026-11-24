"""Job orchestration: enqueue, claim, execute candidate proposals and exports."""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
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
            _sync_search_video_status(
                session,
                job,
                SearchVideoStatus.failed if exhausted else SearchVideoStatus.queued,
                message if exhausted else None,
                commit=False,
            )
            reaped += 1
            logger.warning("job %s: %s", job.id, message)
        session.commit()
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
    _sync_search_video_status(session, job, SearchVideoStatus.running)
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
            _finish(session, job, JobStatus.succeeded)
            _sync_search_video_status(session, job, SearchVideoStatus.done)
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
            )
            _sync_search_video_failure(session, job)
        except ApiError as exc:
            _record_failure(session, job, exc.code, exc, settings=settings, retryable=False)
            _sync_search_video_failure(session, job)
        except Exception as exc:
            logger.exception("unexpected job failure", extra={"job_id": job_id})
            _record_failure(session, job, "JOB_FAILED", exc, settings=settings, retryable=True)
            _sync_search_video_failure(session, job)
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

    request = ProposalRequest(
        video_path=storage.path_for(video.storage_key),
        duration_seconds=duration,
        action_text=action_text,
        max_candidates=settings.max_candidates_per_job,
        min_duration_seconds=settings.candidate_min_duration_seconds,
        max_duration_seconds=settings.candidate_max_duration_seconds,
        params=json.loads(job.params_json or "{}"),
        # Stable per job id so a resumable engine can pick up where a failed attempt stopped.
        work_dir=storage.path_for(f"engine/job-{job.id}"),
        progress=lambda fraction: _set_progress(session, job, 0.05 + 0.30 * fraction),
    )
    proposals = adapter.propose(request)
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


def _finish(session: Session, job: ProcessingJob, status: JobStatus) -> None:
    _fence(session, job)
    job.status = status
    job.progress = 1.0
    job.finished_at = _now()
    job.updated_at = _now()
    if status == JobStatus.succeeded and job.kind == JobKind.candidate_proposal:
        job.error_code = job.error_code or None
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


def refresh_searches_for_video(session: Session, video_id: int) -> list[int]:
    """Detach a video from its searches and re-derive each affected Search.

    Call this *before* deleting the Video row: it owns the SearchVideo rows that
    reference the video (the DB cascade would otherwise remove them silently and
    leave the parent Search stuck).  Returns the affected search ids.
    """
    rows = list(
        session.scalars(select(SearchVideo).where(SearchVideo.video_id == video_id))
    )
    search_ids = sorted({row.search_id for row in rows})
    for row in rows:
        session.delete(row)
    session.flush()
    for search_id in search_ids:
        _recompute_search_status(session, search_id)
    return search_ids


def _sync_search_video_status(
    session: Session,
    job: ProcessingJob,
    status: SearchVideoStatus,
    error_message: str | None = None,
    *,
    commit: bool = True,
) -> None:
    """Mirror a job's state onto its SearchVideo row and re-derive the parent Search."""
    sv = _search_video_for_job(session, job)
    if sv is None:
        return
    sv.status = status
    sv.error_message = error_message
    _recompute_search_status(session, sv.search_id)
    if commit:
        session.commit()


def _sync_search_video_failure(session: Session, job: ProcessingJob) -> None:
    """Mirror the job's own terminal-or-requeued state onto its SearchVideo row."""
    if job.status == JobStatus.failed:
        _sync_search_video_status(
            session, job, SearchVideoStatus.failed, job.error_message
        )
    else:
        # The job was requeued for a retry, so the video is not failed yet.
        _sync_search_video_status(session, job, SearchVideoStatus.queued, None)


def _record_failure(
    session: Session,
    job: ProcessingJob,
    code: str,
    exc: Exception,
    *,
    settings: Settings,
    retryable: bool,
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
    session.commit()


def fail_job_now(session: Session, job: ProcessingJob, code: str, message: str) -> ProcessingJob:
    """Non-retryable failure decided before execution starts (e.g. adapter missing)."""
    job.status = JobStatus.failed
    job.error_code = code
    job.error_message = message[:4000]
    job.finished_at = _now()
    job.updated_at = _now()
    if job.kind == JobKind.dataset_export:
        _fail_export(session, job.export_id, message)
    session.commit()
    _sync_search_video_failure(session, job)
    return job


def retry_job(session: Session, job: ProcessingJob) -> ProcessingJob:
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
    session.commit()
    # The SearchVideo mirrors the job: back to queued, and the parent Search
    # leaves its terminal state (finished_at is cleared by the recompute).
    _sync_search_video_status(session, job, SearchVideoStatus.queued, None)
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
    _sync_search_video_status(
        session, job, SearchVideoStatus.failed, "Job canceled", commit=False
    )
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
    "refresh_searches_for_video",
    "retry_job",
]
