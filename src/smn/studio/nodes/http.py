"""HTTPNode — governed outbound HTTP request.

Config keys
-----------
url : str
    Target URL.  Supports ``{{...}}`` templates.  Must be http/https.
    Private IPs and AWS/GCP metadata endpoints are blocked (SSRF protection).
method : str
    HTTP verb.  Defaults to ``"GET"``.
headers : dict[str, str]
    Optional request headers.  Values support templates.
body : str | dict
    Request body.  Dicts are JSON-serialised.  Only sent for POST/PUT/PATCH.
timeout_seconds : float
    Request timeout.  Defaults to 30 s, hard-capped at 60 s.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from smn.studio.nodes.base import BaseNode, NodeResult

# SSRF protection — block internal/cloud-metadata hosts
_BLOCKED_HOSTS: frozenset[str] = frozenset(
    [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.169.254",       # AWS / Azure IMDS
        "metadata.google.internal",
    ]
)
_BLOCKED_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                     "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")
_MAX_TIMEOUT = 60.0
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


class HTTPNode(BaseNode):
    node_type = "http"

    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        url: str = self.resolve(config.get("url", ""), context)
        method: str = config.get("method", "GET").upper()
        headers: dict[str, str] = self.resolve(config.get("headers", {}), context)
        body: Any = self.resolve(config.get("body", ""), context)
        timeout: float = min(float(config.get("timeout_seconds", 30.0)), _MAX_TIMEOUT)

        if not url:
            raise ValueError("HTTPNode: url is required")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"HTTPNode: only http/https allowed, got '{parsed.scheme}'")
        host = (parsed.hostname or "").lower()
        if host in _BLOCKED_HOSTS or host.startswith(_BLOCKED_PREFIXES):
            raise PermissionError(f"HTTPNode: SSRF protection blocked host '{host}'")

        raw_body: bytes | None = None
        if body and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                raw_body = json.dumps(body).encode()
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(body, str) and body.strip():
                raw_body = body.encode()

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers or None,
                    content=raw_body,
                )
            except httpx.TimeoutException:
                raise TimeoutError(
                    f"HTTPNode: request to {url} timed out after {timeout:.0f}s"
                )
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    f"HTTPNode: could not connect to {url} — {exc}"
                )

        try:
            data: Any = resp.json()
        except Exception:
            data = resp.text

        return NodeResult(
            output={
                "status_code": resp.status_code,
                "ok": resp.is_success,
                "data": data,
                "headers": dict(resp.headers),
            }
        )
