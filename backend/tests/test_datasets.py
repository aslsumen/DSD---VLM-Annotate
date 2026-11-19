"""Dataset CRUD in development mode (authentication disabled)."""

from __future__ import annotations


def test_dataset_crud_without_auth(client) -> None:
    created = client.post(
        "/api/v1/datasets",
        json={"name": "Demo dataset", "description": "no auth in dev"},
    )
    assert created.status_code == 201, created.text
    dataset = created.json()
    assert dataset["name"] == "Demo dataset"
    assert dataset["created_by_id"] is None

    listing = client.get("/api/v1/datasets")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [dataset["id"]]

    fetched = client.get(f"/api/v1/datasets/{dataset['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "no auth in dev"

    members = client.get(f"/api/v1/datasets/{dataset['id']}/members")
    assert members.status_code == 200
    assert members.json() == []


def test_unknown_dataset_returns_404(client) -> None:
    response = client.get("/api/v1/datasets/999")
    assert response.status_code == 404
    assert response.json()["code"] == "DATASET_NOT_FOUND"
