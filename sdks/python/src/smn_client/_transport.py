"""HTTP transport layer — handles requests, retries, and error parsing."""

from __future__ import annotations

import time
from typing import Any, Generator, AsyncGenerator

import httpx

from smn_client._errors import RateLimitError, raise_for_status

_DEFAULT_BASE_URL = "http://localhost:8000"
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_INITIAL_BACKOFF = 0.5


def _backoff(attempt: int) -> float:
    return _INITIAL_BACKOFF * (2 ** attempt)


def _process_response(response: httpx.Response) -> Any:
    """Parse response, raising structured errors for non-2xx."""
    request_id = response.headers.get("x-request-id")
    if response.status_code >= 400:
        try:
            body = response.json()
        except Exception:
            body = {"error": {"message": response.text}}
        raise_for_status(response.status_code, body, request_id)
    if response.status_code == 204:
        return None
    return response.json()


class _SyncTransport:
    """Synchronous HTTP transport with retry logic."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smn-python/0.1.0",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(
                    method, path, json=json, params=params, headers=headers,
                )
                if resp.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                    retry_after = resp.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else _backoff(attempt)
                    time.sleep(wait)
                    continue
                return _process_response(resp)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(_backoff(attempt))
                    continue
                raise

        raise last_exc  # type: ignore[misc]

    def stream_sse(
        self, path: str, *, json: dict | None = None,
    ) -> Generator[tuple[str, dict], None, None]:
        """POST request returning SSE events."""
        import json as json_mod

        headers = {"X-API-Key": self._api_key, "Accept": "text/event-stream"}
        with self._client.stream("POST", path, json=json, headers=headers) as resp:
            if resp.status_code >= 400:
                resp.read()
                try:
                    body = resp.json()
                except Exception:
                    body = {"error": {"message": resp.text}}
                request_id = resp.headers.get("x-request-id")
                raise_for_status(resp.status_code, body, request_id)

            event_type = ""
            data_buf = ""
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_buf = line[6:]
                elif line == "":
                    if event_type and data_buf:
                        yield event_type, json_mod.loads(data_buf)
                    event_type = ""
                    data_buf = ""

    def close(self) -> None:
        self._client.close()


class _AsyncTransport:
    """Async HTTP transport with retry logic."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smn-python/0.1.0",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        import asyncio

        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.request(
                    method, path, json=json, params=params, headers=headers,
                )
                if resp.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                    retry_after = resp.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else _backoff(attempt)
                    await asyncio.sleep(wait)
                    continue
                return _process_response(resp)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(_backoff(attempt))
                    continue
                raise

        raise last_exc  # type: ignore[misc]

    async def stream_sse(
        self, path: str, *, json: dict | None = None,
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """POST request returning SSE events."""
        import json as json_mod

        headers = {"X-API-Key": self._api_key, "Accept": "text/event-stream"}
        async with self._client.stream("POST", path, json=json, headers=headers) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                try:
                    body = resp.json()
                except Exception:
                    body = {"error": {"message": resp.text}}
                request_id = resp.headers.get("x-request-id")
                raise_for_status(resp.status_code, body, request_id)

            event_type = ""
            data_buf = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_buf = line[6:]
                elif line == "":
                    if event_type and data_buf:
                        yield event_type, json_mod.loads(data_buf)
                    event_type = ""
                    data_buf = ""

    async def close(self) -> None:
        await self._client.aclose()
