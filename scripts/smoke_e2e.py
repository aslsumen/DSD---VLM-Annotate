"""Real end-to-end smoke test with actual ffmpeg probing and clip extraction.

Unlike the pytest suite (which injects a fake extractor for speed), this script
synthesises a real H.264/AAC video, drives the HTTP API in-process, lets the
real worker probe the video and cut preview clips, reviews candidates, exports a
dataset ZIP and inspects the archive.  It writes a JSON evidence file.

Usage (from the repository root, Windows):

    .\.venv\Scripts\python.exe scripts\smoke_e2e.py

Exit code 0 = every check passed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

WORKSPACE = Path(tempfile.mkdtemp(prefix="vlm-annotate-smoke-"))
os.environ["VLM_DATA_DIR"] = str(WORKSPACE / "data")
os.environ["VLM_DATABASE_URL"] = f"sqlite:///{(WORKSPACE / 'smoke.db').as_posix()}"
os.environ["VLM_ENVIRONMENT"] = "smoke"

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.media import FFmpegMediaProbe, resolve_ffmpeg_binary  # noqa: E402
from app.worker import JobWorker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS: list[dict[str, object]] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    CHECKS.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})
    if not condition:
        raise AssertionError(f"{name} failed: {detail}")


def make_video(path: Path, seconds: int = 120) -> None:
    ffmpeg = resolve_ffmpeg_binary(get_settings().ffmpeg_binary)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=640x360:rate=25:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    subprocess.run(command, check=True, capture_output=True)


def main() -> int:
    started = time.time()
    video_path = WORKSPACE / "synthetic_2min.mp4"
    make_video(video_path, seconds=120)
    check("ffmpeg produced a source video", video_path.stat().st_size > 10_000,
          {"bytes": video_path.stat().st_size})

    settings = get_settings()
    Base.metadata.create_all(bind=db.engine)
    app = create_app(settings)
    worker = JobWorker(settings)
    probe = FFmpegMediaProbe(settings.ffmpeg_binary)

    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects",
            json={"name": "Smoke project", "description": "generated synthetic footage"},
        ).json()
        action = client.post(
            f"/api/v1/projects/{project['id']}/actions",
            json={
                "name": "person waves",
                "description": "a person waves at the camera with their right hand",
            },
        ).json()

        with video_path.open("rb") as handle:
            upload = client.post(
                f"/api/v1/projects/{project['id']}/videos",
                files={"file": (video_path.name, handle, "video/mp4")},
            )
        check("upload accepted", upload.status_code == 201, upload.text[:300])
        video = upload.json()
        check(
            "real ffmpeg probe found the duration",
            abs((video["duration_seconds"] or 0) - 120.0) < 1.0,
            video["duration_seconds"],
        )

        job = client.post(f"/api/v1/videos/{video['id']}/jobs", json={"action_id": action["id"]})
        check("job accepted asynchronously (202)", job.status_code == 202, job.text[:300])
        job_id = job.json()["id"]

        check("worker processed one job", worker.run_once() is True)
        finished = client.get(f"/api/v1/jobs/{job_id}").json()
        check("job succeeded", finished["status"] == "succeeded", finished)

        candidates = client.get(f"/api/v1/jobs/{job_id}/candidates").json()
        check("candidates returned", 3 <= len(candidates) <= 6, len(candidates))
        for candidate in candidates:
            check(
                f"candidate {candidate['id']} interval inside the source video",
                0 <= candidate["start_seconds"] < candidate["end_seconds"] <= 120,
                [candidate["start_seconds"], candidate["end_seconds"]],
            )
        check(
            "all preview clips extracted with real ffmpeg",
            all(c["clip_status"] == "ready" for c in candidates),
            [c["clip_status"] for c in candidates],
        )

        clip = client.get(f"/api/v1/candidates/{candidates[0]['id']}/clip")
        check("clip endpoint serves mp4 bytes", clip.status_code == 200 and len(clip.content) > 1000,
              {"status": clip.status_code, "bytes": len(clip.content)})

        # Verify the extracted clip is itself a decodable video of the expected length.
        clip_path = WORKSPACE / "first_clip.mp4"
        clip_path.write_bytes(clip.content)
        metadata = probe.probe(clip_path)
        expected = candidates[0]["preview_end_seconds"] - candidates[0]["preview_start_seconds"]
        check(
            "extracted clip is decodable and has the expected duration",
            abs(metadata.duration_seconds - expected) <= 1.0,
            {"clip_duration": metadata.duration_seconds, "expected": round(expected, 3)},
        )

        first = candidates[0]
        corrected_start = round(first["start_seconds"] + 0.5, 3)
        corrected_end = round(min(first["end_seconds"], corrected_start + 3.0), 3)
        annotation = client.put(
            f"/api/v1/candidates/{first['id']}/annotation",
            json={
                "verdict": "true_positive",
                "corrected_start_seconds": corrected_start,
                "corrected_end_seconds": corrected_end,
                "reviewer": "smoke-script",
                "note": "synthetic check",
            },
        )
        check("annotation stored", annotation.status_code == 200, annotation.text[:300])

        export = client.post(f"/api/v1/projects/{project['id']}/exports", json={})
        check("export queued", export.status_code == 202, export.text[:300])
        export_id = export.json()["export"]["id"]
        check("worker processed the export", worker.run_once() is True)
        export_state = client.get(f"/api/v1/exports/{export_id}").json()
        check("export ready", export_state["status"] == "ready", export_state)
        check("export contains exactly the reviewed item", export_state["item_count"] == 1,
              export_state["item_count"])

        download = client.get(f"/api/v1/exports/{export_id}/download")
        check("export downloadable", download.status_code == 200)
        archive_path = WORKSPACE / "dataset.zip"
        archive_path.write_bytes(download.content)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        item = manifest["items"][0]
        check("archive has manifest, labels and clip", {"manifest.json", "labels.csv"} <= set(names),
              names)
        check("archive carries the corrected boundaries",
              item["final"]["start_seconds"] == corrected_start
              and item["final"]["end_seconds"] == corrected_end,
              item["final"])
        check("archive preserves the model proposal separately",
              item["proposal"]["start_seconds"] == first["start_seconds"])
        check("provenance labels the mock adapter", item["provenance"]["mock"] is True)
        clip_names = [name for name in names if name.startswith("clips/")]
        check("one clip inside the archive", len(clip_names) == 1, clip_names)
        clip_bytes = archive.read(clip_names[0])
        check("archived clip is non-trivial", len(clip_bytes) > 1000, len(clip_bytes))

    passed = sum(1 for c in CHECKS if c["status"] == "PASS")
    evidence = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": "windows-local",
        "workspace": str(WORKSPACE),
        "duration_seconds": round(time.time() - started, 2),
        "checks_passed": passed,
        "checks_total": len(CHECKS),
        "checks": CHECKS,
        "note": (
            "Candidate intervals come from the deterministic MOCK adapter: no pixels were "
            "analysed. Probe, clip extraction, annotation, export and archive verification "
            "are real."
        ),
    }
    evidence_dir = ROOT / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    evidence_path = evidence_dir / f"smoke-e2e-{stamp}.json"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    print(f"\nchecks: {passed}/{len(CHECKS)} passed")
    print(f"evidence: {evidence_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
