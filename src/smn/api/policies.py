"""Policies API — manage YAML policy definitions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse, PaginationParams
from smn.auth import get_current_tenant
from smn.core.policy import Policy, _parse_policy_file
from smn.db import get_db
from smn.governance.frameworks import list_frameworks, get_framework
from smn.models import PolicyRecord, Tenant

router = APIRouter(prefix="/policies")


# ── Schemas ──────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    name: str
    content: str  # YAML string


class PolicyResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    version: int
    is_active: bool
    content: str

    model_config = {"from_attributes": True}


class FrameworkResponse(BaseModel):
    id: str
    name: str
    version: str
    effective_date: str
    requirement_count: int


# ── Endpoints ────────────────────────────────────────────────────


@router.post("", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: PolicyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Determine version (increment if name exists)
    result = await db.execute(
        select(PolicyRecord)
        .where(PolicyRecord.tenant_id == tenant.id, PolicyRecord.name == body.name)
        .order_by(PolicyRecord.version.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    version = (existing.version + 1) if existing else 1

    # Deactivate old version
    if existing:
        existing.is_active = False

    record = PolicyRecord(
        tenant_id=tenant.id,
        name=body.name,
        version=version,
        content=body.content,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("", response_model=ListResponse[PolicyResponse])
async def list_policies(
    page: PaginationParams = Depends(),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    base = select(PolicyRecord).where(
        PolicyRecord.tenant_id == tenant.id, PolicyRecord.is_active == True  # noqa: E712
    )
    count_stmt = select(func.count()).select_from(base.subquery())
    data_stmt = base.order_by(PolicyRecord.version.desc())

    result = await db.execute(data_stmt.limit(page.limit).offset(page.offset))
    policies = list(result.scalars().all())
    total = (await db.execute(count_stmt)).scalar() or 0

    return ListResponse(
        data=policies,
        has_more=(page.offset + page.limit) < total,
        total_count=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/frameworks", response_model=list[FrameworkResponse])
async def get_frameworks():
    """List available regulatory frameworks."""
    result = []
    for fw_id in list_frameworks():
        fw = get_framework(fw_id)
        if fw:
            result.append(
                FrameworkResponse(
                    id=fw.id,
                    name=fw.name,
                    version=fw.version,
                    effective_date=fw.effective_date,
                    requirement_count=len(fw.requirements),
                )
            )
    return result


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.id == policy_id,
            PolicyRecord.tenant_id == tenant.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Policy not found")
    return record
