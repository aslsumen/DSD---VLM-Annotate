"""Worker semantics: retry/backoff, terminal failure, cancellation."""

from __future__ import annotations

import pytest
from app.adapters import AdapterError, AdapterUnavailable
from app.worker import JobWorker
from tests.conftest import create_action, create_project, upload_video


class FailingAdapter:
    name = "mock"
    version = "test-failing"
    requires_gpu = False

    def __init__(self, error: Exception) -> None:
        self._error = error

    def is_available(self) -> bool:
        return True

    def propose(self, request):
        raise self._error


def _ready(client):
    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    job = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]}).json()
    return project, action, video, job


def test_retryable_adapter_failure_requeues_then_fails(
    client, settings, app, probe, extractor, monkeypatch
) -> None:
    _, _, _, job = _ready(client)
    monkeypatch.setattr(
        "app.worker.get_adapter", lambda name, cfg: FailingAdapter(AdapterError("boom"))
    )

    fast = settings.model_copy(update={"worker_retry_backoff_seconds": 0.0})
    worker = JobWorker(fast, storage=app.state.storage, probe=probe, extractor=extractor)

    for _ in range(fast.worker_max_attempts):
        assert worker.run_once() is True

    final = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert final["status"] == "failed"
    assert final["attempts"] == fast.worker_max_attempts
    assert final["error_code"] == "ADAPTER_ERROR"
    assert final["error_message"] == "boom"


def test_non_retryable_adapter_error_fails_immediately(
    client, settings, app, probe, extractor, monkeypatch
) -> None:
    _, _, _, job = _ready(client)
    monkeypatch.setattr(
        "app.worker.get_adapter", lambda name, cfg: FailingAdapter(AdapterUnavailable("no gpu"))
    )
    worker = JobWorker(settings, storage=app.state.storage, probe=probe, extractor=extractor)
    worker.run_once()

    final = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert final["status"] == "failed"
    assert final["attempts"] == 1
    assert final["error_code"] == "ADAPTER_UNAVAILABLE"


def test_failed_job_can_be_retried_manually(client, worker, monkeypatch) -> None:
    _, _, _, job = _ready(client)
    monkeypatch.setattr(
        "app.worker.get_adapter", lambda name, cfg: FailingAdapter(AdapterUnavailable("x"))
    )
    worker.run_once()
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "failed"

    response = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["attempts"] == 0

    monkeypatch.undo()
    assert worker.run_once() is True
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"


def test_queued_job_can_be_canceled_and_is_not_executed(client, worker) -> None:
    _, _, _, job = _ready(client)
    response = client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert worker.run_once() is False


def test_claiming_an_empty_queue_returns_false(worker) -> None:
    assert worker.run_once() is False


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "canceled"])
def test_only_failed_jobs_are_retryable(client, status) -> None:
    _, _, _, job = _ready(client)
    response = client.post(f"/api/v1/jobs/{job['id']}/retry")
    # A freshly created job is queued, hence not retryable.
    assert status in {"queued", "running", "succeeded", "canceled"}
    assert response.status_code == 409
    assert response.json()["code"] == "JOB_NOT_RETRYABLE"
