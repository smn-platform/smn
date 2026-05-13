"""Observability — OpenTelemetry instrumentation for tracing and metrics.

Provides:
- Distributed tracing with spans for LLM calls, tool executions, governance gates
- Metrics: latency, token counts, cost, error rates
- Graceful no-op when OpenTelemetry is not installed

Enable by installing ``opentelemetry-sdk`` and ``opentelemetry-api``.
Configure exporters via standard OTEL environment variables.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# ── OpenTelemetry imports (optional) ─────────────────────────────

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

# ── No-op fallbacks for when OTEL is not installed ───────────────


class _NoOpSpan:
    """Minimal span substitute when OpenTelemetry is unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):
        yield _NoOpSpan()


class _NoOpCounter:
    def add(self, amount: int | float, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpHistogram:
    def record(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpMeter:
    def create_counter(self, name: str, **kwargs: Any) -> _NoOpCounter:
        return _NoOpCounter()

    def create_histogram(self, name: str, **kwargs: Any) -> _NoOpHistogram:
        return _NoOpHistogram()


# ── Tracer and meter singletons ──────────────────────────────────


def get_tracer() -> Any:
    """Return the SMN tracer (real or no-op)."""
    if _HAS_OTEL:
        return otel_trace.get_tracer("smn", "0.1.0")
    return _NoOpTracer()


def get_meter() -> Any:
    """Return the SMN meter (real or no-op)."""
    if _HAS_OTEL:
        return otel_metrics.get_meter("smn", "0.1.0")
    return _NoOpMeter()


_tracer = get_tracer()
_meter = get_meter()

# ── Metrics ──────────────────────────────────────────────────────

task_counter = _meter.create_counter(
    "smn.tasks.total",
    description="Total tasks executed",
)
task_duration = _meter.create_histogram(
    "smn.tasks.duration_seconds",
    description="Task execution duration in seconds",
)
llm_call_counter = _meter.create_counter(
    "smn.llm.calls.total",
    description="Total LLM API calls",
)
llm_token_counter = _meter.create_counter(
    "smn.llm.tokens.total",
    description="Total LLM tokens consumed",
)
tool_call_counter = _meter.create_counter(
    "smn.tools.calls.total",
    description="Total tool invocations",
)
tool_error_counter = _meter.create_counter(
    "smn.tools.errors.total",
    description="Total tool execution errors",
)
policy_deny_counter = _meter.create_counter(
    "smn.policy.denials.total",
    description="Total policy denials",
)
cost_counter = _meter.create_counter(
    "smn.cost.usd",
    description="Cumulative cost in USD",
)
guardrail_block_counter = _meter.create_counter(
    "smn.guardrails.blocks.total",
    description="Total guardrail blocks",
)


# ── Tracing helpers ──────────────────────────────────────────────


@asynccontextmanager
async def trace_task(task_id: str, agent_name: str, model: str):
    """Trace an entire task execution."""
    span = _tracer.start_span(
        "smn.task",
        attributes={
            "smn.task.id": task_id,
            "smn.agent.name": agent_name,
            "smn.model": model,
        },
    )
    start = time.monotonic()
    try:
        yield span
    except Exception as exc:
        span.record_exception(exc)
        raise
    finally:
        elapsed = time.monotonic() - start
        task_duration.record(elapsed, {"agent": agent_name, "model": model})
        task_counter.add(1, {"agent": agent_name, "status": "completed"})
        span.end()


@asynccontextmanager
async def trace_llm_call(model: str, step: int):
    """Trace a single LLM API call."""
    span = _tracer.start_span(
        "smn.llm_call",
        attributes={"smn.model": model, "smn.step": step},
    )
    try:
        yield span
        llm_call_counter.add(1, {"model": model})
    except Exception as exc:
        span.record_exception(exc)
        raise
    finally:
        span.end()


@asynccontextmanager
async def trace_tool_call(tool_name: str, agent_name: str):
    """Trace a tool invocation."""
    span = _tracer.start_span(
        "smn.tool_call",
        attributes={"smn.tool.name": tool_name, "smn.agent.name": agent_name},
    )
    try:
        yield span
        tool_call_counter.add(1, {"tool": tool_name, "agent": agent_name})
    except Exception as exc:
        span.record_exception(exc)
        tool_error_counter.add(1, {"tool": tool_name, "agent": agent_name})
        raise
    finally:
        span.end()


def record_tokens(model: str, input_tokens: int, output_tokens: int) -> None:
    """Record token usage metrics."""
    llm_token_counter.add(input_tokens, {"model": model, "direction": "input"})
    llm_token_counter.add(output_tokens, {"model": model, "direction": "output"})


def record_cost(amount_usd: float, category: str) -> None:
    """Record a cost event."""
    cost_counter.add(amount_usd, {"category": category})


def record_policy_denial(action: str, reason: str) -> None:
    """Record a policy denial."""
    policy_deny_counter.add(1, {"action": action, "reason_type": reason[:50]})


def record_guardrail_block(guardrail_type: str) -> None:
    """Record a guardrail block."""
    guardrail_block_counter.add(1, {"type": guardrail_type})
