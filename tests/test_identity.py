"""Tests for identity and permission checks."""

import pytest

from smn.core.identity import Identity, check_permissions


class TestIdentity:
    def test_exact_scope_match(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset(["tickets:read"]))
        assert identity.has_scope("tickets:read") is True
        assert identity.has_scope("tickets:write") is False

    def test_wildcard_scope(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset(["*"]))
        assert identity.has_scope("anything:at:all") is True

    def test_prefix_wildcard(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset(["tickets:*"]))
        assert identity.has_scope("tickets:read") is True
        assert identity.has_scope("tickets:write") is True
        assert identity.has_scope("billing:read") is False

    def test_has_all_scopes(self):
        identity = Identity(
            agent_id="a1", tenant_id="t1",
            scopes=frozenset(["tickets:read", "billing:read"]),
        )
        assert identity.has_all_scopes(["tickets:read", "billing:read"]) is True
        assert identity.has_all_scopes(["tickets:read", "admin:write"]) is False

    def test_missing_scopes(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset(["tickets:read"]))
        missing = identity.missing_scopes(["tickets:read", "admin:write"])
        assert missing == ["admin:write"]


class TestPermissionCheck:
    def test_allowed(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset(["db:read"]))
        result = check_permissions(identity, ["db:read"])
        assert result.allowed is True

    def test_denied(self):
        identity = Identity(agent_id="a1", tenant_id="t1", scopes=frozenset([]))
        result = check_permissions(identity, ["db:read"])
        assert result.allowed is False
        assert "db:read" in result.missing_scopes
