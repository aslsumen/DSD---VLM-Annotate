from conftest import make_info, make_settings
from video_grounding.adapters.base import SyntheticBackend
from video_grounding.models import Query
from video_grounding.scheduler import export, resume, run_scan
from video_grounding.settings import config_hash

GT = [(100, 104), (300, 310), (885, 915)]


class FakeVerifier:
    """Rejects the event at 300 s, fails once on the event at 885 s, confirms the rest."""

    def __init__(self):
        self.calls, self.failed = [], False

    def verify(self, video, info, start, end, query):
        self.calls.append(start)
        if 880 < start < 900 and not self.failed:
            self.failed = True
            raise RuntimeError("429")
        return {"present": not 290 < start < 310, "confidence": 0.9, "reason": "fake", "model": "fake"}


def _by_start(doc):
    return {round(e["event_start_sec"] / 100) * 100: e for e in doc["events"]}


def test_verify_flags_and_caches(tmp_path):
    st = make_settings(verify={"enabled": True})
    assert config_hash(st) == config_hash(make_settings())  # verify settings never block resume
    fake = FakeVerifier()
    doc = run_scan("v.mp4", [Query("q", "x")], st, tmp_path, video_info=make_info(1800.0),
                   backend=SyntheticBackend({"q": GT}), verifier=fake)
    evs = _by_start(doc)
    assert len(evs) == 3 and len(fake.calls) == 3
    assert evs[100]["verdict"]["present"] and "verifier_rejected" not in evs[100]["review_reasons"]
    assert "verifier_rejected" in evs[300]["review_reasons"] and evs[300]["needs_review"]
    assert evs[900]["verdict"] is None and "not_verified" in evs[900]["review_reasons"]

    doc = resume(tmp_path, backend=SyntheticBackend({"q": GT}), video_info=make_info(1800.0), verifier=fake)
    assert len(fake.calls) == 4  # only the failed event is retried
    assert _by_start(doc)[900]["verdict"]["present"]
    assert export(tmp_path)["events"][0]["verdict"] is not None and len(fake.calls) == 4  # export: no API calls
