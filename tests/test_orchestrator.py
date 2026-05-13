"""Tests for multi-agent orchestration — graph execution and handoffs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from smn.core.agent import Agent, AgentResult
from smn.core.orchestrator import AgentGraph, HandoffResult, run_parallel
from smn.core.policy import Policy, PolicyRule

_RC = "smn.core.runtime.reliable_completion"


def _make_agent(name="a1"):
    policy = Policy(name="test", rules=[PolicyRule(action="*", effect="allow")])
    return Agent(name=name, model="test/m", policy=policy, tenant_id="t1")


def _mock_result(output="done", status="completed", cost=0.01, steps=1):
    return AgentResult(
        task_id="t-1", status=status, output=output,
        cost_usd=cost, steps=steps, audit_ids=[],
    )


class TestAgentGraph:
    def test_add_agent(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        assert "a" in g.agents

    def test_get_targets_no_edges(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        assert g.get_targets("a", {}) == []

    def test_get_targets_unconditional(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        g.add_agent("b", _make_agent("b"))
        g.add_edge("a", "b")
        assert g.get_targets("a", {}) == ["b"]

    def test_get_targets_conditional(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        g.add_agent("b", _make_agent("b"))
        g.add_agent("c", _make_agent("c"))
        g.add_edge("a", "b", condition=lambda ctx: ctx.get("route") == "b")
        g.add_edge("a", "c", condition=lambda ctx: ctx.get("route") == "c")
        assert g.get_targets("a", {"route": "b"}) == ["b"]
        assert g.get_targets("a", {"route": "c"}) == ["c"]
        assert g.get_targets("a", {"route": "x"}) == []

    def test_cycle_detection_no_cycle(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        g.add_agent("b", _make_agent("b"))
        g.add_edge("a", "b")
        assert g.has_cycle() is False

    def test_cycle_detection_with_cycle(self):
        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        g.add_agent("b", _make_agent("b"))
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        assert g.has_cycle() is True

    @pytest.mark.asyncio
    @patch(_RC, new_callable=AsyncMock)
    async def test_execute_single_agent(self, mock_rc):
        from unittest.mock import MagicMock

        resp = MagicMock()
        msg = MagicMock()
        msg.content = "result-a"
        msg.tool_calls = None
        msg.model_dump.return_value = {"role": "assistant", "content": "result-a"}
        resp.choices = [MagicMock(message=msg)]
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_rc.return_value = resp

        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        result = await g.execute("a", "do something")

        assert isinstance(result, HandoffResult)
        assert result.final_output == "result-a"
        assert result.handoff_chain == ["a"]
        assert len(result.agent_results) == 1

    @pytest.mark.asyncio
    @patch(_RC, new_callable=AsyncMock)
    async def test_execute_handoff_chain(self, mock_rc):
        from unittest.mock import MagicMock

        def _make_response(content):
            resp = MagicMock()
            msg = MagicMock()
            msg.content = content
            msg.tool_calls = None
            msg.model_dump.return_value = {"role": "assistant", "content": content}
            resp.choices = [MagicMock(message=msg)]
            resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            return resp

        mock_rc.side_effect = [
            _make_response("from-a"),
            _make_response("from-b"),
        ]

        g = AgentGraph()
        g.add_agent("a", _make_agent("a"))
        g.add_agent("b", _make_agent("b"))
        g.add_edge("a", "b")

        result = await g.execute("a", "start")
        assert result.handoff_chain == ["a", "b"]
        assert result.final_output == "from-b"
        assert len(result.agent_results) == 2

    @pytest.mark.asyncio
    async def test_execute_unknown_start(self):
        g = AgentGraph()
        with pytest.raises(ValueError, match="unknown agent"):
            await g.execute("nonexistent", "task")


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_run_parallel(mock_rc):
    from unittest.mock import MagicMock

    def _make_response(content):
        resp = MagicMock()
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = None
        msg.model_dump.return_value = {"role": "assistant", "content": content}
        resp.choices = [MagicMock(message=msg)]
        resp.usage = MagicMock(prompt_tokens=5, completion_tokens=3)
        return resp

    mock_rc.side_effect = [_make_response("r1"), _make_response("r2")]

    agents = {"x": _make_agent("x"), "y": _make_agent("y")}
    results = await run_parallel(agents, "shared task")

    assert set(results.keys()) == {"x", "y"}
    assert all(r.status == "completed" for r in results.values())
