from conftest import make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.fusion import events_for_query
from video_grounding.models import Query, Window


def test_two_peaks_one_window_two_events():
    st = make_settings()
    w = Window("w00000", 0.0, 60.0, "", 0.0, 1.0, 32)
    r = SyntheticBackend({"q": [(10, 14), (40, 44)]}).ground(w, "q", "x")
    evs = events_for_query([(w, r)], Query("q", "x"), duration=60.0, settings=st, model_revision="r", config_hash="h")
    assert len(evs) == 2
    assert evs[0].event_end_sec < 20 < 30 < evs[1].event_start_sec


def test_min_event_score_drops_weak_events():
    st = make_settings()
    w1, w2 = Window("w1", 0.0, 30.0, "", 0.0, 1.0, 32), Window("w2", 30.0, 60.0, "", 30.0, 1.0, 32)
    pairs = [(w1, SyntheticBackend({"q": [(10, 14)]}, peak=0.95).ground(w1, "q", "x")),
             (w2, SyntheticBackend({"q": [(40, 44)]}, peak=0.6).ground(w2, "q", "x"))]
    for thr, n in ((0.0, 2), (0.9, 1)):
        st.fusion.min_event_score = thr
        evs = events_for_query(pairs, Query("q", "x"), duration=60.0, settings=st, model_revision="r", config_hash="h")
        assert len(evs) == n and evs[0].event_start_sec < 20, (thr, evs)
