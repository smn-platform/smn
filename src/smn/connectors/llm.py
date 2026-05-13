"""LLM connector — unified interface to model providers via litellm.

Provides:
- Automatic retries with exponential backoff for transient errors
- Fallback model chain (try primary, then fallback models in order)
- Streaming completions
- Circuit breaker pattern (skip models that fail repeatedly)
- Connector interface for direct LLM calls from tools

The runtime calls ``reliable_completion()`` instead of litellm directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

import litellm

from smn.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)

# Disable litellm's own retry — we handle it with proper backoff.
litellm.num_retries = 0

# Transient error types that are safe to retry.
_RETRYABLE_ERRORS = (
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    litellm.Timeout,
    litellm.APIConnectionError,
    asyncio.TimeoutError,
    ConnectionError,
)

# ── Circuit breaker ──────────────────────────────────────────────

_FAILURE_WINDOW = 300  # 5 minutes
_FAILURE_THRESHOLD = 5


class _CircuitBreaker:
    """Track per-model failures to avoid hammering a broken provider."""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}

    def record_failure(self, model: str) -> None:
        now = time.monotonic()
        self._failures.setdefault(model, []).append(now)

    def record_success(self, model: str) -> None:
        self._failures.pop(model, None)

    def is_open(self, model: str) -> bool:
        failures = self._failures.get(model, [])
        cutoff = time.monotonic() - _FAILURE_WINDOW
        recent = [t for t in failures if t > cutoff]
        self._failures[model] = recent
        return len(recent) >= _FAILURE_THRESHOLD


_circuit = _CircuitBreaker()

# ── Fallback chains ──────────────────────────────────────────────

# Default fallback chain: if the primary model fails, try these in order.
_DEFAULT_FALLBACKS: dict[str, list[str]] = {
    "anthropic/claude-sonnet-4-6-20250415": ["openai/gpt-4o", "openai/gpt-4o-mini"],
    "anthropic/claude-opus-4-6-20250415": ["anthropic/claude-sonnet-4-6-20250415", "openai/gpt-4o"],
    "openai/gpt-4o": ["anthropic/claude-sonnet-4-6-20250415", "openai/gpt-4o-mini"],
    "openai/gpt-4o-mini": ["anthropic/claude-sonnet-4-6-20250415"],
}


def get_fallback_chain(model: str) -> list[str]:
    """Return [primary, fallback1, fallback2, ...] for a model."""
    return [model] + _DEFAULT_FALLBACKS.get(model, [])


# ── Core reliable completion ─────────────────────────────────────


async def reliable_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    fallback_models: list[str] | None = None,
    **kwargs: Any,
) -> Any:
    """Call litellm with retries, backoff, and model fallback.

    1. Try the primary model up to ``max_retries`` times with exponential backoff.
    2. If all retries fail, try each fallback model in order.
    3. If all models fail, raise the last exception.

    Returns the litellm response object.
    """
    chain = fallback_models or get_fallback_chain(model)
    last_error: Exception | None = None

    for candidate in chain:
        if _circuit.is_open(candidate):
            logger.warning("circuit open for %s — skipping", candidate)
            continue

        for attempt in range(1, max_retries + 1):
            try:
                response = await litellm.acompletion(
                    model=candidate,
                    messages=messages,
                    **kwargs,
                )
                _circuit.record_success(candidate)
                if candidate != model:
                    logger.info("completed via fallback model %s", candidate)
                return response

            except _RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "retryable error on %s (attempt %d/%d): %s — retrying in %.1fs",
                        candidate,
                        attempt,
                        max_retries,
                        type(exc).__name__,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    _circuit.record_failure(candidate)
                    logger.warning(
                        "exhausted retries on %s after %d attempts",
                        candidate,
                        max_retries,
                    )

            except Exception as exc:
                # Non-retryable error (auth, bad request, etc.) — don't retry
                last_error = exc
                logger.error("non-retryable error on %s: %s", candidate, exc)
                _circuit.record_failure(candidate)
                break

    raise last_error or RuntimeError("all models in fallback chain failed")


async def reliable_completion_stream(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    fallback_models: list[str] | None = None,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Streaming variant of reliable_completion.

    Yields litellm streaming chunks. Retries on connection errors before
    the first chunk; once streaming starts, errors are raised to the caller.
    """
    chain = fallback_models or get_fallback_chain(model)
    last_error: Exception | None = None

    for candidate in chain:
        if _circuit.is_open(candidate):
            continue

        for attempt in range(1, max_retries + 1):
            try:
                response = await litellm.acompletion(
                    model=candidate,
                    messages=messages,
                    stream=True,
                    **kwargs,
                )
                _circuit.record_success(candidate)
                async for chunk in response:
                    yield chunk
                return

            except _RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                else:
                    _circuit.record_failure(candidate)

            except Exception as exc:
                last_error = exc
                _circuit.record_failure(candidate)
                break

    raise last_error or RuntimeError("all models in fallback chain failed")


# ── Connector class (for advanced use) ───────────────────────────


class LlmConnector(BaseConnector):
    """Connector for LLM providers via litellm with reliability built in."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._model: str = config.params.get("model", "anthropic/claude-sonnet-4-6-20250415")

    async def connect(self) -> None:
        self._is_connected = True

    async def disconnect(self) -> None:
        self._is_connected = False

    async def health_check(self) -> bool:
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return bool(response.choices)
        except Exception:
            return False

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        if operation == "completion":
            return await reliable_completion(
                model=kwargs.get("model", self._model),
                messages=kwargs["messages"],
                **{k: v for k, v in kwargs.items() if k not in ("model", "messages")},
            )
        if operation == "embedding":
            return await litellm.aembedding(
                model=kwargs.get("model", self._model),
                input=kwargs["input"],
            )
        raise ValueError(f"Unknown LLM operation: {operation}")
