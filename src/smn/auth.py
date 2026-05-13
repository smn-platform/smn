"""Authentication — API key management and request authentication.

Implements:
- API key generation with SHA-256 hashed storage (raw key shown only once).
- FastAPI dependency for authenticated endpoints.
- Key rotation and revocation.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from smn.db import get_db
from smn.models import APIKeyRecord, Tenant

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
KEY_PREFIX = "smn_"


def generate_api_key() -> str:
    """Generate a new API key with the smn_ prefix."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_key(raw_key: str) -> str:
    """SHA-256 hash of the raw API key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_api_key(
    db: AsyncSession,
    tenant_id: str,
    name: str,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[APIKeyRecord, str]:
    """Create a new API key. Returns (record, raw_key).

    The raw key is returned only once — it is stored as a hash.
    """
    import json

    raw_key = generate_api_key()
    key_hash = hash_key(raw_key)

    record = APIKeyRecord(
        tenant_id=tenant_id,
        name=name,
        key_hash=key_hash,
        key_prefix=raw_key[:8],
        scopes=json.dumps(scopes or ["api:full"]),
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()
    return record, raw_key


async def revoke_api_key(db: AsyncSession, key_id: str) -> bool:
    """Revoke an API key by ID."""
    result = await db.execute(select(APIKeyRecord).where(APIKeyRecord.id == key_id))
    record = result.scalar_one_or_none()
    if not record:
        return False
    record.is_active = False
    await db.flush()
    return True


async def authenticate_key(db: AsyncSession, raw_key: str) -> APIKeyRecord | None:
    """Look up and validate an API key. Returns the key record or None."""
    key_hash = hash_key(raw_key)
    result = await db.execute(
        select(APIKeyRecord).where(
            APIKeyRecord.key_hash == key_hash,
            APIKeyRecord.is_active == True,  # noqa: E712
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        return None

    # Check expiry
    if record.expires_at and record.expires_at < datetime.now(timezone.utc):
        return None

    # Update last_used_at
    await db.execute(
        update(APIKeyRecord)
        .where(APIKeyRecord.id == record.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )

    return record


async def get_current_tenant(
    api_key: str | None = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """FastAPI dependency — authenticates the request and returns the tenant.

    Raises 401 if no key or invalid key. Raises 403 if tenant is inactive.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Provide X-API-Key header.")

    key_record = await authenticate_key(db, api_key)
    if not key_record:
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    # Load tenant
    result = await db.execute(select(Tenant).where(Tenant.id == key_record.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Tenant is inactive.")

    return tenant
