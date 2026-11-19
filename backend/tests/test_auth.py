"""Session authentication, invitations and role enforcement (Sprint 3)."""

from __future__ import annotations

from tests.conftest import (
    accept_invitation,
    auth_header,
    bootstrap_admin,
    create_dataset,
    invite_user,
    login_user,
)


def test_bootstrap_login_me_logout(auth_client) -> None:
    session = bootstrap_admin(auth_client)
    token = session["access_token"]
    assert session["token_type"] == "bearer"
    assert session["user"]["role"] == "administrator"

    me = auth_client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"

    logout = auth_client.post("/api/v1/auth/logout", headers=auth_header(token))
    assert logout.status_code == 204
    assert auth_client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_bootstrap_requires_secret_and_runs_once(auth_client) -> None:
    payload = {
        "email": "other@example.com",
        "full_name": "Other Admin",
        "password": "another-password",
    }
    wrong = auth_client.post(
        "/api/v1/auth/bootstrap",
        json=payload,
        headers={"X-Bootstrap-Token": "wrong"},
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "INVALID_BOOTSTRAP_TOKEN"

    bootstrap_admin(auth_client)
    again = auth_client.post(
        "/api/v1/auth/bootstrap",
        json=payload,
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "ALREADY_BOOTSTRAPPED"


def test_unauthenticated_requests_are_rejected(auth_client) -> None:
    response = auth_client.get("/api/v1/datasets")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_invitation_flow_and_annotator_scope(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    invitation = invite_user(auth_client, admin["access_token"], "annotator@example.com")
    assert invitation["role"] == "annotator"
    assert invitation["token"]

    annotator = accept_invitation(auth_client, invitation["token"], "Ana Annotator")
    assert annotator["user"]["role"] == "annotator"

    # Annotators cannot create datasets...
    forbidden = auth_client.post(
        "/api/v1/datasets",
        json={"name": "Nope"},
        headers=auth_header(annotator["access_token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    # ...but see the datasets they are assigned to.
    dataset = create_dataset(auth_client, admin["access_token"], "Interviews")
    members = auth_client.get(
        f"/api/v1/datasets/{dataset['id']}/members",
        headers=auth_header(admin["access_token"]),
    )
    assert members.status_code == 200
    assert members.json() == []

    added = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"email": "annotator@example.com"},
        headers=auth_header(admin["access_token"]),
    )
    assert added.status_code == 201, added.text
    assert added.json()["user_id"] == annotator["user"]["id"]

    listing = auth_client.get(
        "/api/v1/datasets", headers=auth_header(annotator["access_token"])
    )
    assert [item["id"] for item in listing.json()] == [dataset["id"]]


def test_dataset_admin_scope_and_privilege_escalation(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    invitation = invite_user(
        auth_client, admin["access_token"], "dadmin@example.com", role="dataset_admin"
    )
    dataset_admin = accept_invitation(auth_client, invitation["token"], "Dana Dataset")
    assert dataset_admin["user"]["role"] == "dataset_admin"

    dataset = create_dataset(auth_client, dataset_admin["access_token"], "Own dataset")

    # A Dataset Administrator may invite annotators...
    annotator_invite = invite_user(
        auth_client, dataset_admin["access_token"], "worker@example.com"
    )
    # ...but not another administrator.
    escalation = auth_client.post(
        "/api/v1/auth/invitations",
        json={"email": "boss@example.com", "role": "administrator"},
        headers=auth_header(dataset_admin["access_token"]),
    )
    assert escalation.status_code == 403

    # ...nor add an administrator to their dataset.
    second_admin_invite = invite_user(
        auth_client, admin["access_token"], "admin2@example.com", role="administrator"
    )
    second_admin = accept_invitation(auth_client, second_admin_invite["token"], "Second Admin")
    escalation2 = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"user_id": second_admin["user"]["id"]},
        headers=auth_header(dataset_admin["access_token"]),
    )
    assert escalation2.status_code == 403

    annotator = accept_invitation(auth_client, annotator_invite["token"], "Worker")
    added = auth_client.post(
        f"/api/v1/datasets/{dataset['id']}/members",
        json={"user_id": annotator["user"]["id"]},
        headers=auth_header(dataset_admin["access_token"]),
    )
    assert added.status_code == 201

    other = create_dataset(auth_client, admin["access_token"], "Other dataset")
    assert (
        auth_client.get(
            f"/api/v1/datasets/{other['id']}",
            headers=auth_header(annotator["access_token"]),
        ).status_code
        == 404
    )
    listing = auth_client.get(
        "/api/v1/datasets", headers=auth_header(annotator["access_token"])
    )
    assert [item["id"] for item in listing.json()] == [dataset["id"]]


def test_lockout_after_failed_logins(auth_client) -> None:
    bootstrap_admin(auth_client)
    for _ in range(3):
        failed = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "wrong-password"},
        )
        assert failed.status_code == 401

    locked = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "admin-password"},
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "ACCOUNT_LOCKED"


def test_invalid_and_duplicate_invitations(auth_client) -> None:
    admin = bootstrap_admin(auth_client)
    invitation = invite_user(auth_client, admin["access_token"], "dup@example.com")
    accept_invitation(auth_client, invitation["token"], "Dup User")

    duplicate = auth_client.post(
        "/api/v1/auth/invitations",
        json={"email": "dup@example.com", "role": "annotator"},
        headers=auth_header(admin["access_token"]),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EMAIL_ALREADY_EXISTS"

    reused = auth_client.post(
        "/api/v1/auth/accept-invitation",
        json={
            "token": invitation["token"],
            "full_name": "Dup Again",
            "password": "password-123",
        },
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "INVITATION_ALREADY_USED"

    invalid = auth_client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": "x" * 40, "full_name": "Nobody", "password": "password-123"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVITATION_INVALID"


def test_login_rejects_unknown_email(auth_client) -> None:
    bootstrap_admin(auth_client)
    response = login_user(auth_client, "admin@example.com", "admin-password")
    assert response["user"]["email"] == "admin@example.com"

    unknown = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever-password"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["code"] == "INVALID_CREDENTIALS"
