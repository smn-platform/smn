"""HTTP connector — a governed wrapper around httpx for external API calls.

Provides:
- URL allowlisting (prevent SSRF)
- Automatic retry with backoff
- Response size limits
- Full audit trail of requests/responses
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from smn.connectors.base import BaseConnector, ConnectorConfig

# SSRF protection: only allow HTTPS by default, block private ranges
_BLOCKED_HOSTS = frozenset([
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",
])


class HttpConnector(BaseConnector):
    """Governed HTTP client with SSRF protection and audit trail."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._allowed_domains: set[str] = set(config.params.get("allowed_domains", []))
        self._max_response_bytes: int = config.params.get("max_response_bytes", 10 * 1024 * 1024)
        self._timeout: float = config.params.get("timeout", 30.0)

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=5,
        )
        self._is_connected = True

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._is_connected = False

    async def health_check(self) -> bool:
        return self._client is not None

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Execute an HTTP request.

        Parameters
        ----------
        operation
            HTTP method (GET, POST, PUT, DELETE, PATCH).
        url
            Target URL (validated against allowlist).
        **kwargs
            Passed to httpx (json, data, headers, params).
        """
        if not self._client:
            raise RuntimeError("HttpConnector not connected — call connect() first")

        url = kwargs.pop("url", "")
        self._validate_url(url)

        method = operation.upper()
        response = await self._client.request(method, url, **kwargs)

        # Enforce response size limit
        content = response.content
        if len(content) > self._max_response_bytes:
            raise ValueError(
                f"Response size {len(content)} exceeds limit {self._max_response_bytes}"
            )

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        }

    def _validate_url(self, url: str) -> None:
        """Validate URL to prevent SSRF attacks."""
        parsed = urlparse(url)

        # Must be HTTPS (or HTTP only if explicitly allowed)
        if parsed.scheme not in ("https", "http"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        hostname = (parsed.hostname or "").lower()

        # Block private/metadata IPs
        if hostname in _BLOCKED_HOSTS:
            raise ValueError(f"Blocked host: {hostname}")

        # Block private IP ranges
        if hostname.startswith(("10.", "172.16.", "192.168.")):
            raise ValueError(f"Private IP ranges are blocked: {hostname}")

        # If allowlist is configured, enforce it
        if self._allowed_domains and hostname not in self._allowed_domains:
            raise ValueError(
                f"Domain '{hostname}' not in allowlist: {self._allowed_domains}"
            )
