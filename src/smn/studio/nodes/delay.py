"""DelayNode — pause workflow execution for a specified duration.

Config keys
-----------
seconds : float
    How long to wait.  Hard-capped at 300 s (5 min) regardless of config.
"""

from __future__ import annotations

import asyncio
from typing import Any

from smn.studio.nodes.base import BaseNode, NodeResult

_MAX_DELAY_S = 300.0  # 5 minutes — prevent runaway delays


class DelayNode(BaseNode):
    node_type = "delay"

    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        seconds = min(float(config.get("seconds", 1.0)), _MAX_DELAY_S)
        await asyncio.sleep(seconds)
        return NodeResult(output={"delayed_seconds": seconds})
