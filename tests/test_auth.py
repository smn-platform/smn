"""Tests for auth module — API key management and authentication."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from smn.auth import authenticate_key, create_api_key, generate_api_key, hash_key, revoke_api_key
from smn.models import APIKeyRecord, Tenant


def test_generate_api_key():
    key = generate_api_key()
    assert key.startswith("smn_")
    assert len(key) > 20


def test_hash_key_deterministic():
    key = "smn_test_key_123"
    h1 = hash_key(key)
    h2 = hash_key(key)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_key_different_keys():
    h1 = hash_key("smn_key_1")
    h2 = hash_key("smn_key_2")
    assert h1 != h2


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> Tenant:
    t = Tenant(name="test-tenant")
    db.add(t)
    await db.flush()
    return t


async def test_create_api_key(db: AsyncSession, tenant: Tenant):
    record, raw_key = await create_api_key(db, tenant.id, "test-key")
    assert raw_key.startswith("smn_")
    assert record.key_prefix == raw_key[:8]
    assert record.tenant_id == tenant.id
    assert record.name == "test-key"
    assert record.is_active is True


async def test_authenticate_valid_key(db: AsyncSession, tenant: Tenant):
    _, raw_key = await create_api_key(db, tenant.id, "auth-test")
    await db.flush()

    result = await authenticate_key(db, raw_key)
    assert result is not None
    assert result.tenant_id == tenant.id


async def test_authenticate_invalid_key(db: AsyncSession, tenant: Tenant):
    result = await authenticate_key(db, "smn_invalid_key_12345")
    assert result is None


async def test_revoke_api_key(db: AsyncSession, tenant: Tenant):
    record, raw_key = await create_api_key(db, tenant.id, "revoke-test")
    await db.flush()

    success = await revoke_api_key(db, record.id)
    assert success is True

    # Should no longer authenticate
    result = await authenticate_key(db, raw_key)
    assert result is None


async def test_revoke_nonexistent_key(db: AsyncSession):
    success = await revoke_api_key(db, "nonexistent-id")
    assert success is False


async def test_create_multiple_keys(db: AsyncSession, tenant: Tenant):
    _, key1 = await create_api_key(db, tenant.id, "key-1")
    _, key2 = await create_api_key(db, tenant.id, "key-2")
    await db.flush()

    result1 = await authenticate_key(db, key1)
    result2 = await authenticate_key(db, key2)
    assert result1 is not None
    assert result2 is not None
    assert result1.id != result2.id
