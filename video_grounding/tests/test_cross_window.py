from conftest import make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.fusion import events_for_query
from video_grounding.models import Query, Window
from video_grounding.sampler import plan_windows


def test_event_spanning_window_boundary_is_single():
    st, be = make_settings(), SyntheticBackend({"q": [(25, 38)]})
    pairs = []
    for i, (s, e) in enumerate(plan_windows(100, 30, 20)):
        w = Window(f"w{i:05d}", s, e, "", s, 2.0, 64)  # 1 s cells: coarse 4 s cells cannot give ~1 s bounds
        pairs.append((w, be.ground(w, "q", "x")))
    evs = events_for_query(pairs, Query("q", "x"), duration=100.0, settings=st, model_revision="r", config_hash="h")
    assert len(evs) == 1
    assert abs(evs[0].event_start_sec - 25) < 1.5 and abs(evs[0].event_end_sec - 38) < 1.5
