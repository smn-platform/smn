"""Workflow execution engine.

Walks a workflow's DAG in topological order, executes each node, and
persists per-step results to the database.  Condition nodes branch the
execution path by matching their output handle (``"true"``/``"false"``) to
edge ``sourceHandle`` values.

Template variables in node config (``{{node_id.field}}``) are resolved from
the accumulated execution context before each node runs.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from smn.studio.nodes import NODE_REGISTRY
from smn.studio.nodes.base import NodeResult
from smn.studio.schemas import WorkflowDefinition

logger = logging.getLogger(__name__)

_NOW = lambda: datetime.now(timezone.utc)


# ── DAG helpers ───────────────────────────────────────────────────


def _topological_sort(definition: WorkflowDefinition) -> list[str]:
    """Kahn's algorithm — returns node IDs in valid execution order.

    Raises ``ValueError`` if the graph contains a cycle.
    """
    in_degree: dict[str, int] = {n.id: 0 for n in definition.nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in definition.edges:
        adjacency[edge.source].append(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

    queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for target in adjacency[nid]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)

    if len(order) != len(definition.nodes):
        raise ValueError("Workflow graph contains a cycle — execution aborted")

    return order


def _build_edge_index(
    definition: WorkflowDefinition,
) -> dict[str, list[tuple[str, str | None]]]:
    """Return {source_id: [(target_id, sourceHandle), ...]}."""
    index: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for edge in definition.edges:
        index[edge.source].append((edge.target, edge.sourceHandle))
    return index


# ── Execution ─────────────────────────────────────────────────────


async def execute_workflow(
    workflow_id: str,
    run_id: str,
    definition: WorkflowDefinition,
    trigger_data: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Execute a workflow and persist per-step results.

    The function runs entirely within the provided ``db`` session, which
    should be the caller's own session (background tasks create a fresh one).

    Returns the output dict of the last executed node, or an error dict.
    """
    from smn.studio.models import WorkflowRun, WorkflowRunStep

    node_map = {n.id: n for n in definition.nodes}
    edge_index = _build_edge_index(definition)

    # Context accumulates node outputs: {"trigger": {...}, "node-id": {...}}
    context: dict[str, Any] = {"trigger": trigger_data}

    # Which source handle each node last emitted (used for condition routing)
    node_handles: dict[str, str] = {}

    # Nodes that actually ran — used to gate downstream execution
    completed_node_ids: set[str] = set()

    # ── Mark run as running ───────────────────────────────────────
    run = await db.get(WorkflowRun, run_id)
    if run:
        run.status = "running"
        run.started_at = _NOW()
        await db.commit()

    # ── Topological execution ─────────────────────────────────────
    try:
        order = _topological_sort(definition)
    except ValueError as exc:
        if run:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = _NOW()
            await db.commit()
        return {"error": str(exc)}

    final_output: dict[str, Any] = {}

    for node_id in order:
        node = node_map[node_id]

        # Trigger nodes seed the context and are never "executed"
        if node.type == "trigger":
            context[node_id] = trigger_data
            completed_node_ids.add(node_id)
            continue

        # Gate: only run if at least one incoming edge comes from an active
        # node AND matches that node's output handle.
        incoming = [e for e in definition.edges if e.target == node_id]
        if incoming:
            should_run = False
            for edge in incoming:
                if edge.source not in completed_node_ids:
                    continue
                # Edge with no sourceHandle → unconditional
                expected_handle = edge.sourceHandle
                actual_handle = node_handles.get(edge.source, "output")
                if expected_handle is None or expected_handle == actual_handle:
                    should_run = True
                    break
            if not should_run:
                logger.debug("Node %s skipped (gated by condition branch)", node_id)
                continue

        # ── Create step record ────────────────────────────────────
        step = WorkflowRunStep(
            run_id=run_id,
            node_id=node_id,
            node_type=node.type,
            node_label=node.data.label or node_id,
            status="running",
            input_data=json.dumps(node.data.config),
            started_at=_NOW(),
        )
        db.add(step)
        await db.commit()
        await db.refresh(step)
        step_id = step.id
        started = step.started_at

        # ── Execute ───────────────────────────────────────────────
        try:
            node_cls = NODE_REGISTRY.get(node.type)
            if node_cls is None:
                raise ValueError(f"Unknown node type: '{node.type}'")

            result: NodeResult = await node_cls().execute(node.data.config, context)

            context[node_id] = result.output
            node_handles[node_id] = result.handle
            completed_node_ids.add(node_id)
            final_output = result.output

            completed = _NOW()
            duration_ms = int((completed - started).total_seconds() * 1000)

            step_record = await db.get(WorkflowRunStep, step_id)
            if step_record:
                step_record.status = "completed"
                step_record.output_data = json.dumps(result.output)
                step_record.completed_at = completed
                step_record.duration_ms = duration_ms
            await db.commit()

            logger.info(
                "Workflow %s | run %s | node %s (%s) completed in %d ms",
                workflow_id, run_id, node_id, node.type, duration_ms,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.exception(
                "Workflow %s | run %s | node %s (%s) failed: %s",
                workflow_id, run_id, node_id, node.type, exc,
            )

            step_record = await db.get(WorkflowRunStep, step_id)
            if step_record:
                step_record.status = "failed"
                step_record.error = error_msg
                step_record.completed_at = _NOW()
            if run:
                run.status = "failed"
                run.error = f"Node '{node_id}' ({node.type}) failed: {error_msg}"
                run.completed_at = _NOW()
            await db.commit()

            return {"error": error_msg}

    # ── Mark run completed ────────────────────────────────────────
    if run:
        run.status = "completed"
        run.output = json.dumps(final_output)
        run.completed_at = _NOW()
        await db.commit()

    logger.info("Workflow %s | run %s completed", workflow_id, run_id)
    return final_output
