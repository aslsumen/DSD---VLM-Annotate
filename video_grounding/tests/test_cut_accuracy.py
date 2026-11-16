import hashlib

import pytest
from _media import frame_ids, make_video, needs_ffmpeg

from video_grounding.cutter import CutError, export_event_clip
from video_grounding.probe import probe_video

pytestmark = needs_ffmpeg


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


@pytest.mark.parametrize("audio", [False, True])
def test_export_event_clip(tmp_path, audio):
    src = make_video(tmp_path / "src.mp4", dur=20, audio=audio)
    info = probe_video(src)
    assert info.has_audio is audio
    before = _sha(src)
    out = tmp_path / "out" / "e.mp4"
    export_event_clip(src, 3.0, 8.0, str(out), info)
    assert _sha(src) == before
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["e.mp4", "src.mp4"]  # no temp left
    dst = probe_video(str(out))
    assert dst.duration_sec == pytest.approx(5.0, abs=1 / 25 + 0.05)  # one frame + aac padding
    assert dst.has_audio is audio
    assert frame_ids(out)[0] == 75  # frame at 3.0 s


def test_failure_leaves_nothing(tmp_path):
    src = make_video(tmp_path / "src.mp4", dur=3)
    info = probe_video(src)
    with pytest.raises(CutError):
        export_event_clip(src, 2.0, 1.0, str(tmp_path / "e.mp4"), info)
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(CutError):
        export_event_clip(str(bad), 0, 1.0, str(tmp_path / "e.mp4"), info)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.mp4", "src.mp4"]
