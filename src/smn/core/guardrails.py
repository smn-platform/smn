"""Output guardrails — validate, filter, and redact LLM outputs before delivery.

Provides layered content safety:
- PII detection and redaction (GDPR Art. 5, CCPA)
- Content policy enforcement (prohibited patterns)
- Structured output validation (JSON schema)
- Maximum length enforcement

Guardrails run after every LLM response and before tool results are returned.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailAction(str, Enum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of a guardrail check."""

    passed: bool
    action: GuardrailAction = GuardrailAction.WARN
    reason: str = ""
    redacted_content: str | None = None


# ── PII patterns ─────────────────────────────────────────────────

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
}

_PII_REDACTION = "[REDACTED]"


def detect_pii(text: str) -> dict[str, list[str]]:
    """Scan text for PII patterns. Returns {type: [matches]}."""
    found: dict[str, list[str]] = {}
    for pii_type, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            found[pii_type] = matches
    return found


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Replace all detected PII with redaction markers.

    Returns (redacted_text, {type: count}).
    """
    counts: dict[str, int] = {}
    result = text
    for pii_type, pattern in _PII_PATTERNS.items():
        new_result, n = pattern.subn(_PII_REDACTION, result)
        if n > 0:
            counts[pii_type] = n
            result = new_result
    return result, counts


# ── Content policy ───────────────────────────────────────────────

_DEFAULT_PROHIBITED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(?:password|secret[_\s]?key|api[_\s]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY)"),
]


@dataclass
class ContentPolicy:
    """Configurable content filter for LLM outputs."""

    prohibited_patterns: list[re.Pattern[str]] = field(
        default_factory=lambda: list(_DEFAULT_PROHIBITED_PATTERNS)
    )
    max_output_length: int = 50_000  # characters

    def check(self, content: str) -> GuardrailResult:
        """Check content against all content policy rules."""
        if len(content) > self.max_output_length:
            return GuardrailResult(
                passed=False,
                action=GuardrailAction.BLOCK,
                reason=f"output exceeds max length ({len(content)} > {self.max_output_length})",
            )
        for pattern in self.prohibited_patterns:
            match = pattern.search(content)
            if match:
                return GuardrailResult(
                    passed=False,
                    action=GuardrailAction.BLOCK,
                    reason=f"prohibited content detected: {pattern.pattern[:60]}",
                )
        return GuardrailResult(passed=True)


# ── Structured output validation ─────────────────────────────────


def validate_json_output(content: str, schema: dict[str, Any] | None = None) -> GuardrailResult:
    """Validate that content is valid JSON, optionally against a schema.

    Performs basic type/key validation without requiring jsonschema dependency.
    """
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        return GuardrailResult(
            passed=False,
            action=GuardrailAction.BLOCK,
            reason=f"invalid JSON: {e}",
        )
    if schema is None:
        return GuardrailResult(passed=True)

    # Basic schema validation (type + required keys)
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(parsed, dict):
        return GuardrailResult(
            passed=False,
            action=GuardrailAction.BLOCK,
            reason=f"expected JSON object, got {type(parsed).__name__}",
        )
    if expected_type == "array" and not isinstance(parsed, list):
        return GuardrailResult(
            passed=False,
            action=GuardrailAction.BLOCK,
            reason=f"expected JSON array, got {type(parsed).__name__}",
        )
    required = schema.get("required", [])
    if isinstance(parsed, dict) and required:
        missing = [k for k in required if k not in parsed]
        if missing:
            return GuardrailResult(
                passed=False,
                action=GuardrailAction.BLOCK,
                reason=f"missing required keys: {missing}",
            )
    return GuardrailResult(passed=True)


# ── Guardrail engine ─────────────────────────────────────────────


@dataclass
class GuardrailEngine:
    """Composite guardrail that runs multiple checks.

    Configure via:
    - ``pii_action``: what to do when PII is detected (block, redact, warn)
    - ``content_policy``: content filter rules
    - ``json_schema``: optional JSON schema for structured output
    """

    pii_action: GuardrailAction = GuardrailAction.REDACT
    content_policy: ContentPolicy = field(default_factory=ContentPolicy)
    json_schema: dict[str, Any] | None = None

    def check(self, content: str) -> GuardrailResult:
        """Run all guardrails on content. Returns first failure or pass."""
        # 1. Content policy (length, prohibited patterns)
        policy_result = self.content_policy.check(content)
        if not policy_result.passed:
            logger.warning("content policy violation: %s", policy_result.reason)
            return policy_result

        # 2. PII detection
        pii_found = detect_pii(content)
        if pii_found:
            if self.pii_action == GuardrailAction.BLOCK:
                return GuardrailResult(
                    passed=False,
                    action=GuardrailAction.BLOCK,
                    reason=f"PII detected: {list(pii_found.keys())}",
                )
            if self.pii_action == GuardrailAction.REDACT:
                redacted, counts = redact_pii(content)
                logger.info("PII redacted: %s", counts)
                return GuardrailResult(
                    passed=True,
                    action=GuardrailAction.REDACT,
                    reason=f"PII redacted: {counts}",
                    redacted_content=redacted,
                )
            # WARN: pass through but log
            logger.warning("PII detected (warn mode): %s", list(pii_found.keys()))

        # 3. JSON schema validation (if configured)
        if self.json_schema is not None:
            json_result = validate_json_output(content, self.json_schema)
            if not json_result.passed:
                return json_result

        return GuardrailResult(passed=True)
