"""Stage V: after refine, Gemini checks each event clip ("does this event happen here?") before export.

The API key comes from the GEMINI_API_KEY environment variable or a `.env` file
(the current directory first, then the video_grounding project root). The key is never written to config or outputs.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import VideoInfo
from .settings import Verify

_ENV_FILES = (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env")
_INLINE_LIMIT = 20 * 1024 * 1024  # Gemini inline request cap
_PROMPT = ('Watch this video clip. Does the following event visibly happen in it?\n'
           'Event: "{query}"\n'
           'Set present=true only if you can see it happen. confidence is 0-1. reason is one short sentence.')
_SCHEMA = {"type": "object", "properties": {"present": {"type": "boolean"}, "confidence": {"type": "number"},
                                            "reason": {"type": "string"}},
           "required": ["present", "confidence", "reason"]}


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
    def __init__(self, cfg: Verify):
        from google import genai  # lazy: optional extra `gemini`
        from google.genai import types

        self.cfg = cfg
        # SDK retries 429/5xx with backoff, so free-tier rate limits slow the stage down instead of failing it
        self.client = genai.Client(api_key=api_key(), http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=6)))

    def verify(self, video: str, info: VideoInfo, start_sec: float, end_sec: float, query: str) -> dict:
        from google.genai import types

        from . import cutter

        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "clip.mp4"
            cutter.cut_window_clip(video, start_sec, end_sec, str(clip), info, max_height=self.cfg.max_height)
            data = clip.read_bytes()
        # ponytail: inline only; a clip over 20 MB stays "not_verified". Switch to the Files API if that happens often.
        if len(data) > _INLINE_LIMIT:
            raise ValueError(f"clip {len(data) / 1e6:.1f} MB exceeds the inline limit; lower verify.max_height")
        video_part = types.Part(inline_data=types.Blob(data=data, mime_type="video/mp4"),
                                video_metadata=types.VideoMetadata(fps=self.cfg.fps))
        resp = self.client.models.generate_content(
            model=self.cfg.model, contents=[video_part, _PROMPT.format(query=query)],
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               response_json_schema=_SCHEMA, temperature=0))
        out = resp.parsed if isinstance(resp.parsed, dict) else json.loads(resp.text)
        return {"present": bool(out["present"]), "confidence": float(out["confidence"]),
                "reason": str(out.get("reason", "")), "model": self.cfg.model}
