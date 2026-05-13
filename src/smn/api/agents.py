"""Agents API — register, list, get, update, and delete agents."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse, PaginationParams
from smn.auth import get_current_tenant
from smn.config import settings
from smn.db import get_db
from smn.models import AgentRecord, Tenant

router = APIRouter(prefix="/agents")


# ── Schemas ──────────────────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    model: str = settings.default_model
    risk_level: Literal["minimal", "limited", "high"] = "limited"
    policy_name: str = "default"
    scopes: list[str] = []
    max_cost_per_task: float = Field(default=5.0, gt=0, le=1000.0)


class AgentResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    model: str
    risk_level: str
    policy_name: str
    scopes: list[str]
    max_cost_per_task: float
    is_active: bool

    model_config = {"from_attributes": True}


class AgentUpdate(BaseModel):
    description: str | None = None
    model: str | None = None
    risk_level: Literal["minimal", "limited", "high"] | None = None
    policy_name: str | None = None
    scopes: list[str] | None = None
    max_cost_per_task: float | None = Field(default=None, gt=0, le=1000.0)
    is_active: bool | None = None


# ── Endpoints ────────────────────────────────────────────────────


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    agent = AgentRecord(
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
        model=body.model,
        risk_level=body.risk_level,
        policy_name=body.policy_name,
        scopes=json.dumps(body.scopes),
        max_cost_per_task=body.max_cost_per_task,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.get("", response_model=ListResponse[AgentResponse])
async def list_agents(
    page: PaginationParams = Depends(),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    base = select(AgentRecord).where(AgentRecord.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(
        base.subquery()
    )
    data_stmt = base.order_by(AgentRecord.created_at.desc())

    result = await db.execute(data_stmt.limit(page.limit).offset(page.offset))
    agents = result.scalars().all()
    total = (await db.execute(count_stmt)).scalar() or 0

    return ListResponse(
        data=[_to_response(a) for a in agents],
        has_more=(page.offset + page.limit) < total,
        total_count=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRecord).where(
            AgentRecord.id == agent_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _to_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRecord).where(
            AgentRecord.id == agent_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")

    updates = body.model_dump(exclude_unset=True)
    if "scopes" in updates:
        updates["scopes"] = json.dumps(updates["scopes"])
    for k, v in updates.items():
        setattr(agent, k, v)
    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.delete("/{agent_id}", status_code=204)
async def deactivate_agent(
    agent_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: marks agent inactive rather than removing the record."""
    result = await db.execute(
        select(AgentRecord).where(
            AgentRecord.id == agent_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.is_active = False
    await db.commit()


def _to_response(agent: AgentRecord) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        description=agent.description,
        model=agent.model,
        risk_level=agent.risk_level,
        policy_name=agent.policy_name,
        scopes=json.loads(agent.scopes),
        max_cost_per_task=agent.max_cost_per_task,
        is_active=agent.is_active,
    )
