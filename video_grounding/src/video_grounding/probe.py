"""ffprobe -> VideoInfo. Global time = video stream PTS - stream start_time (0.0 = first frame)."""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
from fractions import Fraction

from .models import VideoInfo


class ProbeError(RuntimeError):
    pass


def _run(args: list[str]) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise ProbeError(f"ffprobe failed: {r.stderr.strip()[-500:]}")
    return json.loads(r.stdout)


def _rate(s: str | None) -> float:
    try:
        return float(Fraction(s)) if s else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _num(v, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rotation(stream: dict) -> int:
    """Clockwise degrees needed to display the stream upright, in {0, 90, 180, 270}."""
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:  # display matrix: counter-clockwise degrees
            return round(-float(sd["rotation"]) / 90) * 90 % 360
    r = _num(stream.get("tags", {}).get("rotate"))
    return round(r / 90) * 90 % 360 if r is not None else 0


def fingerprint(path: str) -> str:
    st = os.stat(path)
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        f.seek(max(0, st.st_size - (1 << 20)))
        h.update(f.read(1 << 20))
    return f"{st.st_size}:{st.st_mtime_ns}:{h.hexdigest()}"


def _irregular(path: str, index: int) -> bool:
    """Packet-pts spacing check on the first ~300 packets (catches VFR that rates hide)."""
    out = _run(["-select_streams", str(index), "-show_entries", "packet=pts_time",
                "-read_intervals", "%+#300", path])
    pts = sorted(p for p in (_num(x.get("pts_time")) for x in out.get("packets", [])) if p is not None)
    deltas = [b - a for a, b in zip(pts, pts[1:])]
    if len(deltas) < 3:
        return False
    med = statistics.median(deltas)
    return any(abs(d - med) > max(0.1 * med, 0.002) for d in deltas)


def probe_video(path: str) -> VideoInfo:
    data = _run(["-show_streams", "-show_format", path])
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic", 0) != 1), None)
    if video is None:
        raise ProbeError(f"no video stream in {path}")
    fmt = data.get("format", {})
    rot = _rotation(video)
    w, h = int(video["width"]), int(video["height"])
    if rot in (90, 270):
        w, h = h, w
    start = _num(video.get("start_time"), 0.0)
    duration = _num(video.get("duration"))
    if duration is None:
        fmt_dur = _num(fmt.get("duration"))
        if fmt_dur is None:
            raise ProbeError(f"cannot determine duration of {path}")
        duration = fmt_dur - (start - _num(fmt.get("start_time"), 0.0))
    r_rate, avg_rate = _rate(video.get("r_frame_rate")), _rate(video.get("avg_frame_rate"))
    vfr = abs(r_rate - avg_rate) > 0.005 * max(r_rate, avg_rate, 1e-9) or _irregular(path, video["index"])
    return VideoInfo(
        path=path, duration_sec=duration, fps=avg_rate or r_rate, time_base=video.get("time_base", ""),
        stream_index=int(video["index"]), width=w, height=h, rotation=rot,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        start_time_sec=start, is_vfr=vfr, fingerprint=fingerprint(path))
