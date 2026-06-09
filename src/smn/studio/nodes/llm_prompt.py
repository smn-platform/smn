"""LLMPromptNode — raw LLM call with configurable system + user message templates.

Config keys
-----------
model : str
    LiteLLM model string.  Defaults to ``settings.default_model``.
system_prompt : str
    Optional system message.  Supports ``{{...}}`` templates.
user_message : str
    User message.  Required.  Supports ``{{...}}`` templates.
"""

from __future__ import annotations

from typing import Any

from smn.studio.nodes.base import BaseNode, NodeResult


class LLMPromptNode(BaseNode):
    node_type = "llm_prompt"

    async def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        from smn.config import settings
        from smn.connectors.llm import reliable_completion

        model: str = config.get("model", "") or settings.default_model
        system_prompt: str = self.resolve(config.get("system_prompt", ""), context)
        user_message: str = self.resolve(config.get("user_message", ""), context)

        if not user_message:
            raise ValueError("LLMPromptNode: user_message resolved to an empty string")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        response = await reliable_completion(model=model, messages=messages)
        content: str = response.choices[0].message.content or ""

        return NodeResult(output={"output": content, "model": model})
