"""Project/action CRUD and error-envelope tests."""

from __future__ import annotations

from tests.conftest import create_action, create_project


def test_create_and_list_projects(client) -> None:
    project = create_project(client, "Street interviews")
    assert project["name"] == "Street interviews"

    listing = client.get("/api/v1/projects")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [project["id"]]


def test_project_name_is_trimmed_and_blank_rejected(client) -> None:
    response = client.post("/api/v1/projects", json={"name": "   ", "description": ""})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

    response = client.post("/api/v1/projects", json={"name": "  Trimmed  ", "description": ""})
    assert response.status_code == 201
    assert response.json()["name"] == "Trimmed"


def test_patch_and_delete_project(client) -> None:
    project = create_project(client)
    response = client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "Renamed", "description": "new"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"

    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_duplicate_action_name_conflicts(client) -> None:
    project = create_project(client)
    create_action(client, project["id"], name="wave")
    response = client.post(
        f"/api/v1/projects/{project['id']}/actions",
        json={"name": "wave", "description": "same name again"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACTION_NAME_TAKEN"


def test_action_requires_description(client) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/actions", json={"name": "x", "description": ""}
    )
    assert response.status_code == 422


def test_unknown_project_uses_error_envelope(client) -> None:
    response = client.get("/api/v1/projects/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "PROJECT_NOT_FOUND"
    assert "message" in body


def test_stats_on_empty_project(client) -> None:
    project = create_project(client)
    response = client.get(f"/api/v1/projects/{project['id']}/stats")
    assert response.status_code == 200
    assert response.json() == {
        "videos_total": 0,
        "videos_ready": 0,
        "candidates_total": 0,
        "reviewed_total": 0,
        "true_positive_total": 0,
        "false_positive_total": 0,
        "unreviewed_total": 0,
        "jobs_running": 0,
        "jobs_failed": 0,
        "exports_ready": 0,
    }
