"""Immutable, hash-chained audit log.

Every agent action, policy decision, and governance event is recorded here.
The hash chain provides tamper evidence — any modification to historical
entries breaks the chain and is detectable by ``verify_chain()``.

Regulatory alignment:
- EU AI Act Art. 12: Automatic logging for high-risk AI systems
- EU AI Act Art. 20: Corrective actions documentation
- NIST AI RMF MEASURE-2: Risk measurement and monitoring
- NIST AI RMF MANAGE-2: Risk response documentation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.models import AuditEntry

logger = logging.getLogger(__name__)


def _stable_ts(dt: datetime) -> str:
    """Format a datetime deterministically for hash computation.

    SQLite may not preserve timezone info on round-trip, so we normalise
    to UTC and use a fixed format that is identical before and after storage.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


async def log_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    action: str,
    agent_id: str | None = None,
    task_id: str | None = None,
    detail: dict[str, Any] | None = None,
    policy_decision: str = "allow",
    policy_reason: str = "",
    cost_usd: float = 0.0,
) -> AuditEntry:
    """Append one immutable audit entry with hash chaining."""
    detail_str = json.dumps(detail or {}, default=str)

    # Get the hash of the previous entry for chaining
    prev = await db.execute(
        select(AuditEntry.entry_hash)
        .where(AuditEntry.tenant_id == tenant_id)
        .order_by(AuditEntry.id.desc())
        .limit(1)
    )
    prev_hash = prev.scalar_one_or_none() or ("0" * 64)

    now = datetime.now(timezone.utc)
    entry_hash = AuditEntry.compute_hash(
        prev_hash=prev_hash,
        timestamp=_stable_ts(now),
        tenant_id=tenant_id,
        event_type=event_type,
        action=action,
        detail=detail_str,
    )

    entry = AuditEntry(
        tenant_id=tenant_id,
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        action=action,
        detail=detail_str,
        policy_decision=policy_decision,
        policy_reason=policy_reason,
        cost_usd=cost_usd,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        timestamp=now,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(db: AsyncSession, tenant_id: str) -> tuple[bool, str]:
    """Verify the integrity of the audit hash chain for a tenant.

    Returns (is_valid, message).  If the chain is broken, the message
    indicates where the break occurred.
    """
    result = await db.execute(
        select(AuditEntry)
        .where(AuditEntry.tenant_id == tenant_id)
        .order_by(AuditEntry.id.asc())
    )
    entries = result.scalars().all()

    if not entries:
        return True, "no entries to verify"

    expected_prev = "0" * 64
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return False, (
                f"chain broken at entry {entry.entry_id}: "
                f"expected prev_hash={expected_prev[:16]}..., "
                f"got {entry.prev_hash[:16]}..."
            )
        # Recompute and verify
        recomputed = AuditEntry.compute_hash(
            prev_hash=entry.prev_hash,
            timestamp=_stable_ts(entry.timestamp),
            tenant_id=entry.tenant_id,
            event_type=entry.event_type,
            action=entry.action,
            detail=entry.detail,
        )
        if entry.entry_hash != recomputed:
            return False, (
                f"hash mismatch at entry {entry.entry_id}: "
                f"stored={entry.entry_hash[:16]}..., "
                f"computed={recomputed[:16]}..."
            )
        expected_prev = entry.entry_hash

    return True, f"chain verified: {len(entries)} entries intact"


async def get_audit_trail(
    db: AsyncSession,
    tenant_id: str,
    *,
    agent_id: str | None = None,
    task_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEntry]:
    """Query the audit log with filters."""
    stmt = select(AuditEntry).where(AuditEntry.tenant_id == tenant_id)
    if agent_id:
        stmt = stmt.where(AuditEntry.agent_id == agent_id)
    if task_id:
        stmt = stmt.where(AuditEntry.task_id == task_id)
    if event_type:
        stmt = stmt.where(AuditEntry.event_type == event_type)
    stmt = stmt.order_by(AuditEntry.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_audit_count(
    db: AsyncSession,
    tenant_id: str,
    *,
    agent_id: str | None = None,
    task_id: str | None = None,
    event_type: str | None = None,
) -> int:
    """Count audit entries matching filters."""
    stmt = select(func.count(AuditEntry.id)).where(AuditEntry.tenant_id == tenant_id)
    if agent_id:
        stmt = stmt.where(AuditEntry.agent_id == agent_id)
    if task_id:
        stmt = stmt.where(AuditEntry.task_id == task_id)
    if event_type:
        stmt = stmt.where(AuditEntry.event_type == event_type)
    result = await db.execute(stmt)
    return result.scalar() or 0
