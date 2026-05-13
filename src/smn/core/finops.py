"""FinOps — cost tracking, budget enforcement, and usage metering.

Tracks every cent spent by every agent on every task. Provides:
- Real-time cost accumulation per task
- Budget gates that halt execution before overspend
- Usage rollups for billing and reporting

Aligns with NIST AI RMF MANAGE-3 (resource management).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    """A single cost event."""

    timestamp: datetime
    category: str  # "llm_input" | "llm_output" | "tool_call" | "memory"
    model: str
    amount_usd: float
    detail: str = ""


@dataclass
class TaskBudget:
    """Live cost tracker for a single task execution."""

    max_usd: float = 5.0
    entries: list[CostEntry] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(e.amount_usd for e in self.entries)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.max_usd - self.total_usd)

    def can_spend(self, amount: float) -> bool:
        return (self.total_usd + amount) <= self.max_usd

    def record(self, category: str, model: str, amount_usd: float, detail: str = "") -> None:
        if amount_usd < 0:
            raise ValueError("Cost amount must be non-negative")
        self.entries.append(
            CostEntry(
                timestamp=datetime.now(timezone.utc),
                category=category,
                model=model,
                amount_usd=amount_usd,
                detail=detail,
            )
        )

    def summary(self) -> dict:
        by_category: dict[str, float] = {}
        for e in self.entries:
            by_category[e.category] = by_category.get(e.category, 0.0) + e.amount_usd
        return {
            "total_usd": round(self.total_usd, 6),
            "remaining_usd": round(self.remaining_usd, 6),
            "max_usd": self.max_usd,
            "breakdown": {k: round(v, 6) for k, v in by_category.items()},
            "num_entries": len(self.entries),
        }


# ── LLM cost estimation ─────────────────────────────────────────

# Approximate per-token costs (USD) — updated periodically.
# Real costs come from litellm's cost tracking when available.

_MODEL_COSTS: dict[str, dict[str, float]] = {
    "anthropic/claude-sonnet-4-6-20250415": {"input": 3.0e-6, "output": 15.0e-6},
    "anthropic/claude-opus-4-6-20250415": {"input": 15.0e-6, "output": 75.0e-6},
    "openai/gpt-4o": {"input": 2.5e-6, "output": 10.0e-6},
    "openai/gpt-4o-mini": {"input": 0.15e-6, "output": 0.60e-6},
}


def estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the cost of an LLM call. Falls back to mid-range estimate."""
    costs = _MODEL_COSTS.get(model, {"input": 5.0e-6, "output": 15.0e-6})
    return (input_tokens * costs["input"]) + (output_tokens * costs["output"])
