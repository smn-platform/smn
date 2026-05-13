"""Tests for the policy engine."""

from pathlib import Path

import pytest

from smn.core.policy import Policy, PolicyLimits, PolicyRule, GovernanceFlags, load_policy


@pytest.fixture
def allow_all_policy() -> Policy:
    return Policy(
        name="test-allow-all",
        risk_level="minimal",
        rules=[PolicyRule(action="*", effect="allow")],
    )


@pytest.fixture
def restrictive_policy() -> Policy:
    return Policy(
        name="test-restrictive",
        risk_level="high",
        rules=[
            PolicyRule(action="*:read", effect="allow"),
            PolicyRule(action="*:delete", effect="deny", reason="no deletes"),
            PolicyRule(action="*:write", effect="escalate", reason="needs approval"),
            PolicyRule(action="*", effect="deny", reason="default deny"),
        ],
        limits=PolicyLimits(max_cost_per_task_usd=1.0, max_steps_per_task=10),
        governance=GovernanceFlags(require_human_oversight=True),
    )


class TestPolicyEvaluation:
    def test_allow_all(self, allow_all_policy: Policy):
        decision = allow_all_policy.evaluate("anything")
        assert decision.allowed is True
        assert decision.effect == "allow"

    def test_read_allowed(self, restrictive_policy: Policy):
        decision = restrictive_policy.evaluate("tickets:read")
        assert decision.allowed is True

    def test_delete_denied(self, restrictive_policy: Policy):
        decision = restrictive_policy.evaluate("tickets:delete")
        assert decision.allowed is False
        assert decision.effect == "deny"
        assert "no deletes" in decision.reason

    def test_write_escalated(self, restrictive_policy: Policy):
        decision = restrictive_policy.evaluate("tickets:write")
        assert decision.allowed is False
        assert decision.effect == "escalate"

    def test_unknown_action_denied(self, restrictive_policy: Policy):
        decision = restrictive_policy.evaluate("unknown_action")
        assert decision.allowed is False

    def test_empty_rules_denies(self):
        policy = Policy(name="empty", rules=[])
        decision = policy.evaluate("anything")
        assert decision.allowed is False
        assert "default" in decision.reason.lower()


class TestCostChecks:
    def test_within_budget(self, allow_all_policy: Policy):
        decision = allow_all_policy.check_cost(0.0, 0.10)
        assert decision.allowed is True

    def test_exceeds_budget(self, restrictive_policy: Policy):
        decision = restrictive_policy.check_cost(0.90, 0.20)
        assert decision.allowed is False
        assert "exceed" in decision.reason.lower()


class TestStepLimits:
    def test_within_limit(self, restrictive_policy: Policy):
        decision = restrictive_policy.check_step_limit(5)
        assert decision.allowed is True

    def test_at_limit(self, restrictive_policy: Policy):
        decision = restrictive_policy.check_step_limit(10)
        assert decision.allowed is False


class TestPolicyLoader:
    def test_load_default_policy(self):
        policy = load_policy("default", policy_dir=Path("policies"))
        assert policy.name == "default"
        assert policy.risk_level == "limited"
        assert len(policy.rules) > 0

    def test_load_missing_falls_back(self):
        policy = load_policy("nonexistent_policy_xyz")
        assert policy.name == "_restrictive_default"
        assert policy.risk_level == "high"
