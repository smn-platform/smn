"""Tests for FinOps cost tracking."""

import pytest

from smn.core.finops import TaskBudget, estimate_llm_cost


class TestTaskBudget:
    def test_initial_state(self):
        budget = TaskBudget(max_usd=5.0)
        assert budget.total_usd == 0.0
        assert budget.remaining_usd == 5.0

    def test_record_cost(self):
        budget = TaskBudget(max_usd=5.0)
        budget.record("llm", "test-model", 0.01)
        assert budget.total_usd == 0.01
        assert budget.remaining_usd == pytest.approx(4.99)

    def test_budget_check(self):
        budget = TaskBudget(max_usd=1.0)
        budget.record("llm", "test-model", 0.90)
        assert budget.can_spend(0.05) is True
        assert budget.can_spend(0.15) is False

    def test_negative_cost_rejected(self):
        budget = TaskBudget(max_usd=5.0)
        with pytest.raises(ValueError):
            budget.record("llm", "test-model", -0.01)

    def test_summary(self):
        budget = TaskBudget(max_usd=5.0)
        budget.record("llm", "model-a", 0.02)
        budget.record("tool_call", "search", 0.01)
        summary = budget.summary()
        assert summary["total_usd"] == pytest.approx(0.03)
        assert "llm" in summary["breakdown"]
        assert "tool_call" in summary["breakdown"]


class TestLlmCostEstimation:
    def test_known_model(self):
        cost = estimate_llm_cost("anthropic/claude-sonnet-4-6-20250415", 1000, 500)
        assert cost > 0
        assert cost < 1.0  # Sanity check

    def test_unknown_model_fallback(self):
        cost = estimate_llm_cost("unknown/model", 1000, 500)
        assert cost > 0  # Should use fallback pricing
