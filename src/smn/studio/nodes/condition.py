"""ConditionNode — branch the workflow based on a simple comparison.

Config keys
-----------
left : str
    Left-hand value.  Supports ``{{...}}`` templates.
op : str
    Operator.  One of: ``==``, ``!=``, ``>``, ``>=``, ``<``, ``<=``,
    ``contains``, ``startswith``, ``endswith``.
right : str
    Right-hand value.  Supports ``{{...}}`` templates.

Output handle is ``"true"`` or ``"false"`` — only edges matching the result
are followed.
"""

from __future__ import annotations

import operator
from typing import Any, Callable

from smn.studio.nodes.base import BaseNode, NodeResult

_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "contains": lambda a, b: str(b) in str(a),
    "startswith": lambda a, b: str(a).startswith(str(b)),
    "endswith": lambda a, b: str(a).endswith(str(b)),
}


class ConditionNode(BaseNode):
    node_type = "condition"

    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        left_raw: str = self.resolve(config.get("left", ""), context)
        right_raw: str = self.resolve(config.get("right", ""), context)
        op_str: str = config.get("op", "==")

        op_fn = _OPS.get(op_str)
        if op_fn is None:
            raise ValueError(
                f"ConditionNode: unknown operator '{op_str}'. "
                f"Allowed: {', '.join(_OPS)}"
            )

        left: Any = left_raw
        right: Any = right_raw

        # Numeric coercion for ordering comparisons
        if op_str in (">", ">=", "<", "<="):
            try:
                left = float(left_raw)
                right = float(right_raw)
            except (ValueError, TypeError):
                pass  # fall back to string comparison

        result = bool(op_fn(left, right))

        return NodeResult(
            output={
                "result": result,
                "left": str(left_raw),
                "op": op_str,
                "right": str(right_raw),
            },
            handle="true" if result else "false",
        )
