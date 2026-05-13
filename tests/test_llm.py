"""Tests for LLM reliability — retries, fallback, circuit breaker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from smn.connectors.llm import (
    _CircuitBreaker,
    get_fallback_chain,
    reliable_completion,
)


@pytest.mark.asyncio
@patch("smn.connectors.llm.litellm")
async def test_reliable_completion_success(mock_litellm):
    """Succeeds on first try — no retries needed."""
    mock_litellm.acompletion = AsyncMock(return_value="response")
    result = await reliable_completion(
        model="test/model",
        messages=[{"role": "user", "content": "hi"}],
        fallback_models=["test/model"],
        base_delay=0,
    )
    assert result == "response"
    assert mock_litellm.acompletion.call_count == 1


@pytest.mark.asyncio
@patch("smn.connectors.llm.litellm")
async def test_retry_on_transient_error(mock_litellm):
    """Retries on transient error and succeeds on second attempt."""
    mock_litellm.RateLimitError = type("RateLimitError", (Exception,), {})
    mock_litellm.ServiceUnavailableError = type("ServiceUnavailableError", (Exception,), {})
    mock_litellm.Timeout = type("Timeout", (Exception,), {})
    mock_litellm.APIConnectionError = type("APIConnectionError", (Exception,), {})

    # Patch the module-level tuple
    import smn.connectors.llm as llm_mod
    orig = llm_mod._RETRYABLE_ERRORS
    llm_mod._RETRYABLE_ERRORS = (mock_litellm.RateLimitError,)

    mock_litellm.acompletion = AsyncMock(
        side_effect=[mock_litellm.RateLimitError("rate limited"), "ok"]
    )
    try:
        result = await reliable_completion(
            model="test/model",
            messages=[{"role": "user", "content": "hi"}],
            fallback_models=["test/model"],
            base_delay=0,
        )
        assert result == "ok"
        assert mock_litellm.acompletion.call_count == 2
    finally:
        llm_mod._RETRYABLE_ERRORS = orig


@pytest.mark.asyncio
@patch("smn.connectors.llm.litellm")
async def test_fallback_on_exhausted_retries(mock_litellm):
    """Falls back to next model after exhausting retries on primary."""
    mock_litellm.RateLimitError = type("RateLimitError", (Exception,), {})
    import smn.connectors.llm as llm_mod
    orig = llm_mod._RETRYABLE_ERRORS
    llm_mod._RETRYABLE_ERRORS = (mock_litellm.RateLimitError,)

    # Primary fails all 2 retries, fallback succeeds
    mock_litellm.acompletion = AsyncMock(
        side_effect=[
            mock_litellm.RateLimitError("1"),
            mock_litellm.RateLimitError("2"),
            "fallback_ok",
        ]
    )
    try:
        result = await reliable_completion(
            model="primary",
            messages=[{"role": "user", "content": "hi"}],
            fallback_models=["primary", "fallback"],
            max_retries=2,
            base_delay=0,
        )
        assert result == "fallback_ok"
    finally:
        llm_mod._RETRYABLE_ERRORS = orig


@pytest.mark.asyncio
@patch("smn.connectors.llm.litellm")
async def test_non_retryable_error_skips_retries(mock_litellm):
    """Non-retryable errors (e.g., auth) skip retries and try fallback."""
    mock_litellm.acompletion = AsyncMock(
        side_effect=[ValueError("bad request"), "fallback_ok"]
    )
    result = await reliable_completion(
        model="primary",
        messages=[{"role": "user", "content": "hi"}],
        fallback_models=["primary", "fallback"],
        base_delay=0,
    )
    assert result == "fallback_ok"
    assert mock_litellm.acompletion.call_count == 2


def test_fallback_chain():
    """Fallback chain includes the primary model first."""
    chain = get_fallback_chain("anthropic/claude-sonnet-4-6-20250415")
    assert chain[0] == "anthropic/claude-sonnet-4-6-20250415"
    assert len(chain) >= 2


def test_circuit_breaker():
    """Circuit breaker opens after threshold failures."""
    cb = _CircuitBreaker()
    for _ in range(5):
        cb.record_failure("bad-model")
    assert cb.is_open("bad-model")
    assert not cb.is_open("good-model")
    cb.record_success("bad-model")
    assert not cb.is_open("bad-model")
