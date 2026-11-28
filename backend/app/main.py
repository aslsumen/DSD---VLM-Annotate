"""FastAPI application factory."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db
from .api import auth, candidates, datasets, exports, health, jobs, projects, searches, videos
from .config import REPO_ROOT, Settings, get_settings
from .deps import require_token
from .errors import error_body, register_error_handlers
from .models import Base
from .services.media import FFmpegClipExtractor, FFmpegMediaProbe, media_info_json
from .services.storage import LocalStorage

logger = logging.getLogger(__name__)

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
PUBLIC_PATHS = {"/api/v1/health"}


def create_app(
    settings: Settings | None = None,
    *,
    storage: LocalStorage | None = None,
    probe: FFmpegMediaProbe | None = None,
    extractor: FFmpegClipExtractor | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_directories()

    app = FastAPI(
        title="VLM Annotate API",
        version=__version__,
        description=(
            "Asynchronous VLM candidate proposals for long single-view RGB video, "
            "with human true/false-positive verification and dataset export."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.settings = settings
    app.state.storage = storage or LocalStorage(settings.storage_root)
    app.state.probe = probe or FFmpegMediaProbe(settings.ffmpeg_binary)
    app.state.extractor = extractor or FFmpegClipExtractor(settings.ffmpeg_binary)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
        )

    register_error_handlers(app)

    # Enforced in middleware rather than only as a router dependency so that new
    # routes are protected by default and so the guard survives FastAPI's lazy
    # router inclusion.  Health stays public for container probes.
    if settings.api_token:

        @app.middleware("http")
        async def _bearer_guard(request, call_next):  # type: ignore[no-untyped-def]
            path = request.url.path
            if path.startswith("/api/v1") and path not in PUBLIC_PATHS:
                scheme, _, token = request.headers.get("authorization", "").partition(" ")
                if (
                    scheme.lower() != "bearer"
                    or not token
                    or not secrets.compare_digest(token, settings.api_token or "")
                ):
                    return JSONResponse(
                        status_code=401,
                        content=error_body(
                            "UNAUTHENTICATED",
                            "a valid bearer token is required",
                            {"hint": "send Authorization: Bearer <VLM_API_TOKEN>"},
                        ),
                    )
            return await call_next(request)

    if settings.auto_create_schema:
        Base.metadata.create_all(bind=db.engine)

    app.include_router(health.router, prefix="/api/v1")
    # Login / invitation acceptance / one-time bootstrap must stay reachable
    # without a session; everything else lives on the protected router.
    app.include_router(auth.public_router, prefix="/api/v1")

    protected = APIRouter(dependencies=[Depends(require_token)])
    protected.include_router(auth.router)
    protected.include_router(datasets.router)
    protected.include_router(projects.router)
    protected.include_router(searches.router)
    protected.include_router(videos.router)
    protected.include_router(jobs.router)
    protected.include_router(candidates.router)
    protected.include_router(exports.router)
    app.include_router(protected, prefix="/api/v1")

    @app.get("/api/v1/system/media", tags=["system"])
    def media_diagnostics() -> dict[str, object]:
        return media_info_json(settings.ffmpeg_binary)

    if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
        logger.info("serving built frontend from %s", FRONTEND_DIST)
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "app": settings.app_name,
                "docs": "/api/docs",
                "note": "frontend build not found; run `npm run build` in frontend/",
            }

    return app


app = create_app()
