"""Tests for metering module — usage aggregation."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from smn.metering import aggregate_tenant_usage, create_usage_record, get_current_billing_period
from smn.models import AgentRecord, AuditEntry, TaskRecord, Tenant


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> Tenant:
    t = Tenant(name="metering-test")
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture
async def agent(db: AsyncSession, tenant: Tenant) -> AgentRecord:
    a = AgentRecord(
        tenant_id=tenant.id,
        name="test-agent",
        model="test/model",
    )
    db.add(a)
    await db.flush()
    return a


async def test_aggregate_empty_tenant(db: AsyncSession, tenant: Tenant):
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=1)
    period_end = now + timedelta(hours=1)

    usage = await aggregate_tenant_usage(db, tenant.id, period_start, period_end)
    assert usage["task_count"] == 0
    assert usage["total_cost_usd"] == 0.0
    assert usage["tool_call_count"] == 0


async def test_aggregate_with_tasks(db: AsyncSession, tenant: Tenant, agent: AgentRecord):
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=1)
    period_end = now + timedelta(hours=1)

    # Add some tasks
    for i in range(3):
        task = TaskRecord(
            agent_id=agent.id,
            input_text=f"task {i}",
            status="completed",
            total_cost_usd=0.5,
            total_steps=2,
            model_used="test/model",
            started_at=now,
        )
        db.add(task)
    await db.flush()

    usage = await aggregate_tenant_usage(db, tenant.id, period_start, period_end)
    assert usage["task_count"] == 3
    assert usage["total_cost_usd"] == pytest.approx(1.5, abs=0.01)


async def test_create_usage_record(db: AsyncSession, tenant: Tenant, agent: AgentRecord):
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=1)
    period_end = now + timedelta(hours=1)

    record = await create_usage_record(db, tenant.id, period_start, period_end)
    assert record.tenant_id == tenant.id
    assert record.task_count == 0
    assert record.is_billed is False


def test_get_current_billing_period():
    start, end = get_current_billing_period()
    assert start < end
    assert start.day == 1
    assert start.hour == 0
    assert start.minute == 0


async def test_usage_record_idempotent(db: AsyncSession, tenant: Tenant, agent: AgentRecord):
    """Creating the same period twice should update, not duplicate."""
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=1)
    period_end = now + timedelta(hours=1)

    r1 = await create_usage_record(db, tenant.id, period_start, period_end)
    r2 = await create_usage_record(db, tenant.id, period_start, period_end)
    assert r1.id == r2.id
