"""Tests for SSE streaming execution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smn.core.agent import Agent
from smn.core.identity import Identity
from smn.core.policy import Policy, PolicyLimits, PolicyRule
from smn.core.runtime import StreamEvent, execute_task_stream

_RC = "smn.core.runtime.reliable_completion"


def _make_agent(*, tools=(), policy_rules=None, max_steps=10):
    rules = policy_rules or [PolicyRule(action="*", effect="allow")]
    policy = Policy(
        name="test",
        rules=rules,
        limits=PolicyLimits(max_steps_per_task=max_steps),
    )
    return Agent(
        name="stream-test",
        model="test/model",
        tools=tools,
        policy=policy,
        tenant_id="t1",
    )


def _llm_final(content="done"):
    resp = MagicMock()
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
    resp.choices = [MagicMock(message=msg)]
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return resp


def _llm_tool_call(name="add", args='{"a":1}', call_id="c1"):
    resp = MagicMock()
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = args
    tc.id = call_id
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant", "tool_calls": [{"id": call_id}]}
    resp.choices = [MagicMock(message=msg)]
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return resp


async def _collect_events(agent, task, **kwargs) -> list[StreamEvent]:
    events = []
    async for event in execute_task_stream(agent, task, **kwargs):
        events.append(event)
    return events


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_final_answer(mock_rc):
    mock_rc.return_value = _llm_final("hello world")
    agent = _make_agent()
    events = await _collect_events(agent, "say hello")

    event_types = [e.event for e in events]
    assert "task_start" in event_types
    assert "step_start" in event_types
    assert "final_answer" in event_types
    assert "task_complete" in event_types

    final = next(e for e in events if e.event == "final_answer")
    assert final.data["content"] == "hello world"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_tool_call(mock_rc):
    from smn.core.tools import tool

    @tool(scopes=[])
    async def greet(name: str) -> dict:
        """Say hi."""
        return {"greeting": f"hi {name}"}

    mock_rc.side_effect = [
        _llm_tool_call("greet", '{"name":"Alice"}', "c1"),
        _llm_final("greeted Alice"),
    ]
    agent = _make_agent(tools=[greet])
    events = await _collect_events(agent, "greet Alice")

    event_types = [e.event for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "final_answer" in event_types

    tc_event = next(e for e in events if e.event == "tool_call")
    assert tc_event.data["name"] == "greet"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_policy_deny(mock_rc):
    agent = _make_agent(policy_rules=[
        PolicyRule(action="task:execute", effect="deny", reason="blocked"),
    ])
    events = await _collect_events(agent, "do something")

    event_types = [e.event for e in events]
    assert "task_start" in event_types
    assert "task_error" in event_types
    assert "blocked" in events[-1].data.get("error", "")
    mock_rc.assert_not_called()


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_step_limit(mock_rc):
    mock_rc.return_value = _llm_tool_call("add", '{}', "c1")
    agent = _make_agent(max_steps=1)
    events = await _collect_events(agent, "loop forever")

    event_types = [e.event for e in events]
    # Step 1 runs, then step 2 hits limit
    assert "task_error" in event_types


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_unknown_tool(mock_rc):
    mock_rc.side_effect = [
        _llm_tool_call("nonexistent", '{}', "c1"),
        _llm_final("done"),
    ]
    agent = _make_agent()
    events = await _collect_events(agent, "use bad tool")

    denied = [e for e in events if e.event == "tool_denied"]
    assert len(denied) == 1
    assert denied[0].data["name"] == "nonexistent"


@pytest.mark.asyncio
@patch(_RC, new_callable=AsyncMock)
async def test_stream_llm_error(mock_rc):
    mock_rc.side_effect = RuntimeError("LLM exploded")
    agent = _make_agent()
    events = await _collect_events(agent, "crash")

    event_types = [e.event for e in events]
    assert "task_error" in event_types
    assert "LLM exploded" in events[-1].data["error"]
