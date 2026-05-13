"""Policy engine — YAML-based, layered policy evaluation.

Policies are the central governance mechanism.  Every agent action passes
through the policy engine before execution.

A policy file looks like:

    name: default
    risk_level: limited
    rules:
      - action: "*"
        effect: allow
      - action: "db:delete"
        effect: deny
        reason: "Destructive database operations are prohibited"
    limits:
      max_cost_per_task_usd: 5.00
      max_steps_per_task: 50
      max_tool_calls_per_minute: 120
    governance:
      require_transparency_disclosure: true
      require_human_oversight: false
      log_inputs: true
      log_outputs: true

Regulatory alignment:
- EU AI Act Art. 9 (risk management for high-risk)
- EU AI Act Art. 14 (human oversight for high-risk)
- EU AI Act Art. 13 (transparency)
- EU AI Act Art. 52 (transparency for certain AI systems)
- NIST AI RMF GOVERN-1 (policies and processes)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from smn.config import settings

logger = logging.getLogger(__name__)

# ── Condition evaluation (ABAC) ──────────────────────────────────


def _evaluate_conditions(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    """Evaluate all conditions in a rule. All must pass (AND logic).

    Supported condition types:
    - time_after / time_before: HH:MM (UTC)
    - day_of_week: list of weekday names
    - context_match: dict of key/value pairs that must match context
    - risk_level: required risk level
    """
    from datetime import datetime, timezone

    now = context.get("_now") or datetime.now(timezone.utc)  # allow test injection

    for key, value in conditions.items():
        if key == "time_after":
            h, m = (int(x) for x in value.split(":"))
            if now.hour < h or (now.hour == h and now.minute < m):
                return False

        elif key == "time_before":
            h, m = (int(x) for x in value.split(":"))
            if now.hour > h or (now.hour == h and now.minute >= m):
                return False

        elif key == "day_of_week":
            day_names = [d.lower() for d in value]
            current_day = now.strftime("%A").lower()
            if current_day not in day_names:
                return False

        elif key == "context_match":
            if not isinstance(value, dict):
                return False
            for ck, cv in value.items():
                if context.get(ck) != cv:
                    return False

        elif key == "risk_level":
            if context.get("risk_level") != value:
                return False

        else:
            logger.warning("unknown condition type: %s", key)
            # Unknown conditions are ignored (fail-open for extensibility)

    return True

# ── Data structures ──────────────────────────────────────────────


@dataclass
class PolicyRule:
    action: str  # glob pattern, e.g. "tickets:*" or "*"
    effect: str  # allow | deny | escalate
    reason: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyLimits:
    max_cost_per_task_usd: float = 5.0
    max_steps_per_task: int = 50
    max_tool_calls_per_minute: int = 120


@dataclass
class GovernanceFlags:
    require_transparency_disclosure: bool = True  # EU AI Act Art. 52
    require_human_oversight: bool = False  # EU AI Act Art. 14
    log_inputs: bool = True  # EU AI Act Art. 12
    log_outputs: bool = True
    require_impact_assessment: bool = False  # For high-risk
    data_residency: str | None = None  # ISO country code or None


@dataclass
class Policy:
    """A loaded, evaluated policy."""

    name: str
    risk_level: str = "limited"  # minimal | limited | high
    rules: list[PolicyRule] = field(default_factory=list)
    limits: PolicyLimits = field(default_factory=PolicyLimits)
    governance: GovernanceFlags = field(default_factory=GovernanceFlags)
    frameworks: list[str] = field(default_factory=list)  # e.g. ["eu-ai-act", "nist-rmf"]

    # ── Evaluation ────────────────────────────────────────────────

    def evaluate(self, action: str, context: dict[str, Any] | None = None) -> PolicyDecision:
        """Evaluate whether an action is allowed under this policy.

        Rules are evaluated in order; the first matching rule wins.
        If no rule matches, the default is DENY (secure by default).

        Conditions (ABAC) are evaluated when present on a rule:
        - ``time_after`` / ``time_before``: HH:MM bounds (UTC)
        - ``day_of_week``: list of weekday names (e.g. ["monday", "friday"])
        - ``context_match``: dict of key/value pairs that must match context
        - ``risk_level``: required risk level from context

        A rule only matches if its action pattern matches AND all conditions
        are satisfied.
        """
        context = context or {}

        for rule in self.rules:
            if not _action_matches(rule.action, action):
                continue
            if rule.conditions and not _evaluate_conditions(rule.conditions, context):
                continue

            if rule.effect == "deny":
                return PolicyDecision(
                    allowed=False, effect="deny", reason=rule.reason or "denied by rule"
                )
            if rule.effect == "escalate":
                return PolicyDecision(
                    allowed=False,
                    effect="escalate",
                    reason=rule.reason or "requires human approval",
                )
            if rule.effect == "allow":
                return PolicyDecision(allowed=True, effect="allow", reason="allowed by rule")

        # No matching rule → deny by default (secure-by-default)
        return PolicyDecision(
            allowed=False,
            effect="deny",
            reason="no matching policy rule — denied by default",
        )

    def check_cost(self, current_cost: float, additional: float) -> PolicyDecision:
        """Check if a cost increment would exceed the task budget."""
        projected = current_cost + additional
        if projected > self.limits.max_cost_per_task_usd:
            return PolicyDecision(
                allowed=False,
                effect="deny",
                reason=(
                    f"cost ${projected:.4f} would exceed task limit "
                    f"${self.limits.max_cost_per_task_usd:.2f}"
                ),
            )
        if additional > settings.require_human_approval_above_usd:
            return PolicyDecision(
                allowed=False,
                effect="escalate",
                reason=(
                    f"action cost ${additional:.4f} exceeds approval threshold "
                    f"${settings.require_human_approval_above_usd:.2f}"
                ),
            )
        return PolicyDecision(allowed=True, effect="allow", reason="within budget")

    def check_step_limit(self, current_steps: int) -> PolicyDecision:
        if current_steps >= self.limits.max_steps_per_task:
            return PolicyDecision(
                allowed=False,
                effect="deny",
                reason=f"step limit {self.limits.max_steps_per_task} reached",
            )
        return PolicyDecision(allowed=True, effect="allow", reason="within step limit")


@dataclass
class PolicyDecision:
    allowed: bool
    effect: str  # allow | deny | escalate
    reason: str = ""


# ── Pattern matching ─────────────────────────────────────────────


def _action_matches(pattern: str, action: str) -> bool:
    """Simple glob-style matching for action strings.

    - ``"*"`` matches everything.
    - ``"tickets:*"`` matches ``"tickets:read"``, ``"tickets:write"``, etc.
    - ``"*:read"`` matches ``"tickets:read"``, ``"db:read"``, etc.
    - Exact string match otherwise.
    """
    if pattern == "*":
        return True
    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return action == prefix or action.startswith(prefix + ":")
    if pattern.startswith("*:"):
        suffix = pattern[2:]
        return action == suffix or action.endswith(":" + suffix)
    return pattern == action


# ── Loader ────────────────────────────────────────────────────────


def load_policy(name: str, policy_dir: Path | None = None) -> Policy:
    """Load a policy from a YAML file by name."""
    base = policy_dir or settings.policy_dir
    candidates = [base / f"{name}.yaml", base / f"{name}.yml"]
    for path in candidates:
        if path.exists():
            return _parse_policy_file(path)
    logger.warning("Policy '%s' not found in %s — using restrictive default", name, base)
    return _restrictive_default()


def _parse_policy_file(path: Path) -> Policy:
    with open(path) as f:
        data = yaml.safe_load(f)

    rules = [
        PolicyRule(
            action=r.get("action", "*"),
            effect=r.get("effect", "deny"),
            reason=r.get("reason", ""),
            conditions=r.get("conditions", {}),
        )
        for r in data.get("rules", [])
    ]

    lim = data.get("limits", {})
    limits = PolicyLimits(
        max_cost_per_task_usd=lim.get("max_cost_per_task_usd", 5.0),
        max_steps_per_task=lim.get("max_steps_per_task", 50),
        max_tool_calls_per_minute=lim.get("max_tool_calls_per_minute", 120),
    )

    gov = data.get("governance", {})
    governance = GovernanceFlags(
        require_transparency_disclosure=gov.get("require_transparency_disclosure", True),
        require_human_oversight=gov.get("require_human_oversight", False),
        log_inputs=gov.get("log_inputs", True),
        log_outputs=gov.get("log_outputs", True),
        require_impact_assessment=gov.get("require_impact_assessment", False),
        data_residency=gov.get("data_residency"),
    )

    return Policy(
        name=data.get("name", path.stem),
        risk_level=data.get("risk_level", "limited"),
        rules=rules,
        limits=limits,
        governance=governance,
        frameworks=data.get("frameworks", []),
    )


def _restrictive_default() -> Policy:
    """Fallback policy: deny everything except read operations."""
    return Policy(
        name="_restrictive_default",
        risk_level="high",
        rules=[
            PolicyRule(action="*:read", effect="allow", reason="reads allowed by default"),
            PolicyRule(action="*", effect="deny", reason="all other actions denied by default"),
        ],
        limits=PolicyLimits(max_cost_per_task_usd=0.10, max_steps_per_task=5),
        governance=GovernanceFlags(
            require_transparency_disclosure=True,
            require_human_oversight=True,
            log_inputs=True,
            log_outputs=True,
            require_impact_assessment=True,
        ),
    )
