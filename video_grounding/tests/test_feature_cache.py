import os

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from video_grounding.adapters.videojev import VideoJevBackend  # noqa: E402
from video_grounding.feature_cache import FeatureCache  # noqa: E402
from video_grounding.models import Window  # noqa: E402


def feats(seed: int = 0, n: int = 4) -> "torch.Tensor":
    g = torch.Generator().manual_seed(seed)
    return torch.randn(n, 8, generator=g).to(torch.bfloat16)


def test_round_trip(tmp_path):
    c = FeatureCache(tmp_path / "c", 10**9)
    f, rec = feats(), {"frames": 4, "fps": np.float64(1.5), "grid_thw": [2, 4, 4], "score_times": [0.5]}
    c.put("k", f, rec)
    hit = c.get("k")
    assert torch.equal(hit["features"], f) and hit["features"].dtype == torch.bfloat16
    assert hit["device"] == "cpu" and hit["record"] == {**rec, "fps": 1.5}


def test_unknown_key(tmp_path):
    assert FeatureCache(tmp_path, 10**9).get("nope") is None


@pytest.mark.parametrize("truncate", [False, True])
def test_corrupt_file_is_dropped(tmp_path, truncate):
    c = FeatureCache(tmp_path, 10**9)
    p = tmp_path / "k.pt"
    if truncate:
        c.put("k", feats(), {})
        p.write_bytes(p.read_bytes()[:40])
    else:
        p.write_bytes(b"garbage bytes")
    assert c.get("k") is None
    assert not p.exists()


def test_eviction_is_lru(tmp_path):
    probe = FeatureCache(tmp_path / "probe", 10**9)
    probe.put("x", feats(), {})
    size = (tmp_path / "probe" / "x.pt").stat().st_size
    c = FeatureCache(tmp_path / "c", int(size * 3.5))
    for i, k in enumerate("abc"):
        c.put(k, feats(i), {})
        os.utime(tmp_path / "c" / f"{k}.pt", (1000 + i, 1000 + i))
    assert c.get("a") is not None  # refreshes a: b is now the oldest
    c.put("d", feats(9), {})
    names = {p.name for p in (tmp_path / "c").iterdir()}
    assert names == {"a.pt", "c.pt", "d.pt"}
    assert sum(p.stat().st_size for p in (tmp_path / "c").iterdir()) <= size * 3.5


def test_put_failure_never_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    FeatureCache(blocker / "sub", 10**9).put("k", feats(), {})  # root cannot be created


# --- backend with a fake model ---

REC = {"frames": 2, "fps": 1.0, "grid_thw": [1, 2, 2], "tokens": 4, "sampled_duration": 4.0,
       "score_times": [0.5, 2.5], "score_bounds": [[0.0, 2.0], [2.0, 4.0]]}


class FakeModel:
    def __init__(self):
        self.encodes = 0

    def encode_video(self, pixels, grid):
        self.encodes += 1
        return pixels * 2

    def predict_features(self, processor, features, record, questions, context, threshold):
        s = features.float().sum(dim=1)[:2]
        return [{"probabilities": torch.sigmoid(s).tolist(), "interval": None}]


def make_backend(cache, **kw):
    b = VideoJevBackend(**{"model_path": "p", "model_id": "m", "model_revision": "rev", **kw}, feature_cache=cache)
    b._model, b._processor = FakeModel(), object()
    b._prepare_video = lambda proc, path, fps, max_frames, context: (feats(7, 2), dict(REC))
    return b


def window(tmp_path, data=b"clip-bytes", fps=1.0, max_frames=8):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(data)
    return Window("w", 0.0, 4.0, str(clip), 0.0, fps=fps, max_frames=max_frames)


def test_backend_memory_then_disk(tmp_path):
    cache = FeatureCache(tmp_path / "c", 10**9)
    w = window(tmp_path)
    b = make_backend(cache)
    r1, r2 = b.ground(w, "q1", "a"), b.ground(w, "q2", "b")
    assert b._model.encodes == 1
    assert (r1.raw_response["feature_source"], r2.raw_response["feature_source"]) == ("encoded", "memory")
    b2 = make_backend(cache)
    r3 = b2.ground(w, "q3", "c")
    assert b2._model.encodes == 0 and r3.raw_response["feature_source"] == "disk"
    assert r3.probabilities == r1.probabilities


def test_backend_no_cache(tmp_path):
    b = make_backend(None)
    w = window(tmp_path)
    assert b.ground(w, "q", "a").raw_response["feature_source"] == "encoded"
    assert b.ground(w, "q", "a").raw_response["feature_source"] == "memory"


@pytest.mark.parametrize("change", [
    {"data": b"other-bytes"}, {"fps": 2.0}, {"max_frames": 9},
    {"context_tokens": 4096}, {"model_revision": "rev2"}, {"attn_implementation": "sdpa"}])
def test_each_key_part_forces_reencode(tmp_path, change):
    cache = FeatureCache(tmp_path / "c", 10**9)
    make_backend(cache).ground(window(tmp_path), "q", "a")
    w_kw = {k: v for k, v in change.items() if k in ("data", "fps", "max_frames")}
    b_kw = {k: v for k, v in change.items() if k not in w_kw}
    b = make_backend(cache, **b_kw)
    r = b.ground(window(tmp_path, **w_kw), "q", "a")
    assert b._model.encodes == 1 and r.raw_response["feature_source"] == "encoded"
