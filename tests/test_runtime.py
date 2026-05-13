"""Tests for runtime.py — the governed ReAct execution loop.

These tests mock reliable_completion to avoid real LLM calls while exercising
every governance gate: permissions, policy rules, cost budget, approval, step limits.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from smn.core.agent import Agent, AgentResult
from smn.core.policy import GovernanceFlags, Policy, PolicyLimits, PolicyRule
from smn.core.tools import tool

_RC = "smn.core.runtime.reliable_completion"


# ── Test tools ───────────────────────────────────────────────────


@tool(scopes=["math:read"])
async def add(a: int, b: int) -> dict:
    """Add two numbers."""
    return {"result": a + b}


@tool(scopes=["math:read"])
async def multiply(a: int, b: int) -> dict:
    """Multiply two numbers."""
    return {"result": a * b}


@tool(scopes=["data:write"], requires_approval=True)
async def write_data(key: str, value: str) -> dict:
    """Write data (requires approval)."""
    return {"written": True, "key": key}


@tool(scopes=["data:delete"])
async def delete_data(key: str) -> dict:
    """Delete data."""
    return {"deleted": True}


@tool(scopes=["math:read"], cost_estimate_usd=10.0)
async def expensive_fn(query: str) -> dict:
    """An expensive operation."""
    return {"result": query}


@tool(scopes=["error:read"])
async def failing_tool(msg: str) -> dict:
    """A tool that always raises."""
    raise RuntimeError(f"Boom: {msg}")


# ── Helpers ──────────────────────────────────────────────────────


def _make_policy(*, rules=None, limits=None, governance=None):
    return Policy(
        name="test-policy",
        risk_level="limited",
        rules=rules or [PolicyRule(action="*", effect="allow")],
        limits=limits or PolicyLimits(max_cost_per_task_usd=5.0, max_steps_per_task=50),
        governance=governance or GovernanceFlags(),
    )


def _make_agent(tools=None, scopes=None, policy=None, max_cost=5.0):
    t = tools or [add, multiply]
    return Agent(
        name="test-agent",
        tools=t,
        scopes=scopes,
        policy=policy or _make_policy(),
        max_cost_per_task=max_cost,
        tenant_id="test-tenant",
    )


def _llm_final(content):
    msg = SimpleNamespace(content=content, tool_calls=None)
    msg.model_dump = lambda exclude_none=False: {"role": "assistant", "content": content}
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
    return SimpleNamespace(choices=[choice], usage=usage)


def _llm_tc(name, args, call_id="call_1"):
    tc = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )
    msg = SimpleNamespace(content=None, tool_calls=[tc])
    msg.model_dump = lambda exclude_none=False: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}},
        ],
    }
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    return SimpleNamespace(choices=[choice], usage=usage)


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_final_answer(mock_rc):
    mock_rc.return_value = _llm_final("The answer is 42")
    result = await _make_agent().run("What is the answer?")
    assert result.status == "completed"
    assert "42" in result.output
    assert result.steps == 1
    assert result.cost_usd >= 0


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_tool_call_then_answer(mock_rc):
    mock_rc.side_effect = [_llm_tc("add", {"a": 2, "b": 3}), _llm_final("The result is 5")]
    result = await _make_agent().run("Add 2 + 3")
    assert result.status == "completed"
    assert "5" in result.output
    assert result.steps == 2
    assert mock_rc.call_count == 2


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_unknown_tool(mock_rc):
    mock_rc.side_effect = [_llm_tc("nonexistent", {"x": 1}), _llm_final("ok")]
    result = await _make_agent().run("Use nonexistent")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_permission_denied(mock_rc):
    mock_rc.side_effect = [_llm_tc("delete_data", {"key": "foo"}), _llm_final("denied")]
    result = await _make_agent(tools=[delete_data], scopes=["math:read"]).run("Delete foo")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_policy_deny(mock_rc):
    policy = _make_policy(rules=[
        PolicyRule(action="task:execute", effect="allow"),
        PolicyRule(action="add", effect="deny", reason="no math"),
    ])
    mock_rc.side_effect = [_llm_tc("add", {"a": 1, "b": 2}), _llm_final("denied")]
    result = await _make_agent(policy=policy).run("Add 1+2")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_policy_escalate_approved(mock_rc):
    policy = _make_policy(rules=[
        PolicyRule(action="task:execute", effect="allow"),
        PolicyRule(action="add", effect="escalate", reason="needs approval"),
    ])
    mock_rc.side_effect = [_llm_tc("add", {"a": 1, "b": 2}), _llm_final("3")]
    cb = AsyncMock(return_value=True)
    result = await _make_agent(policy=policy).run("Add", approval_callback=cb)
    assert result.status == "completed"
    cb.assert_called_once()


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_policy_escalate_denied(mock_rc):
    policy = _make_policy(rules=[
        PolicyRule(action="task:execute", effect="allow"),
        PolicyRule(action="add", effect="escalate", reason="needs approval"),
    ])
    mock_rc.side_effect = [_llm_tc("add", {"a": 1, "b": 2}), _llm_final("not approved")]
    cb = AsyncMock(return_value=False)
    result = await _make_agent(policy=policy).run("Add", approval_callback=cb)
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_cost_budget_exceeded(mock_rc):
    mock_rc.side_effect = [_llm_tc("expensive_fn", {"query": "x"}), _llm_final("over budget")]
    result = await _make_agent(tools=[expensive_fn], scopes=["math:read"], max_cost=5.0).run("Go")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_approval_required_no_callback(mock_rc):
    mock_rc.side_effect = [_llm_tc("write_data", {"key": "k", "value": "v"}), _llm_final("no")]
    result = await _make_agent(tools=[write_data], scopes=["data:write"]).run("Write")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_gate_approval_required_with_callback(mock_rc):
    mock_rc.side_effect = [_llm_tc("write_data", {"key": "k", "value": "v"}), _llm_final("ok")]
    cb = AsyncMock(return_value=True)
    result = await _make_agent(tools=[write_data], scopes=["data:write"]).run("Write", approval_callback=cb)
    assert result.status == "completed"
    cb.assert_called_once()


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_step_limit_enforced(mock_rc):
    policy = _make_policy(limits=PolicyLimits(max_steps_per_task=2))
    mock_rc.side_effect = [
        _llm_tc("add", {"a": 1, "b": 1}, "c1"),
        _llm_tc("add", {"a": 2, "b": 2}, "c2"),
        _llm_tc("add", {"a": 3, "b": 3}, "c3"),
    ]
    result = await _make_agent(policy=policy).run("Loop")
    assert result.status == "failed"
    assert "step" in (result.error or "").lower()


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_task_denied_by_policy(mock_rc):
    policy = _make_policy(rules=[PolicyRule(action="*", effect="deny", reason="lockdown")])
    result = await _make_agent(policy=policy).run("Anything")
    assert result.status == "denied"
    assert "denied" in (result.error or "").lower()
    mock_rc.assert_not_called()


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_tool_execution_error(mock_rc):
    mock_rc.side_effect = [_llm_tc("failing_tool", {"msg": "boom"}), _llm_final("failed")]
    result = await _make_agent(tools=[failing_tool], scopes=["error:read"]).run("Fail")
    assert result.status == "completed"
    assert result.steps == 2


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_llm_error_caught(mock_rc):
    mock_rc.side_effect = RuntimeError("LLM down")
    result = await _make_agent().run("Crash")
    assert result.status == "failed"
    assert result.error is not None


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_cost_tracking(mock_rc):
    mock_rc.return_value = _llm_final("done")
    result = await _make_agent().run("Quick")
    assert result.cost_usd > 0


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_audit_ids_populated(mock_rc, db):
    mock_rc.return_value = _llm_final("done")
    result = await _make_agent().run("Audit", db_session=db)
    assert len(result.audit_ids) >= 2


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_multiple_tool_calls(mock_rc):
    tc1 = SimpleNamespace(id="c1", function=SimpleNamespace(name="add", arguments='{"a":1,"b":2}'))
    tc2 = SimpleNamespace(id="c2", function=SimpleNamespace(name="multiply", arguments='{"a":3,"b":4}'))
    msg = SimpleNamespace(content=None, tool_calls=[tc1, tc2])
    msg.model_dump = lambda exclude_none=False: {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "add", "arguments": '{"a":1,"b":2}'}},
        {"id": "c2", "type": "function", "function": {"name": "multiply", "arguments": '{"a":3,"b":4}'}},
    ]}
    multi = SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=30))
    mock_rc.side_effect = [multi, _llm_final("3 and 12")]
    result = await _make_agent().run("Both")
    assert result.status == "completed"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_redacts_when_logging_disabled(mock_rc, db):
    mock_rc.return_value = _llm_final("done")
    policy = _make_policy(governance=GovernanceFlags(log_inputs=False, log_outputs=False))
    result = await _make_agent(policy=policy).run("secret", db_session=db)
    assert result.status == "completed"
    from smn.core.audit import get_audit_trail
    entries = await get_audit_trail(db, "test-tenant")
    start = [e for e in entries if e.event_type == "task.start"]
    assert start
    assert "<redacted>" in start[0].detail
