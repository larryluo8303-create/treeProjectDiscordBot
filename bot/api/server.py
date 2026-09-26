"""FastAPI application factory and server lifecycle."""

import asyncio
import logging
import os
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bot.config import (
    API_PASSWORD,
    API_PORT,
    API_SECRET_KEY,
    API_USERNAME,
    CLIENT_API_ENABLED,
    CLIENT_API_KEY,
    CORS_ORIGINS,
)

logger = logging.getLogger(__name__)


def api_credentials_configured() -> bool:
    """True when the API can start: username/password set and secret key long enough.

    Used by main.py to skip the API server (instead of killing the whole bot)
    when the operator never configured API credentials.
    """
    return bool(
        API_USERNAME
        and API_PASSWORD
        and API_SECRET_KEY
        and len(API_SECRET_KEY) >= 32
    )


# ---------------------------------------------------------------------------
# App state — set by main.py before starting the server
# ---------------------------------------------------------------------------
_collection = None
_openai_client = None
_bot = None


def set_dependencies(collection, openai_client, bot) -> None:
    """Inject shared dependencies from the bot process."""
    global _collection, _openai_client, _bot
    _collection = collection
    _openai_client = openai_client
    _bot = bot


def get_collection():
    return _collection


def get_openai_client():
    return _openai_client


def get_bot():
    return _bot


# ---------------------------------------------------------------------------
# SPA static-file serving (security-hardened)
# ---------------------------------------------------------------------------
def _resolve_spa_file(dist_dir: str, full_path: str) -> str | None:
    """Resolve a request path inside the SPA dist dir.

    Returns the absolute file path if it exists and stays inside dist_dir,
    otherwise None (caller falls back to index.html).  Raises HTTPException
    404 on path-traversal attempts.
    """
    if not full_path:
        return None
    # SECURITY: normalize and confine the resolved path inside dist_dir —
    # a raw os.path.join allows traversal (e.g. GET /../../../../etc/passwd).
    file_path = os.path.normpath(os.path.join(dist_dir, full_path))
    if os.path.commonpath([dist_dir, file_path]) != dist_dir:
        raise HTTPException(status_code=404, detail="Not found")
    if os.path.isfile(file_path):
        return file_path
    return None


def create_app() -> FastAPI:
    # SECURITY (fail-closed): the API exposes admin endpoints, so it must not
    # start with missing credentials.  There are no default values — set
    # API_USERNAME / API_PASSWORD / API_SECRET_KEY explicitly (see .env.example).
    if not API_USERNAME or not API_PASSWORD:
        raise RuntimeError(
            "API_USERNAME and API_PASSWORD must be set (no default credentials). "
            "See .env.example."
        )
    if not API_SECRET_KEY or len(API_SECRET_KEY) < 32:
        raise RuntimeError(
            "API_SECRET_KEY must be set to a random string of at least 32 characters "
            "(e.g. generated with: python -c \"import secrets; print(secrets.token_hex(32))\"). "
            "See .env.example."
        )

    app = FastAPI(
        title="BigTree Bot API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS — same-origin by default.  The bundled web-client is served from
    # this same port, so browsers don't need cross-origin access in production.
    # Set CORS_ORIGINS (comma-separated) only for separately-hosted frontends.
    # SECURITY: never combine allow_origins=["*"] with allow_credentials=True.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=bool(CORS_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "x-api-key"],
    )

    if CLIENT_API_ENABLED and not CLIENT_API_KEY:
        logger.warning(
            "CLIENT_API_ENABLED=true with empty CLIENT_API_KEY — "
            "public API endpoints are OPEN to the internet. "
            "Set CLIENT_API_KEY to protect them."
        )

    # Register routers
    from bot.api.auth import router as auth_router
    from bot.api.ws import router as ws_router
    from bot.api.routes_stats import router as stats_router
    from bot.api.routes_config import router as config_router
    from bot.api.routes_kb import router as kb_router
    from bot.api.routes_faq import router as faq_router
    from bot.api.routes_review import router as review_router
    from bot.api.routes_promo import router as promo_router
    from bot.api.routes_digest import router as digest_router
    from bot.api.routes_public import router as public_router

    app.include_router(auth_router)
    app.include_router(ws_router)
    app.include_router(stats_router)
    app.include_router(config_router)
    app.include_router(kb_router)
    app.include_router(faq_router)
    app.include_router(review_router)
    app.include_router(promo_router)
    app.include_router(digest_router)
    app.include_router(public_router)

    @app.get("/api/health")
    async def health():
        from bot.health import uptime_seconds
        return {
            "status": "ok",
            "uptime_seconds": round(uptime_seconds(), 1),
            "timestamp": time.time(),
        }

    # ── Serve web-client static files (production) ────────────────────────
    # After `npm run build` in web-client/, the dist/ folder contains the
    # SPA bundle.  Mount it so customers can access the web UI at the same
    # port as the API (e.g. http://host:8090/).
    _dist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web-client", "dist")
    _dist_dir = os.path.normpath(_dist_dir)
    if os.path.isdir(_dist_dir):
        # Serve static assets (JS/CSS/images)
        app.mount("/assets", StaticFiles(directory=os.path.join(_dist_dir, "assets")), name="static-assets")

        # SPA fallback: any non-API GET returns index.html
        _index_html = os.path.join(_dist_dir, "index.html")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            # Try to serve an exact file first (favicon.ico, etc.),
            # falling back to index.html for SPA client-side routing.
            resolved = _resolve_spa_file(_dist_dir, full_path)
            if resolved:
                return FileResponse(resolved)
            return FileResponse(_index_html)

        logger.info("Serving web-client from %s", _dist_dir)
    else:
        logger.info("web-client/dist not found at %s — run 'npm run build' in web-client/ to enable", _dist_dir)

    return app


# ---------------------------------------------------------------------------
# Server runner (called from main.py as an asyncio task)
# ---------------------------------------------------------------------------
async def run_api_server() -> None:
    """Run the FastAPI server using uvicorn inside the existing event loop."""
    app = create_app()
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("API server starting on port %d", API_PORT)
    await server.serve()
