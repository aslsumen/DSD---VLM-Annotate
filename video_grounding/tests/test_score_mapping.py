import pytest

from video_grounding.adapters.base import SyntheticBackend
from video_grounding.models import AlignmentError, GroundingResult, Window


def test_length_mismatch_raises():
    with pytest.raises(AlignmentError):
        GroundingResult("w", "q", "m", (0.1, 0.2), (1.0,), None, "exact")


def test_synthetic_pts_are_clip_origin_plus_pair_centers():
    w = Window("w", 100.0, 130.0, "", 100.3, 0.5, 16)
    r = SyntheticBackend({}).ground(w, "q", "x")
    # 15 frames at 0,2,..,28 -> pairs (0,2)(4,6)..(24,26)(28,28) -> centers 1,5,..,25,28 (not i/fps)
    assert r.sample_source_pts == pytest.approx(tuple(100.3 + c for c in (1, 5, 9, 13, 17, 21, 25, 28)))
    b = r.raw_response["score_bounds"]
    assert len(b) == len(r.probabilities) + 1 and b[0] == pytest.approx(100.3) and b[-1] == pytest.approx(130.3)


def test_over_cap_uses_uniform_fps():
    w = Window("w", 0.0, 30.0, "", 0.0, 0.5, 8)
    r = SyntheticBackend({}).ground(w, "q", "x")
    assert r.raw_response["frames"] == 8 and len(r.probabilities) == 4
    assert r.raw_response["fps_actual"] == pytest.approx(8 / 30)
