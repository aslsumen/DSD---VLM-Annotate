"""End-to-end vertical slice: upload -> async job -> candidates -> review -> export."""

from __future__ import annotations

import io
import json
import zipfile

from tests.conftest import create_action, create_project, upload_video


def _prepare(client):
    project = create_project(client, "E2E street interviews")
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"], "long_interview.mp4")
    return project, action, video


def test_export_before_any_candidate_is_rejected(client) -> None:
    project = create_project(client)
    response = client.post(f"/api/v1/projects/{project['id']}/exports", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "EMPTY_PROJECT"


def test_full_pipeline(client, worker) -> None:
    _project, action, video = _prepare(client)

    created = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    assert created.status_code == 202, created.text
    job = created.json()
    assert job["status"] == "queued"
    assert job["kind"] == "candidate_proposal"

    assert worker.run_once() is True

    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "succeeded"
    assert job["progress"] == 1.0
    assert job["finished_at"] is not None

    candidates = client.get(f"/api/v1/jobs/{job['id']}/candidates").json()
    assert 3 <= len(candidates) <= 6
    for candidate in candidates:
        assert 0.0 <= candidate["start_seconds"] < candidate["end_seconds"] <= 600.0
        assert candidate["preview_start_seconds"] <= candidate["start_seconds"]
        assert candidate["preview_end_seconds"] >= candidate["end_seconds"]
        assert candidate["preview_end_seconds"] <= 600.0
        assert candidate["clip_status"] == "ready"
        assert candidate["review_state"] == "unreviewed"
        assert candidate["annotation"] is None

    clip = client.get(f"/api/v1/candidates/{candidates[0]['id']}/clip")
    assert clip.status_code == 200
    assert clip.headers["content-type"] == "video/mp4"


def test_idempotency_key_returns_same_job(client) -> None:
    _, action, video = _prepare(client)
    headers = {"Idempotency-Key": "weekly-run-1"}
    first = client.post(
        f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]}, headers=headers
    ).json()
    second = client.post(
        f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]}, headers=headers
    ).json()
    assert first["id"] == second["id"]
    assert len(client.get(f"/api/v1/jobs?video_id={video['id']}").json()) == 1


def test_review_labels_and_unreviewed_export_guard(client, worker) -> None:
    project, action, video = _prepare(client)
    client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    worker.run_once()
    candidates = client.get(f"/api/v1/projects/{project['id']}/candidates").json()

    guard = client.post(f"/api/v1/projects/{project['id']}/exports", json={})
    assert guard.status_code == 409
    assert guard.json()["code"] == "NO_REVIEWED_CANDIDATES"

    first_id = candidates[0]["id"]
    reviewed = client.put(
        f"/api/v1/candidates/{first_id}/annotation",
        json={
            "verdict": "true_positive",
            "corrected_start_seconds": 100.0,
            "corrected_end_seconds": 105.0,
            "note": "clear wave",
            "reviewer": "reviewer-a",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["review_state"] == "reviewed"
    assert body["annotation"]["verdict"] == "true_positive"
    assert body["annotation"]["corrected_start_seconds"] == 100.0

    stats = client.get(f"/api/v1/projects/{project['id']}/stats").json()
    assert stats["reviewed_total"] == 1
    assert stats["true_positive_total"] == 1
    assert stats["unreviewed_total"] == len(candidates) - 1

    # A false positive is still an explicit human label.
    client.put(
        f"/api/v1/candidates/{candidates[1]['id']}/annotation",
        json={"verdict": "false_positive"},
    )
    assert client.get(f"/api/v1/projects/{project['id']}/stats").json()["false_positive_total"] == 1

    # Removing the label restores "unreviewed" rather than silently becoming negative.
    assert client.delete(f"/api/v1/candidates/{candidates[1]['id']}/annotation").status_code == 204
    reset = client.get(f"/api/v1/candidates/{candidates[1]['id']}").json()
    assert reset["review_state"] == "unreviewed"
    assert reset["annotation"] is None


def test_export_zip_contains_verified_labels_and_clips(client, worker) -> None:
    project, action, video = _prepare(client)
    client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    worker.run_once()
    candidates = client.get(f"/api/v1/projects/{project['id']}/candidates").json()

    keep = candidates[0]
    client.put(
        f"/api/v1/candidates/{keep['id']}/annotation",
        json={
            "verdict": "true_positive",
            "corrected_start_seconds": 100.0,
            "corrected_end_seconds": 105.0,
            "reviewer": "reviewer-a",
            "note": "ok",
        },
    )

    created = client.post(f"/api/v1/projects/{project['id']}/exports", json={})
    assert created.status_code == 202, created.text
    export_id = created.json()["export"]["id"]
    assert created.json()["job"]["kind"] == "dataset_export"

    assert worker.run_once() is True

    export = client.get(f"/api/v1/exports/{export_id}").json()
    assert export["status"] == "ready"
    assert export["item_count"] == 1
    assert export["has_file"] is True

    download = client.get(f"/api/v1/exports/{export_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "labels.csv" in names
        assert "README.txt" in names
        assert f"clips/candidate_{keep['id']:05d}.mp4" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["item_count"] == 1
        item = manifest["items"][0]
        assert item["verdict"] == "true_positive"
        assert item["final"] == {"start_seconds": 100.0, "end_seconds": 105.0}
        assert item["proposal"]["start_seconds"] == keep["start_seconds"]
        assert item["provenance"]["mock"] is True
        labels = archive.read("labels.csv").decode()
        assert "true_positive" in labels


def test_include_unreviewed_export_is_explicit(client, worker) -> None:
    project, action, video = _prepare(client)
    client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    worker.run_once()
    total = len(client.get(f"/api/v1/projects/{project['id']}/candidates").json())

    created = client.post(
        f"/api/v1/projects/{project['id']}/exports", json={"include_unreviewed": True}
    )
    assert created.status_code == 202
    export_id = created.json()["export"]["id"]
    worker.run_once()
    export = client.get(f"/api/v1/exports/{export_id}").json()
    assert export["status"] == "ready"
    assert export["item_count"] == total

    download = client.get(f"/api/v1/exports/{export_id}/download")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert all(item["verdict"] == "unreviewed" for item in manifest["items"])


def test_partial_clip_failure_keeps_candidates_reviewable(client, worker, extractor) -> None:
    project, action, video = _prepare(client)
    extractor.fail = True
    client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    worker.run_once()

    job = client.get(f"/api/v1/jobs?video_id={video['id']}").json()[0]
    assert job["status"] == "succeeded"
    assert job["error_code"] == "CLIP_EXTRACTION_PARTIAL"

    candidates = client.get(f"/api/v1/projects/{project['id']}/candidates").json()
    assert candidates
    assert all(candidate["clip_status"] == "failed" for candidate in candidates)
    assert client.get(f"/api/v1/candidates/{candidates[0]['id']}/clip").status_code == 404
