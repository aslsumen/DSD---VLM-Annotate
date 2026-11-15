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
