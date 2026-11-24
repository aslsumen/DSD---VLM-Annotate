"""Video upload validation, probing, streaming and deletion."""

from __future__ import annotations

from tests.conftest import (
    create_action,
    create_project,
    make_engine_dirs,
    make_video_bytes,
    upload_video,
)


def test_upload_ready_video(client, probe) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("interview.mp4", make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["duration_seconds"] == 600.0
    assert body["original_filename"] == "interview.mp4"
    assert len(body["checksum_sha256"]) == 64
    assert "/storage/" not in str(body)  # never expose internal paths


def test_upload_rejects_unsupported_extension(client) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_VIDEO_EXTENSION"


def test_upload_rejects_non_video_bytes(client) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("fake.mp4", b"definitely not a video container", "video/mp4")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNRECOGNISED_CONTAINER"


def test_upload_rejects_duration_outside_limits(client, probe) -> None:
    probe.duration = 60.0 * 60.0 * 5  # 5 hours > 4h limit
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("long.mp4", make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VIDEO_DURATION_OUT_OF_RANGE"


def test_upload_probe_failure_is_reported_and_not_persisted(client, probe) -> None:
    from app.services.media import MediaError

    probe.fail_with = MediaError("MEDIA_PROBE_FAILED", "corrupt container")
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("broken.mp4", make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "MEDIA_PROBE_FAILED"
    assert client.get(f"/api/v1/projects/{project['id']}/videos").json() == []


def test_range_request_returns_partial_content(client) -> None:
    project = create_project(client)
    upload = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("clip.mp4", make_video_bytes(), "video/mp4")},
    ).json()

    response = client.get(f"/api/v1/videos/{upload['id']}/stream", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-9/")
    assert response.headers["accept-ranges"] == "bytes"
    assert len(response.content) == 10


def test_delete_video_removes_rows_and_file(client) -> None:
    project = create_project(client)
    upload = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("clip.mp4", make_video_bytes(), "video/mp4")},
    ).json()
    assert client.delete(f"/api/v1/videos/{upload['id']}").status_code == 204
    assert client.get(f"/api/v1/videos/{upload['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/videos").json() == []


def test_delete_video_removes_its_engine_dirs_only(client) -> None:
    project = create_project(client)
    action = create_action(client, project["id"])
    v1, v2 = upload_video(client, project["id"]), upload_video(client, project["id"], "b.mp4")
    jobs = {
        v["id"]: client.post(
            f"/api/v1/videos/{v['id']}/jobs", json={"action_id": action["id"]}
        ).json()["id"]
        for v in (v1, v2)
    }
    storage = client.app.state.storage
    make_engine_dirs(storage, jobs.values(), [v1["id"], v2["id"]])

    assert client.delete(f"/api/v1/videos/{v1['id']}").status_code == 204
    assert not storage.path_for(f"engine/features/video-{v1['id']}").exists()
    assert not storage.path_for(f"engine/job-{jobs[v1['id']]}").exists()
    assert storage.path_for(f"engine/features/video-{v2['id']}").is_dir()
    assert storage.path_for(f"engine/job-{jobs[v2['id']]}").is_dir()


def test_delete_video_cleans_engine_files_written_by_in_flight_job(client, worker, monkeypatch) -> None:
    from app.adapters.mock import MockTemporalAdapter

    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    url = f"/api/v1/videos/{video['id']}"
    job_id = client.post(f"{url}/jobs", json={"action_id": action["id"]}).json()["id"]
    storage = client.app.state.storage

    def infer(self, request):
        assert client.delete(url).status_code == 204
        make_engine_dirs(storage, [job_id], [video["id"]])
        request.progress(0.5)

    monkeypatch.setattr(MockTemporalAdapter, "propose", infer)

    assert worker.run_once()
    assert not storage.path_for(f"engine/job-{job_id}").exists()
    assert not storage.path_for(f"engine/features/video-{video['id']}").exists()
