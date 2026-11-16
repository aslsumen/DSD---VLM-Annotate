import random

import numpy as np

from video_grounding.fusion import fuse, unsupported_modality
from video_grounding.models import GroundingResult, Window


def _pair(wid, start, end, p):
    w = Window(wid, start, end, "", start, 0.5, 16)
    n = 8
    edges = np.linspace(start, end, n + 1)
    pts = (edges[:-1] + edges[1:]) / 2
    r = GroundingResult(wid, "q", "m", (p,) * n, tuple(pts), None, "exact",
                        {"score_bounds": edges.tolist(), "fps_actual": 0.5})
    return w, r


def test_overlap_does_not_inflate():
    pairs = [_pair("a", 0, 30, 0.6), _pair("b", 20, 50, 0.6)]
    f = fuse(pairs, duration=50)
    assert np.allclose(f.score, 0.6)


def test_order_independent():
    pairs = [_pair(f"w{i}", i * 20, i * 20 + 30, 0.1 * (i + 1)) for i in range(4)]
    a = fuse(pairs, duration=110)
    random.Random(1).shuffle(pairs)
    b = fuse(pairs, duration=110)
    assert np.array_equal(a.score, b.score, equal_nan=True)


def test_uncovered_is_nan():
    f = fuse([_pair("a", 0, 10, 0.5)], duration=20)
    assert np.isnan(f.score[-1]) and not np.isnan(f.score[0])


def test_modality_flag():
    assert unsupported_modality("听到有人说话") and unsupported_modality("he says hello")
    assert not unsupported_modality("pick up the cup")


def _fine(wid, start, end, p, fps):
    w, r = _pair(wid, start, end, p)
    w = Window(wid, start, end, "", start, fps, 16)
    return w, GroundingResult(wid, "q", "m", r.probabilities, r.sample_source_pts, None, "exact",
                              {"score_bounds": r.raw_response["score_bounds"], "fps_actual": fps})


def test_denser_sampling_owns_its_span():
    # a coarse window says 0.9 everywhere; a 1 FPS refine window over [10, 20] says 0.1 -> refine wins there
    f = fuse([_pair("w", 0, 30, 0.9), _fine("r", 10, 20, 0.1, 1.0)], duration=30, smooth_cells=1)
    inside = (f.grid > 10.5) & (f.grid < 19.5)
    assert np.allclose(f.score[inside], 0.1) and np.allclose(f.score[f.grid < 9.5], 0.9)


def test_video_edge_is_not_a_window_edge():
    f = fuse([_pair("w", 0, 30, 0.5)], duration=30)
    assert f.max_weight[0] == 1.0 and f.max_weight[-1] == 1.0
