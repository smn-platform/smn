"""Compliance checks — evaluate an agent's configuration against regulatory frameworks.

Produces a structured compliance report showing:
- Which requirements are satisfied
- Which requirements have gaps
- Recommended actions to close gaps

Usage:
    from smn.governance.checks import check_compliance
    report = check_compliance(agent, frameworks=["eu-ai-act", "nist-ai-rmf"])
    for item in report.items:
        print(f"[{item.status}] {item.requirement_id}: {item.message}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smn.core.agent import Agent
from smn.governance.frameworks import FRAMEWORK_REGISTRY, FrameworkRequirement


@dataclass
class ComplianceItem:
    """Result for a single requirement check."""

    requirement_id: str
    requirement_name: str
    framework: str
    status: str  # "pass" | "fail" | "warning" | "not_applicable"
    message: str
    remediation: str = ""


@dataclass
class ComplianceReport:
    """Full compliance assessment for an agent."""

    agent_name: str
    risk_level: str
    frameworks: list[str]
    items: list[ComplianceItem] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for i in self.items if i.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if i.status == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.items if i.status == "warning")

    @property
    def score(self) -> float:
        """Compliance score 0.0–1.0.

        Passes count as 1.0, warnings (manual-review-needed) as 0.5,
        failures as 0.0.  Not-applicable items are excluded.
        """
        applicable = [i for i in self.items if i.status != "not_applicable"]
        if not applicable:
            return 1.0
        points = sum(
            1.0 if i.status == "pass" else 0.5 if i.status == "warning" else 0.0
            for i in applicable
        )
        return points / len(applicable)

    def summary(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "risk_level": self.risk_level,
            "frameworks": self.frameworks,
            "score": round(self.score, 2),
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "total": len(self.items),
        }


# ── Capability → check mapping ───────────────────────────────────

_CAPABILITY_CHECKS: dict[str, Any] = {}


def _check(capability: str):
    """Decorator to register a compliance check function."""
    def decorator(func):
        _CAPABILITY_CHECKS[capability] = func
        return func
    return decorator


@_check("governance.transparency_disclosure")
def _check_transparency(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.policy.governance.require_transparency_disclosure:
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message="Transparency disclosure is enabled in agent policy.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="fail",
        message="Transparency disclosure is NOT enabled.",
        remediation="Set require_transparency_disclosure=true in the agent's policy.",
    )


@_check("governance.human_oversight")
def _check_human_oversight(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.risk_level != "high":
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="not_applicable",
            message=f"Human oversight not required for '{agent.risk_level}' risk level.",
        )
    if agent.policy.governance.require_human_oversight:
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message="Human oversight is enabled for this high-risk agent.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="fail",
        message="High-risk agent does NOT have human oversight enabled.",
        remediation="Set require_human_oversight=true or use risk_level='high' (auto-enables).",
    )


@_check("audit.immutable_log")
def _check_audit_log(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.policy.governance.log_inputs and agent.policy.governance.log_outputs:
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message="Full input/output audit logging is enabled.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="warning",
        message="Partial audit logging — some inputs or outputs may not be recorded.",
        remediation="Enable log_inputs and log_outputs in the agent's policy.",
    )


@_check("governance.kill_switch")
def _check_kill_switch(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    from smn.config import settings

    if settings.enable_kill_switch:
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message="Kill switch is enabled at platform level.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="fail",
        message="Kill switch is disabled.",
        remediation="Set SMN_ENABLE_KILL_SWITCH=true in environment.",
    )


@_check("policy.engine")
def _check_policy_engine(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.policy and agent.policy.name != "_restrictive_default":
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message=f"Policy '{agent.policy.name}' is loaded and active.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="warning",
        message="Using restrictive default policy — no explicit policy configured.",
        remediation="Create and assign a named policy for this agent.",
    )


@_check("policy.risk_classification")
def _check_risk_classification(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.risk_level in ("minimal", "limited", "high"):
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="pass",
            message=f"Risk level is explicitly set to '{agent.risk_level}'.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="warning",
        message=f"Unrecognized risk level '{agent.risk_level}'.",
        remediation="Use one of: 'minimal', 'limited', 'high'.",
    )


@_check("finops.cost_tracking")
def _check_cost_tracking(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="pass",
        message=f"Cost tracking active with ${agent.max_cost_per_task:.2f} per-task budget.",
    )


@_check("policy.risk_management")
def _check_risk_management(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    if agent.risk_level == "high" and not agent.policy.governance.require_impact_assessment:
        return ComplianceItem(
            requirement_id=req.id,
            requirement_name=req.name,
            framework=req.id.split("-")[0],
            status="fail",
            message="High-risk agent should require impact assessment.",
            remediation="Set require_impact_assessment=true in policy governance flags.",
        )
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="pass",
        message="Risk management controls are appropriately configured.",
    )


# ── Default handler for unmapped capabilities ────────────────────

def _default_check(agent: Agent, req: FrameworkRequirement) -> ComplianceItem:
    return ComplianceItem(
        requirement_id=req.id,
        requirement_name=req.name,
        framework=req.id.split("-")[0],
        status="warning",
        message=f"No automated check for capability '{req.smn_capability}'.",
        remediation="Manual review recommended.",
    )


# ── Main check function ──────────────────────────────────────────


def check_compliance(
    agent: Agent,
    frameworks: list[str] | None = None,
) -> ComplianceReport:
    """Run a full compliance check against selected frameworks.

    Parameters
    ----------
    agent
        The agent to assess.
    frameworks
        Framework IDs to check. Defaults to all registered frameworks.
    """
    fw_ids = frameworks or list(FRAMEWORK_REGISTRY.keys())
    report = ComplianceReport(
        agent_name=agent.name,
        risk_level=agent.risk_level,
        frameworks=fw_ids,
    )

    for fw_id in fw_ids:
        fw = FRAMEWORK_REGISTRY.get(fw_id)
        if fw is None:
            continue
        applicable = fw.requirements_for_level(agent.risk_level)
        for req in applicable:
            check_fn = _CAPABILITY_CHECKS.get(req.smn_capability, _default_check)
            item = check_fn(agent, req)
            item.framework = fw_id
            report.items.append(item)

    return report
