import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from conftest import make_info, make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.models import Query
from video_grounding.scheduler import ResumeMismatch, resume, run_scan


class Crash(BaseException):
    """Simulated process death (not swallowed by the retry logic)."""


class CountingBackend(SyntheticBackend):
    def __init__(self, *a, crash_after=None, **k):
        super().__init__(*a, **k)
        self.crash_after, self.n, self.keys = crash_after, 0, Counter()

    def ground(self, window, query_id, query):
        if self.crash_after is not None and self.n >= self.crash_after:
            raise Crash()
        self.n += 1
        self.keys[(query_id, window.sampling_profile, window.source_start_sec, window.source_end_sec)] += 1
        return super().ground(window, query_id, query)


def _setup():
    return make_settings(), make_info(100.0), [Query("q", "x")]


def test_crash_then_resume_grounds_each_window_once(tmp_path):
    st, info, qs = _setup()
    be = CountingBackend({"q": [(40, 46)]}, crash_after=3)
    with pytest.raises(Crash):
        run_scan("v.mp4", qs, st, tmp_path, video_info=info, backend=be)
    be.crash_after = None
    doc = resume(tmp_path, backend=be, video_info=info)
    assert max(be.keys.values()) == 1, "a window was grounded twice"
    lines = [json.loads(x) for x in (tmp_path / "window_predictions.jsonl").read_text().splitlines()]
    assert lines and all(r["status"] == "succeeded" for r in lines)
    assert Counter((r["query_id"], r["sampling_profile"], r["source_start_sec"], r["source_end_sec"]) for r in lines) \
        == be.keys
    assert doc["scan_complete"] and len(doc["events"]) == 1


def test_resume_rejects_changed_config_or_video(tmp_path):
    st, info, qs = _setup()
    be = CountingBackend({"q": [(40, 46)]}, crash_after=2)
    with pytest.raises(Crash):
        run_scan("v.mp4", qs, st, tmp_path, video_info=info, backend=be)
    be.crash_after = None
    with pytest.raises(ResumeMismatch, match="video"):
        resume(tmp_path, backend=be, video_info=make_info(100.0, "other"))
    cfg = Path(tmp_path / "config.yaml")
    d = yaml.safe_load(cfg.read_text())
    d["fusion"]["high"] = 0.3
    cfg.write_text(yaml.safe_dump(d))
    with pytest.raises(ResumeMismatch, match="config"):
        resume(tmp_path, backend=be, video_info=info)
