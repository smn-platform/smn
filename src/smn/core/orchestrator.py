"""Multi-agent orchestration — governed agent graphs with handoffs.

Supports:
- Directed agent graphs with routing rules
- Sequential, parallel, and conditional execution
- Shared context between agents
- Governed handoffs (each transition checked by policy)
- Cycle detection for safety

Usage:
    graph = AgentGraph()
    graph.add_agent("triage", triage_agent)
    graph.add_agent("support", support_agent)
    graph.add_agent("billing", billing_agent)

    graph.add_edge("triage", "support", condition=lambda ctx: ctx.get("type") == "support")
    graph.add_edge("triage", "billing", condition=lambda ctx: ctx.get("type") == "billing")

    result = await graph.execute("triage", "Help me with my bill")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from smn.core.agent import Agent, AgentResult

logger = logging.getLogger(__name__)


@dataclass
class HandoffResult:
    """Result of a multi-agent orchestration run."""

    final_output: str
    agent_results: list[AgentResult]
    handoff_chain: list[str]
    total_cost_usd: float
    total_steps: int


@dataclass(frozen=True)
class Edge:
    """A directed edge between two agents in the graph."""

    source: str
    target: str
    condition: Callable[[dict[str, Any]], bool] | None = None


class AgentGraph:
    """Directed graph of agents with governed handoffs.

    Agents are nodes. Edges define possible handoffs, optionally
    gated by condition functions that inspect shared context.
    """

    def __init__(self, max_handoffs: int = 10) -> None:
        self._agents: dict[str, Agent] = {}
        self._edges: list[Edge] = []
        self._max_handoffs = max_handoffs

    def add_agent(self, name: str, agent: Agent) -> None:
        """Register an agent as a graph node."""
        self._agents[name] = agent

    def add_edge(
        self,
        source: str,
        target: str,
        condition: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """Add a directed edge (handoff possibility) between two agents."""
        self._edges.append(Edge(source=source, target=target, condition=condition))

    @property
    def agents(self) -> dict[str, Agent]:
        return dict(self._agents)

    def get_targets(self, source: str, context: dict[str, Any]) -> list[str]:
        """Return all reachable targets from a source given current context."""
        targets = []
        for edge in self._edges:
            if edge.source != source:
                continue
            if edge.condition is None or edge.condition(context):
                targets.append(edge.target)
        return targets

    def has_cycle(self) -> bool:
        """Detect cycles in the agent graph using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for edge in self._edges:
                if edge.source != node:
                    continue
                if edge.target not in visited:
                    if _dfs(edge.target):
                        return True
                elif edge.target in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in self._agents:
            if node not in visited:
                if _dfs(node):
                    return True
        return False

    async def execute(
        self,
        start: str,
        task: str,
        *,
        context: dict[str, Any] | None = None,
        db_session: Any | None = None,
        approval_callback: Any | None = None,
    ) -> HandoffResult:
        """Execute the graph starting from a specific agent.

        The starting agent runs the task. Based on its output and
        the shared context, the graph routes to the next agent
        via matching edges. This continues until no further handoffs
        are available or the handoff limit is reached.

        Parameters
        ----------
        start
            Name of the starting agent.
        task
            The initial task description.
        context
            Shared context dict passed to edge conditions and subsequent agents.
        """
        if start not in self._agents:
            raise ValueError(f"unknown agent: {start}")

        ctx = dict(context or {})
        current = start
        current_task = task
        chain: list[str] = []
        results: list[AgentResult] = []
        total_cost = 0.0
        total_steps = 0

        for hop in range(self._max_handoffs):
            agent = self._agents[current]
            chain.append(current)

            logger.info("orchestrator: running agent %s (hop %d)", current, hop + 1)
            result = await agent.run(
                current_task,
                db_session=db_session,
                approval_callback=approval_callback,
            )
            results.append(result)
            total_cost += result.cost_usd
            total_steps += result.steps

            # Update shared context with agent output
            ctx["last_output"] = result.output
            ctx["last_status"] = result.status
            ctx["last_agent"] = current

            # If agent failed or was denied, stop
            if result.status in ("failed", "denied", "killed"):
                break

            # Find next agent via edges
            targets = self.get_targets(current, ctx)
            if not targets:
                break  # Terminal node — done

            # Take the first matching target
            next_agent = targets[0]
            if next_agent in chain and len(chain) > 1:
                logger.warning("orchestrator: cycle detected (%s), stopping", next_agent)
                break

            # Handoff: the next agent's task is the output of the previous
            current = next_agent
            current_task = result.output

        return HandoffResult(
            final_output=results[-1].output if results else "",
            agent_results=results,
            handoff_chain=chain,
            total_cost_usd=total_cost,
            total_steps=total_steps,
        )


async def run_parallel(
    agents: dict[str, Agent],
    task: str,
    *,
    db_session: Any | None = None,
) -> dict[str, AgentResult]:
    """Run multiple agents on the same task in parallel.

    Returns a dict mapping agent name → result.
    """
    import asyncio

    async def _run(name: str, agent: Agent) -> tuple[str, AgentResult]:
        result = await agent.run(task, db_session=db_session)
        return name, result

    tasks = [_run(name, agent) for name, agent in agents.items()]
    pairs = await asyncio.gather(*tasks)
    return dict(pairs)
