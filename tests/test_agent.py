"""Tests for the Agent class and governance checks."""

import pytest

from smn.core.agent import Agent
from smn.core.policy import Policy, PolicyRule
from smn.core.tools import tool
from smn.governance.checks import check_compliance


@tool(scopes=["math:read"])
async def dummy_tool(x: int) -> dict:
    return {"result": x}


class TestAgentCreation:
    def test_basic_creation(self):
        agent = Agent(name="test-bot", tools=[dummy_tool])
        assert agent.name == "test-bot"
        assert len(agent.tools) == 1
        assert agent.risk_level == "limited"

    def test_auto_scope_derivation(self):
        agent = Agent(name="test-bot", tools=[dummy_tool])
        assert agent.identity.has_scope("math:read")

    def test_explicit_scopes_override(self):
        agent = Agent(name="test-bot", tools=[dummy_tool], scopes=["admin:*"])
        assert agent.identity.has_scope("admin:write")
        assert not agent.identity.has_scope("math:read")

    def test_high_risk_auto_escalation(self):
        agent = Agent(name="high-risk-bot", risk_level="high")
        assert agent.policy.governance.require_human_oversight is True
        assert agent.policy.governance.require_impact_assessment is True

    def test_system_prompt_includes_governance(self):
        agent = Agent(name="test-bot", description="Does things")
        prompt = agent._build_system_prompt()
        assert "AI agent" in prompt
        assert "logged" in prompt.lower() or "audit" in prompt.lower()
        assert "test-bot" in prompt


class TestComplianceCheck:
    def test_minimal_risk_mostly_passes(self):
        agent = Agent(name="minimal-bot", risk_level="minimal")
        report = check_compliance(agent, frameworks=["eu-ai-act"])
        assert report.score > 0.5

    def test_high_risk_with_controls_passes(self):
        agent = Agent(name="governed-bot", risk_level="high")
        report = check_compliance(agent, frameworks=["eu-ai-act"])
        # High-risk auto-escalation should satisfy many requirements
        assert report.score > 0.5

    def test_report_summary(self):
        agent = Agent(name="test-bot")
        report = check_compliance(agent)
        summary = report.summary()
        assert "agent" in summary
        assert "score" in summary
        assert "passed" in summary
