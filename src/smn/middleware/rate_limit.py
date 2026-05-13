"""Rate limiting middleware — per-tenant request throttling.

Implements a sliding-window rate limiter backed by Redis (production)
or in-memory (development). Limits are per-tenant based on their plan tier.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from smn.config import settings

logger = logging.getLogger(__name__)

# ── In-memory fallback (development) ─────────────────────────────

_memory_store: dict[str, list[float]] = defaultdict(list)


class _InMemoryLimiter:
    """Simple in-memory sliding window rate limiter for dev/testing."""

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, dict]:
        now = time.time()
        # Clean old entries
        _memory_store[key] = [t for t in _memory_store[key] if t > now - window]
        current = len(_memory_store[key])

        if current >= limit:
            retry_after = int(window - (now - _memory_store[key][0])) + 1
            return False, {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(now + retry_after)),
                "Retry-After": str(retry_after),
            }

        _memory_store[key].append(now)
        return True, {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(limit - current - 1),
            "X-RateLimit-Reset": str(int(now + window)),
        }


# ── Redis-backed limiter (production) ────────────────────────────


class _RedisLimiter:
    """Redis-backed sliding window rate limiter."""

    def __init__(self):
        self._redis = None
        self._fallback = False

    def _get_redis(self):
        if self._fallback:
            return None
        if self._redis is None:
            try:
                import redis as redis_lib

                client = redis_lib.from_url(settings.redis_url, decode_responses=True)
                client.ping()
                self._redis = client
            except Exception:
                logger.warning("Redis not available, falling back to in-memory rate limiter")
                self._fallback = True
                return None
        return self._redis

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, dict]:
        r = self._get_redis()
        if r is None:
            return _InMemoryLimiter().check(key, limit, window)

        try:
            now = time.time()
            pipe = r.pipeline()

            rate_key = f"ratelimit:{key}"
            pipe.zremrangebyscore(rate_key, 0, now - window)
            pipe.zadd(rate_key, {str(now): now})
            pipe.zcard(rate_key)
            pipe.expire(rate_key, window + 1)
            results = pipe.execute()

            current = results[2]

            if current > limit:
                # Over limit — remove the entry we just added
                r.zrem(rate_key, str(now))
                entries = r.zrange(rate_key, 0, 0, withscores=True)
                oldest = entries[0][1] if entries else now
                retry_after = int(window - (now - oldest)) + 1
                return False, {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                    "Retry-After": str(retry_after),
                }

            return True, {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(limit - current),
                "X-RateLimit-Reset": str(int(now + window)),
            }
        except Exception:
            logger.warning("Redis error during rate limit check, falling back to in-memory")
            self._redis = None
            self._fallback = True
            return _InMemoryLimiter().check(key, limit, window)


# ── Middleware ───────────────────────────────────────────────────

_limiter = _RedisLimiter()

# Paths exempt from rate limiting
_EXEMPT_PATHS = {"/", "/docs", "/openapi.json", "/api/v1/health", "/api/v1/billing/webhook"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant rate limiting middleware.

    Uses the X-API-Key header to identify the tenant and applies
    rate limits based on their plan tier.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip exempt paths
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # Skip non-API paths
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Identify the caller
        api_key = request.headers.get("x-api-key", "")
        if not api_key:
            # Unauthenticated — apply a global rate limit by IP
            client_ip = request.client.host if request.client else "unknown"
            key = f"ip:{client_ip}"
            limit = settings.rate_limit_default_rpm
        else:
            # Use key prefix as identifier (first 8 chars)
            key = f"key:{api_key[:8]}"
            limit = settings.rate_limit_default_rpm

        allowed, headers = _limiter.check(key, limit)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please retry later.",
                    "limit": limit,
                },
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to response
        for k, v in headers.items():
            response.headers[k] = v

        return response
