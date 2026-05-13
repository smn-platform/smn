"""Runtime — the execution engine that runs agent tasks with full governance.

This is the heart of SMN.  It implements a governed ReAct loop:

    while not done:
        1. Send context + tools to LLM
        2. LLM responds with tool calls or final answer
        3. For each tool call:
           a. Check identity permissions
           b. Check policy rules
           c. Check cost budget
           d. If denied → log and tell LLM
           e. If escalate → pause for human approval
           f. If allowed → execute, log, track cost
        4. Check step limit
        5. Loop or return result

Every step is logged to the immutable audit trail.
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import litellm

from smn.connectors.llm import reliable_completion
from smn.core.agent import Agent, AgentResult
from smn.core.finops import TaskBudget, estimate_llm_cost
from smn.core.identity import check_permissions
from smn.core.memory import SessionMemory
from smn.core.tools import get_tool_spec, tools_to_openai_schema

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """A single event emitted during streaming execution."""

    event: str  # task_start | step_start | tool_call | tool_result | tool_denied | final_answer | task_complete | task_error
    data: dict[str, Any]


async def execute_task(
    agent: Agent,
    task: str,
    *,
    db_session: Any | None = None,
    approval_callback: Any | None = None,
) -> AgentResult:
    """Execute a task with full governance.

    Parameters
    ----------
    agent
        The agent to run.
    task
        Natural-language task description.
    db_session
        Optional SQLAlchemy async session for audit logging.
        If None, audit entries are logged to stdout only.
    approval_callback
        Optional async callable for human-in-the-loop approval.
        Signature: ``async def approve(action: str, detail: dict) -> bool``
    """
    task_id = _generate_id()
    budget = TaskBudget(max_usd=agent.max_cost_per_task)
    audit_ids: list[str] = []
    step = 0

    # Log task start
    await _audit(
        db_session,
        tenant_id=agent.tenant_id,
        agent_id=agent.identity.agent_id,
        task_id=task_id,
        event_type="task.start",
        action="execute",
        detail={"input": task if agent.policy.governance.log_inputs else "<redacted>"},
        audit_ids=audit_ids,
    )

    # Check if the agent is even allowed to run tasks
    task_decision = agent.policy.evaluate("task:execute")
    if not task_decision.allowed:
        await _audit(
            db_session,
            tenant_id=agent.tenant_id,
            agent_id=agent.identity.agent_id,
            task_id=task_id,
            event_type="task.denied",
            action="execute",
            detail={"reason": task_decision.reason},
            policy_decision=task_decision.effect,
            policy_reason=task_decision.reason,
            audit_ids=audit_ids,
        )
        return AgentResult(
            task_id=task_id,
            status="denied",
            output="",
            error=f"Task denied by policy: {task_decision.reason}",
            audit_ids=audit_ids,
        )

    # Build messages
    system_prompt = agent._build_system_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    tool_schemas = tools_to_openai_schema(agent.tools)
    tool_map = {spec.name: spec for spec in agent.tool_specs}
    tool_func_map = {spec.name: spec.func for spec in agent.tool_specs}

    try:
        while step < agent.policy.limits.max_steps_per_task:
            step += 1

            # Step limit check
            step_decision = agent.policy.check_step_limit(step)
            if not step_decision.allowed:
                await _audit(
                    db_session,
                    tenant_id=agent.tenant_id,
                    agent_id=agent.identity.agent_id,
                    task_id=task_id,
                    event_type="task.step_limit",
                    action="check_step",
                    detail={"step": step, "limit": agent.policy.limits.max_steps_per_task},
                    policy_decision="deny",
                    policy_reason=step_decision.reason,
                    audit_ids=audit_ids,
                )
                return AgentResult(
                    task_id=task_id,
                    status="failed",
                    output="",
                    error=f"Step limit reached: {step_decision.reason}",
                    steps=step,
                    cost_usd=budget.total_usd,
                    audit_ids=audit_ids,
                )

            response = await reliable_completion(
                model=agent.model,
                messages=messages,
                **({
                    "tools": tool_schemas,
                } if tool_schemas else {}),
            )
            choice = response.choices[0]  # type: ignore[index]

            # Track LLM cost
            usage = getattr(response, "usage", None)
            if usage:
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                llm_cost = estimate_llm_cost(agent.model, in_tok, out_tok)
                budget.record("llm", agent.model, llm_cost, f"step {step}")

            msg = choice.message
            messages.append(msg.model_dump(exclude_none=True))

            # If no tool calls → final answer
            if not getattr(msg, "tool_calls", None):
                output = msg.content or ""
                await _audit(
                    db_session,
                    tenant_id=agent.tenant_id,
                    agent_id=agent.identity.agent_id,
                    task_id=task_id,
                    event_type="task.complete",
                    action="final_answer",
                    detail={
                        "output": output if agent.policy.governance.log_outputs else "<redacted>",
                        "cost": budget.summary(),
                    },
                    cost_usd=budget.total_usd,
                    audit_ids=audit_ids,
                )
                return AgentResult(
                    task_id=task_id,
                    status="completed",
                    output=output,
                    steps=step,
                    cost_usd=budget.total_usd,
                    audit_ids=audit_ids,
                )

            # Process tool calls
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args_raw = tc.function.arguments

                # Parse arguments safely
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except json.JSONDecodeError:
                    fn_args = {}

                spec = tool_map.get(fn_name)
                func = tool_func_map.get(fn_name)

                # ── Gate 1: Tool exists ──────────────────────────
                if spec is None or func is None:
                    tool_result = json.dumps({"error": f"Unknown tool: {fn_name}"})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
                    continue

                # ── Gate 2: Identity permissions ─────────────────
                perm_check = check_permissions(agent.identity, list(spec.scopes))
                if not perm_check.allowed:
                    await _audit(
                        db_session,
                        tenant_id=agent.tenant_id,
                        agent_id=agent.identity.agent_id,
                        task_id=task_id,
                        event_type="tool.denied",
                        action=fn_name,
                        detail={"reason": perm_check.reason, "args": fn_args},
                        policy_decision="deny",
                        policy_reason=perm_check.reason,
                        audit_ids=audit_ids,
                    )
                    tool_result = json.dumps({
                        "error": f"Permission denied: {perm_check.reason}"
                    })
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
                    continue

                # ── Gate 3: Policy rules ─────────────────────────
                action_name = fn_name
                policy_decision = agent.policy.evaluate(action_name)
                if not policy_decision.allowed:
                    if policy_decision.effect == "escalate":
                        # Human-in-the-loop gate
                        approved = False
                        if approval_callback:
                            approved = await approval_callback(fn_name, fn_args)
                        if not approved:
                            await _audit(
                                db_session,
                                tenant_id=agent.tenant_id,
                                agent_id=agent.identity.agent_id,
                                task_id=task_id,
                                event_type="tool.escalated",
                                action=fn_name,
                                detail={"args": fn_args, "approved": False},
                                policy_decision="escalate",
                                policy_reason=policy_decision.reason,
                                audit_ids=audit_ids,
                            )
                            tool_result = json.dumps({
                                "error": "Action requires human approval and was not approved"
                            })
                            messages.append(
                                {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                            )
                            continue
                    else:
                        await _audit(
                            db_session,
                            tenant_id=agent.tenant_id,
                            agent_id=agent.identity.agent_id,
                            task_id=task_id,
                            event_type="tool.denied",
                            action=fn_name,
                            detail={"reason": policy_decision.reason, "args": fn_args},
                            policy_decision="deny",
                            policy_reason=policy_decision.reason,
                            audit_ids=audit_ids,
                        )
                        tool_result = json.dumps({
                            "error": f"Action denied by policy: {policy_decision.reason}"
                        })
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                        )
                        continue

                # ── Gate 4: Cost budget ──────────────────────────
                cost_decision = agent.policy.check_cost(
                    budget.total_usd, spec.cost_estimate_usd
                )
                if not cost_decision.allowed:
                    await _audit(
                        db_session,
                        tenant_id=agent.tenant_id,
                        agent_id=agent.identity.agent_id,
                        task_id=task_id,
                        event_type="tool.budget_exceeded",
                        action=fn_name,
                        detail={"budget": budget.summary()},
                        policy_decision=cost_decision.effect,
                        policy_reason=cost_decision.reason,
                        audit_ids=audit_ids,
                    )
                    tool_result = json.dumps({
                        "error": f"Budget exceeded: {cost_decision.reason}"
                    })
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                    )
                    continue

                # ── Gate 5: Approval requirement ─────────────────
                if spec.requires_approval:
                    approved = False
                    if approval_callback:
                        approved = await approval_callback(fn_name, fn_args)
                    if not approved:
                        await _audit(
                            db_session,
                            tenant_id=agent.tenant_id,
                            agent_id=agent.identity.agent_id,
                            task_id=task_id,
                            event_type="tool.approval_required",
                            action=fn_name,
                            detail={"args": fn_args, "approved": False},
                            policy_decision="escalate",
                            policy_reason="tool requires human approval",
                            audit_ids=audit_ids,
                        )
                        tool_result = json.dumps({
                            "error": "This action requires human approval"
                        })
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                        )
                        continue

                # ── Execute tool ─────────────────────────────────
                try:
                    result = await func(**fn_args)
                    tool_result = json.dumps(result, default=str)
                    budget.record(
                        "tool_call", fn_name, spec.cost_estimate_usd, json.dumps(fn_args)
                    )

                    await _audit(
                        db_session,
                        tenant_id=agent.tenant_id,
                        agent_id=agent.identity.agent_id,
                        task_id=task_id,
                        event_type="tool.executed",
                        action=fn_name,
                        detail={
                            "args": fn_args if agent.policy.governance.log_inputs else "<redacted>",
                            "result_preview": tool_result[:500]
                            if agent.policy.governance.log_outputs
                            else "<redacted>",
                        },
                        cost_usd=spec.cost_estimate_usd,
                        audit_ids=audit_ids,
                    )
                except Exception as e:
                    tool_result = json.dumps({"error": f"Tool execution failed: {str(e)}"})
                    await _audit(
                        db_session,
                        tenant_id=agent.tenant_id,
                        agent_id=agent.identity.agent_id,
                        task_id=task_id,
                        event_type="tool.error",
                        action=fn_name,
                        detail={"error": str(e), "traceback": traceback.format_exc()},
                        audit_ids=audit_ids,
                    )

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

        # Exhausted step limit without final answer
        return AgentResult(
            task_id=task_id,
            status="failed",
            output="",
            error="Maximum steps reached without completing the task",
            steps=step,
            cost_usd=budget.total_usd,
            audit_ids=audit_ids,
        )

    except Exception as e:
        await _audit(
            db_session,
            tenant_id=agent.tenant_id,
            agent_id=agent.identity.agent_id,
            task_id=task_id,
            event_type="task.error",
            action="execute",
            detail={"error": str(e), "traceback": traceback.format_exc()},
            audit_ids=audit_ids,
        )
        return AgentResult(
            task_id=task_id,
            status="failed",
            output="",
            error=str(e),
            steps=step,
            cost_usd=budget.total_usd,
            audit_ids=audit_ids,
        )


# ── Helpers ──────────────────────────────────────────────────────


async def execute_task_stream(
    agent: Agent,
    task: str,
    *,
    db_session: Any | None = None,
    approval_callback: Any | None = None,
) -> AsyncIterator[StreamEvent]:
    """Execute a task yielding StreamEvent objects at each stage.

    Same governance as execute_task, but emits events for real-time UIs.
    """
    task_id = _generate_id()
    budget = TaskBudget(max_usd=agent.max_cost_per_task)
    audit_ids: list[str] = []
    step = 0

    yield StreamEvent("task_start", {"task_id": task_id, "agent": agent.name})

    # Policy gate
    task_decision = agent.policy.evaluate("task:execute")
    if not task_decision.allowed:
        yield StreamEvent("task_error", {
            "task_id": task_id, "error": f"Task denied: {task_decision.reason}",
        })
        return

    system_prompt = agent._build_system_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    tool_schemas = tools_to_openai_schema(agent.tools)
    tool_map = {spec.name: spec for spec in agent.tool_specs}
    tool_func_map = {spec.name: spec.func for spec in agent.tool_specs}

    try:
        while step < agent.policy.limits.max_steps_per_task:
            step += 1
            yield StreamEvent("step_start", {"step": step})

            step_decision = agent.policy.check_step_limit(step)
            if not step_decision.allowed:
                yield StreamEvent("task_error", {
                    "task_id": task_id, "error": step_decision.reason,
                })
                return

            response = await reliable_completion(
                model=agent.model, messages=messages,
                **({"tools": tool_schemas} if tool_schemas else {}),
            )
            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            if usage:
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                budget.record("llm", agent.model, estimate_llm_cost(agent.model, in_tok, out_tok), f"step {step}")

            msg = choice.message
            messages.append(msg.model_dump(exclude_none=True))

            if not getattr(msg, "tool_calls", None):
                output = msg.content or ""
                yield StreamEvent("final_answer", {"content": output})
                yield StreamEvent("task_complete", {
                    "task_id": task_id, "status": "completed",
                    "steps": step, "cost_usd": budget.total_usd,
                })
                return

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                except json.JSONDecodeError:
                    fn_args = {}

                spec = tool_map.get(fn_name)
                func = tool_func_map.get(fn_name)

                if spec is None or func is None:
                    yield StreamEvent("tool_denied", {"name": fn_name, "reason": "unknown tool"})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": f"Unknown tool: {fn_name}"})})
                    continue

                perm_check = check_permissions(agent.identity, list(spec.scopes))
                if not perm_check.allowed:
                    yield StreamEvent("tool_denied", {"name": fn_name, "reason": perm_check.reason})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": f"Permission denied: {perm_check.reason}"})})
                    continue

                policy_decision = agent.policy.evaluate(fn_name)
                if not policy_decision.allowed:
                    if policy_decision.effect == "escalate":
                        approved = approval_callback and await approval_callback(fn_name, fn_args)
                        if not approved:
                            yield StreamEvent("tool_denied", {"name": fn_name, "reason": "escalated, not approved"})
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": "requires human approval"})})
                            continue
                    else:
                        yield StreamEvent("tool_denied", {"name": fn_name, "reason": policy_decision.reason})
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": f"Denied: {policy_decision.reason}"})})
                        continue

                cost_decision = agent.policy.check_cost(budget.total_usd, spec.cost_estimate_usd)
                if not cost_decision.allowed:
                    yield StreamEvent("tool_denied", {"name": fn_name, "reason": cost_decision.reason})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": cost_decision.reason})})
                    continue

                yield StreamEvent("tool_call", {"name": fn_name, "args": fn_args})
                try:
                    result = await func(**fn_args)
                    tool_result = json.dumps(result, default=str)
                    budget.record("tool_call", fn_name, spec.cost_estimate_usd, json.dumps(fn_args))
                    yield StreamEvent("tool_result", {"name": fn_name, "result": tool_result[:500]})
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)})
                    yield StreamEvent("tool_result", {"name": fn_name, "error": str(e)})

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

        yield StreamEvent("task_error", {"task_id": task_id, "error": "max steps reached"})

    except Exception as e:
        yield StreamEvent("task_error", {"task_id": task_id, "error": str(e)})


def _generate_id() -> str:
    from uuid import uuid4

    return str(uuid4())


async def _audit(
    db_session: Any | None,
    *,
    tenant_id: str,
    agent_id: str,
    task_id: str,
    event_type: str,
    action: str,
    detail: dict[str, Any],
    policy_decision: str = "allow",
    policy_reason: str = "",
    cost_usd: float = 0.0,
    audit_ids: list[str],
) -> None:
    """Log to audit trail (DB if available, stdout fallback)."""
    if db_session:
        from smn.core.audit import log_event

        entry = await log_event(
            db_session,
            tenant_id=tenant_id,
            agent_id=agent_id,
            task_id=task_id,
            event_type=event_type,
            action=action,
            detail=detail,
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            cost_usd=cost_usd,
        )
        audit_ids.append(entry.entry_id)
    else:
        logger.info(
            "AUDIT | %s | %s | %s | %s | %s | $%.6f",
            tenant_id,
            agent_id,
            event_type,
            action,
            policy_decision,
            cost_usd,
        )
