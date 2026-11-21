"""Shared pytest fixtures.

Environment is pinned *before* importing the app so that the module-level
application factory cannot touch the repository's real data directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="vlm-annotate-tests-"))
os.environ["VLM_DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["VLM_DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["VLM_ENVIRONMENT"] = "test"
os.environ["VLM_API_TOKEN"] = ""
os.environ["VLM_VLM_ADAPTER"] = "mock"

import pytest  # noqa: E402
from app import db  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.media import MediaError, VideoMetadata  # noqa: E402
from app.worker import JobWorker  # noqa: E402


class FakeProbe:
    def __init__(self, duration: float = 600.0, width: int = 1920, height: int = 1080) -> None:
        self.duration = duration
        self.width = width
        self.height = height
        self.fail_with: MediaError | None = None

    def probe(self, path: Path) -> VideoMetadata:
        if self.fail_with is not None:
            raise self.fail_with
        return VideoMetadata(
            duration_seconds=self.duration,
            width=self.width,
            height=self.height,
            fps=30.0,
            codec="h264",
        )


class FakeExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []
        self.fail = False

    def extract(self, source: Path, destination: Path, start: float, end: float) -> None:
        self.calls.append((start, end))
        if self.fail:
            raise MediaError("CLIP_EXTRACTION_FAILED", "synthetic extractor failure")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"fake-clip" * 16)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture()
def probe() -> FakeProbe:
    return FakeProbe()


@pytest.fixture()
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture()
def app(settings: Settings, probe: FakeProbe, extractor: FakeExtractor):
    engine = db.engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    application = create_app(settings, probe=probe, extractor=extractor)
    application.state.probe = probe
    application.state.extractor = extractor
    yield application
    Base.metadata.drop_all(bind=db.engine)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_settings(settings: Settings) -> Settings:
    """Same database, but session authentication is enforced."""
    return Settings(
        auth_required=True,
        bootstrap_token="test-bootstrap-token",
        database_url=settings.database_url,
        data_dir=settings.data_dir,
        auth_max_failed_logins=3,
        auth_lockout_minutes=5,
    )


@pytest.fixture()
def auth_app(auth_settings: Settings, probe: FakeProbe, extractor: FakeExtractor):
    engine = db.engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    application = create_app(auth_settings, probe=probe, extractor=extractor)
    application.state.probe = probe
    application.state.extractor = extractor
    yield application
    Base.metadata.drop_all(bind=db.engine)


@pytest.fixture()
def auth_client(auth_app):
    from fastapi.testclient import TestClient

    with TestClient(auth_app) as test_client:
        yield test_client


@pytest.fixture()
def worker(app, settings: Settings, probe: FakeProbe, extractor: FakeExtractor) -> JobWorker:
    return JobWorker(
        settings,
        storage=app.state.storage,
        probe=probe,
        extractor=extractor,
    )


def make_video_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def create_project(client, name: str = "Test project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "description": "fixture"})
    assert response.status_code == 201, response.text
    return response.json()


def create_action(client, project_id: int, name: str = "wave", description: str | None = None):
    response = client.post(
        f"/api/v1/projects/{project_id}/actions",
        json={
            "name": name,
            "description": description or "a person waves at the camera",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_video(client, project_id: int, filename: str = "clip.mp4") -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/videos",
        files={"file": (filename, make_video_bytes(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #


def login_user(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def bootstrap_admin(
    client,
    email: str = "admin@example.com",
    password: str = "admin-password",
) -> dict:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": email, "full_name": "Admin", "password": password},
        headers={"X-Bootstrap-Token": "test-bootstrap-token"},
    )
    assert response.status_code == 201, response.text
    return login_user(client, email, password)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_dataset(client, token: str, name: str = "Warehouse") -> dict:
    response = client.post(
        "/api/v1/datasets",
        json={"name": name, "description": "fixture"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def invite_user(
    client,
    token: str,
    email: str,
    role: str = "annotator",
) -> dict:
    response = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "role": role},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def accept_invitation(
    client,
    invitation_token: str,
    full_name: str = "Invited User",
    password: str = "invited-password",
) -> dict:
    response = client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": invitation_token, "full_name": full_name, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_engine_dirs(storage, job_ids=(), video_ids=()) -> None:
    """Create the engine work / feature-cache dirs a real search leaves behind."""
    from app.services.pipeline import engine_job_key, feature_cache_key

    keys = [*map(engine_job_key, job_ids), *map(feature_cache_key, video_ids)]
    for key in keys:
        (storage.path_for(key)).mkdir(parents=True)
        (storage.path_for(key) / "x.bin").write_bytes(b"x")
