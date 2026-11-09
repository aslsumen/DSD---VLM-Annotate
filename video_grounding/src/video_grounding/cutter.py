"""Re-encoding cutters. Times are GLOBAL seconds (0.0 = first video frame, see models.py).

ffmpeg input `-ss` is relative to the container's start_time (min over all streams), not to the
video stream's start_time and not to 0, so global G is sought at G + (video_start - format_start).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from functools import lru_cache

from .models import VideoInfo


class CutError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _passthrough_args() -> tuple[str, ...]:
    """Keep source frame timing (no cfr dup/drop). `-fps_mode` needs ffmpeg >= 5.1, else `-vsync 0`."""
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    m = re.search(r"version n?(\d+)\.(\d+)", out)
    old = bool(m) and (int(m[1]), int(m[2])) < (5, 1)  # git builds ("N-123-g...") count as new
    return ("-vsync", "0") if old else ("-fps_mode", "passthrough")


def _ffprobe(args: list[str]) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise CutError(f"ffprobe failed: {r.stderr.strip()[-500:]}")
    return json.loads(r.stdout)


def _seek_sec(src: str, global_sec: float, info: VideoInfo) -> float:
    fmt_start = float(_ffprobe(["-show_entries", "format=start_time", src])["format"].get("start_time") or 0)
    return max(0.0, global_sec + info.start_time_sec - fmt_start)


def first_pts(path: str) -> float:
    """Smallest video packet pts (seconds) of a file. Packet pts_time exists in ffmpeg 4.4 and 8."""
    out = _ffprobe(["-select_streams", "v:0", "-show_entries", "packet=pts_time",
                    "-read_intervals", "%+#10", path])
    pts = [float(p["pts_time"]) for p in out.get("packets", []) if "pts_time" in p]
    if not pts:
        raise CutError(f"no video packets in {path}")
    return min(pts)


def _encode(cmd: list[str], out_path: str) -> str:
    """Run ffmpeg into a temp file next to out_path, then atomically replace out_path (temp removed on failure)."""
    d = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=os.path.splitext(out_path)[1] or ".mp4")
    os.close(fd)
    try:
        r = subprocess.run([*cmd, "-y", tmp], capture_output=True, text=True)
        if r.returncode:
            raise CutError(f"ffmpeg failed ({r.returncode}): {r.stderr.strip()[-800:]}")
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return out_path


def cut_window_clip(src: str, start_sec: float, end_sec: float, out_path: str,
                    info: VideoInfo, max_height: int = 720) -> float:
    """Video-only re-encode of global [start, end]; returns the measured global time of its first frame."""
    start = max(0.0, start_sec)
    if end_sec <= start:
        raise CutError(f"empty window [{start_sec}, {end_sec}]")
    scale = f"scale=-2:trunc(min({int(max_height)}\\,ih)/2)*2"  # ih is post-autorotate (display) height
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{_seek_sec(src, start, info):.6f}", "-i", src,
           "-t", f"{end_sec - start:.6f}", "-map", "0:v:0", "-an", "-vf", scale,
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
           *_passthrough_args(), "-enc_time_base", "1:90000", "-movflags", "+faststart"]
    # Output pts of the first frame = its offset from the seek point, so origin = start + that offset.
    # (Encoder time base is 1/90000: the default 1/fps would round pts onto a frame grid.)
    return start + first_pts(_encode(cmd, out_path))


def export_event_clip(src: str, clip_start_sec: float, clip_end_sec: float, out_path: str,
                      info: VideoInfo, crf: int = 20, preset: str = "fast") -> None:
    """Deliverable clip of global [start, end]: libx264 (+aac when the source has audio). Never touches src."""
    start = max(0.0, clip_start_sec)
    if clip_end_sec <= start:
        raise CutError(f"empty clip [{clip_start_sec}, {clip_end_sec}]")
    audio = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"] if info.has_audio else ["-an"]
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{_seek_sec(src, start, info):.6f}", "-i", src,
           "-t", f"{clip_end_sec - start:.6f}", "-map", "0:v:0", *audio,
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-movflags", "+faststart"]
    _encode(cmd, out_path)
