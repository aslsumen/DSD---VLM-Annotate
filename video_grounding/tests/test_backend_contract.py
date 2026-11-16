import json

from conftest import make_info, make_settings
from video_grounding.adapters.base import GroundingBackend, ReplayBackend, SyntheticBackend, make_backend
from video_grounding.models import Query
from video_grounding.scheduler import export, run_scan

KEYS = ("query_id", "event_start_sec", "event_end_sec", "clip_start_sec", "clip_end_sec", "review_reasons",
        "raw_score_max", "evidence_window_ids", "alignment_status")


def _strip(doc):
    return [{k: e[k] for k in KEYS} for e in doc["events"]]


def test_replay_reproduces_synthetic_job(tmp_path):
    st, info, qs = make_settings(), make_info(120.0), [Query("q", "x")]
    be = SyntheticBackend({"q": [(30, 36), (90, 95)]})
    assert isinstance(be, GroundingBackend)
    doc = run_scan("v.mp4", qs, st, tmp_path / "a", video_info=info, backend=be)
    assert len(doc["events"]) == 2
    rb = ReplayBackend(tmp_path / "a" / "window_predictions.jsonl")
    assert isinstance(rb, GroundingBackend) and rb.model_revision == "synthetic-v1" and not rb.needs_clip
    doc2 = run_scan("v.mp4", qs, st, tmp_path / "b", video_info=info, backend=rb)
    assert _strip(doc2) == _strip(doc)


def test_make_backend_and_export_without_model_calls(tmp_path):
    assert isinstance(make_backend(make_settings()), SyntheticBackend)
    st, info, qs = make_settings(), make_info(60.0), [Query("q", "x")]
    run_scan("v.mp4", qs, st, tmp_path, video_info=info, backend=SyntheticBackend({"q": [(20, 26)]}))
    assert len(export(tmp_path)["events"]) == 1
    assert export(tmp_path, high=0.99)["events"] == []  # raw peak ~0.8 never reaches 0.99
    assert json.loads((tmp_path / "events.json").read_text())["events"] == []
