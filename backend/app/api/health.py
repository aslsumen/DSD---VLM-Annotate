"""Health, capability discovery and adapter listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import __version__
from .. import db as db_module
from ..adapters.registry import list_adapters
from ..config import Settings
from ..deps import settings_dep
from ..schemas import HealthOut

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(settings: Settings = Depends(settings_dep)) -> HealthOut:
    return HealthOut(
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
        database=db_module.engine.url.render_as_string(hide_password=True),
        adapter=settings.vlm_adapter,
    )


@router.get("/adapters")
def adapters(settings: Settings = Depends(settings_dep)) -> dict[str, object]:
    return {"adapters": list_adapters(settings), "default": settings.vlm_adapter}
