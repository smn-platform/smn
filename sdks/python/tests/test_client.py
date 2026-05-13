"""Tests for the SMN Python SDK."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from smn_client import (
    AsyncSMNClient,
    SMNClient,
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from smn_client._types import Agent, Task, Policy, AuditEntry, HealthCheck, ListPage


BASE_URL = "http://test-smn:8000"
API_KEY = "smn_test_key_1234567890"


def _list_envelope(items: list, *, total: int | None = None, limit: int = 20, offset: int = 0) -> dict:
    """Build a pagination envelope matching the API format."""
    total_count = total if total is not None else len(items)
    return {
        "object": "list",
        "data": items,
        "has_more": offset + limit < total_count,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
    }

AGENT_RESPONSE = {
    "id": "agent-1",
    "tenant_id": "tenant-1",
    "name": "analyst",
    "description": "Test agent",
    "model": "gpt-4o",
    "risk_level": "limited",
    "policy_name": "default",
    "scopes": ["api:full"],
    "max_cost_per_task": 5.0,
    "is_active": True,
}

TASK_RESPONSE = {
    "id": "task-1",
    "agent_id": "agent-1",
    "input_text": "Hello",
    "status": "completed",
    "output_text": "Hi there!",
    "error": None,
    "total_cost_usd": 0.01,
    "total_steps": 1,
    "model_used": "gpt-4o",
    "started_at": "2026-04-18T10:00:00Z",
    "completed_at": "2026-04-18T10:00:05Z",
}


# ═══════════════════════════════════════════════════════════════════
#  Sync client tests
# ═══════════════════════════════════════════════════════════════════


class TestSMNClient:
    """Sync SDK tests."""

    def _client(self) -> SMNClient:
        return SMNClient(api_key=API_KEY, base_url=BASE_URL, max_retries=0)

    @respx.mock
    def test_health(self):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy", "version": "0.1.0", "service": "smn"})
        )
        with self._client() as c:
            h = c.health()
        assert isinstance(h, HealthCheck)
        assert h.status == "healthy"

    @respx.mock
    def test_create_agent(self):
        respx.post(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(201, json=AGENT_RESPONSE)
        )
        with self._client() as c:
            agent = c.agents.create(name="analyst", model="gpt-4o")
        assert isinstance(agent, Agent)
        assert agent.id == "agent-1"
        assert agent.name == "analyst"

    @respx.mock
    def test_list_agents(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(200, json=_list_envelope([AGENT_RESPONSE]))
        )
        with self._client() as c:
            page = c.agents.list()
        assert isinstance(page, ListPage)
        assert len(page.data) == 1
        assert page.data[0].name == "analyst"
        assert page.total_count == 1
        assert page.has_more is False

    @respx.mock
    def test_get_agent(self):
        respx.get(f"{BASE_URL}/api/v1/agents/agent-1").mock(
            return_value=httpx.Response(200, json=AGENT_RESPONSE)
        )
        with self._client() as c:
            agent = c.agents.get("agent-1")
        assert agent.id == "agent-1"

    @respx.mock
    def test_update_agent(self):
        updated = {**AGENT_RESPONSE, "description": "Updated"}
        respx.patch(f"{BASE_URL}/api/v1/agents/agent-1").mock(
            return_value=httpx.Response(200, json=updated)
        )
        with self._client() as c:
            agent = c.agents.update("agent-1", description="Updated")
        assert agent.description == "Updated"

    @respx.mock
    def test_delete_agent(self):
        respx.delete(f"{BASE_URL}/api/v1/agents/agent-1").mock(
            return_value=httpx.Response(204)
        )
        with self._client() as c:
            result = c.agents.delete("agent-1")
        assert result is None

    @respx.mock
    def test_create_task(self):
        respx.post(f"{BASE_URL}/api/v1/tasks").mock(
            return_value=httpx.Response(201, json=TASK_RESPONSE)
        )
        with self._client() as c:
            task = c.tasks.create(agent_id="agent-1", input_text="Hello")
        assert isinstance(task, Task)
        assert task.status == "completed"

    @respx.mock
    def test_list_tasks(self):
        respx.get(f"{BASE_URL}/api/v1/tasks").mock(
            return_value=httpx.Response(200, json=_list_envelope([TASK_RESPONSE]))
        )
        with self._client() as c:
            page = c.tasks.list()
        assert len(page.data) == 1

    @respx.mock
    def test_list_tasks_with_filters(self):
        respx.get(f"{BASE_URL}/api/v1/tasks").mock(
            return_value=httpx.Response(200, json=_list_envelope([TASK_RESPONSE], limit=10))
        )
        with self._client() as c:
            page = c.tasks.list(agent_id="agent-1", status="completed", limit=10)
        assert len(page.data) == 1
        assert page.limit == 10

    @respx.mock
    def test_get_task(self):
        respx.get(f"{BASE_URL}/api/v1/tasks/task-1").mock(
            return_value=httpx.Response(200, json=TASK_RESPONSE)
        )
        with self._client() as c:
            task = c.tasks.get("task-1")
        assert task.output_text == "Hi there!"

    @respx.mock
    def test_create_policy(self):
        policy_resp = {
            "id": "pol-1", "tenant_id": "t-1", "name": "strict",
            "version": 1, "is_active": True, "content": "max_steps: 5",
        }
        respx.post(f"{BASE_URL}/api/v1/policies").mock(
            return_value=httpx.Response(201, json=policy_resp)
        )
        with self._client() as c:
            pol = c.policies.create(name="strict", content="max_steps: 5")
        assert isinstance(pol, Policy)
        assert pol.name == "strict"

    @respx.mock
    def test_list_policies(self):
        respx.get(f"{BASE_URL}/api/v1/policies").mock(
            return_value=httpx.Response(200, json=_list_envelope([]))
        )
        with self._client() as c:
            page = c.policies.list()
        assert page.data == []
        assert page.total_count == 0

    @respx.mock
    def test_audit_list(self):
        respx.get(f"{BASE_URL}/api/v1/audit").mock(
            return_value=httpx.Response(200, json=_list_envelope([], limit=100))
        )
        with self._client() as c:
            page = c.audit.list()
        assert page.data == []
        assert page.total_count == 0

    @respx.mock
    def test_audit_verify(self):
        respx.get(f"{BASE_URL}/api/v1/audit/verify").mock(
            return_value=httpx.Response(200, json={"is_valid": True, "message": "OK"})
        )
        with self._client() as c:
            result = c.audit.verify()
        assert result.is_valid is True

    @respx.mock
    def test_billing_status(self):
        respx.get(f"{BASE_URL}/api/v1/billing/status").mock(
            return_value=httpx.Response(200, json={
                "tenant_id": "t-1", "plan_tier": "core",
                "stripe_customer_id": None, "stripe_subscription_id": None,
                "subscription_status": None, "current_period_end": None,
            })
        )
        with self._client() as c:
            status = c.billing.status()
        assert status.plan_tier == "core"

    @respx.mock
    def test_keys_list(self):
        respx.get(f"{BASE_URL}/api/v1/auth/keys").mock(
            return_value=httpx.Response(200, json=_list_envelope([]))
        )
        with self._client() as c:
            page = c.keys.list()
        assert page.data == []
        assert page.total_count == 0

    @respx.mock
    def test_idempotency_key_sent(self):
        route = respx.post(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(201, json=AGENT_RESPONSE)
        )
        with self._client() as c:
            c.agents.create(name="test", idempotency_key="idem-123")
        assert route.calls[0].request.headers.get("idempotency-key") == "idem-123"

    @respx.mock
    def test_api_key_header_sent(self):
        route = respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy", "version": "0.1.0", "service": "smn"})
        )
        with self._client() as c:
            c.health()
        assert route.calls[0].request.headers.get("x-api-key") == API_KEY


# ═══════════════════════════════════════════════════════════════════
#  Error handling tests
# ═══════════════════════════════════════════════════════════════════


class TestErrors:
    def _client(self) -> SMNClient:
        return SMNClient(api_key=API_KEY, base_url=BASE_URL, max_retries=0)

    @respx.mock
    def test_401_raises_authentication_error(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(401, json={
                "error": {"type": "authentication_error", "code": "invalid_api_key", "message": "Bad key"}
            })
        )
        with self._client() as c:
            with pytest.raises(AuthenticationError) as exc_info:
                c.agents.list()
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "invalid_api_key"

    @respx.mock
    def test_403_raises_authorization_error(self):
        respx.get(f"{BASE_URL}/api/v1/admin/tenants").mock(
            return_value=httpx.Response(403, json={
                "error": {"type": "authorization_error", "code": "insufficient_scope", "message": "No admin"}
            })
        )
        with self._client() as c:
            with pytest.raises(AuthorizationError):
                c.admin.tenants()

    @respx.mock
    def test_404_raises_not_found(self):
        respx.get(f"{BASE_URL}/api/v1/agents/missing").mock(
            return_value=httpx.Response(404, json={
                "error": {"type": "invalid_request_error", "code": "resource_not_found", "message": "Agent not found."}
            })
        )
        with self._client() as c:
            with pytest.raises(NotFoundError):
                c.agents.get("missing")

    @respx.mock
    def test_400_raises_bad_request(self):
        respx.post(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(400, json={
                "error": {"type": "invalid_request_error", "code": "bad_request", "message": "Bad"}
            })
        )
        with self._client() as c:
            with pytest.raises(BadRequestError):
                c.agents.create(name="test")

    @respx.mock
    def test_422_raises_validation_error(self):
        respx.post(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(422, json={
                "error": {"type": "invalid_request_error", "code": "validation_error", "message": "Invalid field"}
            })
        )
        with self._client() as c:
            with pytest.raises(ValidationError):
                c.agents.create(name="test")

    @respx.mock
    def test_429_raises_rate_limit_error(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(429, json={
                "error": {"type": "rate_limit_error", "code": "rate_limit_exceeded", "message": "Slow down"}
            })
        )
        with self._client() as c:
            with pytest.raises(RateLimitError):
                c.agents.list()

    @respx.mock
    def test_error_includes_request_id(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(
                401,
                json={"error": {"type": "authentication_error", "code": "invalid_api_key", "message": "Bad"}},
                headers={"X-Request-Id": "req_abc123"},
            )
        )
        with self._client() as c:
            with pytest.raises(AuthenticationError) as exc_info:
                c.agents.list()
        assert exc_info.value.request_id == "req_abc123"


# ═══════════════════════════════════════════════════════════════════
#  Async client tests
# ═══════════════════════════════════════════════════════════════════


class TestAsyncSMNClient:
    def _client(self) -> AsyncSMNClient:
        return AsyncSMNClient(api_key=API_KEY, base_url=BASE_URL, max_retries=0)

    @respx.mock
    async def test_async_health(self):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy", "version": "0.1.0", "service": "smn"})
        )
        async with self._client() as c:
            h = await c.health()
        assert h.status == "healthy"

    @respx.mock
    async def test_async_create_agent(self):
        respx.post(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(201, json=AGENT_RESPONSE)
        )
        async with self._client() as c:
            agent = await c.agents.create(name="analyst", model="gpt-4o")
        assert agent.name == "analyst"

    @respx.mock
    async def test_async_list_agents(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(200, json=_list_envelope([AGENT_RESPONSE]))
        )
        async with self._client() as c:
            page = await c.agents.list()
        assert isinstance(page, ListPage)
        assert len(page.data) == 1

    @respx.mock
    async def test_async_get_agent(self):
        respx.get(f"{BASE_URL}/api/v1/agents/agent-1").mock(
            return_value=httpx.Response(200, json=AGENT_RESPONSE)
        )
        async with self._client() as c:
            agent = await c.agents.get("agent-1")
        assert agent.id == "agent-1"

    @respx.mock
    async def test_async_create_task(self):
        respx.post(f"{BASE_URL}/api/v1/tasks").mock(
            return_value=httpx.Response(201, json=TASK_RESPONSE)
        )
        async with self._client() as c:
            task = await c.tasks.create(agent_id="agent-1", input_text="Hello")
        assert task.status == "completed"

    @respx.mock
    async def test_async_audit_verify(self):
        respx.get(f"{BASE_URL}/api/v1/audit/verify").mock(
            return_value=httpx.Response(200, json={"is_valid": True, "message": "OK"})
        )
        async with self._client() as c:
            result = await c.audit.verify()
        assert result.is_valid is True

    @respx.mock
    async def test_async_error_handling(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(401, json={
                "error": {"type": "authentication_error", "code": "invalid_api_key", "message": "Bad"}
            })
        )
        async with self._client() as c:
            with pytest.raises(AuthenticationError):
                await c.agents.list()


# ═══════════════════════════════════════════════════════════════════
#  Context manager tests
# ═══════════════════════════════════════════════════════════════════


class TestContextManagers:
    @respx.mock
    def test_sync_context_manager(self):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy", "version": "0.1.0", "service": "smn"})
        )
        with SMNClient(api_key=API_KEY, base_url=BASE_URL) as client:
            h = client.health()
        assert h.status == "healthy"

    @respx.mock
    async def test_async_context_manager(self):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy", "version": "0.1.0", "service": "smn"})
        )
        async with AsyncSMNClient(api_key=API_KEY, base_url=BASE_URL) as client:
            h = await client.health()
        assert h.status == "healthy"


# ═══════════════════════════════════════════════════════════════════
#  Pagination tests
# ═══════════════════════════════════════════════════════════════════


class TestPagination:
    def _client(self) -> SMNClient:
        return SMNClient(api_key=API_KEY, base_url=BASE_URL, max_retries=0)

    @respx.mock
    def test_has_more_true(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(200, json=_list_envelope(
                [AGENT_RESPONSE], total=5, limit=2, offset=0,
            ))
        )
        with self._client() as c:
            page = c.agents.list(limit=2)
        assert page.has_more is True
        assert page.total_count == 5
        assert page.limit == 2
        assert page.offset == 0

    @respx.mock
    def test_has_more_false(self):
        respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(200, json=_list_envelope(
                [AGENT_RESPONSE], total=1, limit=20, offset=0,
            ))
        )
        with self._client() as c:
            page = c.agents.list()
        assert page.has_more is False

    @respx.mock
    def test_offset_passed_to_server(self):
        route = respx.get(f"{BASE_URL}/api/v1/agents").mock(
            return_value=httpx.Response(200, json=_list_envelope([], limit=20, offset=40))
        )
        with self._client() as c:
            c.agents.list(offset=40)
        assert "offset=40" in str(route.calls[0].request.url)

    @respx.mock
    def test_list_page_object_field(self):
        respx.get(f"{BASE_URL}/api/v1/tasks").mock(
            return_value=httpx.Response(200, json=_list_envelope([TASK_RESPONSE]))
        )
        with self._client() as c:
            page = c.tasks.list()
        assert page.object == "list"

    @respx.mock
    def test_admin_tenants_pagination(self):
        tenant = {
            "id": "t-1", "name": "Acme", "plan_tier": "core",
            "is_active": True, "stripe_customer_id": None,
            "stripe_subscription_id": None, "agent_count": 2,
            "task_count": 10, "total_cost_usd": 1.5,
            "api_key_count": 1, "created_at": "2026-01-01T00:00:00Z",
        }
        respx.get(f"{BASE_URL}/api/v1/admin/tenants").mock(
            return_value=httpx.Response(200, json=_list_envelope([tenant]))
        )
        with self._client() as c:
            page = c.admin.tenants()
        assert len(page.data) == 1
        assert page.data[0].name == "Acme"
