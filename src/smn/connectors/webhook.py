"""Webhook connector — governed outbound webhook delivery with retry.

Provides:
- HMAC-SHA256 signature for payload integrity
- Automatic retry with exponential backoff
- URL allowlisting (reuses SSRF protection)
- Payload size limits
- Delivery audit trail
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from smn.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = frozenset([
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254", "metadata.google.internal",
])
_MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MB
_DEFAULT_TIMEOUT = 10.0
_MAX_RETRIES = 3


class WebhookConnector(BaseConnector):
    """Governed webhook delivery with HMAC signatures and retry."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._signing_secret: str = config.params.get("signing_secret", "")
        self._allowed_domains: set[str] = set(config.params.get("allowed_domains", []))
        self._timeout: float = config.params.get("timeout", _DEFAULT_TIMEOUT)
        self._max_retries: int = config.params.get("max_retries", _MAX_RETRIES)
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,  # Webhooks should not follow redirects
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
        """Deliver a webhook.

        Parameters
        ----------
        operation
            "deliver" — the only supported operation.
        url
            Target webhook URL.
        payload
            Dictionary to send as JSON body.
        event_type
            Event type header (e.g. "task.completed").
        """
        if operation != "deliver":
            raise ValueError(f"Unknown operation: {operation}. Use 'deliver'.")

        if not self._client:
            raise RuntimeError("WebhookConnector not connected")

        url: str = kwargs.get("url", "")
        payload: dict = kwargs.get("payload", {})
        event_type: str = kwargs.get("event_type", "webhook")

        self._validate_url(url)

        body = json.dumps(payload, default=str, separators=(",", ":"))
        if len(body.encode()) > _MAX_PAYLOAD_BYTES:
            raise ValueError(f"Payload exceeds {_MAX_PAYLOAD_BYTES} byte limit")

        headers = {
            "Content-Type": "application/json",
            "X-SMN-Event": event_type,
            "X-SMN-Timestamp": str(int(time.time())),
        }

        if self._signing_secret:
            signature = self._sign_payload(body, headers["X-SMN-Timestamp"])
            headers["X-SMN-Signature"] = signature

        return await self._deliver_with_retry(url, body, headers)

    def _validate_url(self, url: str) -> None:
        """Validate webhook URL for SSRF safety."""
        if not url:
            raise ValueError("Webhook URL is required")

        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("Webhooks must use HTTPS")

        hostname = parsed.hostname or ""
        if hostname in _BLOCKED_HOSTS:
            raise ValueError(f"Blocked host: {hostname}")

        if self._allowed_domains and hostname not in self._allowed_domains:
            raise ValueError(
                f"Domain '{hostname}' not in allowed list: {self._allowed_domains}"
            )

    def _sign_payload(self, body: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature."""
        message = f"{timestamp}.{body}"
        return hmac.new(
            self._signing_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def _deliver_with_retry(
        self, url: str, body: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        """Deliver with exponential backoff retry."""
        assert self._client is not None

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.post(url, content=body, headers=headers)
                if resp.status_code < 300:
                    return {
                        "status": "delivered",
                        "status_code": resp.status_code,
                        "attempt": attempt,
                    }
                elif resp.status_code >= 500:
                    last_error = RuntimeError(f"Server error: {resp.status_code}")
                    logger.warning(
                        "Webhook delivery failed (attempt %d/%d): %s",
                        attempt, self._max_retries, resp.status_code,
                    )
                else:
                    return {
                        "status": "rejected",
                        "status_code": resp.status_code,
                        "attempt": attempt,
                    }
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                logger.warning(
                    "Webhook delivery error (attempt %d/%d): %s",
                    attempt, self._max_retries, exc,
                )

            if attempt < self._max_retries:
                import asyncio
                await asyncio.sleep(2 ** (attempt - 1))

        return {
            "status": "failed",
            "error": str(last_error),
            "attempts": self._max_retries,
        }
