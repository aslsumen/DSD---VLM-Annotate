"""Stage V: after refine, Gemini Decision 1 checks each event clip ("does this event happen here?").

The API key comes from the GEMINI_API_KEY environment variable or a `.env` file
(the current directory first, then the video_grounding project root). The key is never written to config or outputs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from .models import VideoInfo
from .settings import Verify

_ENV_FILES = (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env")
_INLINE_LIMIT = 20 * 1024 * 1024  # inline request cap
# Charades-STA A/B (docs/EVALUATION.md): vs the bare question 'Does the following event visibly happen in this video
# clip?', true events kept 72% -> 85% at p >= 0.5 while wrong-time and unrelated-caption clips stay removed (96% / 94%).
_INSTRUCTIONS = ('A video search tool proposed this clip for the event below. Does the event happen in the clip?\n'
                 'Event: "{query}"\n'
                 'The event text was written by a person and may be short, informal or misspelled: judge its main '
                 'action and object, not every word. The clip can start before or end after the event, and the '
                 'event can be brief, partly out of frame, dark or low resolution.')
_CRITERIA = {"true_description": "The described action happens at some point in the clip, even briefly or only "
                                 "near its start or end.",
             "false_description": "The described action does not happen anywhere in the clip, or only a "
                                  "different action happens."}
# part of the verdict cache key: editing the question re-verifies instead of reusing old verdicts
QUESTION_ID = hashlib.sha1(json.dumps([_INSTRUCTIONS, _CRITERIA]).encode()).hexdigest()[:8]


def api_key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for f in _ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                k, _, v = line.partition("=")
                if k.strip() == "GEMINI_API_KEY" and v.strip().strip("\"'"):
                    return v.strip().strip("\"'")
    raise RuntimeError("GEMINI_API_KEY is not set: fill it into video_grounding/.env (see .env.example)")


class GeminiVerifier:
    """Gemini Decision 1: one forward pass scores a yes/no question, returning calibrated P(true)."""

    def __init__(self, cfg: Verify):
        from google import genai  # lazy: optional extra `gemini`

        self.cfg = cfg
        self.client = genai.Client(api_key=api_key())

    def verify(self, video: str, info: VideoInfo, start_sec: float, end_sec: float, query: str) -> dict:
        from . import cutter

        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "clip.mp4"
            cutter.cut_window_clip(video, start_sec, end_sec, str(clip), info, max_height=self.cfg.max_height,
                                   fps=self.cfg.fps)
            data = clip.read_bytes()
        # ponytail: inline only; a clip over 20 MB stays "not_verified". Switch to the Files API if that happens often.
        if len(data) > _INLINE_LIMIT:
            raise ValueError(f"clip {len(data) / 1e6:.1f} MB exceeds the inline limit; lower verify.max_height")
        video_in = {"type": "video", "data": base64.b64encode(data).decode(), "mime_type": "video/mp4",
                    "processing": {"type": "static", "fps": self.cfg.fps}}
        q = {"type": "noul", "instructions": _INSTRUCTIONS.format(query=query), "criteria": _CRITERIA}
        for attempt in range(5):  # per-minute rate limits clear within a few minutes; a daily cap still raises
            try:
                r = self.client.decisions.create(model=f"models/{self.cfg.model}", api_version="v1beta",
                                                 input=[video_in], questions={"q": q})
                break
            except Exception as exc:
                if getattr(exc, "status_code", None) != 429 or attempt == 4:
                    raise
                time.sleep(15 * 2 ** attempt)
        p = float(r.answers["q"].noul)
        return {"present": p >= 0.5, "p_present": p, "model": self.cfg.model}
