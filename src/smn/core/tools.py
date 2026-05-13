"""Tool registration and mesh — the decorator-based system for exposing
functions as governed, auditable agent capabilities.

Usage:
    from smn import tool

    @tool(scopes=["tickets:read"])
    async def get_ticket(ticket_id: str) -> dict:
        '''Fetch a support ticket by ID.'''
        return {"id": ticket_id, "status": "open"}

    @tool(scopes=["tickets:write"], requires_approval=True)
    async def close_ticket(ticket_id: str, resolution: str) -> dict:
        '''Close a ticket with a resolution note.'''
        return {"id": ticket_id, "status": "closed"}
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Sequence, get_type_hints


@dataclass(frozen=True)
class ToolSpec:
    """Metadata for a registered tool."""

    name: str
    description: str
    func: Callable
    parameters: dict[str, dict[str, Any]]
    scopes: tuple[str, ...]
    requires_approval: bool = False
    cost_estimate_usd: float = 0.0


# ── Python type → JSON Schema type mapping ───────────────────────

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json(annotation: Any) -> str:
    """Best-effort mapping from a Python annotation to a JSON Schema type."""
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    return _TYPE_MAP.get(annotation, "string")


# ── Decorator ─────────────────────────────────────────────────────


def tool(
    *,
    scopes: Sequence[str] = (),
    requires_approval: bool = False,
    cost_estimate_usd: float = 0.0,
    name: str | None = None,
    description: str | None = None,
) -> Callable:
    """Register a function as a governed agent tool.

    Parameters
    ----------
    scopes
        Permission scopes required to invoke this tool (e.g. ``["db:read"]``).
    requires_approval
        If ``True``, execution pauses for human approval before running.
    cost_estimate_usd
        Estimated cost per invocation (used by FinOps budget checks).
    name
        Override the tool name (defaults to function name).
    description
        Override the tool description (defaults to docstring).
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        params: dict[str, dict[str, Any]] = {}
        for pname, param in sig.parameters.items():
            ann = hints.get(pname, str)
            params[pname] = {
                "type": _python_type_to_json(ann),
                "required": param.default is inspect.Parameter.empty,
            }

        spec = ToolSpec(
            name=name or func.__name__,
            description=(description or func.__doc__ or "").strip(),
            func=func,
            parameters=params,
            scopes=tuple(scopes),
            requires_approval=requires_approval,
            cost_estimate_usd=cost_estimate_usd,
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        wrapper._tool_spec = spec  # type: ignore[attr-defined]
        return wrapper

    return decorator


def get_tool_spec(func: Callable) -> ToolSpec | None:
    """Retrieve the ToolSpec attached to a decorated function."""
    return getattr(func, "_tool_spec", None)


def tools_to_openai_schema(tools: Sequence[Callable]) -> list[dict[str, Any]]:
    """Convert decorated tool functions into OpenAI-compatible function schemas.

    This is the format consumed by litellm and every major LLM provider.
    """
    schemas: list[dict[str, Any]] = []
    for t in tools:
        spec = get_tool_spec(t)
        if spec is None:
            continue
        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, pinfo in spec.parameters.items():
            properties[pname] = {"type": pinfo["type"]}
            if pinfo["required"]:
                required.append(pname)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return schemas
