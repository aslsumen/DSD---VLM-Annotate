"""Application configuration.

All values can be provided through environment variables prefixed with ``VLM_``
(for example ``VLM_DATABASE_URL``) or a local ``.env`` file.  Secrets are never
committed: see ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VLM_",
        env_file=(str(REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VLM Annotate"
    environment: str = "development"
    api_version: str = "v1"

    # --- persistence -------------------------------------------------
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'vlm_annotate.db').as_posix()}"
    data_dir: Path = REPO_ROOT / "data"
    auto_create_schema: bool = True

    # --- access control ----------------------------------------------
    # When set, every /api/v1 route except /health requires
    # `Authorization: Bearer <token>`.  Empty means "development, open".
    api_token: str | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    # --- upload limits ------------------------------------------------
    max_upload_bytes: int = 2 * 1024**3  # 2 GiB
    max_export_bytes: int = 8 * 1024**3  # 8 GiB
    min_video_duration_seconds: float = 1.0
    max_video_duration_seconds: float = 4 * 3600.0
    allowed_video_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".mov", ".m4v", ".webm", ".mkv"]
    )
    allowed_video_content_types: list[str] = Field(
        default_factory=lambda: [
            "video/mp4",
            "video/quicktime",
            "video/x-m4v",
            "video/webm",
            "video/x-matroska",
            "application/octet-stream",
        ]
    )

    # --- candidate proposal ------------------------------------------
    candidate_min_duration_seconds: float = 1.5
    candidate_max_duration_seconds: float = 40.0
    max_candidates_per_job: int = 12
    clip_padding_seconds: float = 1.0
    clip_max_duration_seconds: float = 90.0
    vlm_adapter: str = "mock"
    mock_seed_salt: str = "vlm-annotate-mock-v1"

    # --- worker -------------------------------------------------------
    worker_poll_interval_seconds: float = 1.0
    worker_max_attempts: int = 3
    worker_retry_backoff_seconds: float = 5.0
    ffmpeg_binary: str | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator("allowed_video_extensions")
    @classmethod
    def _normalise_extensions(cls, value: list[str]) -> list[str]:
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in value]

    @property
    def storage_root(self) -> Path:
        return self.data_dir / "storage"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_root.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


def reset_settings_cache() -> None:
    """Used by tests that override environment variables."""
    get_settings.cache_clear()
