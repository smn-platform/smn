"""Tests for the immutable audit log with hash chaining."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from smn.core.audit import get_audit_trail, log_event, verify_chain


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_log_single_event(self, db: AsyncSession):
        entry = await log_event(
            db,
            tenant_id="test-tenant",
            event_type="test.event",
            action="do_something",
            detail={"key": "value"},
        )
        assert entry.entry_id is not None
        assert entry.entry_hash != "0" * 64
        assert entry.prev_hash == "0" * 64  # First entry

    @pytest.mark.asyncio
    async def test_hash_chain(self, db: AsyncSession):
        e1 = await log_event(
            db, tenant_id="t1", event_type="a", action="first",
        )
        e2 = await log_event(
            db, tenant_id="t1", event_type="b", action="second",
        )
        # Second entry's prev_hash should be first entry's hash
        assert e2.prev_hash == e1.entry_hash

    @pytest.mark.asyncio
    async def test_verify_chain_valid(self, db: AsyncSession):
        for i in range(5):
            await log_event(
                db, tenant_id="t1", event_type="test", action=f"action_{i}",
            )
        is_valid, msg = await verify_chain(db, "t1")
        assert is_valid is True
        assert "5 entries" in msg

    @pytest.mark.asyncio
    async def test_verify_empty_chain(self, db: AsyncSession):
        is_valid, msg = await verify_chain(db, "empty-tenant")
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_audit_trail_query(self, db: AsyncSession):
        await log_event(db, tenant_id="t1", event_type="task.start", action="run")
        await log_event(db, tenant_id="t1", event_type="tool.executed", action="search")
        await log_event(db, tenant_id="t2", event_type="task.start", action="run")

        # Query by tenant
        t1_entries = await get_audit_trail(db, "t1")
        assert len(t1_entries) == 2

        # Query by event type
        starts = await get_audit_trail(db, "t1", event_type="task.start")
        assert len(starts) == 1

    @pytest.mark.asyncio
    async def test_cost_tracking(self, db: AsyncSession):
        entry = await log_event(
            db,
            tenant_id="t1",
            event_type="tool.executed",
            action="expensive_call",
            cost_usd=0.0123,
        )
        assert entry.cost_usd == 0.0123
