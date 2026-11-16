"""Video upload validation, probing, streaming and deletion."""

from __future__ import annotations

from tests.conftest import create_project, make_video_bytes


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
