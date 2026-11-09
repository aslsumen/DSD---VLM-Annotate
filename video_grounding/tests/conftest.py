import pytest

from video_grounding.models import VideoInfo
from video_grounding.settings import Settings


def make_info(duration: float, fingerprint: str = "fp1") -> VideoInfo:
    return VideoInfo("synthetic.mp4", duration, 25.0, "1/12800", 0, 640, 360, 0, False, 0.0, False, fingerprint)


def make_settings(**over) -> Settings:
    # synthetic scores peak at 0.8, not VideoJev's raw scale, so the score filter is off in tests
    d = {"runtime": {"backend": "synthetic", "profile": "dev_low_vram"}, "export": {"cut_clips": False},
         "fusion": {"min_event_score": 0.0}}
    for k, v in over.items():
        d.setdefault(k, {}).update(v)
    return Settings.model_validate(d)


@pytest.fixture
def info():
    return make_info
