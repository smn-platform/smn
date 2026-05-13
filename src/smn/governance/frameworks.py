"""Regulatory framework definitions — EU AI Act, NIST AI RMF, and extensible registry.

Each framework defines:
- Risk levels and what they require
- Mandatory controls per level
- Mapping from SMN capabilities to framework articles/functions

This allows SMN to:
1. Auto-configure governance controls based on declared risk level
2. Generate compliance evidence reports
3. Flag gaps between current config and regulatory requirements

Updated for:
- EU AI Act (full enforcement timeline through Aug 2027)
- NIST AI RMF 1.0 + Generative AI Profile (2024-2026)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameworkRequirement:
    """A single regulatory requirement."""

    id: str  # e.g. "EU-AI-ACT-ART-12" or "NIST-MEASURE-2.6"
    name: str
    description: str
    level: str  # risk level it applies to: "all" | "limited" | "high" | "unacceptable"
    smn_capability: str  # which SMN feature satisfies this
    is_mandatory: bool = True


@dataclass
class RegulatoryFramework:
    """A regulatory framework with its requirements."""

    id: str
    name: str
    version: str
    effective_date: str
    requirements: list[FrameworkRequirement] = field(default_factory=list)

    def requirements_for_level(self, risk_level: str) -> list[FrameworkRequirement]:
        """Get all requirements applicable to a given risk level."""
        level_hierarchy = {"minimal": 0, "limited": 1, "high": 2}
        target = level_hierarchy.get(risk_level, 1)
        result = []
        for req in self.requirements:
            if req.level == "all":
                result.append(req)
            else:
                req_level = level_hierarchy.get(req.level, 0)
                if req_level <= target:
                    result.append(req)
        return result


# ── EU AI Act ─────────────────────────────────────────────────────

EU_AI_ACT = RegulatoryFramework(
    id="eu-ai-act",
    name="EU Artificial Intelligence Act",
    version="2024/1689",
    effective_date="2025-02-02",  # Prohibited practices effective
    requirements=[
        # Prohibited practices (Art. 5) — effective Feb 2, 2025
        FrameworkRequirement(
            id="EU-AIA-ART5",
            name="Prohibited AI practices",
            description=(
                "Systems performing social scoring, real-time biometric identification "
                "in public spaces (with exceptions), manipulation, or exploitation of "
                "vulnerabilities are prohibited."
            ),
            level="all",
            smn_capability="policy.prohibited_practice_check",
        ),
        # Transparency for all AI systems (Art. 52) — effective Aug 2, 2025
        FrameworkRequirement(
            id="EU-AIA-ART52",
            name="Transparency obligations",
            description=(
                "Users must be informed they are interacting with an AI system. "
                "AI-generated content must be labeled."
            ),
            level="all",
            smn_capability="governance.transparency_disclosure",
        ),
        # GPAI obligations (Art. 51-56) — effective Aug 2, 2025
        FrameworkRequirement(
            id="EU-AIA-ART51-56",
            name="General-purpose AI model obligations",
            description=(
                "GPAI providers must maintain technical documentation, training data "
                "summaries, and comply with copyright law. Systemic risk models have "
                "additional evaluation and incident reporting obligations."
            ),
            level="all",
            smn_capability="audit.model_documentation",
        ),
        # Risk management (Art. 9) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART9",
            name="Risk management system",
            description=(
                "High-risk AI must have a continuous risk management system covering "
                "identification, estimation, evaluation, and mitigation of risks."
            ),
            level="high",
            smn_capability="policy.risk_management",
        ),
        # Data governance (Art. 10) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART10",
            name="Data governance",
            description=(
                "Training, validation, and testing datasets must meet quality criteria. "
                "Bias examination and mitigation required."
            ),
            level="high",
            smn_capability="governance.data_governance",
        ),
        # Technical documentation (Art. 11) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART11",
            name="Technical documentation",
            description="High-risk AI must maintain technical documentation before market placement.",
            level="high",
            smn_capability="audit.technical_documentation",
        ),
        # Record-keeping / logging (Art. 12) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART12",
            name="Automatic logging",
            description=(
                "High-risk AI must have automatic logging of events throughout the "
                "system's lifetime, ensuring traceability of operations."
            ),
            level="high",
            smn_capability="audit.immutable_log",
        ),
        # Transparency to deployers (Art. 13) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART13",
            name="Transparency to deployers",
            description="High-risk AI must be transparent to deployers with clear usage instructions.",
            level="high",
            smn_capability="governance.deployer_transparency",
        ),
        # Human oversight (Art. 14) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART14",
            name="Human oversight",
            description=(
                "High-risk AI must allow effective human oversight including ability "
                "to understand, monitor, intervene, and stop the system."
            ),
            level="high",
            smn_capability="governance.human_oversight",
        ),
        # Accuracy, robustness, cybersecurity (Art. 15) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART15",
            name="Accuracy, robustness, cybersecurity",
            description="High-risk AI must achieve appropriate levels of accuracy and resilience.",
            level="high",
            smn_capability="governance.robustness",
        ),
        # Corrective actions (Art. 20) — effective Aug 2, 2026
        FrameworkRequirement(
            id="EU-AIA-ART20",
            name="Corrective actions",
            description="Providers must take corrective actions for non-conforming systems.",
            level="high",
            smn_capability="governance.kill_switch",
        ),
    ],
)


# ── NIST AI RMF ──────────────────────────────────────────────────

NIST_AI_RMF = RegulatoryFramework(
    id="nist-ai-rmf",
    name="NIST AI Risk Management Framework",
    version="1.0",
    effective_date="2023-01-26",
    requirements=[
        # GOVERN function
        FrameworkRequirement(
            id="NIST-GOV-1",
            name="Policies and processes",
            description="Establish and maintain AI risk management policies and processes.",
            level="all",
            smn_capability="policy.engine",
        ),
        FrameworkRequirement(
            id="NIST-GOV-1.2",
            name="Risk management process",
            description="Processes for AI risk management are established and integrated.",
            level="all",
            smn_capability="policy.risk_management",
        ),
        FrameworkRequirement(
            id="NIST-GOV-4",
            name="Organizational practices",
            description="Organizational teams document and follow AI risk management practices.",
            level="all",
            smn_capability="governance.organizational_controls",
        ),
        # MAP function
        FrameworkRequirement(
            id="NIST-MAP-1",
            name="Context and risk framing",
            description="Context is established and risks are framed related to AI system.",
            level="all",
            smn_capability="policy.risk_classification",
        ),
        FrameworkRequirement(
            id="NIST-MAP-3",
            name="Benefits and costs",
            description="AI benefits and costs are assessed and documented.",
            level="all",
            smn_capability="finops.cost_tracking",
        ),
        # MEASURE function
        FrameworkRequirement(
            id="NIST-MEAS-2",
            name="Risk measurement",
            description="AI systems are evaluated for trustworthy characteristics.",
            level="all",
            smn_capability="audit.immutable_log",
        ),
        FrameworkRequirement(
            id="NIST-MEAS-2.6",
            name="Monitoring",
            description="AI system performance and risks are monitored on an ongoing basis.",
            level="all",
            smn_capability="finops.monitoring",
        ),
        # MANAGE function
        FrameworkRequirement(
            id="NIST-MAN-1",
            name="Risk response",
            description="AI risks are prioritized and responded to based on impact.",
            level="all",
            smn_capability="governance.kill_switch",
        ),
        FrameworkRequirement(
            id="NIST-MAN-2",
            name="Risk treatment",
            description="Strategies to manage AI risk are planned and implemented.",
            level="all",
            smn_capability="policy.risk_management",
        ),
        FrameworkRequirement(
            id="NIST-MAN-4",
            name="Residual risk documentation",
            description="Residual risks are documented and communicated.",
            level="all",
            smn_capability="audit.risk_documentation",
        ),
    ],
)

# ── Framework Registry ───────────────────────────────────────────

FRAMEWORK_REGISTRY: dict[str, RegulatoryFramework] = {
    "eu-ai-act": EU_AI_ACT,
    "nist-ai-rmf": NIST_AI_RMF,
}


def get_framework(framework_id: str) -> RegulatoryFramework | None:
    return FRAMEWORK_REGISTRY.get(framework_id)


def list_frameworks() -> list[str]:
    return list(FRAMEWORK_REGISTRY.keys())
