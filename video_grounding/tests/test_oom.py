import json

from conftest import make_info, make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.models import Query
from video_grounding.scheduler import run_scan


def _rows(out):
    return [json.loads(x) for x in (out / "window_predictions.jsonl").read_text().splitlines()]


def test_oom_downgrades_to_8(tmp_path):
    st = make_settings(refine={"enabled": False})
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path, video_info=make_info(60.0),
                   backend=SyntheticBackend({"q": [(20, 25)]}, oom_above_frames=8))
    rows = _rows(tmp_path)
    assert all(r["status"] == "succeeded" and r["max_frames"] == 8 and r["oom_log"] == "16->12;12->8;" for r in rows)
    assert doc["scan_complete"]
    assert json.loads((tmp_path / "metrics.json").read_text())["oom_downgrades"] == 2 * len(rows)


def test_exhausted_ladder_is_coverage_gap_not_no_event(tmp_path):
    st = make_settings(refine={"enabled": False})
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path, video_info=make_info(60.0),
                   backend=SyntheticBackend({"q": [(20, 25)]}, oom_above_frames=2))
    ev = json.loads((tmp_path / "events.json").read_text())
    assert ev["scan_complete"] is False and doc["events"] == []
    assert len(ev["coverage_gaps"]) == len(_rows(tmp_path)) > 0
    assert {"query_id", "window_id", "start_sec", "end_sec", "reason"} <= set(ev["coverage_gaps"][0])


def test_retry_then_succeed_or_fail(tmp_path):
    st = make_settings(refine={"enabled": False})
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path / "a", video_info=make_info(30.0),
                   backend=SyntheticBackend({}, fail_plan={"w00000": 2}))
    assert doc["scan_complete"]
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path / "b", video_info=make_info(30.0),
                   backend=SyntheticBackend({}, fail_plan={"w00000": 3}))
    assert not doc["scan_complete"] and doc["coverage_gaps"][0]["window_id"] == "w00000"
