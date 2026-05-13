"""Tests for output guardrails — PII detection, content policy, JSON validation."""

from __future__ import annotations

import pytest

from smn.core.guardrails import (
    ContentPolicy,
    GuardrailAction,
    GuardrailEngine,
    detect_pii,
    redact_pii,
    validate_json_output,
)


# ── PII detection ────────────────────────────────────────────────


class TestPIIDetection:
    def test_detect_email(self):
        found = detect_pii("Contact alice@example.com for help")
        assert "email" in found
        assert "alice@example.com" in found["email"]

    def test_detect_ssn(self):
        found = detect_pii("SSN: 123-45-6789")
        assert "ssn" in found

    def test_detect_credit_card(self):
        found = detect_pii("Card: 4111-1111-1111-1111")
        assert "credit_card" in found

    def test_detect_phone(self):
        found = detect_pii("Call (555) 123-4567")
        assert "phone_us" in found

    def test_no_pii(self):
        found = detect_pii("The weather is nice today")
        assert found == {}

    def test_redact_pii(self):
        text = "Email: alice@example.com, SSN: 123-45-6789"
        redacted, counts = redact_pii(text)
        assert "alice@example.com" not in redacted
        assert "123-45-6789" not in redacted
        assert "[REDACTED]" in redacted
        assert counts["email"] == 1
        assert counts["ssn"] == 1


# ── Content policy ───────────────────────────────────────────────


class TestContentPolicy:
    def test_clean_content_passes(self):
        policy = ContentPolicy()
        result = policy.check("Hello, world!")
        assert result.passed

    def test_max_length_blocks(self):
        policy = ContentPolicy(max_output_length=10)
        result = policy.check("x" * 20)
        assert not result.passed
        assert result.action == GuardrailAction.BLOCK

    def test_prohibited_pattern_blocks(self):
        policy = ContentPolicy()
        result = policy.check("password: s3cret123!")
        assert not result.passed
        assert result.action == GuardrailAction.BLOCK

    def test_private_key_blocked(self):
        policy = ContentPolicy()
        result = policy.check("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
        assert not result.passed


# ── JSON validation ──────────────────────────────────────────────


class TestJSONValidation:
    def test_valid_json(self):
        result = validate_json_output('{"key": "value"}')
        assert result.passed

    def test_invalid_json(self):
        result = validate_json_output("not json at all")
        assert not result.passed

    def test_schema_type_mismatch(self):
        result = validate_json_output("[1,2,3]", schema={"type": "object"})
        assert not result.passed
        assert "expected JSON object" in result.reason

    def test_schema_required_keys(self):
        result = validate_json_output(
            '{"name": "Alice"}',
            schema={"type": "object", "required": ["name", "age"]},
        )
        assert not result.passed
        assert "age" in result.reason

    def test_schema_passes(self):
        result = validate_json_output(
            '{"name": "Alice", "age": 30}',
            schema={"type": "object", "required": ["name", "age"]},
        )
        assert result.passed


# ── GuardrailEngine composite ────────────────────────────────────


class TestGuardrailEngine:
    def test_clean_content_passes(self):
        engine = GuardrailEngine()
        result = engine.check("Normal output text")
        assert result.passed

    def test_pii_redact_mode(self):
        engine = GuardrailEngine(pii_action=GuardrailAction.REDACT)
        result = engine.check("Email: bob@example.com")
        assert result.passed
        assert result.redacted_content is not None
        assert "bob@example.com" not in result.redacted_content

    def test_pii_block_mode(self):
        engine = GuardrailEngine(pii_action=GuardrailAction.BLOCK)
        result = engine.check("Email: bob@example.com")
        assert not result.passed
        assert result.action == GuardrailAction.BLOCK

    def test_content_policy_takes_priority(self):
        engine = GuardrailEngine()
        result = engine.check("password: hunter2")
        assert not result.passed
        assert result.action == GuardrailAction.BLOCK

    def test_json_schema_validation(self):
        engine = GuardrailEngine(
            json_schema={"type": "object", "required": ["result"]}
        )
        result = engine.check('{"result": "ok"}')
        assert result.passed

    def test_json_schema_failure(self):
        engine = GuardrailEngine(
            json_schema={"type": "object", "required": ["result"]}
        )
        result = engine.check('{"data": "wrong"}')
        assert not result.passed
