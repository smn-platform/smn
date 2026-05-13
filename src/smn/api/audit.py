"""Audit API — query the immutable audit log and verify chain integrity."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse
from smn.auth import get_current_tenant
from smn.core.audit import get_audit_trail, get_audit_count, verify_chain
from smn.db import get_db
from smn.models import Tenant

router = APIRouter(prefix="/audit")


# ── Schemas ──────────────────────────────────────────────────────


class AuditEntryResponse(BaseModel):
    entry_id: str
    timestamp: datetime
    tenant_id: str
    agent_id: str | None
    task_id: str | None
    event_type: str
    action: str
    detail: str
    policy_decision: str
    policy_reason: str
    cost_usd: float
    entry_hash: str

    model_config = {"from_attributes": True}


class ChainVerification(BaseModel):
    is_valid: bool
    message: str


# ── Endpoints ────────────────────────────────────────────────────


@router.get("", response_model=ListResponse[AuditEntryResponse])
async def query_audit_log(
    agent_id: str | None = None,
    task_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    entries = await get_audit_trail(
        db,
        tenant_id=tenant.id,
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    total = await get_audit_count(
        db,
        tenant_id=tenant.id,
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
    )
    return ListResponse(
        data=entries,
        has_more=(offset + limit) < total,
        total_count=total,
        limit=limit,
        offset=offset,
    )


@router.get("/verify", response_model=ChainVerification)
async def verify_audit_chain(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Verify the tamper-evidence hash chain for a tenant's audit log."""
    is_valid, message = await verify_chain(db, tenant.id)
    return ChainVerification(is_valid=is_valid, message=message)
