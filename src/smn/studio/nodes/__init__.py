"""Node registry — maps node type strings to their implementation classes."""

from smn.studio.nodes.agent import AgentNode
from smn.studio.nodes.base import BaseNode, NodeResult
from smn.studio.nodes.condition import ConditionNode
from smn.studio.nodes.delay import DelayNode
from smn.studio.nodes.http import HTTPNode
from smn.studio.nodes.llm_prompt import LLMPromptNode

NODE_REGISTRY: dict[str, type[BaseNode]] = {
    "agent": AgentNode,
    "llm_prompt": LLMPromptNode,
    "http": HTTPNode,
    "condition": ConditionNode,
    "delay": DelayNode,
}

__all__ = [
    "NODE_REGISTRY",
    "BaseNode",
    "NodeResult",
    "AgentNode",
    "LLMPromptNode",
    "HTTPNode",
    "ConditionNode",
    "DelayNode",
]
