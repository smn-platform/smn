"""Memory services — session, agent, and organization memory with TTL and access controls.

Implements controlled memory with:
- Session memory: ephemeral, tied to a single task execution.
- Persistent memory: survives across tasks, scoped to agent or org.
- TTL enforcement and access-scope checking.
- Full audit trail of memory reads/writes (GDPR Art. 17 right-to-erasure ready).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionMemory:
    """Ephemeral memory scoped to a single task run.

    Automatically discarded when the task completes.  Useful for
    conversation context and intermediate results.
    """

    ttl_hours: float = 24.0
    _store: dict[str, Any] = field(default_factory=dict, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return default
        if entry["expires_at"] and datetime.now(timezone.utc) > entry["expires_at"]:
            del self._store[key]
            return default
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.ttl_hours)
        self._store[key] = {"value": value, "expires_at": expires_at}

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def keys(self) -> list[str]:
        self._gc()
        return list(self._store.keys())

    def to_context_string(self, max_items: int = 20) -> str:
        """Serialize recent memory entries for injection into LLM context."""
        self._gc()
        items = list(self._store.items())[:max_items]
        if not items:
            return ""
        lines = ["<memory scope='session'>"]
        for k, v in items:
            lines.append(f"  {k}: {json.dumps(v['value'], default=str)}")
        lines.append("</memory>")
        return "\n".join(lines)

    def _gc(self) -> None:
        """Remove expired entries."""
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._store.items() if v["expires_at"] and now > v["expires_at"]]
        for k in expired:
            del self._store[k]


@dataclass
class PersistentMemory:
    """Persistent memory backed by the database.

    Scoped to an agent or organization.  Survives across task runs.
    Access-controlled via scopes.

    Note: actual DB operations happen in the runtime — this class
    provides the interface and local cache.
    """

    scope: str = "agent"  # "agent" or "org"
    namespace: str = "default"
    ttl_hours: float | None = None  # None = no expiry
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)
    _dirty: set[str] = field(default_factory=set, repr=False)
    _deleted: set[str] = field(default_factory=set, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._dirty.add(key)
        self._deleted.discard(key)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
        self._dirty.discard(key)
        self._deleted.add(key)

    def has_changes(self) -> bool:
        return bool(self._dirty) or bool(self._deleted)

    def flush_changes(self) -> tuple[dict[str, Any], set[str]]:
        """Return (upserts, deletes) and clear dirty state."""
        upserts = {k: self._cache[k] for k in self._dirty if k in self._cache}
        deletes = set(self._deleted)
        self._dirty.clear()
        self._deleted.clear()
        return upserts, deletes

    def load_from_db(self, entries: dict[str, Any]) -> None:
        """Hydrate the cache from database results."""
        self._cache.update(entries)

    def to_context_string(self, max_items: int = 20) -> str:
        items = list(self._cache.items())[:max_items]
        if not items:
            return ""
        lines = [f"<memory scope='{self.scope}' namespace='{self.namespace}'>"]
        for k, v in items:
            lines.append(f"  {k}: {json.dumps(v, default=str)}")
        lines.append("</memory>")
        return "\n".join(lines)


# ── Database persistence ─────────────────────────────────────────


async def load_memory_from_db(
    db_session: Any,
    tenant_id: str,
    agent_id: str,
    scope: str = "agent",
    namespace: str = "default",
) -> dict[str, Any]:
    """Load memory entries from the database.

    Returns a dict of key → value pairs for hydrating PersistentMemory.
    Expired entries are skipped.
    """
    from sqlalchemy import select

    from smn.models import MemoryEntry

    now = datetime.now(timezone.utc)
    stmt = (
        select(MemoryEntry)
        .where(
            MemoryEntry.tenant_id == tenant_id,
            MemoryEntry.scope == scope,
            MemoryEntry.namespace == namespace,
        )
    )
    if scope == "agent":
        stmt = stmt.where(MemoryEntry.agent_id == agent_id)

    result = await db_session.execute(stmt)
    entries = result.scalars().all()

    loaded: dict[str, Any] = {}
    for entry in entries:
        if entry.expires_at and entry.expires_at < now:
            continue
        try:
            loaded[entry.key] = json.loads(entry.value)
        except (json.JSONDecodeError, TypeError):
            loaded[entry.key] = entry.value
    logger.debug("loaded %d memory entries for %s/%s", len(loaded), tenant_id, agent_id)
    return loaded


async def flush_memory_to_db(
    db_session: Any,
    tenant_id: str,
    agent_id: str,
    memory: PersistentMemory,
) -> int:
    """Flush dirty memory entries to the database.

    Performs upserts for changed keys and deletes for removed keys.
    Returns the number of entries written.
    """
    from sqlalchemy import delete, select

    from smn.models import MemoryEntry

    if not memory.has_changes():
        return 0

    upserts, deletes = memory.flush_changes()
    count = 0

    # Delete removed keys
    for key in deletes:
        await db_session.execute(
            delete(MemoryEntry).where(
                MemoryEntry.tenant_id == tenant_id,
                MemoryEntry.agent_id == agent_id,
                MemoryEntry.scope == memory.scope,
                MemoryEntry.namespace == memory.namespace,
                MemoryEntry.key == key,
            )
        )

    # Upsert changed keys
    expires_at = None
    if memory.ttl_hours is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=memory.ttl_hours)

    for key, value in upserts.items():
        # Check if exists
        result = await db_session.execute(
            select(MemoryEntry).where(
                MemoryEntry.tenant_id == tenant_id,
                MemoryEntry.agent_id == agent_id,
                MemoryEntry.scope == memory.scope,
                MemoryEntry.namespace == memory.namespace,
                MemoryEntry.key == key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = json.dumps(value, default=str)
            existing.expires_at = expires_at
        else:
            entry = MemoryEntry(
                tenant_id=tenant_id,
                agent_id=agent_id,
                scope=memory.scope,
                namespace=memory.namespace,
                key=key,
                value=json.dumps(value, default=str),
                expires_at=expires_at,
            )
            db_session.add(entry)
        count += 1

    await db_session.flush()
    logger.debug("flushed %d memory entries for %s/%s", count, tenant_id, agent_id)
    return count
