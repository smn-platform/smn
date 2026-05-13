"""Identity and permission management for agents.

Every agent receives a scoped identity that controls what tools and resources
it may access.  Permissions follow the ``resource:action`` convention
(e.g. ``tickets:read``, ``db:write``).

This implements the principle of least privilege required by:
- EU AI Act Art. 9 (risk management) and Art. 15 (accuracy/robustness)
- NIST AI RMF GOVERN-1.2 (processes for risk management)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Identity:
    """An agent's identity and permission boundary."""

    agent_id: str
    tenant_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)

    # ── Permission checks ─────────────────────────────────────────

    def has_scope(self, required: str) -> bool:
        """Check if this identity holds a specific scope.

        Supports wildcard: ``"*"`` grants everything.
        Supports prefix wildcard: ``"tickets:*"`` grants all ticket actions.
        """
        if "*" in self.scopes:
            return True
        if required in self.scopes:
            return True
        # Check prefix wildcard  e.g. "tickets:*" covers "tickets:read"
        resource = required.split(":")[0]
        return f"{resource}:*" in self.scopes

    def has_all_scopes(self, required: list[str]) -> bool:
        return all(self.has_scope(s) for s in required)

    def missing_scopes(self, required: list[str]) -> list[str]:
        return [s for s in required if not self.has_scope(s)]


@dataclass
class PermissionCheckResult:
    """Outcome of a permission check."""

    allowed: bool
    missing_scopes: list[str] = field(default_factory=list)
    reason: str = ""


def check_permissions(identity: Identity, required_scopes: list[str]) -> PermissionCheckResult:
    """Evaluate whether an identity may perform an action requiring the given scopes."""
    missing = identity.missing_scopes(required_scopes)
    if not missing:
        return PermissionCheckResult(allowed=True, reason="all scopes satisfied")
    return PermissionCheckResult(
        allowed=False,
        missing_scopes=missing,
        reason=f"missing scopes: {', '.join(missing)}",
    )
