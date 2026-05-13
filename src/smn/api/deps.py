"""Shared API dependencies — admin auth, pagination helpers."""

from __future__ import annotations

import json
from typing import Generic, Sequence, TypeVar

from fastapi import Depends, Query, Security
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.api.errors import AuthorizationError
from smn.auth import API_KEY_HEADER, authenticate_key, hash_key
from smn.db import get_db
from smn.models import APIKeyRecord, Tenant

T = TypeVar("T", bound=BaseModel)


class ListResponse(BaseModel, Generic[T]):
    """Paginated list envelope — matches Stripe/Cloudflare conventions."""

    object: str = "list"
    data: list[T]
    has_more: bool
    total_count: int
    limit: int
    offset: int


class PaginationParams:
    """Dependency that validates and clamps limit/offset query params."""

    def __init__(
        self,
        limit: int = Query(default=20, ge=1, le=100, description="Max items to return"),
        offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    ):
        self.limit = limit
        self.offset = offset


async def paginate(
    db: AsyncSession,
    stmt: Select,
    count_stmt: Select,
    page: PaginationParams,
) -> tuple[Sequence, int]:
    """Execute a query with pagination, returning (rows, total_count)."""
    total = (await db.execute(count_stmt)).scalar() or 0
    result = await db.execute(stmt.limit(page.limit).offset(page.offset))
    return result.scalars().all(), total


async def require_admin(
    api_key: str | None = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """FastAPI dependency — requires admin scope on the API key.

    Returns the tenant if the key has admin scope, raises 403 otherwise.
    """
    from smn.auth import get_current_tenant

    # First, authenticate normally
    tenant = await get_current_tenant(api_key, db)

    # Then check for admin scope on the key
    if not api_key:
        raise AuthorizationError("Admin access required.")

    key_hash = hash_key(api_key)
    result = await db.execute(
        select(APIKeyRecord).where(
            APIKeyRecord.key_hash == key_hash,
            APIKeyRecord.is_active == True,  # noqa: E712
        )
    )
    key_record = result.scalar_one_or_none()
    if not key_record:
        raise AuthorizationError("Admin access required.")

    scopes = json.loads(key_record.scopes)
    if "admin" not in scopes and "admin:full" not in scopes:
        raise AuthorizationError("Admin scope required. Your API key does not have admin permissions.")

    return tenant
