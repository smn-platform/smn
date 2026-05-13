"""Admin API — internal operations dashboard endpoints.

Provides tenant management, billing overview, usage statistics,
and system health monitoring for platform operators.

All admin endpoints require API key auth with admin scope.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse, PaginationParams, require_admin
from smn.auth import get_current_tenant
from smn.db import get_db
from smn.metering import aggregate_tenant_usage, get_current_billing_period
from smn.models import (
    AgentRecord,
    APIKeyRecord,
    AuditEntry,
    TaskRecord,
    Tenant,
    UsageRecord,
)

router = APIRouter(prefix="/admin")


# ── Schemas ──────────────────────────────────────────────────────


class TenantOverview(BaseModel):
    id: str
    name: str
    plan_tier: str
    is_active: bool
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    agent_count: int
    task_count: int
    total_cost_usd: float
    api_key_count: int
    created_at: datetime


class SystemHealth(BaseModel):
    total_tenants: int
    active_tenants: int
    total_agents: int
    active_agents: int
    total_tasks: int
    tasks_last_24h: int
    total_audit_entries: int
    total_cost_usd: float
    database_status: str


class UsageSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    period_start: str
    period_end: str
    task_count: int
    tool_call_count: int
    llm_call_count: int
    total_cost_usd: float
    total_steps: int
    total_audit_events: int


class TenantUpdate(BaseModel):
    is_active: bool | None = None
    plan_tier: Literal["core", "growth", "enterprise"] | None = None
    rate_limit_rpm: int | None = None


class TenantUpdateResponse(BaseModel):
    status: str
    tenant_id: str


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/tenants", response_model=ListResponse[TenantOverview])
async def list_tenants(
    page: PaginationParams = Depends(),
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants with summary statistics."""
    # Total count
    total = (await db.execute(select(func.count(Tenant.id)))).scalar() or 0

    result = await db.execute(
        select(Tenant)
        .order_by(Tenant.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    tenants = result.scalars().all()

    overviews = []
    for t in tenants:
        # Count agents
        agent_count = (
            await db.execute(
                select(func.count(AgentRecord.id)).where(AgentRecord.tenant_id == t.id)
            )
        ).scalar() or 0

        # Count tasks
        task_result = await db.execute(
            select(
                func.count(TaskRecord.id),
                func.coalesce(func.sum(TaskRecord.total_cost_usd), 0.0),
            )
            .join(AgentRecord)
            .where(AgentRecord.tenant_id == t.id)
        )
        task_row = task_result.one()

        # Count API keys
        key_count = (
            await db.execute(
                select(func.count(APIKeyRecord.id)).where(APIKeyRecord.tenant_id == t.id)
            )
        ).scalar() or 0

        overviews.append(
            TenantOverview(
                id=t.id,
                name=t.name,
                plan_tier=t.plan_tier,
                is_active=t.is_active,
                stripe_customer_id=t.stripe_customer_id,
                stripe_subscription_id=t.stripe_subscription_id,
                agent_count=agent_count,
                task_count=task_row[0],
                total_cost_usd=round(float(task_row[1]), 6),
                api_key_count=key_count,
                created_at=t.created_at,
            )
        )

    return ListResponse(
        data=overviews,
        has_more=(page.offset + page.limit) < total,
        total_count=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantUpdateResponse)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a tenant's settings (admin only)."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Tenant not found")

    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(target, k, v)
    await db.commit()
    return TenantUpdateResponse(status="updated", tenant_id=tenant_id)


@router.get("/health", response_model=SystemHealth)
async def system_health(
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get system-wide health and statistics."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    total_tenants = (await db.execute(select(func.count(Tenant.id)))).scalar() or 0
    active_tenants = (
        await db.execute(
            select(func.count(Tenant.id)).where(Tenant.is_active == True)  # noqa: E712
        )
    ).scalar() or 0

    total_agents = (await db.execute(select(func.count(AgentRecord.id)))).scalar() or 0
    active_agents = (
        await db.execute(
            select(func.count(AgentRecord.id)).where(AgentRecord.is_active == True)  # noqa: E712
        )
    ).scalar() or 0

    total_tasks = (await db.execute(select(func.count(TaskRecord.id)))).scalar() or 0
    tasks_24h = (
        await db.execute(
            select(func.count(TaskRecord.id)).where(TaskRecord.started_at >= day_ago)
        )
    ).scalar() or 0

    total_audit = (await db.execute(select(func.count(AuditEntry.id)))).scalar() or 0

    total_cost_result = await db.execute(
        select(func.coalesce(func.sum(TaskRecord.total_cost_usd), 0.0))
    )
    total_cost = float(total_cost_result.scalar())

    return SystemHealth(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        total_agents=total_agents,
        active_agents=active_agents,
        total_tasks=total_tasks,
        tasks_last_24h=tasks_24h,
        total_audit_entries=total_audit,
        total_cost_usd=round(total_cost, 6),
        database_status="healthy",
    )


@router.get("/usage", response_model=list[UsageSummary])
async def usage_overview(
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary for all tenants for the current billing period."""
    period_start, period_end = get_current_billing_period()

    result = await db.execute(select(Tenant).where(Tenant.is_active == True))  # noqa: E712
    tenants = result.scalars().all()

    summaries = []
    for t in tenants:
        usage = await aggregate_tenant_usage(db, t.id, period_start, period_end)
        summaries.append(
            UsageSummary(
                tenant_id=t.id,
                tenant_name=t.name,
                **usage,
            )
        )

    return summaries


@router.get("/usage/{target_tenant_id}", response_model=UsageSummary)
async def tenant_usage(
    target_tenant_id: str,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary for a specific tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == target_tenant_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Tenant not found")

    period_start, period_end = get_current_billing_period()
    usage = await aggregate_tenant_usage(db, target.id, period_start, period_end)

    return UsageSummary(
        tenant_id=target.id,
        tenant_name=target.name,
        **usage,
    )
