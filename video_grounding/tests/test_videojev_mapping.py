import pytest

from video_grounding.adapters.videojev import to_result
from video_grounding.models import AlignmentError, Window

W = Window("w1", 100.0, 108.0, "clip.mp4", 100.0, fps=1.0, max_frames=8)
REC = {"frames": 8, "fps": 1.0, "grid_thw": [4, 8, 8], "tokens": 64, "sampled_duration": 8.0,
       "score_times": [0.5, 2.5, 4.5, 6.5], "score_bounds": [[0.0, 2.0], [2.0, 4.0], [4.0, 6.0], [6.0, 8.0]]}  # upstream (n, 2)


def test_global_times():
    pred = {"id": "q", "task": "grounding", "probabilities": [0.1, 0.9, 0.8, 0.2], "interval": [2, 6]}
    r = to_result(W, "q", "videojev", REC, pred, {"inference_ms": 5.0, "peak_vram_bytes": None})
    assert r.sample_source_pts == (100.5, 102.5, 104.5, 106.5)
    assert r.raw_response["score_bounds"] == [100.0, 102.0, 104.0, 106.0, 108.0]
    assert r.predicted_local_interval == (2, 6) and r.alignment_status == "estimated"
    assert r.raw_response["fps_actual"] == 1.0 and r.raw_response["inference_ms"] == 5.0
    assert len(r.raw_response["score_bounds"]) == len(r.probabilities) + 1


def test_length_mismatch():
    with pytest.raises(AlignmentError):
        to_result(W, "q", "videojev", REC, {"probabilities": [0.1, 0.2, 0.3], "interval": None})
