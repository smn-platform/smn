"""SDK error classes — mirror the server-side structured error format."""

from __future__ import annotations

from typing import Any


class SMNError(Exception):
    """Base exception for all SMN SDK errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class APIError(SMNError):
    """Error returned by the SMN API.

    Attributes:
        status_code: HTTP status code.
        error_type: One of authentication_error, authorization_error,
            invalid_request_error, rate_limit_error, api_error.
        code: Machine-readable error code.
        param: The parameter that caused the error, if applicable.
        request_id: The X-Request-Id for this request.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_type: str = "api_error",
        code: str = "unknown",
        param: str | None = None,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.param = param
        self.request_id = request_id
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.message!r}, "
            f"status_code={self.status_code}, code={self.code!r})"
        )


class AuthenticationError(APIError):
    """401 — missing or invalid API key."""

    def __init__(self, message: str = "Invalid or missing API key.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=401, error_type="authentication_error", **kwargs)


class AuthorizationError(APIError):
    """403 — insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=403, error_type="authorization_error", **kwargs)


class NotFoundError(APIError):
    """404 — resource not found."""

    def __init__(self, message: str = "Resource not found.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=404, error_type="invalid_request_error", **kwargs)


class BadRequestError(APIError):
    """400 — invalid request."""

    def __init__(self, message: str = "Bad request.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=400, error_type="invalid_request_error", **kwargs)


class ValidationError(APIError):
    """422 — validation error."""

    def __init__(self, message: str = "Validation error.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=422, error_type="invalid_request_error", **kwargs)


class RateLimitError(APIError):
    """429 — rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded.", **kwargs: Any):
        kwargs.pop("status_code", None)
        kwargs.pop("error_type", None)
        super().__init__(message, status_code=429, error_type="rate_limit_error", **kwargs)


_STATUS_TO_ERROR: dict[int, type[APIError]] = {
    401: AuthenticationError,
    403: AuthorizationError,
    404: NotFoundError,
    422: ValidationError,
    429: RateLimitError,
}


def raise_for_status(status_code: int, body: dict[str, Any], request_id: str | None) -> None:
    """Parse an API error response and raise the appropriate exception."""
    error_data = body.get("error", {})
    message = error_data.get("message", body.get("detail", "Unknown error"))
    code = error_data.get("code", "unknown")
    error_type = error_data.get("type", "api_error")
    param = error_data.get("param")

    exc_class = _STATUS_TO_ERROR.get(status_code, APIError)
    if status_code == 400:
        exc_class = BadRequestError

    raise exc_class(
        message,
        status_code=status_code,
        error_type=error_type,
        code=code,
        param=param,
        request_id=request_id,
    )
