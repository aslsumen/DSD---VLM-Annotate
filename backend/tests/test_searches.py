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

from app import db
from app.adapters import AdapterUnavailable
from app.models import (
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
from app.services.pipeline import _now, claim_next_job, reap_stale_jobs
from sqlalchemy import select, update
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

    with db.SessionLocal() as session:
        pipeline._sync_search_video_status(
            session,
            session.get(ProcessingJob, job_id),
            SearchVideoStatus.done,
        )

    # At every derivation the row just written was already committed and visible
    # to a peer, so a concurrent worker cannot miss it.
    assert observed, "the aggregate was never derived"
    assert all(SearchVideoStatus.done in seen for seen in observed)

    # Finish the second video and confirm the search settles.
    with db.SessionLocal() as session:
        pipeline._sync_search_video_status(
            session,
            session.get(ProcessingJob, jobs[video_ids[1]]),
            SearchVideoStatus.done,
        )

    detail = _search_detail(client, search["id"])
    assert detail["status"] == "done"
    assert detail["done_videos"] == 2
    assert detail["finished_at"] is not None

