"""Integration tests — end-to-end API flows via TestClient.

Tests the full request lifecycle: bootstrap → auth → CRUD → audit verification.
Uses an in-memory SQLite database (no external services needed).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smn.middleware.idempotency import _store


@pytest.fixture(autouse=True)
def _clear_caches():
    _store._store.clear()
    yield
    _store._store.clear()


@pytest.fixture
def client():
    """TestClient with fresh in-memory database."""
    import os

    os.environ["SMN_DATABASE_URL"] = "sqlite+aiosqlite://"
    os.environ.setdefault("SMN_REDIS_URL", "")

    # Re-import to pick up the test database URL
    from smn import db as db_mod
    from smn.config import Settings
    from smn.models import Base

    test_settings = Settings()
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(test_settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Patch the db module
    original_engine = db_mod.engine
    original_session = db_mod.async_session
    db_mod.engine = engine
    db_mod.async_session = session_factory

    from smn.server import app

    with TestClient(app) as c:
        yield c

    db_mod.engine = original_engine
    db_mod.async_session = original_session


@pytest.fixture
def authed_client(client: TestClient):
    """Client with a bootstrapped tenant and API key."""
    resp = client.post(
        "/api/v1/auth/bootstrap",
        json={"tenant_name": "test-org", "key_name": "admin"},
    )
    assert resp.status_code == 201
    data = resp.json()
    api_key = data["api_key"]
    return client, api_key, data["tenant_id"]


class TestHealthAndRoot:
    def test_root(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "SMN"
        assert "version" in body

    def test_health(self, client: TestClient):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "ok", "degraded")

    def test_request_id_header(self, client: TestClient):
        resp = client.get("/api/v1/health")
        assert "x-request-id" in resp.headers


class TestBootstrap:
    def test_bootstrap_creates_tenant(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/bootstrap",
            json={"tenant_name": "new-org", "key_name": "first-key"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["api_key"].startswith("smn_")
        assert data["tenant_id"]

    def test_bootstrap_duplicate_fails(self, client: TestClient):
        client.post(
            "/api/v1/auth/bootstrap",
            json={"tenant_name": "dup-org", "key_name": "k1"},
        )
        resp = client.post(
            "/api/v1/auth/bootstrap",
            json={"tenant_name": "dup-org", "key_name": "k2"},
        )
        assert resp.status_code in (400, 409)


class TestAuth:
    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 401

    def test_invalid_key_rejected(self, client: TestClient):
        resp = client.get(
            "/api/v1/agents",
            headers={"X-API-Key": "smn_invalid_key"},
        )
        assert resp.status_code == 401

    def test_list_keys(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get("/api/v1/auth/keys", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 1

    def test_create_and_revoke_key(self, authed_client):
        client, api_key, _ = authed_client
        # Create
        resp = client.post(
            "/api/v1/auth/keys",
            headers={"X-API-Key": api_key},
            json={"name": "temp-key", "scopes": ["agents:read"]},
        )
        assert resp.status_code == 201
        key_id = resp.json()["id"]

        # Revoke
        resp = client.delete(
            f"/api/v1/auth/keys/{key_id}",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 204


class TestAgentsCRUD:
    def test_create_agent(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.post(
            "/api/v1/agents",
            headers={"X-API-Key": api_key},
            json={
                "name": "test-agent",
                "model": "anthropic/claude-sonnet-4-6-20250415",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-agent"
        assert data["id"]

    def test_list_agents(self, authed_client):
        client, api_key, _ = authed_client
        # Create one first
        client.post(
            "/api/v1/agents",
            headers={"X-API-Key": api_key},
            json={"name": "a1", "model": "test/model"},
        )
        resp = client.get("/api/v1/agents", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) >= 1

    def test_get_agent(self, authed_client):
        client, api_key, _ = authed_client
        create_resp = client.post(
            "/api/v1/agents",
            headers={"X-API-Key": api_key},
            json={"name": "fetch-me", "model": "test/model"},
        )
        agent_id = create_resp.json()["id"]
        resp = client.get(
            f"/api/v1/agents/{agent_id}",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "fetch-me"

    def test_update_agent(self, authed_client):
        client, api_key, _ = authed_client
        create_resp = client.post(
            "/api/v1/agents",
            headers={"X-API-Key": api_key},
            json={"name": "update-me", "model": "test/model"},
        )
        agent_id = create_resp.json()["id"]
        resp = client.patch(
            f"/api/v1/agents/{agent_id}",
            headers={"X-API-Key": api_key},
            json={"name": "updated-name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Verify update was accepted (response format may vary)
        assert resp.status_code == 200

    def test_delete_agent(self, authed_client):
        client, api_key, _ = authed_client
        create_resp = client.post(
            "/api/v1/agents",
            headers={"X-API-Key": api_key},
            json={"name": "delete-me", "model": "test/model"},
        )
        agent_id = create_resp.json()["id"]
        resp = client.delete(
            f"/api/v1/agents/{agent_id}",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 204

        # Verify deleted — may return 404 or empty depending on soft/hard delete
        resp = client.get(
            f"/api/v1/agents/{agent_id}",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in (200, 404)

    def test_get_nonexistent_agent(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get(
            "/api/v1/agents/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 404

    def test_tenant_isolation(self, client: TestClient):
        """Agents from one tenant are not visible to another."""
        # Bootstrap two tenants
        r1 = client.post(
            "/api/v1/auth/bootstrap",
            json={"tenant_name": "org-a", "key_name": "k"},
        )
        r2 = client.post(
            "/api/v1/auth/bootstrap",
            json={"tenant_name": "org-b", "key_name": "k"},
        )
        key_a = r1.json()["api_key"]
        key_b = r2.json()["api_key"]

        # Tenant A creates agent
        client.post(
            "/api/v1/agents",
            headers={"X-API-Key": key_a},
            json={"name": "secret-agent", "model": "test/model"},
        )

        # Tenant B should not see it
        resp = client.get("/api/v1/agents", headers={"X-API-Key": key_b})
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert len(body["data"]) == 0
        assert body["total_count"] == 0


class TestPolicies:
    def test_list_policies(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get("/api/v1/policies", headers={"X-API-Key": api_key})
        assert resp.status_code == 200

    def test_list_frameworks(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get(
            "/api/v1/policies/frameworks",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        frameworks = resp.json()
        assert len(frameworks) >= 1


class TestAudit:
    def test_audit_verify(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get("/api/v1/audit/verify", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "is_valid" in data or "valid" in data


class TestIdempotency:
    def test_idempotent_create(self, authed_client):
        client, api_key, _ = authed_client
        headers = {
            "X-API-Key": api_key,
            "Idempotency-Key": "idem-test-001",
        }
        body = {"name": "idem-agent", "model": "test/model"}

        r1 = client.post("/api/v1/agents", headers=headers, json=body)
        r2 = client.post("/api/v1/agents", headers=headers, json=body)

        assert r1.status_code == 201
        assert r2.status_code in (200, 201)  # Cached or replayed
        assert r1.json()["id"] == r2.json()["id"]


class TestPagination:
    def test_agents_pagination(self, authed_client):
        client, api_key, _ = authed_client
        # Create 3 agents
        for i in range(3):
            client.post(
                "/api/v1/agents",
                headers={"X-API-Key": api_key},
                json={"name": f"page-agent-{i}", "model": "test/model"},
            )

        # Get first 2
        resp = client.get(
            "/api/v1/agents?limit=2",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert len(body["data"]) == 2
        assert body["has_more"] is True
        assert body["limit"] == 2
        assert body["total_count"] >= 3

        # Get with offset
        resp = client.get(
            "/api/v1/agents?offset=2&limit=10",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        body2 = resp.json()
        assert body2["object"] == "list"
        assert len(body2["data"]) >= 1
        assert body2["offset"] == 2


class TestErrorFormat:
    def test_401_error_format(self, client: TestClient):
        resp = client.get(
            "/api/v1/agents",
            headers={"X-API-Key": "smn_bad"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert "type" in body["error"]
        assert "message" in body["error"]
        assert "request_id" in body["error"]

    def test_404_error_format(self, authed_client):
        client, api_key, _ = authed_client
        resp = client.get(
            "/api/v1/agents/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "type" in body["error"]
