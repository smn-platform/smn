"""SMN — Secure Multi-agent Network.

Deploy, govern, and scale AI agents safely.

Usage:
    import smn

    @smn.tool(scopes=["tickets:read"])
    async def get_ticket(ticket_id: str) -> dict:
        return {"id": ticket_id, "status": "open"}

    agent = smn.Agent(
        name="support-bot",
        tools=[get_ticket],
        risk_level="limited",
    )

    result = await agent.run("Resolve ticket #1234")
"""

from smn.core.agent import Agent
from smn.core.guardrails import GuardrailEngine
from smn.core.memory import PersistentMemory, SessionMemory
from smn.core.orchestrator import AgentGraph
from smn.core.policy import Policy
from smn.core.tools import tool

__all__ = [
    "Agent",
    "AgentGraph",
    "GuardrailEngine",
    "Policy",
    "PersistentMemory",
    "SessionMemory",
    "tool",
]
__version__ = "0.1.0"
