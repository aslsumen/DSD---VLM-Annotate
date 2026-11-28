"""Candidate list filters: ``review_state`` and ``verdict`` combined must work.

Both filters target the ``annotations`` table.  When each one added its own
join, the compiled SQL contained ``annotations`` twice, so combining them
raised an ambiguous-column error (surfacing as a 500) instead of filtering.
These tests pin the single-join behaviour on both routes that expose the pair:
the legacy project listing and the dataset search listing.
"""

from __future__ import annotations

from tests.conftest import (
    create_action,
    create_project,
    make_video_bytes,
    upload_video,
)


def _create_dataset(client, name: str = "Filter dataset") -> dict:
    """Create a dataset through the unauthenticated dev route (auth off)."""
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


def _annotate(client, candidate_id: int, verdict: str) -> None:
    response = client.put(
        f"/api/v1/candidates/{candidate_id}/annotation",
        json={"verdict": verdict, "reviewer": "ana"},
    )
    assert response.status_code == 200, response.text


def _project_candidates(client, worker) -> tuple[dict, list[dict]]:
    """Run one legacy project search and review its first two candidates."""
    project = create_project(client, "Filter project")
    action = create_action(client, project["id"])
    video = upload_video(client, project["id"], "filter.mp4")
    client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    assert worker.run_once() is True
    candidates = client.get(f"/api/v1/projects/{project['id']}/candidates").json()
    assert len(candidates) >= 2
    _annotate(client, candidates[0]["id"], "true_positive")
    _annotate(client, candidates[1]["id"], "false_positive")
    return project, candidates


def test_project_candidates_filter_by_review_state_and_verdict(client, worker) -> None:
    project, candidates = _project_candidates(client, worker)
    base = f"/api/v1/projects/{project['id']}/candidates"

    # Each filter alone still works.
    reviewed = client.get(f"{base}?review_state=reviewed")
    assert reviewed.status_code == 200, reviewed.text
    assert {item["id"] for item in reviewed.json()} == {c["id"] for c in candidates[:2]}

    unreviewed = client.get(f"{base}?review_state=unreviewed")
    assert unreviewed.status_code == 200, unreviewed.text
    assert {item["id"] for item in unreviewed.json()} == {c["id"] for c in candidates[2:]}

    # …and so does the combination that used to join ``annotations`` twice.
    combined = client.get(f"{base}?review_state=reviewed&verdict=true_positive")
    assert combined.status_code == 200, combined.text
    assert {item["id"] for item in combined.json()} == {candidates[0]["id"]}

    combined_false = client.get(f"{base}?review_state=reviewed&verdict=false_positive")
    assert combined_false.status_code == 200, combined_false.text
    assert {item["id"] for item in combined_false.json()} == {candidates[1]["id"]}

    # An annotation cannot be both absent and set, so this must be empty, not
    # an error (the outer join and the verdict predicate share one alias).
    empty = client.get(f"{base}?review_state=unreviewed&verdict=true_positive")
    assert empty.status_code == 200, empty.text
    assert empty.json() == []


def test_verdict_filter_alone_joins_annotations_once(client, worker) -> None:
    project, candidates = _project_candidates(client, worker)
    base = f"/api/v1/projects/{project['id']}/candidates"

    true_positives = client.get(f"{base}?verdict=true_positive")
    assert true_positives.status_code == 200, true_positives.text
    assert {item["id"] for item in true_positives.json()} == {candidates[0]["id"]}

    false_positives = client.get(f"{base}?verdict=false_positive")
    assert false_positives.status_code == 200, false_positives.text
    assert {item["id"] for item in false_positives.json()} == {candidates[1]["id"]}


def test_search_candidates_filter_by_review_state_and_verdict(client, worker) -> None:
    dataset = _create_dataset(client, "Filter dataset")
    _upload_dataset_video(client, dataset["id"], "filter.mp4")
    launched = client.post(
        f"/api/v1/datasets/{dataset['id']}/searches",
        json={"prompt": "a person waves at the camera"},
    )
    assert launched.status_code == 202, launched.text
    search = launched.json()
    assert worker.run_once() is True

    base = f"/api/v1/searches/{search['id']}/candidates"
    candidates = client.get(base).json()
    assert len(candidates) >= 2
    _annotate(client, candidates[0]["id"], "true_positive")
    _annotate(client, candidates[1]["id"], "false_positive")

    reviewed = client.get(f"{base}?review_state=reviewed")
    assert reviewed.status_code == 200, reviewed.text
    assert {item["id"] for item in reviewed.json()} == {c["id"] for c in candidates[:2]}

    unreviewed = client.get(f"{base}?review_state=unreviewed")
    assert unreviewed.status_code == 200, unreviewed.text
    assert {item["id"] for item in unreviewed.json()} == {c["id"] for c in candidates[2:]}

    combined = client.get(f"{base}?review_state=reviewed&verdict=true_positive")
    assert combined.status_code == 200, combined.text
    assert {item["id"] for item in combined.json()} == {candidates[0]["id"]}

    empty = client.get(f"{base}?review_state=unreviewed&verdict=true_positive")
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    verdict_only = client.get(f"{base}?verdict=false_positive")
    assert verdict_only.status_code == 200, verdict_only.text
    assert {item["id"] for item in verdict_only.json()} == {candidates[1]["id"]}
