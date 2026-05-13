"""Tests for OpenTelemetry instrumentation — verifies no-op fallback and tracing helpers."""

from __future__ import annotations

import pytest

from smn.core.telemetry import (
    _NoOpCounter,
    _NoOpHistogram,
    _NoOpMeter,
    _NoOpSpan,
    _NoOpTracer,
    get_meter,
    get_tracer,
    record_cost,
    record_guardrail_block,
    record_policy_denial,
    record_tokens,
    trace_llm_call,
    trace_task,
    trace_tool_call,
)


class TestNoOpFallbacks:
    """Ensure no-op objects work without OpenTelemetry installed."""

    def test_noop_span(self):
        span = _NoOpSpan()
        span.set_attribute("key", "value")
        span.set_status("OK")
        span.record_exception(RuntimeError("oops"))
        span.add_event("test", {"k": "v"})
        span.end()

    def test_noop_span_context_manager(self):
        with _NoOpSpan() as span:
            span.set_attribute("a", 1)

    def test_noop_tracer(self):
        tracer = _NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, _NoOpSpan)
        with tracer.start_as_current_span("test2") as s:
            s.set_attribute("x", True)

    def test_noop_counter(self):
        counter = _NoOpCounter()
        counter.add(1, {"key": "val"})

    def test_noop_histogram(self):
        hist = _NoOpHistogram()
        hist.record(1.5, {"key": "val"})

    def test_noop_meter(self):
        meter = _NoOpMeter()
        counter = meter.create_counter("test.counter")
        assert isinstance(counter, _NoOpCounter)
        hist = meter.create_histogram("test.hist")
        assert isinstance(hist, _NoOpHistogram)


class TestTracerAndMeter:
    """Verify get_tracer/get_meter return usable objects."""

    def test_get_tracer(self):
        tracer = get_tracer()
        assert tracer is not None

    def test_get_meter(self):
        meter = get_meter()
        assert meter is not None


class TestMetricHelpers:
    """Verify metric recording functions don't raise."""

    def test_record_tokens(self):
        record_tokens("test/model", 100, 50)

    def test_record_cost(self):
        record_cost(0.05, "llm")

    def test_record_policy_denial(self):
        record_policy_denial("db:delete", "prohibited action")

    def test_record_guardrail_block(self):
        record_guardrail_block("pii")


@pytest.mark.asyncio
async def test_trace_task():
    async with trace_task("task-1", "test-agent", "test/model") as span:
        span.set_attribute("custom", "value")


@pytest.mark.asyncio
async def test_trace_llm_call():
    async with trace_llm_call("test/model", 1) as span:
        span.set_attribute("tokens", 100)


@pytest.mark.asyncio
async def test_trace_tool_call():
    async with trace_tool_call("search", "agent-1") as span:
        span.set_attribute("args", "{}")
