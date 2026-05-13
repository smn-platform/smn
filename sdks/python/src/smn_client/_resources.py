"""Resource classes — each maps to an API resource group."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generator, AsyncGenerator, TYPE_CHECKING

from smn_client._types import (
    Agent,
    APIKey,
    APIKeyCreated,
    AuditEntry,
    BillingStatus,
    BootstrapResult,
    ChainVerification,
    CustomerResult,
    Framework,
    HealthCheck,
    ListPage,
    Policy,
    StreamEvent,
    SubscriptionResult,
    SystemHealth,
    Task,
    TenantOverview,
    TenantUpdateResult,
    UsageSummary,
)

if TYPE_CHECKING:
    from smn_client._transport import _AsyncTransport, _SyncTransport


# ═══════════════════════════════════════════════════════════════════
#  Sync resources
# ═══════════════════════════════════════════════════════════════════


class _AgentsResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def create(
        self,
        *,
        name: str,
        description: str = "",
        model: str = "anthropic/claude-sonnet-4-6-20250415",
        risk_level: str = "limited",
        policy_name: str = "default",
        scopes: list[str] | None = None,
        max_cost_per_task: float = 5.0,
        idempotency_key: str | None = None,
    ) -> Agent:
        data = self._t.request(
            "POST", "/api/v1/agents",
            json={
                "name": name,
                "description": description,
                "model": model,
                "risk_level": risk_level,
                "policy_name": policy_name,
                "scopes": scopes or [],
                "max_cost_per_task": max_cost_per_task,
            },
            idempotency_key=idempotency_key,
        )
        return Agent.model_validate(data)

    def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[Agent]:
        data = self._t.request(
            "GET", "/api/v1/agents",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[Agent.model_validate(a) for a in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def get(self, agent_id: str) -> Agent:
        data = self._t.request("GET", f"/api/v1/agents/{agent_id}")
        return Agent.model_validate(data)

    def update(
        self,
        agent_id: str,
        *,
        description: str | None = None,
        model: str | None = None,
        risk_level: str | None = None,
        policy_name: str | None = None,
        scopes: list[str] | None = None,
        max_cost_per_task: float | None = None,
        is_active: bool | None = None,
    ) -> Agent:
        body: dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if model is not None:
            body["model"] = model
        if risk_level is not None:
            body["risk_level"] = risk_level
        if policy_name is not None:
            body["policy_name"] = policy_name
        if scopes is not None:
            body["scopes"] = scopes
        if max_cost_per_task is not None:
            body["max_cost_per_task"] = max_cost_per_task
        if is_active is not None:
            body["is_active"] = is_active
        data = self._t.request("PATCH", f"/api/v1/agents/{agent_id}", json=body)
        return Agent.model_validate(data)

    def delete(self, agent_id: str) -> None:
        self._t.request("DELETE", f"/api/v1/agents/{agent_id}")


class _TasksResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def create(
        self,
        *,
        agent_id: str,
        input_text: str,
        async_execution: bool = False,
        idempotency_key: str | None = None,
    ) -> Task:
        data = self._t.request(
            "POST", "/api/v1/tasks",
            json={
                "agent_id": agent_id,
                "input_text": input_text,
                "async_execution": async_execution,
            },
            idempotency_key=idempotency_key,
        )
        return Task.model_validate(data)

    def list(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ListPage[Task]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        data = self._t.request("GET", "/api/v1/tasks", params=params)
        return ListPage(
            data=[Task.model_validate(t) for t in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def get(self, task_id: str) -> Task:
        data = self._t.request("GET", f"/api/v1/tasks/{task_id}")
        return Task.model_validate(data)

    def stream(
        self,
        *,
        agent_id: str,
        input_text: str,
    ) -> Generator[StreamEvent, None, None]:
        for event_type, data in self._t.stream_sse(
            "/api/v1/stream",
            json={"agent_id": agent_id, "input_text": input_text},
        ):
            yield StreamEvent(event=event_type, data=data)


class _PoliciesResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def create(
        self,
        *,
        name: str,
        content: str,
        idempotency_key: str | None = None,
    ) -> Policy:
        data = self._t.request(
            "POST", "/api/v1/policies",
            json={"name": name, "content": content},
            idempotency_key=idempotency_key,
        )
        return Policy.model_validate(data)

    def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[Policy]:
        data = self._t.request(
            "GET", "/api/v1/policies",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[Policy.model_validate(p) for p in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def get(self, policy_id: str) -> Policy:
        data = self._t.request("GET", f"/api/v1/policies/{policy_id}")
        return Policy.model_validate(data)

    def frameworks(self) -> list[Framework]:
        data = self._t.request("GET", "/api/v1/policies/frameworks")
        return [Framework.model_validate(f) for f in data]


class _AuditResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def list(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ListPage[AuditEntry]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        if task_id:
            params["task_id"] = task_id
        if event_type:
            params["event_type"] = event_type
        data = self._t.request("GET", "/api/v1/audit", params=params)
        return ListPage(
            data=[AuditEntry.model_validate(e) for e in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def verify(self) -> ChainVerification:
        data = self._t.request("GET", "/api/v1/audit/verify")
        return ChainVerification.model_validate(data)


class _KeysResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def create(
        self,
        *,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> APIKeyCreated:
        body: dict[str, Any] = {"name": name}
        if scopes is not None:
            body["scopes"] = scopes
        if expires_at is not None:
            body["expires_at"] = expires_at.isoformat()
        data = self._t.request(
            "POST", "/api/v1/auth/keys", json=body,
            idempotency_key=idempotency_key,
        )
        return APIKeyCreated.model_validate(data)

    def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[APIKey]:
        data = self._t.request(
            "GET", "/api/v1/auth/keys",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[APIKey.model_validate(k) for k in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def revoke(self, key_id: str) -> None:
        self._t.request("DELETE", f"/api/v1/auth/keys/{key_id}")


class _BillingResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def create_customer(self, *, email: str | None = None) -> CustomerResult:
        data = self._t.request(
            "POST", "/api/v1/billing/customer",
            json={"email": email},
        )
        return CustomerResult.model_validate(data)

    def subscribe(self, *, tier: str = "core") -> SubscriptionResult:
        data = self._t.request(
            "POST", "/api/v1/billing/subscribe",
            json={"tier": tier},
        )
        return SubscriptionResult.model_validate(data)

    def status(self) -> BillingStatus:
        data = self._t.request("GET", "/api/v1/billing/status")
        return BillingStatus.model_validate(data)


class _AdminResource:
    def __init__(self, transport: _SyncTransport):
        self._t = transport

    def tenants(self, *, limit: int = 20, offset: int = 0) -> ListPage[TenantOverview]:
        data = self._t.request(
            "GET", "/api/v1/admin/tenants",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[TenantOverview.model_validate(t) for t in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    def update_tenant(
        self,
        tenant_id: str,
        *,
        is_active: bool | None = None,
        plan_tier: str | None = None,
        rate_limit_rpm: int | None = None,
    ) -> TenantUpdateResult:
        body: dict[str, Any] = {}
        if is_active is not None:
            body["is_active"] = is_active
        if plan_tier is not None:
            body["plan_tier"] = plan_tier
        if rate_limit_rpm is not None:
            body["rate_limit_rpm"] = rate_limit_rpm
        data = self._t.request("PATCH", f"/api/v1/admin/tenants/{tenant_id}", json=body)
        return TenantUpdateResult.model_validate(data)

    def health(self) -> SystemHealth:
        data = self._t.request("GET", "/api/v1/admin/health")
        return SystemHealth.model_validate(data)

    def usage(self) -> list[UsageSummary]:
        data = self._t.request("GET", "/api/v1/admin/usage")
        return [UsageSummary.model_validate(u) for u in data]

    def tenant_usage(self, tenant_id: str) -> UsageSummary:
        data = self._t.request("GET", f"/api/v1/admin/usage/{tenant_id}")
        return UsageSummary.model_validate(data)


# ═══════════════════════════════════════════════════════════════════
#  Async resources
# ═══════════════════════════════════════════════════════════════════


class _AsyncAgentsResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def create(
        self,
        *,
        name: str,
        description: str = "",
        model: str = "anthropic/claude-sonnet-4-6-20250415",
        risk_level: str = "limited",
        policy_name: str = "default",
        scopes: list[str] | None = None,
        max_cost_per_task: float = 5.0,
        idempotency_key: str | None = None,
    ) -> Agent:
        data = await self._t.request(
            "POST", "/api/v1/agents",
            json={
                "name": name,
                "description": description,
                "model": model,
                "risk_level": risk_level,
                "policy_name": policy_name,
                "scopes": scopes or [],
                "max_cost_per_task": max_cost_per_task,
            },
            idempotency_key=idempotency_key,
        )
        return Agent.model_validate(data)

    async def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[Agent]:
        data = await self._t.request(
            "GET", "/api/v1/agents",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[Agent.model_validate(a) for a in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def get(self, agent_id: str) -> Agent:
        data = await self._t.request("GET", f"/api/v1/agents/{agent_id}")
        return Agent.model_validate(data)

    async def update(
        self,
        agent_id: str,
        *,
        description: str | None = None,
        model: str | None = None,
        risk_level: str | None = None,
        policy_name: str | None = None,
        scopes: list[str] | None = None,
        max_cost_per_task: float | None = None,
        is_active: bool | None = None,
    ) -> Agent:
        body: dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if model is not None:
            body["model"] = model
        if risk_level is not None:
            body["risk_level"] = risk_level
        if policy_name is not None:
            body["policy_name"] = policy_name
        if scopes is not None:
            body["scopes"] = scopes
        if max_cost_per_task is not None:
            body["max_cost_per_task"] = max_cost_per_task
        if is_active is not None:
            body["is_active"] = is_active
        data = await self._t.request("PATCH", f"/api/v1/agents/{agent_id}", json=body)
        return Agent.model_validate(data)

    async def delete(self, agent_id: str) -> None:
        await self._t.request("DELETE", f"/api/v1/agents/{agent_id}")


class _AsyncTasksResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def create(
        self,
        *,
        agent_id: str,
        input_text: str,
        async_execution: bool = False,
        idempotency_key: str | None = None,
    ) -> Task:
        data = await self._t.request(
            "POST", "/api/v1/tasks",
            json={
                "agent_id": agent_id,
                "input_text": input_text,
                "async_execution": async_execution,
            },
            idempotency_key=idempotency_key,
        )
        return Task.model_validate(data)

    async def list(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ListPage[Task]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        data = await self._t.request("GET", "/api/v1/tasks", params=params)
        return ListPage(
            data=[Task.model_validate(t) for t in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def get(self, task_id: str) -> Task:
        data = await self._t.request("GET", f"/api/v1/tasks/{task_id}")
        return Task.model_validate(data)

    async def stream(
        self,
        *,
        agent_id: str,
        input_text: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        async for event_type, data in self._t.stream_sse(
            "/api/v1/stream",
            json={"agent_id": agent_id, "input_text": input_text},
        ):
            yield StreamEvent(event=event_type, data=data)


class _AsyncPoliciesResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def create(
        self,
        *,
        name: str,
        content: str,
        idempotency_key: str | None = None,
    ) -> Policy:
        data = await self._t.request(
            "POST", "/api/v1/policies",
            json={"name": name, "content": content},
            idempotency_key=idempotency_key,
        )
        return Policy.model_validate(data)

    async def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[Policy]:
        data = await self._t.request(
            "GET", "/api/v1/policies",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[Policy.model_validate(p) for p in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def get(self, policy_id: str) -> Policy:
        data = await self._t.request("GET", f"/api/v1/policies/{policy_id}")
        return Policy.model_validate(data)

    async def frameworks(self) -> list[Framework]:
        data = await self._t.request("GET", "/api/v1/policies/frameworks")
        return [Framework.model_validate(f) for f in data]


class _AsyncAuditResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def list(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ListPage[AuditEntry]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        if task_id:
            params["task_id"] = task_id
        if event_type:
            params["event_type"] = event_type
        data = await self._t.request("GET", "/api/v1/audit", params=params)
        return ListPage(
            data=[AuditEntry.model_validate(e) for e in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def verify(self) -> ChainVerification:
        data = await self._t.request("GET", "/api/v1/audit/verify")
        return ChainVerification.model_validate(data)


class _AsyncKeysResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def create(
        self,
        *,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> APIKeyCreated:
        body: dict[str, Any] = {"name": name}
        if scopes is not None:
            body["scopes"] = scopes
        if expires_at is not None:
            body["expires_at"] = expires_at.isoformat()
        data = await self._t.request(
            "POST", "/api/v1/auth/keys", json=body,
            idempotency_key=idempotency_key,
        )
        return APIKeyCreated.model_validate(data)

    async def list(self, *, limit: int = 20, offset: int = 0) -> ListPage[APIKey]:
        data = await self._t.request(
            "GET", "/api/v1/auth/keys",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[APIKey.model_validate(k) for k in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def revoke(self, key_id: str) -> None:
        await self._t.request("DELETE", f"/api/v1/auth/keys/{key_id}")


class _AsyncBillingResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def create_customer(self, *, email: str | None = None) -> CustomerResult:
        data = await self._t.request(
            "POST", "/api/v1/billing/customer", json={"email": email},
        )
        return CustomerResult.model_validate(data)

    async def subscribe(self, *, tier: str = "core") -> SubscriptionResult:
        data = await self._t.request(
            "POST", "/api/v1/billing/subscribe", json={"tier": tier},
        )
        return SubscriptionResult.model_validate(data)

    async def status(self) -> BillingStatus:
        data = await self._t.request("GET", "/api/v1/billing/status")
        return BillingStatus.model_validate(data)


class _AsyncAdminResource:
    def __init__(self, transport: _AsyncTransport):
        self._t = transport

    async def tenants(self, *, limit: int = 20, offset: int = 0) -> ListPage[TenantOverview]:
        data = await self._t.request(
            "GET", "/api/v1/admin/tenants",
            params={"limit": limit, "offset": offset},
        )
        return ListPage(
            data=[TenantOverview.model_validate(t) for t in data["data"]],
            has_more=data["has_more"],
            total_count=data["total_count"],
            limit=data["limit"],
            offset=data["offset"],
        )

    async def update_tenant(
        self,
        tenant_id: str,
        *,
        is_active: bool | None = None,
        plan_tier: str | None = None,
        rate_limit_rpm: int | None = None,
    ) -> TenantUpdateResult:
        body: dict[str, Any] = {}
        if is_active is not None:
            body["is_active"] = is_active
        if plan_tier is not None:
            body["plan_tier"] = plan_tier
        if rate_limit_rpm is not None:
            body["rate_limit_rpm"] = rate_limit_rpm
        data = await self._t.request("PATCH", f"/api/v1/admin/tenants/{tenant_id}", json=body)
        return TenantUpdateResult.model_validate(data)

    async def health(self) -> SystemHealth:
        data = await self._t.request("GET", "/api/v1/admin/health")
        return SystemHealth.model_validate(data)

    async def usage(self) -> list[UsageSummary]:
        data = await self._t.request("GET", "/api/v1/admin/usage")
        return [UsageSummary.model_validate(u) for u in data]

    async def tenant_usage(self, tenant_id: str) -> UsageSummary:
        data = await self._t.request("GET", f"/api/v1/admin/usage/{tenant_id}")
        return UsageSummary.model_validate(data)
