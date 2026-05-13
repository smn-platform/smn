"""Idempotency key middleware — prevents duplicate mutations.

When a client sends an Idempotency-Key header on a POST/PUT/PATCH request,
the response is cached. Subsequent requests with the same key return the
cached response without re-executing the handler.

Keys are scoped by API key prefix to prevent cross-tenant collisions.
Cache TTL is 24 hours.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}
_CACHE_TTL = 86400  # 24 hours
_MAX_CACHE_SIZE = 10000


class _InMemoryIdempotencyStore:
    """Simple in-memory LRU cache for idempotency. Production should use Redis."""

    def __init__(self, max_size: int = _MAX_CACHE_SIZE):
        self._store: OrderedDict[str, tuple[float, int, dict, bytes]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> tuple[int, dict, bytes] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, status, headers, body = entry
        if time.time() - ts > _CACHE_TTL:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return status, headers, body

    def set(self, key: str, status_code: int, headers: dict, body: bytes) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time(), status_code, headers, body)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)


_store = _InMemoryIdempotencyStore()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in _IDEMPOTENT_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("idempotency-key")
        if not idempotency_key:
            return await call_next(request)

        # Scope by API key prefix to prevent cross-tenant collisions
        api_key = request.headers.get("x-api-key", "")
        scope = api_key[:8] if api_key else "anon"
        cache_key = f"{scope}:{idempotency_key}"

        # Check cache
        cached = _store.get(cache_key)
        if cached is not None:
            status_code, headers, body = cached
            response = Response(
                content=body,
                status_code=status_code,
                media_type="application/json",
            )
            for k, v in headers.items():
                response.headers[k] = v
            response.headers["X-Idempotent-Replayed"] = "true"
            return response

        # Execute the request
        response = await call_next(request)

        # Cache the response (only for 2xx and 4xx — not 5xx)
        if 200 <= response.status_code < 500:
            body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    body += chunk.encode()
                else:
                    body += chunk

            resp_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in ("content-length", "transfer-encoding")
            }
            _store.set(cache_key, response.status_code, resp_headers, body)

            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=resp_headers,
            )

        return response
