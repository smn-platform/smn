"""Tests for rate limiting middleware."""

import time
from smn.middleware.rate_limit import _InMemoryLimiter, _memory_store


def test_in_memory_limiter_allows_under_limit():
    limiter = _InMemoryLimiter()
    key = f"test_allow_{time.time()}"
    allowed, headers = limiter.check(key, limit=5, window=60)
    assert allowed is True
    assert headers["X-RateLimit-Remaining"] == "4"


def test_in_memory_limiter_blocks_over_limit():
    limiter = _InMemoryLimiter()
    key = f"test_block_{time.time()}"

    # Use up the limit
    for i in range(5):
        allowed, _ = limiter.check(key, limit=5, window=60)
        assert allowed is True

    # Should be blocked now
    allowed, headers = limiter.check(key, limit=5, window=60)
    assert allowed is False
    assert headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in headers


def test_in_memory_limiter_rate_limit_headers():
    limiter = _InMemoryLimiter()
    key = f"test_headers_{time.time()}"
    _, headers = limiter.check(key, limit=100, window=60)
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert headers["X-RateLimit-Limit"] == "100"
