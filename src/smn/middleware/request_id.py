"""Request ID middleware — assigns a unique ID to every request.

Every response includes an X-Request-Id header. If the client sends
one, it is echoed back; otherwise a new one is generated.
"""

from __future__ import annotations

import secrets

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def _generate_request_id() -> str:
    return f"req_{secrets.token_urlsafe(16)}"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID or generate one
        request_id = request.headers.get("x-request-id") or _generate_request_id()
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
