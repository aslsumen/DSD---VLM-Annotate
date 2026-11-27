"""Durable storage cleanup: deletes that survive a crash after their commit.

A delete commits the row removal before it unlinks the bytes.  The only record
of those keys used to be the row that had just been deleted, so a process that
died in the window stranded files nobody could find again.  These tests pin the
two halves of the fix: the intent rows written inside the deleting transaction,
and the sweep that drains them (plus the two directory kinds a *late writer* can
repopulate after its row is gone).
"""

from __future__ import annotations

import os
import time

import pytest
from app import db
from app.models import Candidate, PendingDeletion, ProcessingJob, SearchVideo, Video
from app.services.pipeline import engine_job_key, feature_cache_key
from app.services.storage_gc import purge_storage, record_deletions
from sqlalchemy import func, select
from tests.conftest import make_video_bytes

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _create_dataset(client, name: str = "Storage GC") -> dict:
    response = client.post("/api/v1/datasets", json={"name": name, "description": "fixture"})
    assert response.status_code == 201, response.text
    return response.json()


def _upload_video(client, dataset_id: int, filename: str = "clip.mp4") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/videos",
        files={"file": (filename, make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _launch_search(client, dataset_id: int, *, prompt: str = "a person waves") -> dict:
    response = client.post(f"/api/v1/datasets/{dataset_id}/searches", json={"prompt": prompt})
    assert response.status_code == 202, response.text
    return response.json()


def _storage(client):
    return client.app.state.storage


def _pending_keys() -> list[str]:
    with db.SessionLocal() as session:
        return [row.storage_key for row in session.scalars(select(PendingDeletion))]


def _clip_keys(video_id: int) -> list[str]:
    with db.SessionLocal() as session:
        return [
            key
            for key in session.scalars(
                select(Candidate.clip_storage_key).where(Candidate.video_id == video_id)
            )
            if key
        ]


def _count(model) -> int:
    with db.SessionLocal() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _job_id_of(video_id: int) -> int:
    with db.SessionLocal() as session:
        return int(
            session.scalar(select(ProcessingJob.id).where(ProcessingJob.video_id == video_id))
        )


def _storage_key_of(video_id: int) -> str:
    """The API never exposes storage keys, so read the row instead."""
    with db.SessionLocal() as session:
        video = session.get(Video, video_id)
        assert video is not None
        return video.storage_key


def _age(path, seconds: float) -> None:
    """Backdate a file/dir so the grace period does not protect it."""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


# --------------------------------------------------------------------------- #
# 1. The happy path clears its own queue
# --------------------------------------------------------------------------- #


def test_delete_video_commits_intents_then_purges_them(client, worker) -> None:
    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"])
    _launch_search(client, dataset["id"])
    assert worker.run_once() is True

    storage = _storage(client)
    source_key = _storage_key_of(video["id"])
    clip_keys = _clip_keys(video["id"])
    assert storage.path_for(source_key).is_file()
    assert clip_keys and all(storage.path_for(key).is_file() for key in clip_keys)

    assert client.delete(f"/api/v1/videos/{video['id']}").status_code == 204

    assert not storage.path_for(source_key).exists()
    assert all(not storage.path_for(key).exists() for key in clip_keys)
    # The fast path drained what it queued, so nothing is left for the sweep.
    assert _pending_keys() == []


# --------------------------------------------------------------------------- #
# 2. A crash after the commit leaves recoverable intents (reviewer's 3A)
# --------------------------------------------------------------------------- #


def test_interrupted_delete_leaves_recoverable_intents(client, worker, monkeypatch) -> None:
    from app.api import videos as videos_api

    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"])
    _launch_search(client, dataset["id"])
    assert worker.run_once() is True

    storage = _storage(client)
    source_key = _storage_key_of(video["id"])
    clip_keys = _clip_keys(video["id"])
    assert clip_keys

    def crash_after_commit(session, storage_, *, keys=None, limit=200):
        raise RuntimeError("simulated crash after the delete commit")

    monkeypatch.setattr(videos_api, "flush_pending_deletions", crash_after_commit)

    with pytest.raises(RuntimeError):
        client.delete(f"/api/v1/videos/{video['id']}")

    # The rows are gone -- that is what "after the commit" means -- and the
    # bytes are still there, but they are named by the queue, not lost.
    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is None
    assert _count(SearchVideo) == 0
    assert storage.path_for(source_key).is_file()
    assert all(storage.path_for(key).is_file() for key in clip_keys)
    queued = set(_pending_keys())
    assert source_key in queued
    assert set(clip_keys).issubset(queued)

    # A later sweep -- the one the worker runs every tick -- finishes the job.
    with db.SessionLocal() as session:
        purge_storage(session, storage, grace_seconds=300.0)
    assert not storage.path_for(source_key).exists()
    assert all(not storage.path_for(key).exists() for key in clip_keys)
    assert _pending_keys() == []


# --------------------------------------------------------------------------- #
# 3. A dead process's queue is drained by the next worker tick
# --------------------------------------------------------------------------- #


def test_worker_tick_purges_intents_from_a_dead_process(client, worker) -> None:
    storage = _storage(client)
    keys = ["videos/1/stranded.mp4", "clips/stranded-1-2.mp4"]
    for key in keys:
        path = storage.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stranded")
    with db.SessionLocal() as session:
        record_deletions(session, keys=keys, reason="video")
        session.commit()

    # No queued job, so the tick returns False -- but the sweep still runs.
    assert worker.run_once() is False

    assert all(not storage.path_for(key).exists() for key in keys)
    assert _pending_keys() == []


# --------------------------------------------------------------------------- #
# 4. A clip written after its video was deleted is not left behind (3B)
# --------------------------------------------------------------------------- #


def test_late_clip_written_after_the_delete_is_collected(client, worker, monkeypatch) -> None:
    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"], "late.mp4")
    _launch_search(client, dataset["id"])
    storage = _storage(client)
    url = f"/api/v1/videos/{video['id']}"
    extractor = client.app.state.extractor
    written: list[str] = []

    def extract_after_delete(source, destination, start, end):
        # Exactly the reviewer's scenario: the extractor is paused before it
        # writes, the video is deleted, and only then does the file appear.
        assert client.delete(url).status_code == 204
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"late-clip")
        written.append(str(destination))

    monkeypatch.setattr(extractor, "extract", extract_after_delete)

    assert worker.run_once() is True

    # The worker noticed the candidate was gone and dropped the bytes it had
    # just written instead of leaving an unreferenced clip on disk.
    assert written
    assert all(not os.path.exists(path) for path in written)
    assert _count(Candidate) == 0
    with db.SessionLocal() as session:
        purge_storage(session, storage, grace_seconds=300.0)
    for path in written:
        assert not os.path.exists(path)


# --------------------------------------------------------------------------- #
# 5. The orphan sweep respects the grace period
# --------------------------------------------------------------------------- #


def test_orphan_sweep_respects_the_grace_period(client) -> None:
    storage = _storage(client)
    fresh = storage.path_for("clips/fresh-orphan.mp4")
    stale = storage.path_for("clips/stale-orphan.mp4")
    for path in (fresh, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"orphan")
    _age(stale, 3600)

    with db.SessionLocal() as session:
        purge_storage(session, storage, grace_seconds=300.0)

    assert fresh.is_file(), "a writer may still be producing this file"
    assert not stale.exists()


# --------------------------------------------------------------------------- #
# 5b. The engine sweep keeps what is still owned, however old it is
# --------------------------------------------------------------------------- #


def test_orphan_sweep_keeps_engine_dirs_that_are_still_owned(client) -> None:
    """Ownership decides, not age.

    A worker can be mid-inference on ``engine/job-N`` and silent for minutes, so
    its directory must survive even when it looks abandoned; and
    ``engine/features/video-N`` is a cache the next search on that video reuses.
    Both are older than the grace period here, which is exactly the case a pure
    age sweep would get wrong.
    """
    storage = _storage(client)
    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"])
    _launch_search(client, dataset["id"])
    job_id = _job_id_of(video["id"])

    live_job_dir = storage.path_for(engine_job_key(job_id))
    live_cache_dir = storage.path_for(feature_cache_key(video["id"]))
    dead_job_dir = storage.path_for(engine_job_key(999_999))
    dead_cache_dir = storage.path_for(feature_cache_key(999_999))
    for path in (live_job_dir, live_cache_dir, dead_job_dir, dead_cache_dir):
        path.mkdir(parents=True, exist_ok=True)
        _age(path, 3600)

    with db.SessionLocal() as session:
        purge_storage(session, storage, grace_seconds=300.0)

    assert live_job_dir.is_dir(), "the engine may be mid-inference and silent for minutes"
    assert live_cache_dir.is_dir(), "the next search on this video reuses the cache"
    assert not dead_job_dir.exists()
    assert not dead_cache_dir.exists()


# --------------------------------------------------------------------------- #
# 6. An intent for a key that can never be removed is dropped, not retried
# --------------------------------------------------------------------------- #


def test_pending_deletion_of_a_missing_file_is_dropped(client) -> None:
    storage = _storage(client)
    with db.SessionLocal() as session:
        record_deletions(session, keys=["clips/never-existed.mp4"], reason="video")
        session.commit()

    with db.SessionLocal() as session:
        purge_storage(session, storage, grace_seconds=300.0)

    assert _pending_keys() == []


# --------------------------------------------------------------------------- #
# 7. The queue is part of the same transaction as the row deletion
# --------------------------------------------------------------------------- #


def test_queued_deletions_roll_back_with_the_row(client) -> None:
    """Intent rows and the row they belong to cannot diverge."""
    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"])
    source_key = _storage_key_of(video["id"])

    with db.SessionLocal() as session:
        record_deletions(session, keys=[source_key], reason="video")
        session.delete(session.get(Video, video["id"]))
        session.rollback()

    # A rolled-back delete must not leave a cleanup order behind, otherwise the
    # sweep would unlink a file the surviving row still points at.
    assert _pending_keys() == []
    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is not None

    # And the committed direction keeps both halves.
    with db.SessionLocal() as session:
        record_deletions(session, keys=[source_key], reason="video")
        session.delete(session.get(Video, video["id"]))
        session.commit()

    assert _pending_keys() == [source_key]
    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is None


def test_failed_delete_queues_nothing(client, monkeypatch) -> None:
    from app.api import videos as videos_api

    dataset = _create_dataset(client)
    video = _upload_video(client, dataset["id"])
    _launch_search(client, dataset["id"])
    storage = _storage(client)
    source_key = _storage_key_of(video["id"])
    job_id = _job_id_of(video["id"])

    real_refresh = videos_api.refresh_searches_for_video

    def boom(session, video_id, *, commit=True):
        real_refresh(session, video_id, commit=False)
        raise RuntimeError("simulated crash before the delete commit")

    monkeypatch.setattr(videos_api, "refresh_searches_for_video", boom)

    with pytest.raises(RuntimeError):
        client.delete(f"/api/v1/videos/{video['id']}")

    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is not None
        assert session.get(ProcessingJob, job_id) is not None
    assert storage.path_for(source_key).is_file()
    assert _pending_keys() == []
