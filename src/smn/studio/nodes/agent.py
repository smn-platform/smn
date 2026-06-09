"""AgentNode — run a governed SMN Agent as a workflow step.

Config keys
-----------
input_template : str
    The task prompt, with ``{{...}}`` template variables resolved from context.
model : str
    LiteLLM model string.  Defaults to ``settings.default_model``.
policy_name : str
    Policy file to load.  Defaults to ``"default"``.
"""

from __future__ import annotations

import logging
from typing import Any

from smn.studio.nodes.base import BaseNode, NodeResult

logger = logging.getLogger(__name__)


class AgentNode(BaseNode):
    node_type = "agent"

    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        from smn import Agent
        from smn.core.runtime import execute_task

        input_text: str = self.resolve(config.get("input_template", ""), context)
        if not input_text:
            raise ValueError("AgentNode: input_template resolved to an empty string")

        model: str = config.get("model", "")
        policy_name: str = config.get("policy_name", "default")

        agent = Agent(
            name="studio-ephemeral",
            model=model or None,
            policy_name=policy_name,
        )

        result = await execute_task(agent, input_text)

        return NodeResult(
            output={
                "output": result.output,
                "status": result.status,
                "steps": result.steps,
                "cost_usd": result.cost_usd,
            }
        )
