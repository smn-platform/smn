"""Tests for request ID, idempotency, and error handler middleware."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from smn.api.errors import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    SMNAPIError,
    install_error_handlers,
)
from smn.middleware.idempotency import IdempotencyMiddleware, _store
from smn.middleware.request_id import RequestIdMiddleware


# ═══════════════════════════════════════════════════════════════════
#  Test fixtures
# ═══════════════════════════════════════════════════════════════════


def _create_app() -> FastAPI:
    """Create a minimal FastAPI app with all middleware installed."""
    app = FastAPI()

    # Middleware (outermost first)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RequestIdMiddleware)

    install_error_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.post("/create")
    async def create(request: Request):
        body = await request.json()
        return {"id": "new-1", "name": body.get("name", "")}

    @app.get("/fail/401")
    async def fail_401():
        raise AuthenticationError()

    @app.get("/fail/403")
    async def fail_403():
        raise AuthorizationError()

    @app.get("/fail/404")
    async def fail_404():
        raise NotFoundError("Agent", param="agent_id")

    @app.get("/fail/400")
    async def fail_400():
        raise BadRequestError("Agent is deactivated", code="agent_deactivated")

    @app.get("/fail/429")
    async def fail_429():
        raise RateLimitError()

    @app.get("/fail/500")
    async def fail_500():
        raise RuntimeError("Unexpected boom")

    class ValidationInput(BaseModel):
        name: str
        count: int

    @app.post("/validate")
    async def validate_input(body: ValidationInput):
        return {"name": body.name}

    return app


@pytest.fixture
def client():
    app = _create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_idempotency_cache():
    """Clear the idempotency cache between tests."""
    _store._store.clear()


# ═══════════════════════════════════════════════════════════════════
#  Request ID middleware tests
# ═══════════════════════════════════════════════════════════════════


class TestRequestIdMiddleware:
    def test_generates_request_id(self, client):
        resp = client.get("/ok")
        assert resp.status_code == 200
        req_id = resp.headers.get("x-request-id")
        assert req_id is not None
        assert req_id.startswith("req_")

    def test_echoes_client_request_id(self, client):
        resp = client.get("/ok", headers={"X-Request-Id": "my-custom-id"})
        assert resp.headers["x-request-id"] == "my-custom-id"

    def test_unique_ids_per_request(self, client):
        r1 = client.get("/ok")
        r2 = client.get("/ok")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    def test_request_id_in_error_response(self, client):
        resp = client.get("/fail/401")
        req_id = resp.headers.get("x-request-id")
        body = resp.json()
        assert req_id is not None
        assert body["error"]["request_id"] == req_id


# ═══════════════════════════════════════════════════════════════════
#  Idempotency middleware tests
# ═══════════════════════════════════════════════════════════════════


class TestIdempotencyMiddleware:
    def test_no_idempotency_key_passes_through(self, client):
        r1 = client.post("/create", json={"name": "first"})
        r2 = client.post("/create", json={"name": "second"})
        assert r1.json()["name"] == "first"
        assert r2.json()["name"] == "second"

    def test_same_key_returns_cached_response(self, client):
        headers = {"Idempotency-Key": "test-key-1"}
        r1 = client.post("/create", json={"name": "original"}, headers=headers)
        r2 = client.post("/create", json={"name": "different"}, headers=headers)
        assert r1.json() == r2.json()
        assert r2.headers.get("x-idempotent-replayed") == "true"

    def test_different_keys_execute_separately(self, client):
        r1 = client.post("/create", json={"name": "a"}, headers={"Idempotency-Key": "key-a"})
        r2 = client.post("/create", json={"name": "b"}, headers={"Idempotency-Key": "key-b"})
        assert r1.json()["name"] == "a"
        assert r2.json()["name"] == "b"

    def test_get_requests_bypass_idempotency(self, client):
        r1 = client.get("/ok", headers={"Idempotency-Key": "get-key"})
        r2 = client.get("/ok", headers={"Idempotency-Key": "get-key"})
        # GET requests should not be cached — no replay header
        assert r2.headers.get("x-idempotent-replayed") is None

    def test_idempotency_scoped_by_api_key(self, client):
        """Different API keys with same idempotency key should execute separately."""
        headers_a = {"Idempotency-Key": "shared-key", "X-API-Key": "smn_aaaa_key"}
        headers_b = {"Idempotency-Key": "shared-key", "X-API-Key": "smn_bbbb_key"}
        r1 = client.post("/create", json={"name": "tenant-a"}, headers=headers_a)
        r2 = client.post("/create", json={"name": "tenant-b"}, headers=headers_b)
        assert r1.json()["name"] == "tenant-a"
        assert r2.json()["name"] == "tenant-b"


# ═══════════════════════════════════════════════════════════════════
#  Error handler tests
# ═══════════════════════════════════════════════════════════════════


class TestErrorHandlers:
    def test_401_structured_response(self, client):
        resp = client.get("/fail/401")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "invalid_api_key"
        assert "request_id" in body["error"]

    def test_403_structured_response(self, client):
        resp = client.get("/fail/403")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["type"] == "authorization_error"
        assert body["error"]["code"] == "insufficient_scope"

    def test_404_structured_response(self, client):
        resp = client.get("/fail/404")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["code"] == "resource_not_found"
        assert body["error"]["param"] == "agent_id"
        assert "Agent not found" in body["error"]["message"]

    def test_400_structured_response(self, client):
        resp = client.get("/fail/400")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "agent_deactivated"

    def test_429_structured_response(self, client):
        resp = client.get("/fail/429")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["type"] == "rate_limit_error"

    def test_500_does_not_leak_stack_trace(self, client):
        # Need a client that doesn't raise server exceptions
        app = _create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/fail/500")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["type"] == "api_error"
        assert body["error"]["code"] == "internal_error"
        # Must NOT contain the actual exception message
        assert "Unexpected boom" not in body["error"]["message"]
        assert "retry later" in body["error"]["message"].lower()

    def test_422_validation_error(self, client):
        resp = client.post("/validate", json={"name": 123, "count": "not-int"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["code"] == "validation_error"

    def test_all_errors_have_request_id(self, client):
        """Every error response should include the request_id field."""
        for path in ["/fail/401", "/fail/403", "/fail/404", "/fail/400", "/fail/429"]:
            resp = client.get(path)
            body = resp.json()
            assert "request_id" in body["error"], f"Missing request_id in {path}"
        # 500 needs raise_server_exceptions=False
        app = _create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/fail/500")
            body = resp.json()
            assert "request_id" in body["error"], "Missing request_id in /fail/500"
