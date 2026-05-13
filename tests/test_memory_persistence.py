"""Tests for memory persistence — DB load/flush operations."""

from __future__ import annotations

import pytest

from smn.core.memory import (
    PersistentMemory,
    flush_memory_to_db,
    load_memory_from_db,
)
from smn.models import MemoryEntry


@pytest.mark.asyncio
async def test_flush_and_load_round_trip(db):
    """Write memory entries to DB and read them back."""
    mem = PersistentMemory(scope="agent", namespace="test")
    mem.set("key1", "value1")
    mem.set("key2", {"nested": True})

    count = await flush_memory_to_db(db, "tenant1", "agent1", mem)
    assert count == 2
    assert not mem.has_changes()

    loaded = await load_memory_from_db(db, "tenant1", "agent1", scope="agent", namespace="test")
    assert loaded["key1"] == "value1"
    assert loaded["key2"] == {"nested": True}


@pytest.mark.asyncio
async def test_flush_upsert(db):
    """Flushing an existing key updates it."""
    mem = PersistentMemory(scope="agent", namespace="test")
    mem.set("k", "v1")
    await flush_memory_to_db(db, "t1", "a1", mem)

    mem.set("k", "v2")
    await flush_memory_to_db(db, "t1", "a1", mem)

    loaded = await load_memory_from_db(db, "t1", "a1", scope="agent", namespace="test")
    assert loaded["k"] == "v2"


@pytest.mark.asyncio
async def test_flush_deletes(db):
    """Deleted keys are removed from DB."""
    mem = PersistentMemory(scope="agent", namespace="test")
    mem.set("keep", "yes")
    mem.set("remove", "no")
    await flush_memory_to_db(db, "t1", "a1", mem)

    mem.delete("remove")
    await flush_memory_to_db(db, "t1", "a1", mem)

    loaded = await load_memory_from_db(db, "t1", "a1", scope="agent", namespace="test")
    assert "keep" in loaded
    assert "remove" not in loaded


@pytest.mark.asyncio
async def test_no_changes_no_writes(db):
    """Flushing with no changes writes nothing."""
    mem = PersistentMemory(scope="agent", namespace="test")
    count = await flush_memory_to_db(db, "t1", "a1", mem)
    assert count == 0


@pytest.mark.asyncio
async def test_load_empty(db):
    """Loading from empty DB returns empty dict."""
    loaded = await load_memory_from_db(db, "t1", "a1")
    assert loaded == {}


@pytest.mark.asyncio
async def test_scope_isolation(db):
    """Different scopes/namespaces are isolated."""
    mem1 = PersistentMemory(scope="agent", namespace="ns1")
    mem1.set("x", 1)
    await flush_memory_to_db(db, "t1", "a1", mem1)

    mem2 = PersistentMemory(scope="agent", namespace="ns2")
    mem2.set("x", 2)
    await flush_memory_to_db(db, "t1", "a1", mem2)

    loaded1 = await load_memory_from_db(db, "t1", "a1", scope="agent", namespace="ns1")
    loaded2 = await load_memory_from_db(db, "t1", "a1", scope="agent", namespace="ns2")
    assert loaded1["x"] == 1
    assert loaded2["x"] == 2
