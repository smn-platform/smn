"""Metering — usage aggregation and billing integration.

Tallies TaskRecord and AuditEntry costs per tenant per billing period.
Pushes aggregated usage to Stripe Usage Records for invoicing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from smn.models import AuditEntry, TaskRecord, Tenant, UsageRecord, AgentRecord

logger = logging.getLogger(__name__)


async def aggregate_tenant_usage(
    db: AsyncSession,
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """Aggregate usage metrics for a tenant over a billing period.

    Returns a dict of usage counters and cost totals.
    """
    # Count tasks
    task_result = await db.execute(
        select(
            func.count(TaskRecord.id).label("task_count"),
            func.coalesce(func.sum(TaskRecord.total_cost_usd), 0.0).label("task_cost"),
            func.coalesce(func.sum(TaskRecord.total_steps), 0).label("total_steps"),
        )
        .join(AgentRecord, TaskRecord.agent_id == AgentRecord.id)
        .where(
            AgentRecord.tenant_id == tenant_id,
            TaskRecord.started_at >= period_start,
            TaskRecord.started_at < period_end,
        )
    )
    task_row = task_result.one()

    # Count audit events by type
    audit_result = await db.execute(
        select(
            func.count(AuditEntry.id).label("event_count"),
            func.coalesce(func.sum(AuditEntry.cost_usd), 0.0).label("audit_cost"),
        ).where(
            AuditEntry.tenant_id == tenant_id,
            AuditEntry.timestamp >= period_start,
            AuditEntry.timestamp < period_end,
        )
    )
    audit_row = audit_result.one()

    # Count tool calls specifically
    tool_call_result = await db.execute(
        select(func.count(AuditEntry.id)).where(
            AuditEntry.tenant_id == tenant_id,
            AuditEntry.event_type == "tool.executed",
            AuditEntry.timestamp >= period_start,
            AuditEntry.timestamp < period_end,
        )
    )
    tool_call_count = tool_call_result.scalar() or 0

    # Count LLM calls
    llm_call_result = await db.execute(
        select(func.count(AuditEntry.id)).where(
            AuditEntry.tenant_id == tenant_id,
            AuditEntry.event_type == "llm.call",
            AuditEntry.timestamp >= period_start,
            AuditEntry.timestamp < period_end,
        )
    )
    llm_call_count = llm_call_result.scalar() or 0

    return {
        "tenant_id": tenant_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "task_count": task_row.task_count,
        "tool_call_count": tool_call_count,
        "llm_call_count": llm_call_count,
        "total_cost_usd": round(float(task_row.task_cost) + float(audit_row.audit_cost), 6),
        "total_steps": task_row.total_steps,
        "total_audit_events": audit_row.event_count,
    }


async def create_usage_record(
    db: AsyncSession,
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
) -> UsageRecord:
    """Create or update a UsageRecord for the given tenant and period."""
    # Check for existing record
    existing = await db.execute(
        select(UsageRecord).where(
            UsageRecord.tenant_id == tenant_id,
            UsageRecord.period_start == period_start,
            UsageRecord.period_end == period_end,
        )
    )
    record = existing.scalar_one_or_none()

    usage = await aggregate_tenant_usage(db, tenant_id, period_start, period_end)

    if record:
        record.task_count = usage["task_count"]
        record.tool_call_count = usage["tool_call_count"]
        record.llm_call_count = usage["llm_call_count"]
        record.total_cost_usd = usage["total_cost_usd"]
    else:
        record = UsageRecord(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            task_count=usage["task_count"],
            tool_call_count=usage["tool_call_count"],
            llm_call_count=usage["llm_call_count"],
            total_cost_usd=usage["total_cost_usd"],
        )
        db.add(record)

    await db.flush()
    return record


async def aggregate_all_tenants(
    db: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> list[UsageRecord]:
    """Aggregate usage for all active tenants. Returns list of UsageRecords."""
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))  # noqa: E712
    tenants = result.scalars().all()

    records = []
    for tenant in tenants:
        record = await create_usage_record(db, tenant.id, period_start, period_end)
        records.append(record)

    await db.flush()
    return records


async def push_usage_to_stripe(db: AsyncSession, period_start: datetime, period_end: datetime):
    """Push unbilled usage records to Stripe.

    Calls Stripe Usage Record API for each tenant with a subscription.
    """
    from smn.billing import report_usage

    result = await db.execute(
        select(UsageRecord).where(
            UsageRecord.period_start == period_start,
            UsageRecord.period_end == period_end,
            UsageRecord.is_billed == False,  # noqa: E712
        )
    )
    records = result.scalars().all()

    for record in records:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == record.tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant or not tenant.stripe_subscription_id:
            continue

        usage_result = await report_usage(
            tenant,
            quantity=record.task_count,
            timestamp=int(period_end.timestamp()),
        )

        if usage_result:
            record.is_billed = True
            record.stripe_usage_record_id = usage_result.get("usage_record_id")
            logger.info(
                "Billed %d tasks for tenant %s (period %s to %s)",
                record.task_count,
                tenant.id,
                period_start.isoformat(),
                period_end.isoformat(),
            )

    await db.flush()


def get_current_billing_period() -> tuple[datetime, datetime]:
    """Get the current monthly billing period (start, end)."""
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)
    return period_start, period_end
