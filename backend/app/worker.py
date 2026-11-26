"""Standalone worker process.

Run with::

    python -m app.worker --loop        # production-ish
    python -m app.worker --once        # one job (tests/CI/demo)

The worker is a separate OS process from the API, which is what keeps the HTTP
request that starts a job fast: the API only inserts a row and returns 202.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError

from .adapters.registry import get_adapter
from .config import Settings, get_settings
from .db import SessionLocal
from .errors import ApiError
from .models import JobKind, ProcessingJob
from .services.media import FFmpegClipExtractor, FFmpegMediaProbe
from .services.pipeline import (
    claim_next_job,
    execute_job,
    fail_job_now,
    heartbeat,
    reap_stale_jobs,
    reconcile_search_state,
)
from .services.storage import LocalStorage

logger = logging.getLogger("vlm_annotate.worker")


class JobWorker:
    def __init__(
        self,
        settings: Settings,
        *,
        storage: LocalStorage | None = None,
        probe: FFmpegMediaProbe | None = None,
        extractor: FFmpegClipExtractor | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or LocalStorage(settings.storage_root)
        self.probe = probe or FFmpegMediaProbe(settings.ffmpeg_binary)
        self.extractor = extractor or FFmpegClipExtractor(settings.ffmpeg_binary)

    def run_once(self) -> bool:
        with SessionLocal() as session:
            # Stale = 3 missed beats; a requeued job is then claimed like any other.
            reap_stale_jobs(session, 3 * self.settings.worker_heartbeat_seconds)
            # Repair any SearchVideo/Search row an older write path (or a hard
            # kill) left out of step with its job before picking up new work.
            reconcile_search_state(session)
            job = claim_next_job(session)
            if job is None:
                return False
            stop_beat = threading.Event()
            beat = threading.Thread(
                target=self._beat,
                args=(job.id, job.attempts, stop_beat),
                name=f"heartbeat-job-{job.id}",
                daemon=True,
            )
            beat.start()
            try:
                self._run_claimed(session, job)
            finally:
                stop_beat.set()
                beat.join()
            return True

    def _run_claimed(self, session: Session, job: ProcessingJob) -> None:
        job_id, kind = job.id, job.kind
        adapter = None
        if kind == JobKind.candidate_proposal:
            try:
                adapter = get_adapter(job.adapter_name, self.settings)
            except ApiError as exc:
                fail_job_now(session, job, exc.code, exc.message)
                return
        execute_job(
            session,
            job_id,
            storage=self.storage,
            probe=self.probe,
            extractor=self.extractor,
            adapter=adapter,
            settings=self.settings,
        )
        try:
            status = job.status.value
        except ObjectDeletedError:
            # The job was deleted while it ran (its action or video was deleted).
            status = "deleted"
        logger.info("job %s (%s) finished with status=%s", job_id, kind.value, status)

    def _beat(self, job_id: int, attempts: int, stop: threading.Event) -> None:
        """Touch the job every interval so a long silent adapter step is not reaped."""
        while not stop.wait(self.settings.worker_heartbeat_seconds):
            try:
                with SessionLocal() as session:
                    if not heartbeat(session, job_id, attempts):
                        return  # lost ownership; the main thread learns at its next fence
            except Exception:
                # e.g. SQLite locked: harmless, only 3 missed beats in a row matter.
                logger.warning("heartbeat for job %s failed", job_id, exc_info=True)

    def run_forever(self, stop: threading.Event) -> None:
        logger.info("worker started (poll=%ss)", self.settings.worker_poll_interval_seconds)
        while not stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("worker iteration failed")
                worked = False
            if not worked:
                stop.wait(self.settings.worker_poll_interval_seconds)
        logger.info("worker stopped")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VLM Annotate processing worker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--loop", action="store_true", help="poll for jobs until stopped")
    group.add_argument("--once", action="store_true", help="process at most one job and exit")
    group.add_argument("--drain", action="store_true", help="process queued jobs then exit")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    worker = JobWorker(settings)

    if args.once:
        worker.run_once()
        return 0
    if args.drain:
        while worker.run_once():
            pass
        return 0

    stop = threading.Event()

    def _handle_signal(_signum: int, _frame: object) -> None:
        logger.info("stop signal received")
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    worker.run_forever(stop)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
