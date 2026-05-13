"""Pydantic response types for SMN API resources."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ListPage(BaseModel, Generic[T]):
    """Paginated list response from the SMN API."""

    object: str = "list"
    data: list[T]
    has_more: bool
    total_count: int
    limit: int
    offset: int


# ── Agents ────────────────────────────────────────────────────────


class Agent(BaseModel):
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


# ── Tasks ─────────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    agent_id: str
    input_text: str
    status: str
    output_text: str | None = None
    error: str | None = None
    total_cost_usd: float
    total_steps: int
    model_used: str
    started_at: datetime
    completed_at: datetime | None = None


# ── Policies ──────────────────────────────────────────────────────


class Policy(BaseModel):
    id: str
    tenant_id: str
    name: str
    version: int
    is_active: bool
    content: str


class Framework(BaseModel):
    id: str
    name: str
    version: str
    effective_date: str
    requirement_count: int


# ── Audit ─────────────────────────────────────────────────────────


class AuditEntry(BaseModel):
    entry_id: str
    timestamp: datetime
    tenant_id: str
    agent_id: str | None = None
    task_id: str | None = None
    event_type: str
    action: str
    detail: str
    policy_decision: str
    policy_reason: str
    cost_usd: float
    entry_hash: str


class ChainVerification(BaseModel):
    is_valid: bool
    message: str


# ── Auth / Keys ───────────────────────────────────────────────────


class APIKey(BaseModel):
    id: str
    tenant_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class APIKeyCreated(APIKey):
    raw_key: str


class BootstrapResult(BaseModel):
    tenant_id: str
    tenant_name: str
    api_key: str
    key_id: str
    message: str


# ── Billing ───────────────────────────────────────────────────────


class CustomerResult(BaseModel):
    stripe_customer_id: str


class SubscriptionResult(BaseModel):
    subscription_id: str | None = None
    status: str | None = None
    tier: str | None = None


class BillingStatus(BaseModel):
    tenant_id: str
    plan_tier: str
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    subscription_status: str | None = None
    current_period_end: str | None = None


# ── Admin ─────────────────────────────────────────────────────────


class TenantOverview(BaseModel):
    id: str
    name: str
    plan_tier: str
    is_active: bool
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    agent_count: int
    task_count: int
    total_cost_usd: float
    api_key_count: int
    created_at: datetime


class SystemHealth(BaseModel):
    total_tenants: int
    active_tenants: int
    total_agents: int
    active_agents: int
    total_tasks: int
    tasks_last_24h: int
    total_audit_entries: int
    total_cost_usd: float
    database_status: str


class UsageSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    period_start: str
    period_end: str
    task_count: int
    tool_call_count: int
    llm_call_count: int
    total_cost_usd: float
    total_steps: int
    total_audit_events: int


class TenantUpdateResult(BaseModel):
    status: str
    tenant_id: str


# ── Health ────────────────────────────────────────────────────────


class HealthCheck(BaseModel):
    status: str
    version: str
    service: str


# ── Streaming ─────────────────────────────────────────────────────


class StreamEvent:
    """A single Server-Sent Event from a streaming task."""

    __slots__ = ("event", "data")

    def __init__(self, event: str, data: dict):
        self.event = event
        self.data = data

    def __repr__(self) -> str:
        return f"StreamEvent(event={self.event!r}, data={self.data!r})"
