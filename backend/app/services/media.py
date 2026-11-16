"""ffmpeg-backed media probing and clip extraction.

The ffmpeg binary is provided by the ``imageio-ffmpeg`` wheel (no system install
required); ``VLM_FFMPEG_BINARY`` can override it.  Both operations are blocking
and are called from the worker thread, never from the HTTP request that starts a
job.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..validation import round_seconds


class MediaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int | None
    height: int | None
    fps: float | None
    codec: str | None


class MediaProbe(Protocol):
    def probe(self, path: Path) -> VideoMetadata: ...


class ClipExtractor(Protocol):
    def extract(self, source: Path, destination: Path, start: float, end: float) -> None: ...


def resolve_ffmpeg_binary(explicit: str | None = None) -> str:
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_file():
            raise MediaError("FFMPEG_NOT_FOUND", f"configured ffmpeg binary not found: {explicit}")
        return str(candidate)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - environment dependent
        raise MediaError(
            "FFMPEG_NOT_FOUND",
            "ffmpeg is unavailable: install imageio-ffmpeg or set VLM_FFMPEG_BINARY",
        ) from exc


class FFmpegMediaProbe:
    def __init__(self, ffmpeg_binary: str | None = None) -> None:
        self._ffmpeg = ffmpeg_binary

    def probe(self, path: Path) -> VideoMetadata:
        # `read_frames` starts ffmpeg and yields a metadata dict first; we never
        # decode a frame, so this is cheap even for long videos.
        try:
            import imageio_ffmpeg

            generator = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
            meta = next(generator)
            with contextlib.suppress(Exception):
                generator.close()
        except MediaError:
            raise
        except Exception as exc:
            raise MediaError("MEDIA_PROBE_FAILED", f"could not read video metadata: {exc}") from exc

        duration = meta.get("duration")
        if not duration:
            raise MediaError("MEDIA_PROBE_FAILED", "video duration is missing or zero")
        size = meta.get("size") or (None, None)
        fps = meta.get("fps")
        return VideoMetadata(
            duration_seconds=round_seconds(float(duration)),
            width=int(size[0]) if size and size[0] else None,
            height=int(size[1]) if size and size[1] else None,
            fps=float(fps) if fps else None,
            codec=meta.get("codec"),
        )


class FFmpegClipExtractor:
    """Cuts a small, browser-playable H.264/AAC clip from the source video."""

    def __init__(self, ffmpeg_binary: str | None = None, timeout_seconds: int = 600) -> None:
        self._ffmpeg = ffmpeg_binary
        self._timeout = timeout_seconds

    def extract(self, source: Path, destination: Path, start: float, end: float) -> None:
        duration = round(end - start, 3)
        if duration <= 0:
            raise MediaError("INVALID_CLIP_INTERVAL", f"invalid clip interval {start}-{end}")
        ffmpeg = resolve_ffmpeg_binary(self._ffmpeg)
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{round(start, 3):.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "26",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaError("CLIP_EXTRACTION_TIMEOUT", "clip extraction timed out") from exc
        except OSError as exc:
            raise MediaError("FFMPEG_NOT_FOUND", f"could not start ffmpeg: {exc}") from exc
        if result.returncode != 0 or not destination.exists():
            tail = (result.stderr or "").strip().splitlines()[-3:]
            raise MediaError("CLIP_EXTRACTION_FAILED", "ffmpeg failed: " + " | ".join(tail))


class UnavailableMediaProbe:
    """Explicit stub used when tests want to bypass ffmpeg."""

    def probe(self, path: Path) -> VideoMetadata:  # pragma: no cover - test helper
        raise MediaError("MEDIA_PROBE_UNAVAILABLE", "media probing is not configured")


def ffmpeg_available(ffmpeg_binary: str | None = None) -> bool:
    try:
        resolve_ffmpeg_binary(ffmpeg_binary)
        return True
    except MediaError:
        return False


def media_info_json(ffmpeg_binary: str | None = None) -> dict[str, object]:
    """Small diagnostics payload for /health."""
    try:
        binary = resolve_ffmpeg_binary(ffmpeg_binary)
    except MediaError:
        return {"ffmpeg": None, "available": False}
    version = None
    try:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
        version = result.stdout.splitlines()[0] if result.stdout else None
    except Exception:  # pragma: no cover - diagnostics only
        version = None
    return {"ffmpeg": binary, "version": version, "available": True}


def _json_or_none(raw: str) -> dict[str, object] | None:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):  # pragma: no cover
        return None


__all__ = [
    "ClipExtractor",
    "FFmpegClipExtractor",
    "FFmpegMediaProbe",
    "MediaError",
    "MediaProbe",
    "UnavailableMediaProbe",
    "VideoMetadata",
    "ffmpeg_available",
    "media_info_json",
    "resolve_ffmpeg_binary",
    "tempfile",
]
