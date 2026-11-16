"""Synthetic-video helpers: each frame's index N is encoded as brightness (two hex digits)."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from video_grounding.cutter import _passthrough_args

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg/ffprobe not installed")
# low hex digit of N in the left half, high digit in the right half; steps of 14 luma levels
ID_SRC = ("color=c=black:s=160x96:r=25:d={d},geq=lum='if(lt(X,W/2),16+mod(N,16)*14,"
          "16+mod(floor(N/16),16)*14)':cb=128:cr=128")


def run(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])


def make_video(path, *, dur=10, setpts=None, audio=False, extra_out=()) -> str:
    """Frame-id video; optional setpts expression (VFR) and sine audio. Output pts use a 1/90000 base."""
    vf = ID_SRC.format(d=dur) + (f",setpts='{setpts}'" if setpts else "") + ",format=yuv420p"
    inputs = ["-f", "lavfi", "-i", vf]
    if audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}"]
    run(*inputs, "-c:v", "libx264", "-preset", "ultrafast", "-g", "25", *_passthrough_args(),
        "-enc_time_base:v", "1:90000", *(["-c:a", "aac"] if audio else []), *extra_out, str(path))
    return str(path)


def frame_ids(path) -> list[int]:
    """Decoded frames' ids in display order, no dup/drop (passthrough)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", *_passthrough_args(),
                          "-vf", "scale=16:8:flags=area,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    digit = lambda v: round(v * 219 / 255 / 14)  # gray is expanded from tv range
    return [digit(f[2 * 16 + 2]) + 16 * digit(f[2 * 16 + 13])
            for f in (raw[i:i + 128] for i in range(0, len(raw), 128))]


def video_pts(path) -> list[float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "packet=pts_time", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return sorted(float(p["pts_time"]) for p in json.loads(out.stdout)["packets"])


def stream_info(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]
