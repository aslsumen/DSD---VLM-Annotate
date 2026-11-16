import numpy as np
import pytest

from video_grounding.evaluation import evaluate


def _ev(q, s, e):
    return {"query_id": q, "event_start_sec": s, "event_end_sec": e}


def test_known_ious():
    pred = {"events": [_ev("a", 0, 10), _ev("a", 20, 30), _ev("a", 50, 60), _ev("b", 0, 10)],
            "coverage_gaps": [{"x": 1}]}
    gt = {"events": [{"query_id": "a", "start_sec": 2, "end_sec": 10},     # IoU 0.8 with pred 0
                     {"query_id": "a", "start_sec": 25, "end_sec": 35},    # IoU 5/15=0.333 with pred 1
                     {"query_id": "a", "start_sec": 100, "end_sec": 110},  # unmatched
                     {"query_id": "b", "start_sec": 0, "end_sec": 4}]}     # IoU 0.4 (other query ignored for a)
    r = evaluate(pred, gt)
    assert r["R@IoU0.3"] == pytest.approx(3 / 4) and r["R@IoU0.5"] == pytest.approx(1 / 4)
    assert r["R@IoU0.7"] == pytest.approx(1 / 4)
    assert r["event_recall"] == pytest.approx(3 / 4) and r["event_precision"] == pytest.approx(3 / 4)
    assert r["temporal_miou"] == pytest.approx((0.8 + 5 / 15 + 0 + 0.4) / 4)
    assert r["start_err_p50"] == pytest.approx(2.0) and r["coverage_gaps"] == 1


def test_one_to_one():
    pred = {"events": [_ev("a", 0, 10)]}
    gt = {"events": [{"query_id": "a", "start_sec": 0, "end_sec": 10}, {"query_id": "a", "start_sec": 0, "end_sec": 9}]}
    assert evaluate(pred, gt)["event_recall"] == pytest.approx(0.5)


def test_review_metrics():
    from video_grounding.evaluation import evaluate_review

    e = lambda i, q, s, t: {"event_id": i, "query_id": q, "event_start_sec": s, "event_end_sec": t,  # noqa: E731
                            "clip_start_sec": s - 0.5, "clip_end_sec": t + 0.5}
    pred = {"events": [e("a", "q1", 0, 10), e("b", "q1", 20, 30), e("c", "q2", 40, 50), e("d", "q2", 60, 70)]}
    reviews = [{"event_id": "a", "accepted": True},                                  # unchanged -> inside clip
               {"event_id": "b", "accepted": True, "start_sec": 18, "end_sec": 30},  # extended past the clip
               {"event_id": "c", "accepted": False}]                                 # d not reviewed yet
    r = evaluate_review(pred, reviews)
    assert r["n_reviewed"] == 3 and r["accept_rate"] == pytest.approx(2 / 3)
    assert r["complete_clip_rate"] == pytest.approx(1.0)  # b misses 1.5 s: within the default 2 s tolerance
    assert evaluate_review(pred, reviews, tolerance_sec=0)["complete_clip_rate"] == pytest.approx(0.5)
    assert r["per_query"]["q2"] == {"reviewed": 1, "accepted": 0, "accept_rate": 0.0}
    assert r["boundary_adjust_p90"] == pytest.approx(np.percentile([0, 2, 0, 0], 90))
    with pytest.raises(ValueError):
        evaluate_review(pred, [{"event_id": "zz", "accepted": True}])
