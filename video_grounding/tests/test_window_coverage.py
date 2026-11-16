import pytest

from video_grounding.sampler import plan_windows


@pytest.mark.parametrize("dur", [7, 30, 31, 600, 1799.3, 1800])
def test_covers_without_gaps(dur):
    w = plan_windows(dur, 30, 20)
    assert w[0][0] == 0 and w[-1][1] == pytest.approx(dur)
    assert all(b[0] <= a[1] for a, b in zip(w, w[1:]))  # next starts before previous ends
    assert all(e - s <= 30 + 1e-9 for s, e in w)


def test_1800_is_90_windows():
    assert len(plan_windows(1800, 30, 20)) == 90
