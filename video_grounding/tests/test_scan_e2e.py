import json

from conftest import make_info, make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.evaluation import evaluate
from video_grounding.models import Query
from video_grounding.scheduler import run_scan

GT = [(100, 104), (300, 310), (330, 340), (885, 915), (1792, 1800)]


def test_30min_scan(tmp_path):
    st = make_settings()
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path, video_info=make_info(1800.0),
                   backend=SyntheticBackend({"q": GT}))
    assert doc["scan_complete"] and doc["coverage_gaps"] == []
    evs = sorted(doc["events"], key=lambda e: e["event_start_sec"])
    assert len(evs) == 5, [(e["event_start_sec"], e["event_end_sec"]) for e in evs]
    r = evaluate(doc, {"events": [{"query_id": "q", "start_sec": s, "end_sec": e} for s, e in GT]})
    assert r["R@IoU0.5"] == 1.0 and r["event_precision"] == 1.0, r
    assert "touches_video_end" in evs[-1]["review_reasons"]
    assert (tmp_path / "events.json").exists() and (tmp_path / "manifest.json").exists()
    assert any(json.loads(x)["sampling_profile"] == "refine"
               for x in (tmp_path / "window_predictions.jsonl").read_text().splitlines())
