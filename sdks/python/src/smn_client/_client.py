"""SMN Python SDK client — sync and async versions.

Usage:
    # Sync
    client = SMNClient(api_key="smn_...")
    agent = client.agents.create(name="analyst", model="gpt-4o")

    # Async
    client = AsyncSMNClient(api_key="smn_...")
    agent = await client.agents.create(name="analyst", model="gpt-4o")
"""

from __future__ import annotations

from smn_client._resources import (
    _AdminResource,
    _AgentsResource,
    _AsyncAdminResource,
    _AsyncAgentsResource,
    _AsyncAuditResource,
    _AsyncBillingResource,
    _AsyncKeysResource,
    _AsyncPoliciesResource,
    _AsyncTasksResource,
    _AuditResource,
    _BillingResource,
    _KeysResource,
    _PoliciesResource,
    _TasksResource,
)
from smn_client._transport import _AsyncTransport, _SyncTransport
from smn_client._types import BootstrapResult, HealthCheck

_DEFAULT_BASE_URL = "http://localhost:8000"


class SMNClient:
    """Synchronous SMN API client.

    Example:
        client = SMNClient(api_key="smn_...")
        agents = client.agents.list()
        task = client.tasks.create(agent_id=agents[0].id, input_text="Hello")
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._transport = _SyncTransport(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.agents = _AgentsResource(self._transport)
        self.tasks = _TasksResource(self._transport)
        self.policies = _PoliciesResource(self._transport)
        self.audit = _AuditResource(self._transport)
        self.keys = _KeysResource(self._transport)
        self.billing = _BillingResource(self._transport)
        self.admin = _AdminResource(self._transport)

    def health(self) -> HealthCheck:
        """Check API health."""
        data = self._transport.request("GET", "/api/v1/health")
        return HealthCheck.model_validate(data)

    @staticmethod
    def bootstrap(
        *,
        tenant_name: str,
        key_name: str = "default",
        base_url: str = _DEFAULT_BASE_URL,
    ) -> BootstrapResult:
        """Create a new tenant and first API key. No auth required.

        Returns the tenant ID and raw API key (shown only once).
        """
        import httpx

        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/v1/auth/bootstrap",
            json={"tenant_name": tenant_name, "key_name": key_name},
        )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"error": {"message": resp.text}}
            from smn_client._errors import raise_for_status
            raise_for_status(resp.status_code, body, resp.headers.get("x-request-id"))
        return BootstrapResult.model_validate(resp.json())

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._transport.close()

    def __enter__(self) -> SMNClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()


class AsyncSMNClient:
    """Async SMN API client.

    Example:
        async with AsyncSMNClient(api_key="smn_...") as client:
            agents = await client.agents.list()
            task = await client.tasks.create(agent_id=agents[0].id, input_text="Hello")
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._transport = _AsyncTransport(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.agents = _AsyncAgentsResource(self._transport)
        self.tasks = _AsyncTasksResource(self._transport)
        self.policies = _AsyncPoliciesResource(self._transport)
        self.audit = _AsyncAuditResource(self._transport)
        self.keys = _AsyncKeysResource(self._transport)
        self.billing = _AsyncBillingResource(self._transport)
        self.admin = _AsyncAdminResource(self._transport)

    async def health(self) -> HealthCheck:
        """Check API health."""
        data = await self._transport.request("GET", "/api/v1/health")
        return HealthCheck.model_validate(data)

    @staticmethod
    async def bootstrap(
        *,
        tenant_name: str,
        key_name: str = "default",
        base_url: str = _DEFAULT_BASE_URL,
    ) -> BootstrapResult:
        """Create a new tenant and first API key. No auth required."""
        import httpx

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{base_url.rstrip('/')}/api/v1/auth/bootstrap",
                json={"tenant_name": tenant_name, "key_name": key_name},
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"error": {"message": resp.text}}
            from smn_client._errors import raise_for_status
            raise_for_status(resp.status_code, body, resp.headers.get("x-request-id"))
        return BootstrapResult.model_validate(resp.json())

    async def close(self) -> None:
        """Close the underlying HTTP connection."""
        await self._transport.close()

    async def __aenter__(self) -> AsyncSMNClient:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
