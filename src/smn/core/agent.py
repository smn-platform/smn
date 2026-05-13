"""Agent — the primary user-facing object.

An Agent encapsulates identity, policy, tools, memory, and model configuration.
It is the only object most developers need to interact with.

Usage:
    import smn

    @smn.tool(scopes=["tickets:read"])
    async def get_ticket(ticket_id: str) -> dict:
        return {"id": ticket_id, "status": "open"}

    agent = smn.Agent(
        name="support-bot",
        tools=[get_ticket],
    )
    result = await agent.run("Find ticket #1234")
    print(result.output)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from smn.config import settings
from smn.core.identity import Identity
from smn.core.memory import PersistentMemory, SessionMemory
from smn.core.policy import Policy, load_policy
from smn.core.tools import ToolSpec, get_tool_spec


@dataclass
class AgentResult:
    """The outcome of an agent task execution."""

    task_id: str
    status: str  # completed | failed | denied | killed
    output: str
    error: str | None = None
    steps: int = 0
    cost_usd: float = 0.0
    audit_ids: list[str] = field(default_factory=list)


class Agent:
    """A governed, auditable AI agent.

    Parameters
    ----------
    name
        Human-readable agent name (must be unique per tenant).
    description
        What this agent does (included in LLM system prompt).
    model
        LLM model in litellm format (``provider/model``).
    tools
        Functions decorated with ``@smn.tool``.
    scopes
        Permission scopes granted to this agent.
    risk_level
        EU AI Act risk classification: ``minimal``, ``limited``, or ``high``.
    policy
        Policy name to load, or a Policy instance.
    max_cost_per_task
        Maximum USD budget per task execution.
    memory
        Memory configuration (SessionMemory, PersistentMemory, or None).
    system_prompt
        Additional system instructions (appended after governance preamble).
    tenant_id
        Tenant scope (defaults to ``"default"``).
    """

    def __init__(
        self,
        name: str,
        *,
        description: str = "",
        model: str | None = None,
        tools: Sequence[Callable] = (),
        scopes: Sequence[str] | None = None,
        risk_level: str = "limited",
        policy: str | Policy = "default",
        max_cost_per_task: float | None = None,
        memory: SessionMemory | PersistentMemory | None = None,
        system_prompt: str = "",
        tenant_id: str = "default",
    ) -> None:
        self.name = name
        self.description = description
        self.model = model or settings.default_model
        self.risk_level = risk_level
        self.max_cost_per_task = max_cost_per_task or settings.max_cost_per_task_usd
        self.memory = memory or SessionMemory()
        self.system_prompt = system_prompt
        self.tenant_id = tenant_id

        # Resolve tools and auto-derive scopes
        self._tools: list[Callable] = list(tools)
        self._tool_specs: list[ToolSpec] = []
        auto_scopes: set[str] = set()
        for t in self._tools:
            spec = get_tool_spec(t)
            if spec:
                self._tool_specs.append(spec)
                auto_scopes.update(spec.scopes)

        # Use explicit scopes if provided, otherwise auto-derive from tools
        effective_scopes = frozenset(scopes) if scopes is not None else frozenset(auto_scopes)

        self.identity = Identity(
            agent_id=f"{tenant_id}/{name}",
            tenant_id=tenant_id,
            scopes=effective_scopes,
        )

        # Load policy
        if isinstance(policy, str):
            self.policy = load_policy(policy)
        else:
            self.policy = policy

        # Auto-escalate governance for high-risk agents
        if self.risk_level == "high":
            self.policy.governance.require_human_oversight = True
            self.policy.governance.require_impact_assessment = True
            self.policy.governance.log_inputs = True
            self.policy.governance.log_outputs = True

    @property
    def tools(self) -> list[Callable]:
        return list(self._tools)

    @property
    def tool_specs(self) -> list[ToolSpec]:
        return list(self._tool_specs)

    def _build_system_prompt(self) -> str:
        """Construct the full system prompt with governance preamble."""
        parts: list[str] = []

        # Governance preamble (EU AI Act Art. 52 transparency)
        if self.policy.governance.require_transparency_disclosure:
            parts.append(
                "You are an AI agent operating under governance controls. "
                "All actions are logged and auditable. "
                "You must not attempt to circumvent safety policies."
            )

        # Agent identity
        parts.append(f"Agent: {self.name}")
        if self.description:
            parts.append(f"Purpose: {self.description}")

        # Permission boundary
        scope_str = ", ".join(sorted(self.identity.scopes)) or "none"
        parts.append(f"Granted permissions: {scope_str}")

        # Budget
        parts.append(f"Task budget: ${self.max_cost_per_task:.2f} USD")

        # Risk level
        parts.append(f"Risk classification: {self.risk_level}")

        # Memory context
        if self.memory:
            ctx = self.memory.to_context_string()
            if ctx:
                parts.append(ctx)

        # User-provided system prompt
        if self.system_prompt:
            parts.append(self.system_prompt)

        return "\n\n".join(parts)

    async def run(self, task: str, **kwargs: Any) -> AgentResult:
        """Execute a task through the governed runtime.

        This is the primary entry point. It:
        1. Creates a task record
        2. Evaluates policy
        3. Runs the LLM loop with tool calls
        4. Enforces budgets and permissions at each step
        5. Logs everything to the audit trail
        """
        from smn.core.runtime import execute_task

        return await execute_task(self, task, **kwargs)

    def __repr__(self) -> str:
        return (
            f"Agent(name={self.name!r}, model={self.model!r}, "
            f"risk_level={self.risk_level!r}, tools={len(self._tools)})"
        )
