"""Structured API error handling.

Provides consistent error responses matching industry standards (Stripe, Cloudflare).
All API errors return:

    {
        "error": {
            "type": "invalid_request_error",
            "code": "resource_not_found",
            "message": "Agent not found.",
            "param": "agent_id",
            "request_id": "req_abc123..."
        }
    }

Error types:
    - authentication_error: Missing or invalid API key.
    - authorization_error: Valid key but insufficient permissions.
    - invalid_request_error: Bad input, missing resource, validation failure.
    - rate_limit_error: Too many requests.
    - api_error: Internal server error (unexpected).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class SMNAPIError(Exception):
    """Base class for all structured API errors."""

    def __init__(
        self,
        *,
        status_code: int,
        error_type: str,
        code: str,
        message: str,
        param: str | None = None,
    ):
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.message = message
        self.param = param
        super().__init__(message)


class AuthenticationError(SMNAPIError):
    """401 — missing or invalid credentials."""

    def __init__(self, message: str = "Invalid or missing API key.", code: str = "invalid_api_key"):
        super().__init__(
            status_code=401,
            error_type="authentication_error",
            code=code,
            message=message,
        )


class AuthorizationError(SMNAPIError):
    """403 — valid credentials but insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions.", code: str = "insufficient_scope"):
        super().__init__(
            status_code=403,
            error_type="authorization_error",
            code=code,
            message=message,
        )


class NotFoundError(SMNAPIError):
    """404 — resource does not exist (or not accessible to this tenant)."""

    def __init__(self, resource: str = "Resource", param: str | None = None):
        super().__init__(
            status_code=404,
            error_type="invalid_request_error",
            code="resource_not_found",
            message=f"{resource} not found.",
            param=param,
        )


class BadRequestError(SMNAPIError):
    """400 — invalid request (e.g. deactivated agent, duplicate tenant)."""

    def __init__(self, message: str, code: str = "bad_request", param: str | None = None):
        super().__init__(
            status_code=400,
            error_type="invalid_request_error",
            code=code,
            message=message,
            param=param,
        )


class RateLimitError(SMNAPIError):
    """429 — too many requests."""

    def __init__(self, message: str = "Rate limit exceeded. Please retry later.", limit: int = 0):
        super().__init__(
            status_code=429,
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
            message=message,
        )
        self.limit = limit


def _build_error_body(
    error_type: str,
    code: str,
    message: str,
    param: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": error_type,
        "code": code,
        "message": message,
    }
    if param:
        body["param"] = param
    if request_id:
        body["request_id"] = request_id
    return {"error": body}


def install_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(SMNAPIError)
    async def smn_error_handler(request: Request, exc: SMNAPIError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_body(
                exc.error_type, exc.code, exc.message, exc.param, request_id
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Map status codes to error types
        if exc.status_code == 401:
            error_type = "authentication_error"
            code = "invalid_api_key"
        elif exc.status_code == 403:
            error_type = "authorization_error"
            code = "forbidden"
        elif exc.status_code == 404:
            error_type = "invalid_request_error"
            code = "resource_not_found"
        elif exc.status_code == 429:
            error_type = "rate_limit_error"
            code = "rate_limit_exceeded"
        else:
            error_type = "invalid_request_error"
            code = "bad_request"

        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_body(
                error_type, code, str(exc.detail), request_id=request_id
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Extract the first error for a clean message
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = first.get("loc", [])
            param = ".".join(str(p) for p in loc[1:]) if len(loc) > 1 else None
            message = first.get("msg", "Validation error")
        else:
            param = None
            message = "Validation error"

        return JSONResponse(
            status_code=422,
            content=_build_error_body(
                "invalid_request_error",
                "validation_error",
                message,
                param=param,
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception (request_id=%s)", request_id)
        return JSONResponse(
            status_code=500,
            content=_build_error_body(
                "api_error",
                "internal_error",
                "An internal error occurred. Please retry later.",
                request_id=request_id,
            ),
        )
