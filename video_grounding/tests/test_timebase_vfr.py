import pytest
from _media import frame_ids, make_video, needs_ffmpeg, run, stream_info, video_pts

from video_grounding.cutter import cut_window_clip
from video_grounding.probe import ProbeError, probe_video

pytestmark = needs_ffmpeg


def test_cfr_probe_and_cut(tmp_path):
    src = make_video(tmp_path / "cfr.mp4")
    info = probe_video(src)
    assert (info.width, info.height, info.rotation) == (160, 96, 0)
    assert info.fps == 25 and not info.is_vfr and not info.has_audio and info.start_time_sec == 0
    assert info.duration_sec == pytest.approx(10, abs=0.05)
    assert info.fingerprint.split(":")[0] == str(tmp_path.joinpath("cfr.mp4").stat().st_size)
    out = tmp_path / "c.mp4"
    origin = cut_window_clip(src, 2.01, 4.0, str(out), info, max_height=48)
    assert origin == pytest.approx(2.04, abs=0.002) and frame_ids(out)[0] == 51  # first frame at/after 2.01
    assert (stream_info(out)["width"], stream_info(out)["height"]) == (80, 48)  # scaled down, aspect kept
    cut_window_clip(src, 0, 1.0, str(out), info)  # never upscale
    assert stream_info(out)["height"] == 96 and frame_ids(out)[0] == 0


def test_vfr_origin_is_true_pts(tmp_path):
    # 40 ms spacing for 125 frames (to 5.0 s), then 100 ms spacing
    src = make_video(tmp_path / "vfr.mp4", setpts="if(lt(N,125),N/25,5+(N-125)/10)/TB",
                     extra_out=["-frames:v", "175"])
    info = probe_video(src)
    assert info.is_vfr
    pts = video_pts(src)
    out = tmp_path / "c.mp4"
    for start in (3.03, 5.03, 6.0):
        want = next(i for i, p in enumerate(pts) if p >= start - 1e-6)
        origin = cut_window_clip(src, start, start + 1.5, str(out), info)
        assert origin == pytest.approx(pts[want], abs=0.002)
        assert frame_ids(out)[0] == want  # same frame, not a cfr-shifted neighbour


def test_rotation_metadata(tmp_path):
    base = make_video(tmp_path / "base.mp4", dur=3)
    rot = str(tmp_path / "rot.mp4")
    expected = {270}
    try:
        run("-display_rotation", "90", "-i", base, "-c", "copy", rot)  # ffmpeg >= 6; 90 = counter-clockwise
    except RuntimeError:
        try:
            run("-i", base, "-c", "copy", "-metadata:s:v", "rotate=270", rot)  # older ffmpeg
        except RuntimeError:
            pytest.skip("cannot create rotated video with this ffmpeg")
        # ffmpeg 4.4's muxer writes rotate=270 as a 90° clockwise matrix (ffprobe: tag 90, matrix -90),
        # so the sign of the written file is muxer-dependent; only the 90° axis swap is certain here.
        expected = {90, 270}
    info = probe_video(rot)
    if info.rotation == 0:
        pytest.skip("rotation metadata not written by this ffmpeg")
    assert info.rotation in expected and (info.width, info.height) == (96, 160)
    out = tmp_path / "c.mp4"
    cut_window_clip(rot, 0.5, 1.5, str(out), info)
    assert (stream_info(out)["width"], stream_info(out)["height"]) == (96, 160)  # upright, display dims


def test_nonzero_start_time_uses_global_seconds(tmp_path):
    # mpegts + audio: video starts ~6.6 s, container start (audio) differs from the video start
    src = make_video(tmp_path / "off.ts", audio=True, extra_out=["-output_ts_offset", "5.2"])
    info = probe_video(src)
    assert info.start_time_sec > 5 and info.has_audio
    out = tmp_path / "c.mp4"
    assert cut_window_clip(src, 0, 1.0, str(out), info) == pytest.approx(0.0, abs=0.002)
    assert frame_ids(out)[0] == 0
    assert cut_window_clip(src, 2.02, 3.0, str(out), info) == pytest.approx(2.04, abs=0.002)  # ss=2.02 relative to video start would give frame 50
    assert frame_ids(out)[0] == 51


def test_no_video_stream(tmp_path):
    run("-f", "lavfi", "-i", "sine=duration=1", str(tmp_path / "a.wav"))
    with pytest.raises(ProbeError):
        probe_video(str(tmp_path / "a.wav"))
