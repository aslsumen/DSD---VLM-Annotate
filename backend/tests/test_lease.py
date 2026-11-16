"""Heartbeat lease: reaping, fencing, cancel of running jobs, worker heartbeat thread."""

from __future__ import annotations

import time
from datetime import timedelta

from app import db
from app.adapters import ProposedInterval
from app.models import (
    Candidate,
    DatasetExport,
    ExportStatus,
    JobKind,
    JobStatus,
    ProcessingJob,
)
from app.services.pipeline import (
    _now,
    cancel_job,
    claim_next_job,
    heartbeat,
    reap_stale_jobs,
)
from sqlalchemy import select, update
from tests.conftest import create_action, create_project, upload_video


def _queued_job(client) -> int:
    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    response = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    return response.json()["id"]


def _patch(job_id: int, **values) -> None:
    with db.SessionLocal() as other:
        other.execute(update(ProcessingJob).where(ProcessingJob.id == job_id).values(**values))
        other.commit()


def _row(job_id: int) -> ProcessingJob:
    with db.SessionLocal() as other:
        return other.get(ProcessingJob, job_id)


def _claim_and_age(job_id: int, seconds: float = 100.0) -> None:
    with db.SessionLocal() as session:
        assert claim_next_job(session).id == job_id
    _patch(job_id, updated_at=_now() - timedelta(seconds=seconds))


# --------------------------------------------------------------------------- #
# Reaper
# --------------------------------------------------------------------------- #


def test_stale_running_job_is_requeued_and_claimable_again(client) -> None:
    job_id = _queued_job(client)
    _claim_and_age(job_id)

    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, stale_after_seconds=30) == 1
    row = _row(job_id)
    assert row.status == JobStatus.queued
    assert row.error_code == "WORKER_LOST"
    assert row.error_message == "worker stopped heart-beating; requeued"
    assert row.attempts == 1

    with db.SessionLocal() as session:
        claimed = claim_next_job(session)
        assert (claimed.id, claimed.attempts) == (job_id, 2)


def test_fresh_running_job_is_not_reaped(client) -> None:
    job_id = _queued_job(client)
    _claim_and_age(job_id, seconds=1.0)
    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, stale_after_seconds=30) == 0
    assert _row(job_id).status == JobStatus.running


def test_stale_job_with_exhausted_attempts_fails_with_its_export(client) -> None:
    project_id = create_project(client)["id"]
    with db.SessionLocal() as session:
        export = DatasetExport(project_id=project_id, status=ExportStatus.queued)
        session.add(export)
        session.flush()
        job = ProcessingJob(
            kind=JobKind.dataset_export,
            project_id=project_id,
            export_id=export.id,
            available_at=_now(),
        )
        session.add(job)
        session.commit()
        export_id = job.id
    _claim_and_age(export_id)
    # onupdate would refresh updated_at, so re-age it in the same statement
    _patch(
        export_id,
        attempts=_row(export_id).max_attempts,
        updated_at=_now() - timedelta(seconds=100),
    )

    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, stale_after_seconds=30) == 1
        row = session.get(ProcessingJob, export_id)
        assert (row.status, row.error_code) == (JobStatus.failed, "WORKER_LOST")
        assert row.finished_at is not None
        export = session.get(DatasetExport, row.export_id)
        assert export.status == ExportStatus.failed
        assert "heart-beating" in export.error_message


def test_reap_uses_the_given_clock(client) -> None:
    job_id = _queued_job(client)
    _claim_and_age(job_id, seconds=0.0)
    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, 30, now=_now() + timedelta(seconds=10)) == 0
        assert reap_stale_jobs(session, 30, now=_now() + timedelta(seconds=60)) == 1


# --------------------------------------------------------------------------- #
# Heartbeat / fencing token
# --------------------------------------------------------------------------- #


def test_heartbeat_true_while_owned_false_after_cancel_or_reclaim(client) -> None:
    job_id = _queued_job(client)
    with db.SessionLocal() as session:
        attempts = claim_next_job(session).attempts
    _patch(job_id, updated_at=_now() - timedelta(seconds=100))

    with db.SessionLocal() as session:
        assert heartbeat(session, job_id, attempts) is True
    assert _row(job_id).updated_at > _now() - timedelta(seconds=10)

    with db.SessionLocal() as session:
        assert heartbeat(session, job_id, attempts + 1) is False  # another claim bumped attempts

    with db.SessionLocal() as session:
        cancel_job(session, session.get(ProcessingJob, job_id))
        assert heartbeat(session, job_id, attempts) is False


def test_cancel_endpoint_accepts_running_and_still_rejects_finished(client) -> None:
    job_id = _queued_job(client)
    _claim_and_age(job_id, seconds=0.0)
    response = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert _row(job_id).finished_at is not None

    again = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert again.status_code == 409
    assert again.json()["code"] == "JOB_NOT_CANCELABLE"


# --------------------------------------------------------------------------- #
# Worker: canceled / reclaimed mid-run, heartbeat keeps long jobs alive
# --------------------------------------------------------------------------- #


class HookAdapter:
    name = "mock"
    version = "test-hook"
    requires_gpu = False

    def __init__(self, hook) -> None:
        self._hook = hook

    def is_available(self) -> bool:
        return True

    def propose(self, request):
        self._hook()
        if request.progress:
            request.progress(0.5)
        return [ProposedInterval(1.0, 4.0, 0.9, "x")]


def _run_with(worker, monkeypatch, hook) -> None:
    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: HookAdapter(hook))
    assert worker.run_once() is True


def _candidates(job_id: int) -> int:
    with db.SessionLocal() as other:
        video_id = other.get(ProcessingJob, job_id).video_id
        return len(other.scalars(select(Candidate).where(Candidate.video_id == video_id)).all())


def test_cancel_during_run_drops_result(client, worker, monkeypatch) -> None:
    job_id = _queued_job(client)
    _run_with(
        worker,
        monkeypatch,
        lambda: _patch(job_id, status=JobStatus.canceled, finished_at=_now()),
    )
    row = _row(job_id)
    assert row.status == JobStatus.canceled
    assert row.attempts == 1
    assert _candidates(job_id) == 0


def test_stale_worker_after_reclaim_does_not_overwrite(client, worker, monkeypatch) -> None:
    job_id = _queued_job(client)
    _run_with(worker, monkeypatch, lambda: _patch(job_id, attempts=2, progress=0.0))
    row = _row(job_id)
    assert (row.status, row.attempts, row.progress) == (JobStatus.running, 2, 0.0)
    assert _candidates(job_id) == 0


def test_heartbeat_keeps_a_long_silent_job_alive(
    client, settings, app, probe, extractor, monkeypatch
) -> None:
    from app.worker import JobWorker

    job_id = _queued_job(client)
    fast = settings.model_copy(update={"worker_heartbeat_seconds": 0.05})
    worker = JobWorker(fast, storage=app.state.storage, probe=probe, extractor=extractor)
    reaped: list[int] = []

    def long_silent_step() -> None:
        # No progress ticks for 10x the stale window; only the heartbeat thread touches the row.
        for _ in range(10):
            time.sleep(0.05)
            with db.SessionLocal() as other:
                reaped.append(reap_stale_jobs(other, stale_after_seconds=0.15))

    _run_with(worker, monkeypatch, long_silent_step)
    assert reaped == [0] * 10
    row = _row(job_id)
    assert (row.status, row.attempts) == (JobStatus.succeeded, 1)
    assert _candidates(job_id) == 1


def test_reaper_runs_before_claim_in_run_once(client, settings, app, probe, extractor) -> None:
    from app.worker import JobWorker

    job_id = _queued_job(client)
    _claim_and_age(job_id)
    fast = settings.model_copy(update={"worker_heartbeat_seconds": 0.05})
    worker = JobWorker(fast, storage=app.state.storage, probe=probe, extractor=extractor)
    assert worker.run_once() is True  # reaps, then re-claims and completes
    row = _row(job_id)
    assert (row.status, row.attempts) == (JobStatus.succeeded, 2)
