"""Adapter registry."""

from __future__ import annotations

from ..config import Settings
from ..errors import ApiError
from . import VLMAdapter
from .mock import MockTemporalAdapter
from .qwen import Qwen25VLAdapter
from .videojev import VideoJevAdapter


def _build(settings: Settings) -> dict[str, VLMAdapter]:
    return {
        "mock": MockTemporalAdapter(seed_salt=settings.mock_seed_salt),
        "qwen2.5-vl": Qwen25VLAdapter(),
        "videojev": VideoJevAdapter(settings.videojev_config),
    }


def list_adapters(settings: Settings) -> list[dict[str, object]]:
    return [
        {
            "name": adapter.name,
            "version": adapter.version,
            "requires_gpu": adapter.requires_gpu,
            "available": adapter.is_available(),
            "default": adapter.name == settings.vlm_adapter,
        }
        for adapter in _build(settings).values()
    ]


def get_adapter(name: str | None, settings: Settings) -> VLMAdapter:
    requested = name or settings.vlm_adapter
    adapters = _build(settings)
    adapter = adapters.get(requested)
    if adapter is None:
        raise ApiError(
            422,
            "UNKNOWN_ADAPTER",
            f"unknown model adapter '{requested}'",
            {"available": sorted(adapters)},
        )
    if not adapter.is_available():
        raise ApiError(
            409,
            "ADAPTER_UNAVAILABLE",
            f"adapter '{requested}' is registered but not available in this environment",
            {"adapter": requested, "version": adapter.version},
        )
    return adapter
