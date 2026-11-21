"""Search fan-out, status aggregation, and role/dataset scoping (S3-06).

Covers the dataset-level search lifecycle: launch a search across a dataset's
ready videos, synchronise per-video SearchVideo status from the processing jobs,
aggregate the parent Search status, and enforce membership-based access.
"""

from __future__ import annotations

import uuid

from app import db
from app.adapters import AdapterUnavailable
from app.models import Search, SearchVideo, Video, VideoStatus
from sqlalchemy import select
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
