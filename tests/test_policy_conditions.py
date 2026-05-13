"""Tests for ABAC policy conditions — time, day-of-week, context matching."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smn.core.policy import Policy, PolicyDecision, PolicyRule, _evaluate_conditions


class TestEvaluateConditions:
    def test_empty_conditions_pass(self):
        assert _evaluate_conditions({}, {}) is True

    def test_time_after_pass(self):
        now = datetime(2024, 6, 15, 14, 30, tzinfo=timezone.utc)  # 14:30
        assert _evaluate_conditions({"time_after": "09:00"}, {"_now": now}) is True

    def test_time_after_fail(self):
        now = datetime(2024, 6, 15, 7, 0, tzinfo=timezone.utc)  # 07:00
        assert _evaluate_conditions({"time_after": "09:00"}, {"_now": now}) is False

    def test_time_before_pass(self):
        now = datetime(2024, 6, 15, 8, 0, tzinfo=timezone.utc)  # 08:00
        assert _evaluate_conditions({"time_before": "17:00"}, {"_now": now}) is True

    def test_time_before_fail(self):
        now = datetime(2024, 6, 15, 18, 0, tzinfo=timezone.utc)  # 18:00
        assert _evaluate_conditions({"time_before": "17:00"}, {"_now": now}) is False

    def test_time_range_pass(self):
        now = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        result = _evaluate_conditions(
            {"time_after": "09:00", "time_before": "17:00"}, {"_now": now}
        )
        assert result is True

    def test_time_range_fail(self):
        now = datetime(2024, 6, 15, 20, 0, tzinfo=timezone.utc)
        result = _evaluate_conditions(
            {"time_after": "09:00", "time_before": "17:00"}, {"_now": now}
        )
        assert result is False

    def test_day_of_week_pass(self):
        # 2024-06-17 is a Monday
        now = datetime(2024, 6, 17, 12, 0, tzinfo=timezone.utc)
        assert _evaluate_conditions(
            {"day_of_week": ["Monday", "Tuesday"]}, {"_now": now}
        ) is True

    def test_day_of_week_fail(self):
        # 2024-06-15 is a Saturday
        now = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        assert _evaluate_conditions(
            {"day_of_week": ["Monday", "Tuesday"]}, {"_now": now}
        ) is False

    def test_context_match_pass(self):
        assert _evaluate_conditions(
            {"context_match": {"env": "prod", "tier": "enterprise"}},
            {"env": "prod", "tier": "enterprise"},
        ) is True

    def test_context_match_fail(self):
        assert _evaluate_conditions(
            {"context_match": {"env": "prod"}},
            {"env": "staging"},
        ) is False

    def test_context_match_missing_key(self):
        assert _evaluate_conditions(
            {"context_match": {"env": "prod"}},
            {},
        ) is False

    def test_risk_level_pass(self):
        assert _evaluate_conditions(
            {"risk_level": "high"},
            {"risk_level": "high"},
        ) is True

    def test_risk_level_fail(self):
        assert _evaluate_conditions(
            {"risk_level": "high"},
            {"risk_level": "low"},
        ) is False

    def test_unknown_condition_ignored(self):
        assert _evaluate_conditions({"future_feature": True}, {}) is True

    def test_combined_conditions_all_must_pass(self):
        now = datetime(2024, 6, 17, 12, 0, tzinfo=timezone.utc)  # Monday 12:00
        result = _evaluate_conditions(
            {
                "time_after": "09:00",
                "time_before": "17:00",
                "day_of_week": ["Monday"],
                "context_match": {"env": "prod"},
            },
            {"_now": now, "env": "prod"},
        )
        assert result is True

    def test_combined_conditions_one_fails(self):
        now = datetime(2024, 6, 17, 12, 0, tzinfo=timezone.utc)  # Monday 12:00
        result = _evaluate_conditions(
            {
                "time_after": "09:00",
                "day_of_week": ["Tuesday"],  # fails — it's Monday
            },
            {"_now": now},
        )
        assert result is False


class TestPolicyWithConditions:
    def test_conditional_rule_skipped_when_conditions_not_met(self):
        now = datetime(2024, 6, 15, 20, 0, tzinfo=timezone.utc)  # 20:00 — outside window
        policy = Policy(
            name="test",
            rules=[
                PolicyRule(
                    action="deploy",
                    effect="allow",
                    conditions={"time_after": "09:00", "time_before": "17:00"},
                ),
                PolicyRule(action="deploy", effect="deny", reason="outside hours"),
            ],
        )
        decision = policy.evaluate("deploy", {"_now": now})
        assert not decision.allowed
        assert "outside hours" in decision.reason

    def test_conditional_rule_matches_when_conditions_met(self):
        now = datetime(2024, 6, 17, 12, 0, tzinfo=timezone.utc)
        policy = Policy(
            name="test",
            rules=[
                PolicyRule(
                    action="deploy",
                    effect="allow",
                    conditions={"time_after": "09:00", "time_before": "17:00"},
                ),
                PolicyRule(action="deploy", effect="deny", reason="fallback"),
            ],
        )
        decision = policy.evaluate("deploy", {"_now": now})
        assert decision.allowed

    def test_context_based_routing(self):
        policy = Policy(
            name="test",
            rules=[
                PolicyRule(
                    action="db:write",
                    effect="allow",
                    conditions={"context_match": {"env": "dev"}},
                ),
                PolicyRule(
                    action="db:write",
                    effect="escalate",
                    reason="prod writes need approval",
                    conditions={"context_match": {"env": "prod"}},
                ),
                PolicyRule(action="db:write", effect="deny", reason="denied"),
            ],
        )
        dev = policy.evaluate("db:write", {"env": "dev"})
        assert dev.allowed

        prod = policy.evaluate("db:write", {"env": "prod"})
        assert not prod.allowed
        assert prod.effect == "escalate"

        staging = policy.evaluate("db:write", {"env": "staging"})
        assert not staging.allowed
        assert staging.effect == "deny"

    def test_unconditional_rules_still_work(self):
        policy = Policy(
            name="test",
            rules=[PolicyRule(action="*", effect="allow")],
        )
        assert policy.evaluate("anything").allowed
