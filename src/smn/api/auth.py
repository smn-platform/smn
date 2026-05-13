"""Auth API — API key management endpoints."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.deps import ListResponse, PaginationParams
from smn.auth import create_api_key, get_current_tenant, revoke_api_key
from smn.db import get_db
from smn.models import APIKeyRecord, Tenant

router = APIRouter(prefix="/auth")


# ── Schemas ──────────────────────────────────────────────────────


class APIKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["api:full"]
    expires_at: datetime | None = None


class APIKeyResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreated(APIKeyResponse):
    """Response when a key is first created — includes the raw key (shown only once)."""
    raw_key: str


# ── Bootstrap endpoint (no auth required) ────────────────────────


class BootstrapRequest(BaseModel):
    tenant_name: str
    key_name: str = "default"


class BootstrapResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    api_key: str
    key_id: str
    message: str


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
async def bootstrap_tenant(body: BootstrapRequest, db: AsyncSession = Depends(get_db)):
    """Create a new tenant and their first API key.

    This is the only endpoint that does not require authentication.
    Use it to create the initial tenant and key for a new deployment.
    """
    # Check if tenant already exists
    result = await db.execute(select(Tenant).where(Tenant.name == body.tenant_name))
    if result.scalar_one_or_none():
        raise HTTPException(400, f"Tenant '{body.tenant_name}' already exists.")

    tenant = Tenant(name=body.tenant_name)
    db.add(tenant)
    await db.flush()

    key_record, raw_key = await create_api_key(db, tenant.id, body.key_name)
    await db.commit()

    return BootstrapResponse(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        api_key=raw_key,
        key_id=key_record.id,
        message="Save this API key — it will not be shown again.",
    )


# ── Authenticated endpoints ──────────────────────────────────────


@router.post("/keys", response_model=APIKeyCreated, status_code=201)
async def create_key(
    body: APIKeyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key for the authenticated tenant."""
    key_record, raw_key = await create_api_key(
        db, tenant.id, body.name, body.scopes, body.expires_at
    )
    await db.commit()
    await db.refresh(key_record)
    return APIKeyCreated(
        id=key_record.id,
        tenant_id=key_record.tenant_id,
        name=key_record.name,
        key_prefix=key_record.key_prefix,
        scopes=json.loads(key_record.scopes),
        is_active=key_record.is_active,
        last_used_at=key_record.last_used_at,
        expires_at=key_record.expires_at,
        created_at=key_record.created_at,
        raw_key=raw_key,
    )


@router.get("/keys", response_model=ListResponse[APIKeyResponse])
async def list_keys(
    page: PaginationParams = Depends(),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the authenticated tenant."""
    base = select(APIKeyRecord).where(APIKeyRecord.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(base.subquery())

    result = await db.execute(
        base.order_by(APIKeyRecord.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    keys = result.scalars().all()
    total = (await db.execute(count_stmt)).scalar() or 0

    return ListResponse(
        data=[
            APIKeyResponse(
                id=k.id,
                tenant_id=k.tenant_id,
                name=k.name,
                key_prefix=k.key_prefix,
                scopes=json.loads(k.scopes),
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
                created_at=k.created_at,
            )
            for k in keys
        ],
        has_more=(page.offset + page.limit) < total,
        total_count=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    # Verify key belongs to tenant
    result = await db.execute(
        select(APIKeyRecord).where(
            APIKeyRecord.id == key_id,
            APIKeyRecord.tenant_id == tenant.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "API key not found.")
    await revoke_api_key(db, key_id)
    await db.commit()
