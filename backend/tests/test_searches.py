"""Search fan-out, status aggregation, and role/dataset scoping (S3-06).

Covers the dataset-level search lifecycle: launch a search across a dataset's
ready videos, synchronise per-video SearchVideo status from the processing jobs,
aggregate the parent Search status, and enforce membership-based access.

Section 6 pins the job-lifecycle hooks: a Search must never be left stuck in
``queued``/``running`` when a job is canceled, reaped as stale, retried, or when
the video it was running on is deleted.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from app import db
from app.adapters import AdapterUnavailable
from app.models import (
    Candidate,
    JobStatus,
    ProcessingJob,
    Search,
    SearchStatus,
    SearchVideo,
    SearchVideoStatus,
    Video,
    VideoStatus,
)
from app.services import pipeline
from app.services.pipeline import _now, claim_next_job, fail_job_now, reap_stale_jobs
from sqlalchemy import func, select, update
from tests.conftest import (
    accept_invitation,
    auth_header,
    bootstrap_admin,
    create_dataset,
    invite_user,
    make_video_bytes,
)


class FailingAdapter:
    """Raises a non-retryable adapter error, so a job fails on its first attempt."""

    name = "mock"
    version = "test-failing"
    requires_gpu = False

    def is_available(self) -> bool:
        return True

    def propose(self, request):
        raise AdapterUnavailable("no gpu")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _create_dev_dataset(client, name: str = "Search dataset") -> dict:
    response = client.post("/api/v1/datasets", json={"name": name, "description": "fixture"})
    assert response.status_code == 201, response.text
    return response.json()


def _upload_dataset_video(client, dataset_id: int, filename: str = "clip.mp4") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/videos",
        files={"file": (filename, make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_dataset_video_auth(client, dataset_id: int, token: str, filename: str = "clip.mp4") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/videos",
        files={"file": (filename, make_video_bytes(), "video/mp4")},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _launch_search(client, dataset_id: int, *, prompt: str = "a person waves at the camera") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/searches", json={"prompt": prompt}
    )
    assert response.status_code == 202, response.text
    return response.json()


def _launch_search_auth(client, dataset_id: int, token: str, *, prompt: str = "a person waves") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/searches",
        json={"prompt": prompt},
        headers=auth_header(token),
    )
    assert response.status_code == 202, response.text
    return response.json()


def _insert_uploaded_video(dataset_id: int) -> int:
    """Insert a video row that has not been probed yet (status=uploaded)."""
    with db.SessionLocal() as session:
        video = Video(
            dataset_id=dataset_id,
            project_id=None,
            original_filename="pending.mp4",
            storage_key=f"videos/dataset-{dataset_id}/pending-{uuid.uuid4().hex}.mp4",
            content_type="video/mp4",
            size_bytes=100,
            checksum_sha256="0" * 64,
            status=VideoStatus.uploaded,
        )
        session.add(video)
        session.commit()
        session.refresh(video)
        return video.id


def _job_by_video(search_id: int) -> dict[int, int]:
    """Map video_id -> ProcessingJob.id for the SearchVideo rows of one search."""
    with db.SessionLocal() as session:
        rows = session.execute(
            select(SearchVideo.video_id, SearchVideo.job_id).where(
                SearchVideo.search_id == search_id
            )
        ).all()
    return {video_id: job_id for video_id, job_id in rows}


def _claim_and_age(job_id: int, *, attempts: int | None = None) -> None:
    """Claim the next queued job, then age its lease so the reaper sees it as stale.

    ``attempts`` is forced in the same UPDATE that ages ``updated_at``, because
    ``onupdate=utcnow`` would otherwise undo a separate attempts-only patch.
    """
    with db.SessionLocal() as session:
        assert claim_next_job(session).id == job_id
    values: dict[str, object] = {"updated_at": _now() - timedelta(seconds=100)}
    if attempts is not None:
        values["attempts"] = attempts
    with db.SessionLocal() as other:
        other.execute(
            update(ProcessingJob).where(ProcessingJob.id == job_id).values(**values)
        )
        other.commit()


def _job_row(job_id: int) -> ProcessingJob:
    with db.SessionLocal() as other:
        return other.get(ProcessingJob, job_id)


def _search_detail(client, search_id: int) -> dict:
    response = client.get(f"/api/v1/searches/{search_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _mark_search_running(search_id: int, video_id: int) -> None:
    """Put a Search and one of its videos in the state a worker leaves mid-run.

    This is what makes the lifecycle tests regression tests: before the fix a
    canceled, reaped or deleted job left the SearchVideo stuck in ``running`` and
    the parent Search stuck in ``running`` forever.
    """
    with db.SessionLocal() as session:
        session.execute(
            update(SearchVideo)
            .where(
                SearchVideo.search_id == search_id, SearchVideo.video_id == video_id
            )
            .values(status=SearchVideoStatus.running)
        )
        session.execute(
            update(Search).where(Search.id == search_id).values(status=SearchStatus.running)
        )
        session.commit()


def _search_with_two_videos(client, name: str = "Consistency"):
    """Create a dataset with two ready videos and launch a search over them."""
    dataset = _create_dev_dataset(client, name)
    video_ids = [
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")["id"]
        for index in range(2)
    ]
    search = _launch_search(client, dataset["id"])
    return dataset, search, video_ids


def _finish_video(job_id: int) -> None:
    """Complete one video the way ``execute_job`` does: commit both rows, then derive."""
    with db.SessionLocal() as session:
        search_video = session.scalar(
            select(SearchVideo).where(SearchVideo.job_id == job_id)
        )
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(status=JobStatus.succeeded, progress=1.0, finished_at=_now())
            .execution_options(synchronize_session=False)
        )
        search_video.status = SearchVideoStatus.done
        search_video.error_message = None
        session.commit()
        pipeline._settle_search_status(session, search_video.search_id)


def _count_rows(model) -> int:
    with db.SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------- #
# 1. Fan-out execution
# --------------------------------------------------------------------------- #


def test_fan_out_skips_unready_videos_and_populates_search_id(client, worker) -> None:
    dataset = _create_dev_dataset(client)
    ready_ids = [
        _upload_dataset_video(client, dataset["id"], f"ready-{index}.mp4")["id"]
        for index in range(3)
    ]
    _insert_uploaded_video(dataset["id"])

    search = _launch_search(client, dataset["id"])
    assert search["status"] == "queued"
    assert search["total_videos"] == 3
    assert search["queued_videos"] == 3

    # Exactly one Search and three SearchVideo rows; the uploaded video is skipped.
    with db.SessionLocal() as session:
        assert len(session.scalars(select(Search)).all()) == 1
        rows = list(
            session.scalars(
                select(SearchVideo).where(SearchVideo.search_id == search["id"])
            )
        )
        assert len(rows) == 3
        assert {row.video_id for row in rows} == set(ready_ids)

    # Drain the three queued jobs through the mock detector.
    for _ in range(3):
        assert worker.run_once() is True

    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "done"
    assert detail["done_videos"] == 3
    assert detail["finished_at"] is not None

    candidates = client.get(f"/api/v1/searches/{search['id']}/candidates").json()
    assert len(candidates) >= 9  # 3 videos x at least 3 candidates each
    assert {candidate["video_id"] for candidate in candidates} == set(ready_ids)
    for candidate in candidates:
        assert candidate["search_id"] == search["id"]


def test_fan_out_filters_to_requested_videos_and_auto_titles(client) -> None:
    dataset = _create_dev_dataset(client)
    first = _upload_dataset_video(client, dataset["id"], "a.mp4")["id"]
    second = _upload_dataset_video(client, dataset["id"], "b.mp4")["id"]
    _upload_dataset_video(client, dataset["id"], "c.mp4")

    prompt = "detect " + "a person waving at the camera " * 8
    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": prompt, "video_ids": [first, second]},
    )
    assert response.status_code == 202, response.text
    search = response.json()
    assert search["total_videos"] == 2
    assert {video["video_id"] for video in search["videos"]} == {first, second}
    assert search["title"] is not None
    assert len(search["title"]) <= 60
    assert prompt.startswith(search["title"])


def test_fan_out_rejects_video_not_in_dataset(client) -> None:
    dataset = _create_dev_dataset(client)
    first = _upload_dataset_video(client, dataset["id"], "a.mp4")["id"]
    other = _create_dev_dataset(client, "Other dataset")
    outsider = _upload_dataset_video(client, other["id"], "b.mp4")["id"]

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "x", "video_ids": [first, outsider]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VIDEOS_NOT_IN_DATASET"


def test_empty_video_ids_is_rejected_instead_of_queuing_every_video(client) -> None:
    """An explicit empty list is a caller mistake, not "use every ready video"."""
    dataset = _create_dev_dataset(client)
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"clip-{index}.mp4")

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "x", "video_ids": []},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

    # Nothing may be queued: the request is rejected before the endpoint body runs.
    with db.SessionLocal() as session:
        assert list(session.scalars(select(Search))) == []
        assert list(session.scalars(select(SearchVideo))) == []


def test_search_on_dataset_without_ready_videos_is_done(client) -> None:
    dataset = _create_dev_dataset(client)
    search = _launch_search(client, dataset["id"])
    assert search["status"] == "done"
    assert search["total_videos"] == 0
    assert search["finished_at"] is not None


# --------------------------------------------------------------------------- #
# 2. Status aggregation and partial results
# --------------------------------------------------------------------------- #


def test_status_aggregation_transitions(client, worker) -> None:
    dataset = _create_dev_dataset(client)
    for index in range(3):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])

    # queued immediately after creation.
    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "queued"
    assert detail["queued_videos"] == 3

    # running once one video finishes and two remain queued.
    assert worker.run_once() is True
    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "running"
    assert detail["done_videos"] == 1
    assert detail["queued_videos"] == 2

    # done once all three succeed (finished_at populated).
    assert worker.run_once() is True
    assert worker.run_once() is True
    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "done"
    assert detail["done_videos"] == 3
    assert detail["finished_at"] is not None


def test_partial_search_when_one_video_fails(client, worker, monkeypatch) -> None:
    dataset = _create_dev_dataset(client)
    for index in range(3):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])

    # Two videos succeed...
    assert worker.run_once() is True
    assert worker.run_once() is True

    # ...the third fails non-retryably.
    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    assert worker.run_once() is True

    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "partial"
    assert detail["done_videos"] == 2
    assert detail["failed_videos"] == 1
    assert detail["finished_at"] is not None

    failed = [video for video in detail["videos"] if video["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error_message"] == "no gpu"


def test_failed_search_when_all_videos_fail(client, worker, monkeypatch) -> None:
    dataset = _create_dev_dataset(client)
    for index in range(3):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])

    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    for _ in range(3):
        assert worker.run_once() is True

    detail = client.get(f"/api/v1/searches/{search['id']}").json()
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 3
    assert detail["finished_at"] is not None
    assert all(video["status"] == "failed" for video in detail["videos"])
    assert all(video["error_message"] == "no gpu" for video in detail["videos"])


# --------------------------------------------------------------------------- #
# 3. Role and dataset scoping
# --------------------------------------------------------------------------- #


def test_annotator_member_can_read_but_not_launch(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    admin_token = admin["access_token"]

    dataset = create_dataset(auth_client, admin_token, "Scoped dataset")
    invitation = invite_user(auth_client, admin_token, "annotator@example.com")
    annotator = accept_invitation(auth_client, invitation["token"], "Ana Annotator")
    annotator_token = annotator["access_token"]

    added = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"user_id": annotator["user"]["id"]},
        headers=auth_header(admin_token),
    )
    assert added.status_code == 201

    _upload_dataset_video_auth(auth_client, dataset["id"], admin_token)
    search = _launch_search_auth(auth_client, dataset["id"], admin_token)

    # A member annotator can read the search and its candidates.
    read = auth_client.get(
        f"/api/v1/searches/{search['id']}", headers=auth_header(annotator_token)
    )
    assert read.status_code == 200, read.text
    candidates = auth_client.get(
        f"/api/v1/searches/{search['id']}/candidates",
        headers=auth_header(annotator_token),
    )
    assert candidates.status_code == 200

    # ...but cannot launch a search (role gate fires first).
    forbidden = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "another prompt"},
        headers=auth_header(annotator_token),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


def test_non_member_cannot_view_or_launch(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    admin_token = admin["access_token"]

    dataset = create_dataset(auth_client, admin_token, "Secret dataset")
    _upload_dataset_video_auth(auth_client, dataset["id"], admin_token)
    search = _launch_search_auth(auth_client, dataset["id"], admin_token)

    dadmin_invite = invite_user(
        auth_client, admin_token, "outsider-dadmin@example.com", role="dataset_admin"
    )
    dadmin = accept_invitation(auth_client, dadmin_invite["token"], "Outsider DAdmin")
    dadmin_token = dadmin["access_token"]

    anon_invite = invite_user(auth_client, admin_token, "outsider-annotator@example.com")
    anon = accept_invitation(auth_client, anon_invite["token"], "Outsider Annotator")
    anon_token = anon["access_token"]

    # Viewing hides the dataset's existence from any non-member: 404 for both.
    for token in (dadmin_token, anon_token):
        read = auth_client.get(
            f"/api/v1/searches/{search['id']}", headers=auth_header(token)
        )
        assert read.status_code == 404
        assert read.json()["code"] == "DATASET_NOT_FOUND"

        candidates = auth_client.get(
            f"/api/v1/searches/{search['id']}/candidates", headers=auth_header(token)
        )
        assert candidates.status_code == 404

    # Launching: dataset_admin passes the role gate, then fails the access check -> 404.
    dadmin_launch = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "x"},
        headers=auth_header(dadmin_token),
    )
    assert dadmin_launch.status_code == 404

    # Launching: annotator fails the role gate first -> 403 (not 404).
    anon_launch = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "x"},
        headers=auth_header(anon_token),
    )
    assert anon_launch.status_code == 403
    assert anon_launch.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# 4. Listing a dataset's searches
# --------------------------------------------------------------------------- #


def test_list_searches_is_scoped_to_the_dataset_and_counts_videos(client) -> None:
    mine = _create_dev_dataset(client, "Mine")
    other = _create_dev_dataset(client, "Other")
    for index in range(2):
        _upload_dataset_video(client, mine["id"], f"mine-{index}.mp4")
    _upload_dataset_video(client, other["id"], "other.mp4")

    first = _launch_search(client, mine["id"], prompt="first prompt")
    second = _launch_search(client, mine["id"], prompt="second prompt")
    _launch_search(client, other["id"], prompt="not mine")

    response = client.get(f"/api/v1/datasets/{mine['id']}/searches")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [row["id"] for row in body] == [second["id"], first["id"]]  # newest first
    assert all(row["dataset_id"] == mine["id"] for row in body)
    assert body[0]["total_videos"] == 2
    assert body[0]["queued_videos"] == 2
    assert body[0]["done_videos"] == 0
    # A list row is a SearchOut: it must not pretend each search has zero videos.
    assert "videos" not in body[0]


def test_list_searches_pages_and_filters_by_status(client) -> None:
    dataset = _create_dev_dataset(client, "Paged")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    searches = [
        _launch_search(client, dataset["id"], prompt=f"prompt {index}")
        for index in range(3)
    ]

    limited = client.get(f"/api/v1/datasets/{dataset['id']}/searches?limit=2").json()
    assert len(limited) == 2
    offset = client.get(f"/api/v1/datasets/{dataset['id']}/searches?limit=2&offset=2").json()
    assert [row["id"] for row in offset] == [searches[0]["id"]]

    queued = client.get(f"/api/v1/datasets/{dataset['id']}/searches?status=queued").json()
    assert len(queued) == 3
    done = client.get(f"/api/v1/datasets/{dataset['id']}/searches?status=done").json()
    assert done == []


def test_list_searches_on_empty_dataset_and_unknown_dataset(client) -> None:
    empty = _create_dev_dataset(client, "Empty")
    response = client.get(f"/api/v1/datasets/{empty['id']}/searches")
    assert response.status_code == 200
    assert response.json() == []

    missing = client.get("/api/v1/datasets/9999/searches")
    assert missing.status_code == 404
    assert missing.json()["code"] == "DATASET_NOT_FOUND"


def test_list_searches_respects_membership(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    admin_token = admin["access_token"]
    dataset = create_dataset(auth_client, admin_token, "Listed dataset")
    _upload_dataset_video_auth(auth_client, dataset["id"], admin_token)
    _launch_search_auth(auth_client, dataset["id"], admin_token)

    invitation = invite_user(auth_client, admin_token, "lister@example.com")
    annotator = accept_invitation(auth_client, invitation["token"], "Lee Lister")
    annotator_token = annotator["access_token"]

    # Non-member: the dataset's existence is hidden.
    denied = auth_client.get(
        f"/api/v1/datasets/{dataset['id']}/searches",
        headers=auth_header(annotator_token),
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "DATASET_NOT_FOUND"

    auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"user_id": annotator["user"]["id"]},
        headers=auth_header(admin_token),
    )
    allowed = auth_client.get(
        f"/api/v1/datasets/{dataset['id']}/searches",
        headers=auth_header(annotator_token),
    )
    assert allowed.status_code == 200
    assert len(allowed.json()) == 1


# --------------------------------------------------------------------------- #
# 5. Idempotency-Key on search creation
# --------------------------------------------------------------------------- #


def test_idempotency_key_replays_the_same_search(client) -> None:
    dataset = _create_dev_dataset(client, "Idempotent")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"clip-{index}.mp4")
    headers = {"Idempotency-Key": "search-once-1"}
    payload = {"prompt": "a dog runs in the snow"}

    first = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)
    second = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["total_videos"] == 2

    with db.SessionLocal() as session:
        assert len(list(session.scalars(select(Search)))) == 1
        assert len(list(session.scalars(select(SearchVideo)))) == 2
        assert len(list(session.scalars(select(ProcessingJob)))) == 2


def test_different_idempotency_keys_create_separate_searches(client) -> None:
    dataset = _create_dev_dataset(client, "Distinct")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    payload = {"prompt": "same prompt"}

    first = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json=payload,
        headers={"Idempotency-Key": "key-a"},
    )
    second = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json=payload,
        headers={"Idempotency-Key": "key-b"},
    )

    assert first.json()["id"] != second.json()["id"]
    with db.SessionLocal() as session:
        assert len(list(session.scalars(select(Search)))) == 2
        assert len(list(session.scalars(select(ProcessingJob)))) == 2


def test_idempotency_key_reuse_with_different_payload_conflicts(client) -> None:
    dataset = _create_dev_dataset(client, "Conflict")
    videos = [
        _upload_dataset_video(client, dataset["id"], f"clip-{index}.mp4")["id"]
        for index in range(2)
    ]
    headers = {"Idempotency-Key": "reused-key"}

    created = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "first prompt", "video_ids": videos},
        headers=headers,
    )
    assert created.status_code == 202

    other_prompt = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "second prompt", "video_ids": videos},
        headers=headers,
    )
    assert other_prompt.status_code == 409
    assert other_prompt.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    other_videos = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "first prompt", "video_ids": [videos[0]]},
        headers=headers,
    )
    assert other_videos.status_code == 409
    assert other_videos.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    with db.SessionLocal() as session:
        assert len(list(session.scalars(select(Search)))) == 1


def test_idempotency_key_longer_than_100_is_rejected(client) -> None:
    dataset = _create_dev_dataset(client, "Too long")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "x"},
        headers={"Idempotency-Key": "k" * 101},
    )
    assert response.status_code == 422
    with db.SessionLocal() as session:
        assert list(session.scalars(select(Search))) == []


def test_idempotent_replay_reports_current_status(client, worker) -> None:
    dataset = _create_dev_dataset(client, "Replay status")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    headers = {"Idempotency-Key": "replay-status"}
    payload = {"prompt": "a cat sleeps"}

    first = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)
    assert first.status_code == 202
    assert worker.run_once() is True

    replay = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)
    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["status"] == "done"
    assert replay.json()["done_videos"] == 1
    assert replay.json()["queued_videos"] == 0


def test_idempotency_key_ignores_video_scope_when_videos_omitted(client) -> None:
    dataset = _create_dev_dataset(client, "Growing")
    _upload_dataset_video(client, dataset["id"], "first.mp4")
    headers = {"Idempotency-Key": "growing-dataset"}
    payload = {"prompt": "a boat sails"}

    first = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)
    assert first.status_code == 202
    # A new video appears after the original request.
    _upload_dataset_video(client, dataset["id"], "second.mp4")

    replay = client.post(f"/api/v1/datasets/{dataset['id']}/searches", json=payload, headers=headers)
    assert replay.status_code == 202, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["total_videos"] == 1


# --------------------------------------------------------------------------- #
# 6. Job lifecycle: canceled, reaped, retried, and deleted-video jobs
# --------------------------------------------------------------------------- #


def test_cancel_job_marks_the_video_failed_and_reason_is_kept(client, worker) -> None:
    dataset = _create_dev_dataset(client, "Cancel one")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])
    jobs = _job_by_video(search["id"])

    # A worker claimed the job and is running it, so the video is ``running``
    # too -- that is the state that used to stay stuck after a cancel.
    with db.SessionLocal() as session:
        claimed = claim_next_job(session)
    assert claimed is not None
    canceled_video = next(video_id for video_id, job_id in jobs.items() if job_id == claimed.id)
    _mark_search_running(search["id"], canceled_video)
    assert _search_detail(client, search["id"])["status"] == "running"

    response = client.post(f"/api/v1/jobs/{jobs[canceled_video]}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "canceled"

    detail = _search_detail(client, search["id"])
    # One video failed, one is still queued: the search is not stuck in running
    # and it is not finished yet either.
    assert detail["status"] == "running"
    assert detail["failed_videos"] == 1
    assert detail["queued_videos"] == 1
    assert detail["finished_at"] is None
    canceled_row = next(row for row in detail["videos"] if row["video_id"] == canceled_video)
    assert canceled_row["status"] == "failed"
    assert canceled_row["error_message"] == "Job canceled"

    # The surviving job finishing settles the search as partial.
    assert worker.run_once() is True
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "partial"
    assert detail["done_videos"] == 1
    assert detail["failed_videos"] == 1
    assert detail["finished_at"] is not None


def test_canceling_every_video_fails_the_search_with_the_cancel_reason(client) -> None:
    dataset = _create_dev_dataset(client, "Cancel all")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])

    for job_id in _job_by_video(search["id"]).values():
        assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 200

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 2
    assert detail["finished_at"] is not None
    assert detail["error_message"] == "Job canceled"
    assert all(row["error_message"] == "Job canceled" for row in detail["videos"])


def test_reaped_job_requeues_its_search_video_instead_of_leaving_it_running(client) -> None:
    dataset = _create_dev_dataset(client, "Reap requeue")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    video_id, job_id = next(iter(_job_by_video(search["id"]).items()))

    _claim_and_age(job_id)
    _mark_search_running(search["id"], video_id)
    assert _search_detail(client, search["id"])["status"] == "running"

    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, stale_after_seconds=30) == 1

    assert _job_row(job_id).status == JobStatus.queued
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "queued"
    assert detail["queued_videos"] == 1
    assert detail["running_videos"] == 0
    assert detail["finished_at"] is None
    assert detail["videos"][0]["error_message"] is None

    # The requeued job is claimable again.
    with db.SessionLocal() as session:
        assert claim_next_job(session).id == job_id


def test_reaped_job_with_exhausted_attempts_fails_the_search(client) -> None:
    dataset = _create_dev_dataset(client, "Reap exhausted")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    job_id = next(iter(_job_by_video(search["id"]).values()))

    row = _job_row(job_id)
    _claim_and_age(job_id, attempts=row.max_attempts)
    _mark_search_running(search["id"], next(iter(_job_by_video(search["id"]))))
    with db.SessionLocal() as session:
        assert reap_stale_jobs(session, stale_after_seconds=30) == 1

    assert _job_row(job_id).status == JobStatus.failed
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 1
    assert detail["finished_at"] is not None
    assert "attempts exhausted" in detail["error_message"]
    assert "attempts exhausted" in detail["videos"][0]["error_message"]


def test_retry_reopens_the_search_video_and_the_search(client, worker, monkeypatch) -> None:
    dataset = _create_dev_dataset(client, "Retry")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    job_id = next(iter(_job_by_video(search["id"]).values()))

    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    assert worker.run_once() is True
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["error_message"] == "no gpu"

    retried = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retried.status_code == 202, retried.text

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "queued"
    assert detail["queued_videos"] == 1
    assert detail["failed_videos"] == 0
    assert detail["finished_at"] is None
    assert detail["error_message"] is None
    assert detail["videos"][0]["status"] == "queued"
    assert detail["videos"][0]["error_message"] is None


def test_deleting_a_running_video_recomputes_the_search(client) -> None:
    dataset = _create_dev_dataset(client, "Delete running")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")
    search = _launch_search(client, dataset["id"])
    jobs = _job_by_video(search["id"])
    running_video = min(jobs)

    # Put the search in the state a worker produces when it starts a job:
    # SearchVideo and the parent Search are both ``running``.
    _mark_search_running(search["id"], running_video)
    assert _search_detail(client, search["id"])["status"] == "running"

    response = client.delete(f"/api/v1/videos/{running_video}")
    assert response.status_code == 204, response.text

    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 1
    assert detail["status"] == "queued"
    assert detail["running_videos"] == 0
    assert all(row["video_id"] != running_video for row in detail["videos"])
    with db.SessionLocal() as session:
        rows = list(
            session.scalars(select(SearchVideo).where(SearchVideo.video_id == running_video))
        )
    assert rows == []


def test_deleting_every_video_settles_a_running_search_as_done(client) -> None:
    dataset = _create_dev_dataset(client, "Delete all")
    video_ids = [
        _upload_dataset_video(client, dataset["id"], f"v{index}.mp4")["id"] for index in range(2)
    ]
    search = _launch_search(client, dataset["id"])
    # Nobody will ever finish these jobs, so only the delete path can settle the
    # search. Before the fix the SearchVideo rows were left behind and the search
    # stayed ``running`` forever.
    _mark_search_running(search["id"], video_ids[0])
    assert _search_detail(client, search["id"])["status"] == "running"

    for video_id in video_ids:
        assert client.delete(f"/api/v1/videos/{video_id}").status_code == 204

    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 0
    assert detail["videos"] == []
    assert detail["status"] == "done"
    assert detail["finished_at"] is not None
    assert detail["error_message"] is None


def test_concurrent_completion_settles_the_search(client, monkeypatch) -> None:
    """The aggregate must be derived from committed rows, not a pre-write snapshot.

    Two workers can finish the last two videos of one search at the same time.
    If a worker derives the aggregate *before* committing its own SearchVideo
    row, its peer derives from a snapshot in which the other video still looks
    ``running``: both write ``running`` and nothing ever re-derives the search.
    So the invariant is "commit the row, then derive" — asserted here by
    inspecting, from an independent session at the moment of derivation, whether
    the worker's own row is already visible.
    """
    dataset = _create_dev_dataset(client, "Concurrent completion")
    video_ids = [
        _upload_dataset_video(client, dataset["id"], f"c{index}.mp4")["id"]
        for index in range(2)
    ]
    search = _launch_search(client, dataset["id"])
    jobs = _job_by_video(search["id"])
    assert len(jobs) == 2

    job_id = jobs[video_ids[0]]
    observed: list[set[SearchVideoStatus]] = []
    original = pipeline._recompute_search_status

    def spy(session, search_id):
        # A peer worker's session, opening a brand-new transaction right now.
        with db.SessionLocal() as peer:
            rows = list(
                peer.scalars(
                    select(SearchVideo).where(SearchVideo.search_id == search_id)
                )
            )
            observed.append({row.status for row in rows})
        return original(session, search_id)

    monkeypatch.setattr(pipeline, "_recompute_search_status", spy)

    _finish_video(job_id)

    # At every derivation the row just written was already committed and visible
    # to a peer, so a concurrent worker cannot miss it.
    assert observed, "the aggregate was never derived"
    assert all(SearchVideoStatus.done in seen for seen in observed)

    # Finish the second video and confirm the search settles.
    _finish_video(jobs[video_ids[1]])

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "done"
    assert detail["done_videos"] == 2
    assert detail["finished_at"] is not None


# --------------------------------------------------------------------------- #
# 7. Job / SearchVideo / Search consistency across a crash or an interruption
# --------------------------------------------------------------------------- #


def test_execute_job_does_not_resurrect_a_canceled_video(client, worker) -> None:
    """A cancel that lands between the claim and the start must stick.

    ``execute_job`` used to paint the SearchVideo "running" before checking that it
    still owned the job, so a cancel in that window was overwritten and the search
    hung in ``running`` with nothing left to finish it.
    """
    _, search, video_ids = _search_with_two_videos(client)
    job_id = _job_by_video(search["id"])[video_ids[0]]

    with db.SessionLocal() as session:
        claimed = claim_next_job(session)
        assert claimed is not None and claimed.id == job_id
        # Exactly what POST /jobs/{id}/cancel does, one moment after the claim.
        pipeline.cancel_job(session, claimed)

    assert _job_row(job_id).status == JobStatus.canceled

    with db.SessionLocal() as session:
        pipeline.execute_job(
            session,
            job_id,
            storage=worker.storage,
            probe=worker.probe,
            extractor=worker.extractor,
            adapter=FailingAdapter(),
            settings=worker.settings,
        )

    assert _job_row(job_id).status == JobStatus.canceled

    detail = _search_detail(client, search["id"])
    assert detail["running_videos"] == 0
    canceled = next(row for row in detail["videos"] if row["video_id"] == video_ids[0])
    assert canceled["status"] == "failed"
    assert canceled["error_message"] == "Job canceled"
    # The other video is still queued, so the search itself is legitimately in
    # progress; what matters is that the canceled video was not flipped back.
    assert detail["queued_videos"] == 1


def test_reconcile_repairs_a_video_left_running_by_a_crashed_job(client) -> None:
    """Drift written by an older build is repaired from the job, the source of truth."""
    _, search, video_ids = _search_with_two_videos(client)
    jobs = _job_by_video(search["id"])

    # What the old code left behind: both jobs succeeded, but the row of the
    # first one still says "running", so the search stays "running" forever.
    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id.in_(list(jobs.values())))
            .values(status=JobStatus.succeeded, progress=1.0, finished_at=_now())
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == jobs[video_ids[0]])
            .values(status=SearchVideoStatus.running)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == jobs[video_ids[1]])
            .values(status=SearchVideoStatus.done)
        )
        session.execute(
            update(Search).where(Search.id == search["id"]).values(status=SearchStatus.running)
        )
        session.commit()

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) >= 1

    detail = _search_detail(client, search["id"])
    assert detail["done_videos"] == 2
    assert detail["running_videos"] == 0
    assert detail["status"] == "done"
    assert detail["finished_at"] is not None


def test_reconcile_settles_a_search_whose_videos_all_finished(client) -> None:
    """A kill between the child commit and the aggregate commit leaves only the Search stale.

    ``execute_job`` commits the job and its ``SearchVideo`` first and derives the parent
    afterwards, so this window is real: both rows say ``done`` while the ``Search`` still
    says ``running``.  ``reap_stale_jobs`` ignores it (no job is stale any more), which is
    exactly why the worker runs this sweep on every tick.  The sweep must also report the
    repair, or a caller would take the torn database for a clean one.
    """
    _, search, _ = _search_with_two_videos(client)
    jobs = _job_by_video(search["id"])

    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id.in_(list(jobs.values())))
            .values(status=JobStatus.succeeded, progress=1.0, finished_at=_now())
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id.in_(list(jobs.values())))
            .values(status=SearchVideoStatus.done, error_message=None)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(Search)
            .where(Search.id == search["id"])
            .values(status=SearchStatus.running, finished_at=None)
        )
        session.commit()

    # The torn state: every video finished, the aggregate never derived.
    detail = _search_detail(client, search["id"])
    assert detail["done_videos"] == 2
    assert detail["status"] == "running"

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) == 1

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "done"
    assert detail["finished_at"] is not None
    assert detail["error_message"] is None

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) == 0


def test_reconcile_repairs_a_requeued_job_and_settles_an_idle_search(client) -> None:
    """A retried job whose row still says "failed" goes back to "queued".

    Neither video is running, so a Search stuck at ``running`` is stale as well:
    the sweep has to fix both the row and the aggregate in one pass.
    """
    _, search, video_ids = _search_with_two_videos(client)
    job_id = _job_by_video(search["id"])[video_ids[0]]

    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(status=JobStatus.queued, attempts=0, finished_at=None)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == job_id)
            .values(status=SearchVideoStatus.failed, error_message="stale failure")
            .execution_options(synchronize_session=False)
        )
        # Stale aggregate: nothing is running, yet the Search says it is.
        session.execute(
            update(Search)
            .where(Search.id == search["id"])
            .values(status=SearchStatus.running, finished_at=None)
        )
        session.commit()

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) >= 1

    with db.SessionLocal() as session:
        row = session.scalar(select(SearchVideo).where(SearchVideo.job_id == job_id))
    assert row.status == SearchVideoStatus.queued
    assert row.error_message is None

    detail = _search_detail(client, search["id"])
    assert detail["queued_videos"] == 2
    assert detail["failed_videos"] == 0
    assert detail["running_videos"] == 0
    assert detail["status"] == "queued"
    assert detail["finished_at"] is None

    # Reconcile is idempotent: a second sweep changes nothing.
    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) == 0


def test_reconcile_does_not_overwrite_a_newer_result(client, monkeypatch) -> None:
    """A repair must re-check its observation, or it drags a finished video back.

    The sweep reads a page of drifted rows and writes them in one transaction, so a
    worker can finish one of those videos in between.  Applying the stale
    observation would put the row -- and, through the aggregate, the whole Search --
    back from ``done`` to ``running``.
    """
    _, search, video_ids = _search_with_two_videos(client)
    jobs = _job_by_video(search["id"])
    stale_job = jobs[video_ids[0]]

    # The torn state: both jobs succeeded, but the first row still says "running".
    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id.in_(list(jobs.values())))
            .values(status=JobStatus.succeeded, progress=1.0, finished_at=_now())
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == stale_job)
            .values(status=SearchVideoStatus.running)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == jobs[video_ids[1]])
            .values(status=SearchVideoStatus.done)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(Search).where(Search.id == search["id"]).values(status=SearchStatus.running)
        )
        session.commit()

    real_repair = pipeline._repair_drifted_search_video
    state = {"raced": False}

    def a_worker_finishes_it_first(session, **kwargs):
        if not state["raced"]:
            state["raced"] = True
            # A worker completes the very video this sweep is about to repaint.
            with db.SessionLocal() as peer:
                peer.execute(
                    update(SearchVideo)
                    .where(SearchVideo.id == kwargs["row_id"])
                    .values(status=SearchVideoStatus.done, error_message=None)
                    .execution_options(synchronize_session=False)
                )
                peer.commit()
                pipeline._settle_search_status(peer, search["id"])
        return real_repair(session, **kwargs)

    monkeypatch.setattr(
        pipeline, "_repair_drifted_search_video", a_worker_finishes_it_first
    )

    with db.SessionLocal() as session:
        pipeline.reconcile_search_state(session)

    assert state["raced"] is True
    # The newer result won: the sweep noticed its observation no longer held.
    detail = _search_detail(client, search["id"])
    assert detail["done_videos"] == 2
    assert detail["running_videos"] == 0
    assert detail["status"] == "done"

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) == 0


def test_reconcile_settles_a_parent_left_failed_by_an_interrupted_retry(client) -> None:
    """A terminal Search with a restarted video is drift, even if the child is fine.

    ``retry_search`` commits the replacement job and its row before it settles the
    aggregate, so a kill in between leaves ``failed`` on a Search whose only video is
    ``queued`` again.  The child already matches its job, so nothing else in the sweep
    sees it -- and a caller would be told the database was consistent.
    """
    dataset = _create_dev_dataset(client, "Interrupted retry")
    video = _upload_dataset_video(client, dataset["id"], "retry.mp4")
    search = _launch_search(client, dataset["id"])
    job_id = _job_by_video(search["id"])[video["id"]]

    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(
                status=JobStatus.queued,
                attempts=0,
                progress=0.0,
                error_code=None,
                error_message=None,
                finished_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id == job_id)
            .values(status=SearchVideoStatus.queued, error_message=None)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(Search)
            .where(Search.id == search["id"])
            .values(
                status=SearchStatus.failed,
                finished_at=_now(),
                error_message="Job canceled",
            )
        )
        session.commit()

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) >= 1

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "queued"
    assert detail["queued_videos"] == 1
    assert detail["failed_videos"] == 0
    assert detail["finished_at"] is None
    assert detail["error_message"] is None

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) == 0


def test_reconcile_still_repairs_other_rows_after_a_skipped_observation(
    client, monkeypatch
) -> None:
    """One stale observation must not stop the sweep repairing the rest of the page."""
    _, search, video_ids = _search_with_two_videos(client)
    jobs = _job_by_video(search["id"])
    raced_job = jobs[video_ids[0]]
    other_job = jobs[video_ids[1]]

    # Both rows disagree with their jobs: each still says "running".
    with db.SessionLocal() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id.in_(list(jobs.values())))
            .values(status=JobStatus.succeeded, progress=1.0, finished_at=_now())
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(SearchVideo)
            .where(SearchVideo.job_id.in_(list(jobs.values())))
            .values(status=SearchVideoStatus.running)
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(Search).where(Search.id == search["id"]).values(status=SearchStatus.running)
        )
        session.commit()

    real_repair = pipeline._repair_drifted_search_video

    def a_worker_completes_the_first_one(session, **kwargs):
        if kwargs["job_id"] == raced_job:
            with db.SessionLocal() as peer:
                peer.execute(
                    update(SearchVideo)
                    .where(SearchVideo.id == kwargs["row_id"])
                    .values(status=SearchVideoStatus.done)
                    .execution_options(synchronize_session=False)
                )
                peer.commit()
        return real_repair(session, **kwargs)

    monkeypatch.setattr(
        pipeline, "_repair_drifted_search_video", a_worker_completes_the_first_one
    )

    with db.SessionLocal() as session:
        assert pipeline.reconcile_search_state(session) >= 1

    with db.SessionLocal() as session:
        rows = {row.job_id: row.status for row in session.scalars(select(SearchVideo))}
    assert rows[raced_job] == SearchVideoStatus.done
    assert rows[other_job] == SearchVideoStatus.done

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "done"
    assert detail["done_videos"] == 2


# --------------------------------------------------------------------------- #
# 8. Video deletion: one transaction with the search settle, and a clean cascade
# --------------------------------------------------------------------------- #


def test_video_delete_rolls_back_with_its_search_settle(client, monkeypatch) -> None:
    """A failure after the settle must leave the video, its job and its row in place.

    Before the fix ``refresh_searches_for_video`` committed the row removals and the
    derived status itself, so a crash before the ``Video`` delete was durable: the
    video and its job survived while the search already claimed to be ``done`` with
    zero videos.
    """
    from app.api import videos as videos_api

    dataset = _create_dev_dataset(client)
    video = _upload_dataset_video(client, dataset["id"], "only.mp4")
    search = _launch_search(client, dataset["id"])
    job_id = search["videos"][0]["job_id"]

    real_refresh = videos_api.refresh_searches_for_video

    def boom(session, video_id, *, commit=True):
        real_refresh(session, video_id, commit=False)
        raise RuntimeError("simulated crash between the settle and the delete")

    monkeypatch.setattr(videos_api, "refresh_searches_for_video", boom)

    with pytest.raises(RuntimeError):
        client.delete(f"/api/v1/videos/{video['id']}")

    # Everything the request touched is still there after the session is gone.
    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is not None
        assert session.get(ProcessingJob, job_id) is not None
        assert (
            session.scalar(
                select(SearchVideo).where(SearchVideo.video_id == video["id"])
            )
            is not None
        )
    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 1
    assert detail["status"] != "done"

    # With the fault removed the same request succeeds and settles the search.
    monkeypatch.setattr(videos_api, "refresh_searches_for_video", real_refresh)
    assert client.delete(f"/api/v1/videos/{video['id']}").status_code == 204
    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 0
    assert detail["status"] == "done"
    assert detail["finished_at"] is not None


def test_deleting_a_video_mid_run_does_not_strand_the_job(client, worker, monkeypatch) -> None:
    """Deleting the video under a running job must not leave an ownerless ``running`` job.

    The old ``Video.jobs`` relationship nulled ``processing_jobs.video_id`` instead of
    letting the foreign key cascade, so the job survived with no video and no project;
    the next candidate insert failed, the session was left unusable and the job stayed
    ``running`` for ever.
    """
    from app.adapters.mock import MockTemporalAdapter

    dataset = _create_dev_dataset(client)
    video = _upload_dataset_video(client, dataset["id"], "midrun.mp4")
    search = _launch_search(client, dataset["id"])
    url = f"/api/v1/videos/{video['id']}"

    def infer(self, request):
        assert client.delete(url).status_code == 204
        request.progress(0.5)  # the job is gone; this must interrupt cleanly

    monkeypatch.setattr(MockTemporalAdapter, "propose", infer)

    assert worker.run_once() is True

    with db.SessionLocal() as session:
        assert session.get(Video, video["id"]) is None
        assert session.scalar(select(ProcessingJob)) is None
        assert session.scalar(select(SearchVideo)) is None
        assert (
            session.scalar(select(func.count()).select_from(Candidate)) or 0
        ) == 0
    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 0
    assert detail["status"] == "done"


def test_deleting_a_video_cascades_its_jobs_and_candidates(client, worker) -> None:
    """The job history of a deleted video goes with it, as the DDL always intended."""
    dataset = _create_dev_dataset(client)
    video = _upload_dataset_video(client, dataset["id"], "cascade.mp4")
    search = _launch_search(client, dataset["id"])

    assert worker.run_once() is True
    assert _count_rows(Candidate) > 0
    job_id = _job_by_video(search["id"])[video["id"]]

    assert client.delete(f"/api/v1/videos/{video['id']}").status_code == 204

    with db.SessionLocal() as session:
        assert session.get(ProcessingJob, job_id) is None
    assert _count_rows(Candidate) == 0
    with db.SessionLocal() as session:
        assert session.scalar(select(SearchVideo)) is None

    detail = _search_detail(client, search["id"])
    assert detail["total_videos"] == 0
    assert detail["status"] == "done"


# --------------------------------------------------------------------------- #
# 9. Idempotency request scope, and search-level cancel / restart
# --------------------------------------------------------------------------- #


def _create_search(
    client,
    dataset_id: int,
    payload: dict,
    *,
    key: str = "scope-key",
    expected: int = 202,
) -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/searches",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == expected, response.text
    return response.json()


def test_idempotent_replay_survives_deleting_the_selected_video(client) -> None:
    """The original request must keep matching itself after its video is gone.

    This is the local regression from the review: the replay used to be judged
    against the live ``search_videos`` rows, so deleting the selected video made
    the very same request come back as 409 instead of the original search.
    """
    dataset = _create_dev_dataset(client, "Replay after delete")
    video = _upload_dataset_video(client, dataset["id"], "keep.mp4")
    payload = {"prompt": "a person waves", "video_ids": [video["id"]]}

    created = _create_search(client, dataset["id"], payload)
    assert created["total_videos"] == 1

    assert client.delete(f"/api/v1/videos/{video['id']}").status_code == 204

    replay = _create_search(client, dataset["id"], payload)
    assert replay["id"] == created["id"]
    assert replay["total_videos"] == 0
    assert replay["status"] == "done"

    with db.SessionLocal() as session:
        assert len(list(session.scalars(select(Search)))) == 1


def test_idempotency_key_reuse_with_different_params_conflicts(client) -> None:
    dataset = _create_dev_dataset(client, "Param conflict")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")

    _create_search(
        client, dataset["id"], {"prompt": "a cat", "params": {"threshold": 0.5}}
    )
    conflict = _create_search(
        client,
        dataset["id"],
        {"prompt": "a cat", "params": {"threshold": 0.9}},
        expected=409,
    )
    assert conflict["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert conflict["details"]["mismatched_fields"] == ["params"]


def test_idempotency_key_reuse_switching_from_subset_to_all_conflicts(client) -> None:
    dataset = _create_dev_dataset(client, "Subset then all")
    video = _upload_dataset_video(client, dataset["id"], "clip.mp4")

    _create_search(client, dataset["id"], {"prompt": "a dog", "video_ids": [video["id"]]})
    conflict = _create_search(client, dataset["id"], {"prompt": "a dog"}, expected=409)
    assert conflict["details"]["mismatched_fields"] == ["video_ids"]


def test_idempotency_key_reuse_switching_from_all_to_subset_conflicts(client) -> None:
    """The reverse direction is the same mistake and must also be refused."""
    dataset = _create_dev_dataset(client, "All then subset")
    video = _upload_dataset_video(client, dataset["id"], "clip.mp4")

    _create_search(client, dataset["id"], {"prompt": "a dog"})
    conflict = _create_search(
        client, dataset["id"], {"prompt": "a dog", "video_ids": [video["id"]]}, expected=409
    )
    assert conflict["details"]["mismatched_fields"] == ["video_ids"]


def test_idempotency_key_tolerates_video_order_and_duplicates(client) -> None:
    """The scope is a set: order and repeats are not a different request."""
    dataset = _create_dev_dataset(client, "Order")
    first = _upload_dataset_video(client, dataset["id"], "a.mp4")
    second = _upload_dataset_video(client, dataset["id"], "b.mp4")

    created = _create_search(
        client,
        dataset["id"],
        {"prompt": "a bird", "video_ids": [first["id"], second["id"]]},
    )
    replay = _create_search(
        client,
        dataset["id"],
        {"prompt": "a bird", "video_ids": [second["id"], first["id"], first["id"]]},
    )
    assert replay["id"] == created["id"]
    assert replay["total_videos"] == 2


def test_idempotency_key_ignores_the_title(client) -> None:
    """``title`` is presentation only, so it is not part of the request scope."""
    dataset = _create_dev_dataset(client, "Title")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")

    created = _create_search(client, dataset["id"], {"prompt": "a boat", "title": "Boat"})
    replay = _create_search(
        client, dataset["id"], {"prompt": "a boat", "title": "Another title"}
    )
    assert replay["id"] == created["id"]
    assert replay["title"] == "Boat"


def test_idempotency_key_treats_the_default_adapter_as_equivalent(client) -> None:
    """Omitting ``adapter_name`` and naming the configured default are one request."""
    dataset = _create_dev_dataset(client, "Adapter default")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")

    created = _create_search(client, dataset["id"], {"prompt": "a train"})
    replay = _create_search(
        client, dataset["id"], {"prompt": "a train", "adapter_name": "mock"}
    )
    assert replay["id"] == created["id"]


def test_idempotency_key_reuse_with_different_adapter_conflicts(client) -> None:
    dataset = _create_dev_dataset(client, "Adapter conflict")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")

    _create_search(client, dataset["id"], {"prompt": "a train", "adapter_name": "mock"})
    conflict = _create_search(
        client,
        dataset["id"],
        {"prompt": "a train", "adapter_name": "qwen2.5-vl"},
        expected=409,
    )
    assert conflict["details"]["mismatched_fields"] == ["adapter_name"]


def test_idempotency_key_conflict_lists_every_mismatched_field(client) -> None:
    dataset = _create_dev_dataset(client, "Multi conflict")
    video = _upload_dataset_video(client, dataset["id"], "clip.mp4")

    _create_search(
        client,
        dataset["id"],
        {"prompt": "first", "params": {"threshold": 0.5}, "video_ids": [video["id"]]},
    )
    conflict = _create_search(
        client,
        dataset["id"],
        {"prompt": "second", "params": {"threshold": 0.9}},
        expected=409,
    )
    assert conflict["details"]["mismatched_fields"] == ["prompt", "params", "video_ids"]


def test_legacy_search_without_a_stored_scope_still_replays(client) -> None:
    """Rows written before the column existed fall back to the old comparison."""
    dataset = _create_dev_dataset(client, "Legacy scope")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    created = _create_search(client, dataset["id"], {"prompt": "a cup"})

    with db.SessionLocal() as session:
        session.execute(
            update(Search)
            .where(Search.id == created["id"])
            .values(request_scope_json="{}")
        )
        session.commit()

    replay = _create_search(client, dataset["id"], {"prompt": "a cup"})
    assert replay["id"] == created["id"]

    conflict = _create_search(client, dataset["id"], {"prompt": "a mug"}, expected=409)
    assert conflict["details"]["mismatched_fields"] == ["prompt"]


def test_search_cancel_cancels_every_video_and_settles_the_search(client) -> None:
    dataset = _create_dev_dataset(client, "Cancel search")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"c{index}.mp4")
    search = _launch_search(client, dataset["id"])
    jobs = _job_by_video(search["id"])

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/cancel"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_videos"] == 2
    assert body["queued_videos"] == 0
    assert body["running_videos"] == 0
    assert body["finished_at"] is not None
    assert all(video["error_message"] == "Job canceled" for video in body["videos"])
    for job_id in jobs.values():
        assert _job_row(job_id).status == JobStatus.canceled


def test_search_cancel_is_a_no_op_once_settled(client, worker) -> None:
    """The frontend may retry a cancel; a settled search is returned unchanged."""
    dataset = _create_dev_dataset(client, "Cancel twice")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    assert worker.run_once() is True

    for _ in range(2):
        response = client.post(
            f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/cancel"
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"
        assert response.json()["done_videos"] == 1


def test_search_cancel_wins_against_a_worker_that_already_claimed(
    client, worker
) -> None:
    """A cancel between claim and start must survive the worker resuming.

    This is the concurrent-cancellation case from the review: the job is already
    ``running`` in a worker's hands when the user cancels the search.  The worker
    then runs the job anyway; it must drop its result instead of repainting the
    video ``running``/``done`` and un-settling the search.
    """
    dataset = _create_dev_dataset(client, "Cancel mid run")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    job_id = next(iter(_job_by_video(search["id"]).values()))

    with db.SessionLocal() as session:
        claimed = claim_next_job(session)
    assert claimed is not None
    assert claimed.id == job_id

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/cancel"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["failed_videos"] == 1
    assert response.json()["videos"][0]["error_message"] == "Job canceled"

    # The worker resumes the job it had claimed and finds it canceled.
    with db.SessionLocal() as session:
        pipeline.execute_job(
            session,
            job_id,
            storage=worker.storage,
            probe=worker.probe,
            extractor=worker.extractor,
            adapter=FailingAdapter(),
            settings=worker.settings,
        )

    assert _job_row(job_id).status == JobStatus.canceled
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 1
    assert detail["running_videos"] == 0
    assert detail["done_videos"] == 0


def test_search_retry_requeues_only_the_failed_videos(
    client, worker, monkeypatch
) -> None:
    from app.adapters.registry import get_adapter as real_get_adapter

    dataset = _create_dev_dataset(client, "Retry search")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"r{index}.mp4")
    search = _launch_search(client, dataset["id"])

    # One video succeeds, the other fails non-retryably.
    assert worker.run_once() is True
    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    assert worker.run_once() is True

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "partial"
    assert detail["done_videos"] == 1
    assert detail["failed_videos"] == 1

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry"
    )
    assert response.status_code == 202, response.text
    body = response.json()
    # One video finished, one is back in the queue, so the search is in progress
    # again rather than partial/done.
    assert body["status"] == "running"
    assert body["queued_videos"] == 1
    assert body["done_videos"] == 1
    assert body["failed_videos"] == 0
    assert body["finished_at"] is None

    # With the fault removed the retried video runs and the search finishes green.
    monkeypatch.setattr("app.worker.get_adapter", real_get_adapter)
    assert worker.run_once() is True
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "done"
    assert detail["done_videos"] == 2


def test_search_retry_without_failures_is_refused(client) -> None:
    dataset = _create_dev_dataset(client, "Retry nothing")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEARCH_NOT_RETRYABLE"


def test_search_cancel_and_retry_respect_the_dataset_boundary(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    admin_token = admin["access_token"]
    dataset = create_dataset(auth_client, admin_token, "Guarded search")

    invitation = invite_user(auth_client, admin_token, "reader@example.com")
    annotator = accept_invitation(auth_client, invitation["token"], "Ana Reader")
    annotator_token = annotator["access_token"]
    added = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"user_id": annotator["user"]["id"]},
        headers=auth_header(admin_token),
    )
    assert added.status_code == 201

    outsider_invite = invite_user(
        auth_client, admin_token, "outsider-ds@example.com", role="dataset_admin"
    )
    outsider = accept_invitation(auth_client, outsider_invite["token"], "Otto Outsider")
    outsider_token = outsider["access_token"]

    _upload_dataset_video_auth(auth_client, dataset["id"], admin_token)
    search = _launch_search_auth(auth_client, dataset["id"], admin_token)
    for action in ("cancel", "retry"):
        url = f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/{action}"
        # A member annotator lacks the write role.
        assert auth_client.post(url, headers=auth_header(annotator_token)).status_code == 403
        # A non-member never sees the dataset, whatever their global role.
        denied = auth_client.post(url, headers=auth_header(outsider_token))
        assert denied.status_code == 404
        assert denied.json()["code"] == "DATASET_NOT_FOUND"

    # The admin (a member by definition) may cancel.
    assert (
        auth_client.post(
            f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/cancel",
            headers=auth_header(admin_token),
        ).status_code
        == 200
    )


def _jobs_for_video(video_id: int) -> list[ProcessingJob]:
    with db.SessionLocal() as session:
        return list(
            session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.video_id == video_id)
                .order_by(ProcessingJob.id)
            )
        )


def _fail_one_video(client, worker, monkeypatch, *, name: str) -> tuple[dict, dict, int]:
    """A one-video search whose job failed; returns (dataset, search, failed_job_id)."""
    dataset = _create_dev_dataset(client, name)
    video = _upload_dataset_video(client, dataset["id"], "race.mp4")
    search = _launch_search(client, dataset["id"])

    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    assert worker.run_once() is True
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 1
    return dataset, search, _job_by_video(search["id"])[video["id"]]


def test_concurrent_search_retry_queues_one_replacement_per_video(
    client, worker, monkeypatch
) -> None:
    """Two retries released together must leave one replacement job, not two.

    The endpoint reads the failed job, queues a replacement and then installs it
    on the ``SearchVideo``.  Two requests doing that at once used to both answer
    202 while the second overwrote the link, leaving an orphan job behind.  Here
    a peer request is simulated just before this one installs its replacement,
    so both really do reach the swap with the same stale snapshot.
    """
    from app.api import searches as searches_api

    dataset, search, failed_job_id = _fail_one_video(
        client, worker, monkeypatch, name="Concurrent retry"
    )
    video_id = search["videos"][0]["video_id"]

    real_enqueue = searches_api.enqueue_candidate_job
    state = {"peer_finished": False}

    def a_peer_installs_its_replacement_first(*args, **kwargs):
        if not state["peer_finished"]:
            state["peer_finished"] = True
            with db.SessionLocal() as peer:
                row = peer.scalar(
                    select(SearchVideo).where(SearchVideo.search_id == search["id"])
                )
                assert row is not None
                assert row.status == SearchVideoStatus.failed
                video = peer.get(Video, row.video_id)
                replacement = pipeline.enqueue_candidate_job(
                    peer,
                    video=video,
                    action=None,
                    adapter_name="mock",
                    params={},
                    idempotency_key=None,
                    max_attempts=3,
                )
                row.job_id = replacement.id
                row.status = SearchVideoStatus.queued
                row.error_message = None
                peer.commit()
                pipeline.settle_searches(peer, [search["id"]])
        return real_enqueue(*args, **kwargs)

    monkeypatch.setattr(
        searches_api, "enqueue_candidate_job", a_peer_installs_its_replacement_first
    )
    loser = client.post(f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry")
    assert state["peer_finished"] is True
    assert loser.status_code == 202, loser.text

    # One failed job (kept as history) plus exactly one replacement -- the
    # loser's own job was deleted instead of staying queued.
    jobs = _jobs_for_video(video_id)
    assert len(jobs) == 2, [(job.id, job.status) for job in jobs]
    assert jobs[0].id == failed_job_id
    assert jobs[0].status == JobStatus.failed
    queued = [job for job in jobs if job.status == JobStatus.queued]
    assert len(queued) == 1

    with db.SessionLocal() as session:
        row = session.scalar(
            select(SearchVideo).where(SearchVideo.search_id == search["id"])
        )
        assert row is not None
        assert row.job_id == queued[0].id
        assert row.status == SearchVideoStatus.queued

    detail = _search_detail(client, search["id"])
    assert detail["queued_videos"] == 1
    assert detail["failed_videos"] == 0


def test_job_retry_refuses_a_superseded_search_job(
    client, worker, monkeypatch
) -> None:
    """The replaced job is not runnable any more: its SearchVideo moved on."""
    dataset, search, failed_job_id = _fail_one_video(
        client, worker, monkeypatch, name="Superseded job"
    )

    retried = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry"
    )
    assert retried.status_code == 202, retried.text

    response = client.post(f"/api/v1/jobs/{failed_job_id}/retry")
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "JOB_SUPERSEDED"

    # The refusal must not have requeued anything: the search stays as the
    # search-level retry left it.
    assert [job.status for job in _jobs_for_video(search["videos"][0]["video_id"])] == [
        JobStatus.failed,
        JobStatus.queued,
    ]
    detail = _search_detail(client, search["id"])
    assert detail["queued_videos"] == 1
    assert detail["failed_videos"] == 0


def test_search_retry_after_a_lost_race_returns_the_restarted_search(
    client, worker, monkeypatch
) -> None:
    """A retry that lost the race answers 202 with the state it found."""
    from app.api import searches as searches_api

    dataset = _create_dev_dataset(client, "Lost race")
    for index in range(2):
        _upload_dataset_video(client, dataset["id"], f"l{index}.mp4")
    search = _launch_search(client, dataset["id"])

    # One video succeeds, the other fails.
    assert worker.run_once() is True
    monkeypatch.setattr("app.worker.get_adapter", lambda name, cfg: FailingAdapter())
    assert worker.run_once() is True
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "partial"
    assert detail["failed_videos"] == 1

    real_enqueue = searches_api.enqueue_candidate_job
    state = {"peer_finished": False}

    def a_peer_restarts_it_first(*args, **kwargs):
        if not state["peer_finished"]:
            state["peer_finished"] = True
            with db.SessionLocal() as peer:
                row = peer.scalar(
                    select(SearchVideo).where(
                        SearchVideo.search_id == search["id"],
                        SearchVideo.status == SearchVideoStatus.failed,
                    )
                )
                assert row is not None
                video = peer.get(Video, row.video_id)
                replacement = pipeline.enqueue_candidate_job(
                    peer,
                    video=video,
                    action=None,
                    adapter_name="mock",
                    params={},
                    idempotency_key=None,
                    max_attempts=3,
                )
                row.job_id = replacement.id
                row.status = SearchVideoStatus.queued
                row.error_message = None
                peer.commit()
        return real_enqueue(*args, **kwargs)

    monkeypatch.setattr(
        searches_api, "enqueue_candidate_job", a_peer_restarts_it_first
    )
    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry"
    )

    # Losing the race is not a client error: the search is restarted either way.
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["queued_videos"] == 1
    assert body["failed_videos"] == 0
    assert body["finished_at"] is None

    # Its own replacement was dropped instead of being left orphaned.
    jobs = _jobs_for_video(
        next(
            row["video_id"]
            for row in body["videos"]
            if row["status"] == SearchVideoStatus.queued
        )
    )
    assert [job.status for job in jobs].count(JobStatus.queued) == 1


def test_search_retry_still_refuses_when_no_video_failed(
    client, worker, monkeypatch
) -> None:
    """A finished search has nothing to restart, so the answer stays 409."""
    dataset = _create_dev_dataset(client, "Retry a done search")
    _upload_dataset_video(client, dataset["id"], "ok.mp4")
    search = _launch_search(client, dataset["id"])
    assert worker.run_once() is True
    assert _search_detail(client, search["id"])["status"] == "done"

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches/{search['id']}/retry"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SEARCH_NOT_RETRYABLE"


def test_preflight_failure_does_not_resurrect_a_canceled_job(client) -> None:
    """A canceled job stays canceled when the adapter lookup fails afterwards.

    The worker claims a job and only then resolves the adapter.  A cancel that
    lands in that window used to be overwritten by ``fail_job_now``, which had no
    ownership fence: the job went ``canceled`` -> ``failed`` and the SearchVideo
    mirror carried the adapter message instead of "Job canceled".
    """
    dataset = _create_dev_dataset(client, "Preflight cancel")
    _upload_dataset_video(client, dataset["id"], "clip.mp4")
    search = _launch_search(client, dataset["id"])
    video_id, job_id = next(iter(_job_by_video(search["id"]).items()))

    # The worker has claimed the job and is about to resolve the adapter.
    with db.SessionLocal() as session:
        assert claim_next_job(session).id == job_id
    _mark_search_running(search["id"], video_id)

    # An operator cancels it in that window.
    canceled = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "canceled"

    # Now the adapter lookup fails, as the worker's preflight would report it.
    with db.SessionLocal() as session:
        job = session.get(ProcessingJob, job_id)
        assert job is not None
        fail_job_now(session, job, "UNKNOWN_ADAPTER", "unknown model adapter 'mock'")

    # The cancellation wins: the job did not come back to life as failed.
    assert _job_row(job_id).status == JobStatus.canceled
    detail = _search_detail(client, search["id"])
    assert detail["status"] == "failed"
    assert detail["failed_videos"] == 1
    assert detail["error_message"] == "Job canceled"
    assert detail["videos"][0]["error_message"] == "Job canceled"

