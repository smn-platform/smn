"""Base class for all Studio workflow nodes."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeResult:
    """Outcome of a single node execution.

    ``output`` is merged into the run context under the node's ID.
    ``handle`` determines which outgoing edges are followed — "output" for
    regular nodes, "true"/"false" for condition nodes.
    """

    output: dict[str, Any]
    handle: str = "output"


class BaseNode(ABC):
    """Abstract base for all workflow node types."""

    node_type: str = ""

    @abstractmethod
    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        """Run the node.

        Parameters
        ----------
        config:
            Node-specific configuration from the workflow definition.
        context:
            Accumulated outputs keyed by node ID, plus ``"trigger"`` for
            the trigger data that started the run.
        """
        ...

    # ── Template resolution ───────────────────────────────────────

    @staticmethod
    def resolve(value: Any, context: dict[str, Any]) -> Any:
        """Recursively resolve ``{{node_id.field}}`` templates in a value."""
        if isinstance(value, str):
            return BaseNode._resolve_str(value, context)
        if isinstance(value, dict):
            return {k: BaseNode.resolve(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [BaseNode.resolve(v, context) for v in value]
        return value

    @staticmethod
    def _resolve_str(template: str, context: dict[str, Any]) -> str:
        """Replace ``{{a.b.c}}`` paths with their values from context."""

        def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
            parts = match.group(1).strip().split(".")
            val: Any = context
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part, "")
                else:
                    return ""
            return str(val) if val is not None else ""

        return re.sub(r"\{\{([^}]+)\}\}", _replace, template)
