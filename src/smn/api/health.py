"""Health check endpoint with DB and Redis connectivity probes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from smn import __version__
from smn.config import settings
from smn.db import async_session

router = APIRouter()


async def _check_db() -> dict:
    """Probe the database with a trivial query."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "connected"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_redis() -> dict:
    """Probe Redis with a PING."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await client.ping()
            return {"status": "connected" if pong else "error"}
        finally:
            await client.aclose()
    except ImportError:
        return {"status": "skipped", "detail": "redis package not installed"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/health")
async def health_check():
    db = await _check_db()
    redis = await _check_redis()

    overall = "healthy"
    if db["status"] != "connected":
        overall = "degraded"
    if redis["status"] == "error":
        overall = "degraded"

    return {
        "status": overall,
        "version": __version__,
        "service": "smn",
        "checks": {
            "database": db,
            "redis": redis,
        },
    }
