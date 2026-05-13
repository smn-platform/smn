"""FastAPI server — the SMN control plane API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from smn import __version__
from smn.api import api_router
from smn.api.errors import install_error_handlers
from smn.config import settings
from smn.db import init_db
from smn.middleware.idempotency import IdempotencyMiddleware
from smn.middleware.rate_limit import RateLimitMiddleware
from smn.middleware.request_id import RequestIdMiddleware

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    await init_db()
    yield


app = FastAPI(
    title="SMN — Secure Multi-agent Network",
    description=(
        "Deploy, govern, and scale AI agents safely. "
        "Full audit trail, policy enforcement, and regulatory compliance."
    ),
    version=__version__,
    lifespan=lifespan,
)

# Middleware (outermost first: request ID → rate limit → idempotency)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)

# Structured error handlers
install_error_handlers(app)

app.include_router(api_router)

# ── Static assets ────────────────────────────────────────────────

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    path = _STATIC_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=204)


@app.get("/.well-known/{path:path}", include_in_schema=False)
async def well_known(path: str):
    return Response(status_code=204)


@app.get("/")
async def root():
    return {
        "service": "SMN",
        "version": __version__,
        "docs": "/docs",
        "api": "/api/v1",
    }


def serve() -> None:
    """Run the server with uvicorn."""
    import uvicorn

    uvicorn.run(
        "smn.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
