"""Access-control and adapter-availability tests."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import create_action, create_project, upload_video


def test_bearer_token_is_enforced_when_configured(settings, probe, extractor) -> None:
    secured = settings.model_copy(update={"api_token": "s3cret"})
    application = create_app(secured, probe=probe, extractor=extractor)
    with TestClient(application) as client:
        assert client.get("/api/v1/health").status_code == 200
        unauthenticated = client.get("/api/v1/projects")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "UNAUTHENTICATED"

        wrong = client.get("/api/v1/projects", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401

        allowed = client.get("/api/v1/projects", headers={"Authorization": "Bearer s3cret"})
        assert allowed.status_code == 200


def test_unknown_adapter_is_rejected(client) -> None:
    _, action, video = _ready(client)
    response = client.post(
        f"/api/v1/videos/{video['id']}/jobs",
        json={"action_id": action["id"], "adapter": "does-not-exist"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_ADAPTER"


def test_registered_but_unavailable_adapter_is_rejected(client) -> None:
    _, action, video = _ready(client)
    response = client.post(
        f"/api/v1/videos/{video['id']}/jobs",
        json={"action_id": action["id"], "adapter": "qwen2.5-vl"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ADAPTER_UNAVAILABLE"


def test_job_requires_probed_video(client, probe) -> None:
    project = create_project(client)
    action = create_action(client, project["id"])
    from app.services.media import MediaError

    probe.fail_with = MediaError("MEDIA_PROBE_FAILED", "no probe")
    response = client.post(
        f"/api/v1/projects/{project['id']}/videos",
        files={"file": ("x.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8, "video/mp4")},
    )
    assert response.status_code == 422
    # No video exists, so a job cannot reference one either.
    assert (
        client.post("/api/v1/videos/999/jobs", json={"action_id": action["id"]}).status_code == 404
    )


def _ready(client):
    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    return project, action, video
