"""Durable storage cleanup.

Every delete path commits the database rows first and unlinks the bytes after
that commit.  Process death inside that window used to leave files no row could
ever name again, because the row holding the key was already gone.  This module
makes the cleanup recoverable in two layers:

* :func:`record_deletions` writes intent rows in the *deleting* transaction, so
  "the row is gone" always implies "the cleanup is still queued";
* :func:`purge_storage` drains the queue and, for the two directories a late
  writer can populate after its row is gone (engine work dirs and preview
  clips), removes files no row references.

Nothing here imports :mod:`app.services.pipeline` — the key builders live at
the call sites — to keep the dependency acyclic.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, false, or_, select, update
from sqlalchemy.orm import Session

from ..models import (
    Candidate,
    ClipStatus,
    JobStatus,
    PendingDeletion,
    ProcessingJob,
    Video,
)
from .storage import LocalStorage, StorageError

logger = logging.getLogger(__name__)

CLIP_PREFIX = "clips"
ENGINE_PREFIX = "engine"


def record_deletions(
    session: Session,
    *,
    keys: Iterable[str | None],
    reason: str,
    is_tree: bool = False,
) -> int:
    """Queue storage keys for removal; does **not** commit.

    Call this before ``session.delete(...)`` of the row that owns the keys: the
    intent rows then land in the same transaction, so a rollback discards both
    and a commit guarantees the sweep can still find the bytes.
    """
    queued = 0
    for key in keys:
        if not key:
            continue
        session.add(PendingDeletion(storage_key=key, reason=reason, is_tree=is_tree))
        queued += 1
    return queued


def _lock_sqlite_writer(session: Session) -> None:
    # A SELECT cannot lock a missing row. Reserve SQLite's write transaction
    # through unlink so another transaction cannot reuse an ID after our check.
    if session.get_bind().dialect.name == "sqlite":
        session.execute(
            update(PendingDeletion).where(false()).values(attempts=PendingDeletion.attempts)
        )


def _in_use(session: Session, key: str, *, is_tree: bool, intent: bool = False) -> bool:
    if is_tree:
        if key.startswith("engine/features/video-"):
            suffix = key.removeprefix("engine/features/video-")
            if suffix.isdecimal():
                return (
                    session.scalar(
                        select(Video.id).where(Video.id == int(suffix)).with_for_update()
                    )
                    is not None
                )
        elif key.startswith("engine/job-"):
            suffix = key.removeprefix("engine/job-")
            if suffix.isdecimal():
                state = session.scalar(
                    select(ProcessingJob.status)
                    .where(ProcessingJob.id == int(suffix))
                    .with_for_update()
                )
                if intent:
                    return state is not None
                return state in (JobStatus.queued, JobStatus.running, JobStatus.failed)
    elif key.startswith("clips/"):
        owned = Candidate.clip_storage_key == key
        # Both historical and new preview names begin with the candidate ID.
        # Read the pending and published states in the same database snapshot.
        candidate_id, sep, _ = key.removeprefix("clips/").partition("-")
        if sep and candidate_id.isdecimal():
            owned = or_(
                owned,
                and_(
                    Candidate.id == int(candidate_id),
                    Candidate.clip_status == ClipStatus.pending,
                    Candidate.job.has(ProcessingJob.status == JobStatus.running),
                ),
            )
        return session.scalar(select(Candidate.id).where(owned).limit(1)) is not None
    return False


def _remove_one(storage: LocalStorage, key: str, *, is_tree: bool) -> None:
    path = storage.path_for(key)
    if is_tree:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            if path.exists():
                raise
    else:
        path.unlink(missing_ok=True)


def flush_pending_deletions(
    session: Session,
    storage: LocalStorage,
    *,
    keys: Sequence[str | None] | None = None,
    limit: int = 200,
) -> int:
    """Drain intent rows, returning how many keys were removed.

    ``keys`` restricts the pass to a known set (the fast path an API delete runs
    right after its commit); omitted, the whole queue is drained (the worker
    sweep).  A row whose key is unrecoverable is dropped: ``path_for`` rejects
    it, so no future attempt could ever remove it.
    """
    statement = select(PendingDeletion).order_by(PendingDeletion.id)
    if keys is not None:
        wanted = [key for key in keys if key]
        if not wanted:
            return 0
        statement = statement.where(PendingDeletion.storage_key.in_(wanted))
        # One key may have several intent rows (a racing delete queued it too),
        # so the cap has to scale with the request rather than being a page size.
        cap = max(limit, len(wanted) * 4)
    else:
        cap = limit
    statement = statement.limit(cap)

    # Avoid taking a database write lock on an empty worker tick. Once the
    # lock is acquired, read the queue again: a peer may already have drained it.
    if session.scalar(statement.with_only_columns(PendingDeletion.id).limit(1)) is None:
        return 0
    _lock_sqlite_writer(session)
    removed = 0
    for row in list(session.scalars(statement.with_for_update())):
        if _in_use(session, row.storage_key, is_tree=row.is_tree, intent=True):
            session.delete(row)  # The old intent no longer owns this path.
            continue
        try:
            _remove_one(storage, row.storage_key, is_tree=row.is_tree)
        except StorageError:
            logger.warning(
                "dropping pending deletion %s: %r is not a usable storage key",
                row.id,
                row.storage_key,
            )
            session.delete(row)
            continue
        except OSError as exc:
            row.attempts += 1
            row.last_error = str(exc)[:4000]
            logger.warning("pending deletion %s failed: %s", row.id, exc)
            continue
        session.delete(row)
        removed += 1
    session.commit()
    return removed


def _referenced_clip_keys(session: Session) -> set[str]:
    return {
        key
        for key in session.scalars(
            select(Candidate.clip_storage_key).where(Candidate.clip_storage_key.is_not(None))
        )
        if key
    }


def _sweep_orphan_clips(session: Session, storage: LocalStorage, *, older_than: datetime) -> int:
    """Delete ``clips/*`` no Candidate points at, older than the grace period."""
    root = storage.path_for(CLIP_PREFIX)
    if not root.is_dir():
        return 0
    referenced = _referenced_clip_keys(session)
    removed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        key = f"{CLIP_PREFIX}/{path.relative_to(root).as_posix()}"
        if key in referenced:
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) >= older_than:
                continue
        except OSError:
            continue
        _lock_sqlite_writer(session)
        if _in_use(session, key, is_tree=False):
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:  # pragma: no cover - permission races
            logger.warning("orphan clip %s could not be removed: %s", key, exc)
    return removed


def _sweep_orphan_engine_dirs(
    session: Session, storage: LocalStorage, *, older_than: datetime
) -> int:
    """Delete engine work/feature dirs nothing can use any more.

    A worker whose video was deleted mid-run recreates ``engine/job-N`` (or
    ``engine/features/video-N``) after the delete already collected the old
    directory, and nothing references the new one.  Ownership, not age, is what
    decides: a ``job-N`` dir is kept while job *N* is queued, running, or failed and retryable (the
    engine may be mid-inference and silent for minutes), and a
    ``features/video-N`` dir is kept while video *N* still exists, because the
    next search on that video reuses the cache.  Age only gates the *removal* of
    an already-unowned directory, so a directory that is momentarily unowned
    during a rename is not collected.
    """
    root = storage.path_for(ENGINE_PREFIX)
    if not root.is_dir():
        return 0

    removed = 0
    job_dirs = list(root.glob("job-*"))
    if job_dirs:
        job_ids = {int(path.name[4:]) for path in job_dirs if path.name[4:].isdigit()}
        live_jobs = set()
        if job_ids:
            live_jobs = {
                job_id
                for job_id in session.scalars(
                    select(ProcessingJob.id).where(
                        ProcessingJob.id.in_(job_ids),
                        ProcessingJob.status.in_(
                            (JobStatus.queued, JobStatus.running, JobStatus.failed)
                        ),
                    )
                )
            }
        for path in job_dirs:
            suffix = path.name[4:]
            if not suffix.isdigit() or int(suffix) in live_jobs:
                continue
            if _is_old_enough(path, older_than) and path.is_dir():
                removed += _remove_orphan_tree(session, storage, path)

    feature_dirs = list(root.glob("features/video-*"))
    if feature_dirs:
        # Slice the directory *name* ("video-7"), not the key ("features/video-7").
        prefix = "video-"
        video_ids = {
            int(path.name[len(prefix) :])
            for path in feature_dirs
            if path.name[len(prefix) :].isdigit()
        }
        live_videos = set()
        if video_ids:
            live_videos = {
                video_id
                for video_id in session.scalars(select(Video.id).where(Video.id.in_(video_ids)))
            }
        for path in feature_dirs:
            suffix = path.name[len(prefix) :]
            if not suffix.isdigit() or int(suffix) in live_videos:
                continue
            if _is_old_enough(path, older_than) and path.is_dir():
                removed += _remove_orphan_tree(session, storage, path)
    return removed


def _remove_orphan_tree(session: Session, storage: LocalStorage, path: Path) -> int:
    key = path.relative_to(storage.root).as_posix()
    _lock_sqlite_writer(session)
    if _in_use(session, key, is_tree=True):
        return 0
    try:
        _remove_one(storage, key, is_tree=True)
    except OSError as exc:
        logger.warning("orphan directory %s could not be removed: %s", key, exc)
        return 0
    return 1


def _is_old_enough(path: Path, older_than: datetime) -> bool:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC) < older_than
    except OSError:
        return False


def _age_gate(grace_seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=max(0.0, grace_seconds))


def purge_storage(
    session: Session,
    storage: LocalStorage,
    *,
    grace_seconds: float = 300.0,
    batch_size: int = 200,
) -> int:
    """Run one cleanup pass: drain the queue, then collect unreferenced orphans.

    Safe to call from several processes at once — removing a file twice is a
    no-op and the table rows disappear with the first winner.
    """
    removed = flush_pending_deletions(session, storage, limit=batch_size)
    older_than = _age_gate(grace_seconds)
    removed += _sweep_orphan_clips(session, storage, older_than=older_than)
    removed += _sweep_orphan_engine_dirs(session, storage, older_than=older_than)
    session.commit()
    return removed


__all__ = [
    "flush_pending_deletions",
    "purge_storage",
    "record_deletions",
]
