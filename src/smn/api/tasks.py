"""Tasks API — run agent tasks and query execution history."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse, PaginationParams
from smn.auth import get_current_tenant
from smn.config import settings
from smn.core.agent import Agent
from smn.core.policy import load_policy
from smn.db import get_db
from smn.models import AgentRecord, TaskRecord, Tenant

router = APIRouter(prefix="/tasks")


# ── Schemas ──────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    agent_id: str
    input_text: str
    async_execution: bool = False  # If True, dispatch to task queue


class TaskResponse(BaseModel):
    id: str
    agent_id: str
    input_text: str
    status: str
    output_text: str | None
    error: str | None
    total_cost_usd: float
    total_steps: int
    model_used: str
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────


@router.post("", response_model=TaskResponse, status_code=201)
async def run_task(
    body: TaskCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create and execute a task for a registered agent."""
    # Load agent from DB (scoped to tenant)
    result = await db.execute(
        select(AgentRecord).where(
            AgentRecord.id == body.agent_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    agent_rec = result.scalar_one_or_none()
    if not agent_rec:
        raise HTTPException(404, "Agent not found")
    if not agent_rec.is_active:
        raise HTTPException(400, "Agent is deactivated")

    # Build runtime Agent (no tools from API — tools are defined in code)
    policy = load_policy(agent_rec.policy_name)
    agent = Agent(
        name=agent_rec.name,
        description=agent_rec.description,
        model=agent_rec.model,
        scopes=agent_rec.scope_list,
        risk_level=agent_rec.risk_level,
        policy=policy,
        max_cost_per_task=agent_rec.max_cost_per_task,
        tenant_id=agent_rec.tenant_id,
    )

    # Create task record
    task = TaskRecord(
        agent_id=agent_rec.id,
        input_text=body.input_text,
        status="pending" if body.async_execution else "running",
        model_used=agent.model,
    )
    db.add(task)
    await db.flush()

    if body.async_execution:
        # Dispatch to Celery worker
        try:
            from smn.worker import execute_task_async

            execute_task_async.delay(task.id, agent_rec.id, body.input_text)
            task.status = "queued"
        except Exception:
            # Celery not available — fall back to sync
            task.status = "running"
            agent_result = await agent.run(body.input_text, db_session=db)
            task.status = agent_result.status
            task.output_text = agent_result.output
            task.error = agent_result.error
            task.total_cost_usd = agent_result.cost_usd
            task.total_steps = agent_result.steps
            task.completed_at = datetime.now(timezone.utc)
    else:
        # Run synchronously
        agent_result = await agent.run(body.input_text, db_session=db)
        task.status = agent_result.status
        task.output_text = agent_result.output
        task.error = agent_result.error
        task.total_cost_usd = agent_result.cost_usd
        task.total_steps = agent_result.steps
        task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    return task


@router.get("", response_model=ListResponse[TaskResponse])
async def list_tasks(
    agent_id: str | None = None,
    status: str | None = None,
    page: PaginationParams = Depends(),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    base = select(TaskRecord).join(AgentRecord).where(AgentRecord.tenant_id == tenant.id)
    if agent_id:
        base = base.where(TaskRecord.agent_id == agent_id)
    if status:
        base = base.where(TaskRecord.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    data_stmt = base.order_by(TaskRecord.started_at.desc())

    result = await db.execute(data_stmt.limit(page.limit).offset(page.offset))
    tasks = list(result.scalars().all())
    total = (await db.execute(count_stmt)).scalar() or 0

    return ListResponse(
        data=tasks,
        has_more=(page.offset + page.limit) < total,
        total_count=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TaskRecord)
        .join(AgentRecord)
        .where(
            TaskRecord.id == task_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    return task
