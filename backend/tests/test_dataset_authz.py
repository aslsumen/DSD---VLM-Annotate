"""Dataset authorization on the shared routes inherited from the project API.

The dataset routes check membership themselves, but the routes that serve the
same rows by id — ``/videos/{id}``, its ``/stream``, ``/jobs/{id}/*`` and
``/candidates/{id}/*`` — used to perform a primary-key lookup and nothing else.
Any caller could therefore read, stream, cancel or delete a dataset-owned row
without holding a membership, and with ``VLM_AUTH_REQUIRED`` on those routes
never even asked for a token.

These tests pin the matrix those routes now follow:

* a **global administrator** may do anything;
* a **member** may read, and may write when the row's write role allows it
  (deleting videos, retrying or cancelling jobs need ``dataset_admin``;
  annotating needs nothing beyond membership, because that is the annotator's
  job);
* a **non-member** — whatever their role — answers ``404`` rather than ``403``,
  so the answer does not reveal that the dataset exists;
* an **anonymous** caller is told to authenticate (``401``) once the row belongs
  to a dataset — there is nothing to hide, the caller simply has no identity;
* **project-owned rows** (``dataset_id is None``) keep their historical,
  unauthenticated behaviour, which is what the legacy tests rely on.

Denials are also checked for side effects: a refused delete must leave the row
and the stored bytes, a refused cancel must leave the job status, and a refused
annotation must not create the annotation row.
"""

from __future__ import annotations

from app import db
from app.models import Annotation, Candidate, ProcessingJob, SearchVideo, Video
from sqlalchemy import select, update
from tests.conftest import (
    accept_invitation,
    auth_header,
    bootstrap_admin,
    invite_user,
    make_video_bytes,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _create_dataset(client, token: str, name: str = "Authz dataset") -> dict:
    response = client.post(
        "/api/v1/datasets",
        json={"name": name, "description": "fixture"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_dataset_video(client, dataset_id: int, token: str, filename: str = "clip.mp4") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/videos",
        files={"file": (filename, make_video_bytes(), "video/mp4")},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _launch_search(client, dataset_id: int, token: str, prompt: str = "a person waves") -> dict:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/searches",
        json={"prompt": prompt},
        headers=auth_header(token),
    )
    assert response.status_code == 202, response.text
    return response.json()


def _add_member(client, dataset_id: int, token: str, user_id: int) -> None:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/members",
        json={"user_id": user_id},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text


def _cast(client, admin: dict, dataset_id: int) -> dict[str, dict]:
    """Bootstrap the four caller types a dataset row can meet.

    ``dataset_admin`` and ``annotator`` are members of the dataset; ``outsider``
    is a dataset administrator who is *not* a member, which is the interesting
    case: they hold a write role globally yet must still get ``404``.
    """
    people: dict[str, dict] = {
        "admin": {"token": admin["access_token"], "user_id": admin["user"]["id"]}
    }
    for key, email, role, full_name in (
        ("dataset_admin", "dana@example.com", "dataset_admin", "Dana Dataset"),
        ("annotator", "ana@example.com", "annotator", "Ana Annotator"),
        ("outsider", "otto@example.com", "dataset_admin", "Otto Outsider"),
    ):
        invitation = invite_user(client, admin["access_token"], email, role=role)
        session = accept_invitation(client, invitation["token"], full_name)
        people[key] = {
            "token": session["access_token"],
            "user_id": session["user"]["id"],
        }
    for key in ("dataset_admin", "annotator"):
        _add_member(client, dataset_id, admin["access_token"], people[key]["user_id"])
    return people


def _headers(people: dict[str, dict], key: str) -> dict[str, str]:
    return auth_header(people[key]["token"])


def _video_row(video_id: int) -> Video | None:
    with db.SessionLocal() as session:
        return session.get(Video, video_id)


def _job_row(job_id: int) -> ProcessingJob | None:
    with db.SessionLocal() as session:
        return session.get(ProcessingJob, job_id)


def _annotation_count(candidate_id: int) -> int:
    with db.SessionLocal() as session:
        return len(
            list(
                session.scalars(
                    select(Annotation).where(Annotation.candidate_id == candidate_id)
                )
            )
        )


def _insert_candidates(job_id: int, video_id: int, search_id: int, count: int = 2) -> list[int]:
    """Materialise candidates without running the pipeline (authorization only)."""
    created: list[int] = []
    with db.SessionLocal() as session:
        for rank in range(count):
            candidate = Candidate(
                job_id=job_id,
                search_id=search_id,
                video_id=video_id,
                start_seconds=float(rank * 10),
                end_seconds=float(rank * 10 + 4),
                preview_start_seconds=float(rank * 10),
                preview_end_seconds=float(rank * 10 + 5),
                rank=rank,
                score=0.9 - rank * 0.1,
                model_notes="",
            )
            session.add(candidate)
            session.flush()
            created.append(candidate.id)
        session.commit()
    return created


# --------------------------------------------------------------------------- #
# 1. Videos
# --------------------------------------------------------------------------- #


def test_video_reads_are_scoped_to_the_dataset(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    video = _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])

    # The global administrator passes on role alone.
    assert (
        auth_client.get(
            f"/api/v1/videos/{video['id']}", headers=_headers(people, "admin")
        ).status_code
        == 200
    )

    # Both members can read the row and the bytes.
    for key in ("dataset_admin", "annotator"):
        detail = auth_client.get(f"/api/v1/videos/{video['id']}", headers=_headers(people, key))
        assert detail.status_code == 200, detail.text
        assert detail.json()["dataset_id"] == dataset["id"]
        stream = auth_client.get(
            f"/api/v1/videos/{video['id']}/stream", headers=_headers(people, key)
        )
        assert stream.status_code == 200, stream.text

    # A non-member answers 404, not 403: hold a write role globally and still
    # learn nothing about the dataset.
    outsider = auth_client.get(
        f"/api/v1/videos/{video['id']}", headers=_headers(people, "outsider")
    )
    assert outsider.status_code == 404
    assert outsider.json()["code"] == "VIDEO_NOT_FOUND"

    # An anonymous caller is told to authenticate: the row belongs to a dataset,
    # so there is nothing to hide behind a 404 here. Project-owned rows stay
    # open (see the last test in this file).
    anonymous = auth_client.get(f"/api/v1/videos/{video['id']}")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "UNAUTHENTICATED"


def test_video_delete_needs_the_dataset_write_role(auth_client, auth_app) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    video = _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])

    storage = auth_app.state.storage
    storage_key = _video_row(video["id"]).storage_key
    stored_path = storage.path_for(storage_key)
    assert stored_path.exists()

    # A member annotator may read but not delete.
    forbidden = auth_client.delete(
        f"/api/v1/videos/{video['id']}", headers=_headers(people, "annotator")
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert _video_row(video["id"]) is not None
    assert stored_path.exists()

    # A non-member gets 404 and nothing is removed.
    missing = auth_client.delete(
        f"/api/v1/videos/{video['id']}", headers=_headers(people, "outsider")
    )
    assert missing.status_code == 404
    assert _video_row(video["id"]) is not None
    assert stored_path.exists()

    # A member dataset administrator may delete; the row and the file go.
    done = auth_client.delete(
        f"/api/v1/videos/{video['id']}", headers=_headers(people, "dataset_admin")
    )
    assert done.status_code == 204, done.text
    assert _video_row(video["id"]) is None
    assert not stored_path.exists()


def test_dataset_video_cannot_be_sent_through_the_project_job_route(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    video = _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])

    # The guard runs before the action lookup, so even a missing action cannot
    # make this route look like a valid entry point for dataset work.
    refused = auth_client.post(
        f"/api/v1/videos/{video['id']}/jobs",
        json={"action_id": 1},
        headers=_headers(people, "dataset_admin"),
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "PROJECT_MISMATCH"

    # …and an outsider does not get that far: the row is invisible to them.
    hidden = auth_client.post(
        f"/api/v1/videos/{video['id']}/jobs",
        json={"action_id": 1},
        headers=_headers(people, "outsider"),
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "VIDEO_NOT_FOUND"


# --------------------------------------------------------------------------- #
# 2. Jobs
# --------------------------------------------------------------------------- #


def test_job_access_is_derived_from_the_owning_dataset(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    search = _launch_search(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])
    job_id = search["videos"][0]["job_id"]

    # Members read the job; the outsider sees nothing.
    for key in ("dataset_admin", "annotator"):
        readable = auth_client.get(f"/api/v1/jobs/{job_id}", headers=_headers(people, key))
        assert readable.status_code == 200, readable.text
    assert (
        auth_client.get(
            f"/api/v1/jobs/{job_id}", headers=_headers(people, "admin")
        ).status_code
        == 200
    )
    invisible = auth_client.get(f"/api/v1/jobs/{job_id}", headers=_headers(people, "outsider"))
    assert invisible.status_code == 404
    assert invisible.json()["code"] == "JOB_NOT_FOUND"

    anonymous = auth_client.get(f"/api/v1/jobs/{job_id}")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "UNAUTHENTICATED"

    before = _job_row(job_id).status

    # A refused cancel must leave the job untouched.
    refused = auth_client.post(
        f"/api/v1/jobs/{job_id}/cancel", headers=_headers(people, "outsider")
    )
    assert refused.status_code == 404
    assert _job_row(job_id).status == before

    # Cancelling mutates the queue, so membership alone is not enough.
    forbidden = auth_client.post(
        f"/api/v1/jobs/{job_id}/cancel", headers=_headers(people, "annotator")
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert _job_row(job_id).status == before

    # A member dataset administrator may cancel.
    cancelled = auth_client.post(
        f"/api/v1/jobs/{job_id}/cancel", headers=_headers(people, "dataset_admin")
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "canceled"


def test_list_jobs_filters_dataset_jobs_per_membership(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    search = _launch_search(auth_client, dataset["id"], admin["access_token"])
    dataset_job = search["videos"][0]["job_id"]
    people = _cast(auth_client, admin, dataset["id"])

    # A project-owned job, which predates datasets and must stay visible to all.
    project = auth_client.post(
        "/api/v1/projects", json={"name": "Legacy project", "description": "fixture"}
    )
    assert project.status_code == 201, project.text
    action = auth_client.post(
        f"/api/v1/projects/{project.json()['id']}/actions",
        json={"name": "wave", "description": "a person waves"},
    )
    assert action.status_code == 201, action.text
    uploaded = auth_client.post(
        f"/api/v1/projects/{project.json()['id']}/videos",
        files={"file": ("legacy.mp4", make_video_bytes(), "video/mp4")},
    )
    assert uploaded.status_code == 201, uploaded.text
    legacy = auth_client.post(
        f"/api/v1/videos/{uploaded.json()['id']}/jobs",
        json={"action_id": action.json()["id"]},
    )
    assert legacy.status_code == 202, legacy.text
    legacy_job = legacy.json()["id"]

    def listed(headers: dict[str, str] | None = None) -> set[int]:
        response = auth_client.get("/api/v1/jobs", headers=headers)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()}

    assert {dataset_job, legacy_job} <= listed(_headers(people, "admin"))
    assert {dataset_job, legacy_job} <= listed(_headers(people, "dataset_admin"))
    assert {dataset_job, legacy_job} <= listed(_headers(people, "annotator"))

    # The outsider keeps the legacy job and loses the dataset one.
    outsider_view = listed(_headers(people, "outsider"))
    assert legacy_job in outsider_view
    assert dataset_job not in outsider_view

    # Anonymous callers are filtered the same way, not rejected.
    anonymous_view = listed()
    assert legacy_job in anonymous_view
    assert dataset_job not in anonymous_view


def test_job_whose_video_was_deleted_fails_closed(auth_client) -> None:
    """A search job with no dataset and no project to resolve fails closed.

    Deleting a video now removes its jobs through the database cascade, so the
    ownerless row an older build left behind is built here directly: it is still
    reachable — anyone who kept the id can ask for it — and must not become the
    way around the dataset boundary.
    """
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    search = _launch_search(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])
    job_id = search["videos"][0]["job_id"]

    with db.SessionLocal() as session:
        # The old delete path also dropped the video's ``SearchVideo`` row (that is
        # what ``refresh_searches_for_video`` does), so the leftover job has no video,
        # no search link and no candidate: nothing can resolve it to a dataset.
        for link in list(
            session.scalars(select(SearchVideo).where(SearchVideo.job_id == job_id))
        ):
            session.delete(link)
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(video_id=None, project_id=None)
            .execution_options(synchronize_session=False)
        )
        session.commit()

    # The job row survives but nothing links it to a dataset any more.
    row = _job_row(job_id)
    assert row is not None
    assert row.video_id is None
    assert row.project_id is None

    # Failing closed: only the administrator can still inspect it.
    assert (
        auth_client.get(
            f"/api/v1/jobs/{job_id}", headers=_headers(people, "admin")
        ).status_code
        == 200
    )
    for key in ("dataset_admin", "annotator", "outsider"):
        hidden = auth_client.get(f"/api/v1/jobs/{job_id}", headers=_headers(people, key))
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "JOB_NOT_FOUND"


# --------------------------------------------------------------------------- #
# 3. Candidates and annotations
# --------------------------------------------------------------------------- #


def test_candidate_access_and_annotation_rights(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    video = _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    search = _launch_search(auth_client, dataset["id"], admin["access_token"])
    people = _cast(auth_client, admin, dataset["id"])
    job_id = search["videos"][0]["job_id"]
    first, second = _insert_candidates(job_id, video["id"], search["id"])

    # Reading is member-only.
    for key in ("dataset_admin", "annotator"):
        readable = auth_client.get(f"/api/v1/candidates/{first}", headers=_headers(people, key))
        assert readable.status_code == 200, readable.text
    invisible = auth_client.get(
        f"/api/v1/candidates/{first}", headers=_headers(people, "outsider")
    )
    assert invisible.status_code == 404
    assert invisible.json()["code"] == "CANDIDATE_NOT_FOUND"

    # A refused annotation must not create the row.
    refused = auth_client.put(
        f"/api/v1/candidates/{first}/annotation",
        json={"verdict": "true_positive", "reviewer": "otto"},
        headers=_headers(people, "outsider"),
    )
    assert refused.status_code == 404
    assert _annotation_count(first) == 0

    # Annotating is the annotator's job: membership is enough, no write role.
    written = auth_client.put(
        f"/api/v1/candidates/{first}/annotation",
        json={"verdict": "true_positive", "reviewer": "ana"},
        headers=_headers(people, "annotator"),
    )
    assert written.status_code == 200, written.text
    assert written.json()["review_state"] == "reviewed"

    # …and the outsider still cannot delete it.
    refused_delete = auth_client.delete(
        f"/api/v1/candidates/{first}/annotation", headers=_headers(people, "outsider")
    )
    assert refused_delete.status_code == 404
    assert _annotation_count(first) == 1

    # A member dataset administrator can.
    deleted = auth_client.delete(
        f"/api/v1/candidates/{first}/annotation", headers=_headers(people, "dataset_admin")
    )
    assert deleted.status_code == 204, deleted.text
    assert _annotation_count(first) == 0
    assert _annotation_count(second) == 0


def test_search_candidate_listing_is_not_reachable_through_the_project_route(
    auth_client,
) -> None:
    """The project candidate list is pinned to ``Video.project_id``, so it cannot
    surface dataset rows even though it carries no dataset guard."""
    admin = bootstrap_admin(auth_client)
    dataset = _create_dataset(auth_client, admin["access_token"])
    video = _upload_dataset_video(auth_client, dataset["id"], admin["access_token"])
    search = _launch_search(auth_client, dataset["id"], admin["access_token"])
    job_id = search["videos"][0]["job_id"]
    _insert_candidates(job_id, video["id"], search["id"])

    project = auth_client.post(
        "/api/v1/projects", json={"name": "Unrelated", "description": "fixture"}
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    # Give the project a video of its own, so the join below has real rows and a
    # ``video_id`` filter has something to match on.
    own_video = auth_client.post(
        f"/api/v1/projects/{project_id}/videos",
        files={"file": ("own.mp4", make_video_bytes(), "video/mp4")},
    )
    assert own_video.status_code == 201, own_video.text

    assert auth_client.get(f"/api/v1/projects/{project_id}/candidates").json() == []

    # Asking for the dataset video explicitly through the project route still
    # returns nothing: the ``Video.project_id`` predicate excludes it.
    sneaky = auth_client.get(
        f"/api/v1/projects/{project_id}/candidates", params={"video_id": video["id"]}
    )
    assert sneaky.status_code == 200
    assert sneaky.json() == []


# --------------------------------------------------------------------------- #
# 4. Legacy project-owned rows keep working without a token
# --------------------------------------------------------------------------- #


def test_project_owned_rows_keep_their_unauthenticated_behaviour(auth_client) -> None:
    """The whole legacy flow, with ``VLM_AUTH_REQUIRED`` on and no token sent.

    This is the regression that matters for the migration: the dataset guard
    must not leak onto rows that belong to no dataset.
    """
    project = auth_client.post(
        "/api/v1/projects", json={"name": "Legacy project", "description": "fixture"}
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    action = auth_client.post(
        f"/api/v1/projects/{project_id}/actions",
        json={"name": "wave", "description": "a person waves at the camera"},
    )
    assert action.status_code == 201, action.text

    uploaded = auth_client.post(
        f"/api/v1/projects/{project_id}/videos",
        files={"file": ("legacy.mp4", make_video_bytes(), "video/mp4")},
    )
    assert uploaded.status_code == 201, uploaded.text
    video = uploaded.json()
    assert video["dataset_id"] is None

    assert auth_client.get(f"/api/v1/videos/{video['id']}").status_code == 200
    assert auth_client.get(f"/api/v1/videos/{video['id']}/stream").status_code == 200

    created = auth_client.post(
        f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action.json()["id"]}
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    assert auth_client.get(f"/api/v1/jobs/{job_id}").status_code == 200
    assert auth_client.get(f"/api/v1/jobs/{job_id}/candidates").status_code == 200
    assert auth_client.get("/api/v1/jobs", params={"video_id": video["id"]}).status_code == 200
    assert auth_client.get(f"/api/v1/projects/{project_id}/candidates").status_code == 200

    # Deleting a project video stays open, as it always was.
    assert auth_client.delete(f"/api/v1/videos/{video['id']}").status_code == 204


def test_job_list_limit_applies_to_visible_rows(auth_client):
    from tests.conftest import bootstrap_admin, create_action, create_project, upload_video

    project = create_project(auth_client)
    action = create_action(auth_client, project["id"])
    video = upload_video(auth_client, project["id"])
    before = auth_client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
    assert before.status_code == 202, before.text
    token = bootstrap_admin(auth_client)["access_token"]
    dataset = _create_dataset(auth_client, token)["id"]
    _upload_dataset_video(auth_client, dataset, token)
    _launch_search(auth_client, dataset, token)
    result = auth_client.get("/api/v1/jobs", params={"limit": 1})
    assert result.status_code == 200
    assert [item["id"] for item in result.json()] == [before.json()["id"]], result.text
