import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "heldout_bench.py"


def test_score_fails_when_default_selection_has_no_results(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "score", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not result.stdout
    assert "yc/" in result.stderr and "road/" in result.stderr


def test_score_uses_selection_and_rejects_incomplete_results(tmp_path):
    selection = tmp_path / "selection"
    selection.mkdir()
    for name, video_id in (("youcook2", "cooking"), ("road", "driving")):
        (selection / f"heldout_{name}.json").write_text(json.dumps({"videos": [{"id": video_id}]}))

    out = tmp_path / "output"
    for domain, video_id in (("yc", "cooking"), ("road", "driving"), ("yc", "extra")):
        unit = out / domain / video_id
        run = unit / "custom-run"
        run.mkdir(parents=True)
        (unit / "gt.json").write_text(json.dumps({"events": [
            {"video": video_id, "query_id": "q", "start_sec": 1.0, "end_sec": 3.0},
        ]}))
        (unit / "prompts.json").write_text('[{"query_id":"q"}]')
        (run / "manifest.json").write_text('{"timings":{"scan_s":5.0}}')
        (run / "events.json").write_text(json.dumps({"video_duration_sec": 10.0, "events": [
            {"query_id": "q", "event_start_sec": 1.0, "event_end_sec": 3.0,
             "clip_start_sec": 1.0, "clip_end_sec": 3.0},
        ]}))

    command = [
        sys.executable, str(SCRIPT), "score", str(out), "custom-run",
        "--selection", str(selection),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert set(report) == {"yc", "road"}
    assert all(domain["videos"] == 1 for domain in report.values())
    assert all(domain["before_verify"]["recall"] == [1.0, 1.0, 1.0] for domain in report.values())

    (out / "road" / "driving" / "custom-run" / "events.json").unlink()

    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert not result.stdout
    assert "road/driving" in result.stderr
