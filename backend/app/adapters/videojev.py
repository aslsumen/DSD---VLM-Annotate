"""VideoJev-4B zero-shot grounding engine (``video_grounding/``) as a model adapter.

The engine is an optional, GPU-heavy install (``pip install -e ./video_grounding[videojev]``)
needed only in the worker process.  Everything engine-related is imported lazily so the
API process can register and list this adapter without torch.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import AdapterError, AdapterUnavailable, ProposalRequest, ProposedInterval

# One model backend per worker process, reused across jobs (loading takes tens of seconds).
_BACKENDS: dict[str | None, Any] = {}


def _engine_version() -> str:
    try:
        return importlib.metadata.version("video-grounding")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class VideoJevAdapter:
    name = "videojev"
    requires_gpu = True
    # Returns every event the engine finds; zero events is a valid answer, not a failure.
    exhaustive = True

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path
        self.version = f"videojev-4b-{_engine_version()}"

    def is_available(self) -> bool:
        # The API process enqueues jobs without the engine installed, so only the config is
        # checked here; a worker without the engine fails the job with AdapterUnavailable.
        return self._config_path is None or Path(self._config_path).is_file()

    def propose(self, request: ProposalRequest) -> list[ProposedInterval]:
        try:
            from video_grounding.adapters.base import make_backend
            from video_grounding.models import Query
            from video_grounding.scheduler import ResumeMismatch, resume, run_scan
            from video_grounding.settings import Settings as EngineSettings
            from video_grounding.settings import load_settings
        except ImportError as exc:
            raise AdapterUnavailable(f"video_grounding engine is not installed: {exc}") from exc

        engine = load_settings(self._config_path) if self._config_path else EngineSettings()
        # The backend cuts its own preview clips from the proposed intervals.
        engine = engine.model_copy(
            update={"export": engine.export.model_copy(update={"cut_clips": False})}
        )
        work_dir = request.work_dir or Path(tempfile.mkdtemp(prefix="videojev-"))
        try:
            backend = _BACKENDS.get(self._config_path)
            if backend is None:
                backend = _BACKENDS[self._config_path] = make_backend(engine)
            kwargs: dict[str, Any] = {
                "backend": backend,
                "keep_loaded": True,
                "progress": request.progress,
            }
            result = None
            if (work_dir / "job.sqlite").exists():
                try:
                    result = resume(work_dir, **kwargs)
                except ResumeMismatch:
                    shutil.rmtree(work_dir)  # config / model / video changed: start over
            if result is None:
                result = run_scan(
                    str(request.video_path),
                    [Query("q1", request.action_text)],
                    engine,
                    work_dir,
                    **kwargs,
                )
        except ImportError as exc:
            raise AdapterUnavailable(f"video_grounding dependency missing: {exc}") from exc
        except Exception as exc:  # CUDA OOM, decode errors, ... - retryable
            # Drop the cached backend so the retry starts from a clean GPU state.
            if (stale := _BACKENDS.pop(self._config_path, None)) is not None:
                with contextlib.suppress(Exception):
                    stale.unload()
            raise AdapterError(f"videojev engine failed: {type(exc).__name__}: {exc}") from exc

        incomplete = not result.get("scan_complete", True)
        return [
            ProposedInterval(
                start_seconds=float(event["event_start_sec"]),
                end_seconds=float(event["event_end_sec"]),
                score=float(event["raw_score_max"]),
                notes=", ".join(
                    [*event.get("review_reasons", []), *(["scan incomplete"] if incomplete else [])]
                ),
            )
            for event in result["events"]
        ]
