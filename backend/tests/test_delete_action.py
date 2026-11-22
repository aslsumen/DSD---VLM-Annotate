"""Deleting a prompt (action) removes everything it produced."""

from __future__ import annotations

from tests.conftest import create_action, create_project, upload_video


def _run_search(client, worker, project_id: int, action_id: int) -> list[dict]:
    video = upload_video(client, project_id)
    job = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action_id}).json()
    assert worker.run_once() is True
    candidates = client.get(f"/api/v1/jobs/{job['id']}/candidates").json()
    assert candidates
    return candidates


def test_delete_action_removes_jobs_candidates_annotations_and_clips(client, worker) -> None:
    project = create_project(client)
    kept = create_action(client, project["id"], name="kept")
    doomed = create_action(client, project["id"], name="doomed")
    kept_candidates = _run_search(client, worker, project["id"], kept["id"])
    doomed_candidates = _run_search(client, worker, project["id"], doomed["id"])

    # A review decision on a candidate of the deleted search.
    reviewed = client.put(
        f"/api/v1/candidates/{doomed_candidates[0]['id']}/annotation",
        json={"verdict": "true_positive", "reviewer": "ana"},
    )
    assert reviewed.status_code == 200

    storage = client.app.state.storage
    clip = client.get(f"/api/v1/candidates/{doomed_candidates[0]['id']}/clip")
    assert clip.status_code == 200
    doomed_job_id = doomed_candidates[0]["job_id"]

    response = client.delete(f"/api/v1/actions/{doomed['id']}")
    assert response.status_code == 204

    remaining = client.get(f"/api/v1/projects/{project['id']}/candidates").json()
    assert {c["id"] for c in remaining} == {c["id"] for c in kept_candidates}
    assert all(c["action_id"] == kept["id"] for c in remaining)
    assert client.get(f"/api/v1/candidates/{doomed_candidates[0]['id']}").status_code == 404
    assert client.get(f"/api/v1/jobs/{doomed_job_id}").status_code == 404

    stats = client.get(f"/api/v1/projects/{project['id']}/stats").json()
    assert stats["candidates_total"] == len(kept_candidates)
    assert stats["reviewed_total"] == 0

    # Clip files of the deleted search are gone; the other search keeps its clips.
    clips_dir = storage.path_for("clips")
    remaining_files = {p.name for p in clips_dir.iterdir()} if clips_dir.is_dir() else set()
    assert not any(name.startswith(f"{c['id']}-") for c in doomed_candidates for name in remaining_files)
    assert any(name.startswith(f"{c['id']}-") for c in kept_candidates for name in remaining_files)
    assert client.get(f"/api/v1/candidates/{kept_candidates[0]['id']}/clip").status_code == 200


def test_delete_action_without_jobs(client) -> None:
    project = create_project(client)
    action = create_action(client, project["id"])
    assert client.delete(f"/api/v1/actions/{action['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}/actions").json() == []
    assert client.delete(f"/api/v1/actions/{action['id']}").status_code == 404


def test_queued_job_of_a_deleted_action_is_never_executed(client, worker) -> None:
    project = create_project(client)
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"])
    job = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]}).json()
    assert client.delete(f"/api/v1/actions/{action['id']}").status_code == 204
    assert client.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert worker.run_once() is False
