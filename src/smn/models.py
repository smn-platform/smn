"""SQLAlchemy models — the canonical data layer for SMN.

Every agent action, policy decision, and state change is persisted here.
The audit_entries table is append-only with hash chaining for tamper evidence
(EU AI Act Art. 12 logging; NIST AI RMF MEASURE function).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


# ── Base ──────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── Tenants ───────────────────────────────────────────────────────


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    plan_tier: Mapped[str] = mapped_column(String(50), default="core")  # core|growth|enterprise
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60)  # requests per minute

    agents: Mapped[list[AgentRecord]] = relationship(back_populates="tenant")


# ── Agents ────────────────────────────────────────────────────────


class AgentRecord(Base):
    """Registered agent definition (not a running instance)."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), default="limited")  # minimal|limited|high
    policy_name: Mapped[str] = mapped_column(String(255), default="default")
    scopes: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of permission scopes
    max_cost_per_task: Mapped[float] = mapped_column(Float, default=5.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped[Tenant] = relationship(back_populates="agents")
    tasks: Mapped[list[TaskRecord]] = relationship(back_populates="agent")

    @property
    def scope_list(self) -> list[str]:
        return json.loads(self.scopes)


# ── Tasks (execution runs) ───────────────────────────────────────


class TaskRecord(Base):
    """A single agent execution run."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|running|completed|failed|denied|killed
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    model_used: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # for sub-tasks

    agent: Mapped[AgentRecord] = relationship(back_populates="tasks")

    __table_args__ = (Index("ix_tasks_agent_status", "agent_id", "status"),)


# ── Audit Log (append-only, hash-chained) ────────────────────────


class AuditEntry(Base):
    """Immutable, hash-chained audit record.

    Each entry contains the SHA-256 hash of the previous entry, forming a
    tamper-evident chain.  This satisfies:
    - EU AI Act Art. 12 (automatic logging for high-risk systems)
    - NIST AI RMF MEASURE-2.6 (measurement of AI risks)
    """

    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    policy_decision: Mapped[str] = mapped_column(String(50), default="allow")  # allow|deny|escalate
    policy_reason: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    prev_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "timestamp"),)

    @staticmethod
    def compute_hash(
        prev_hash: str,
        timestamp: str,
        tenant_id: str,
        event_type: str,
        action: str,
        detail: str,
    ) -> str:
        payload = f"{prev_hash}|{timestamp}|{tenant_id}|{event_type}|{action}|{detail}"
        return hashlib.sha256(payload.encode()).hexdigest()


# ── Memory ────────────────────────────────────────────────────────


class MemoryEntry(Base):
    """Stored memory with access controls and TTL."""

    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # session|agent|org
    namespace: Mapped[str] = mapped_column(String(255), default="default")
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_scopes: Mapped[str] = mapped_column(Text, default="[]")  # JSON — who can read

    __table_args__ = (
        Index("ix_memory_lookup", "tenant_id", "scope", "namespace", "key"),
    )


# ── Policy Records ───────────────────────────────────────────────


class PolicyRecord(Base):
    """Stored policy definition (versioned)."""

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # YAML
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_policy_tenant_name", "tenant_id", "name"),)


# ── API Keys ──────────────────────────────────────────────────────


class APIKeyRecord(Base):
    """API key for tenant authentication.

    Keys are stored as SHA-256 hashes — the raw key is only shown once at creation.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)  # first 8 chars for identification
    scopes: Mapped[str] = mapped_column(Text, default='["api:full"]')  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped[Tenant] = relationship()

    __table_args__ = (Index("ix_api_keys_hash", "key_hash"),)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Usage / Metering Records ─────────────────────────────────────


class UsageRecord(Base):
    """Aggregated usage record per tenant per billing period."""

    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    memory_writes: Mapped[int] = mapped_column(Integer, default=0)
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_usage_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_usage_tenant_period", "tenant_id", "period_start"),)


# ── Checkpoints ───────────────────────────────────────────────────


class CheckpointRecord(Base):
    """Persisted execution checkpoint for task resumability."""

    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_checkpoint_task_step", "task_id", "step"),)
