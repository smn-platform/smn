"""Example 3: Multi-Agent Orchestration — agents delegating to sub-agents.

Demonstrates:
- A coordinator agent that delegates to specialist agents
- Each agent has its own identity, permissions, and budget
- The coordinator can only invoke agents it has permission to use

Run:
    python examples/03_multi_agent.py
"""

import asyncio

import smn


# ── Specialist tools ─────────────────────────────────────────────


@smn.tool(scopes=["tickets:read", "tickets:write"])
async def handle_support_ticket(ticket_id: str, action: str) -> dict:
    """Process a support ticket (read, update, close)."""
    return {"ticket_id": ticket_id, "action": action, "status": "done"}


@smn.tool(scopes=["billing:read"])
async def check_billing(customer_id: str) -> dict:
    """Check a customer's billing status."""
    return {"customer_id": customer_id, "balance": 142.50, "status": "current"}


@smn.tool(scopes=["knowledge:read"])
async def search_knowledge_base(query: str) -> list:
    """Search the internal knowledge base."""
    return [
        {"title": "Password Reset Guide", "relevance": 0.95},
        {"title": "Account Recovery Process", "relevance": 0.87},
    ]


# ── Create specialist agents ────────────────────────────────────


support_agent = smn.Agent(
    name="support-specialist",
    description="Handles ticket triage and resolution.",
    tools=[handle_support_ticket, search_knowledge_base],
    risk_level="limited",
    max_cost_per_task=1.00,
)

billing_agent = smn.Agent(
    name="billing-specialist",
    description="Handles billing inquiries and account checks.",
    tools=[check_billing],
    risk_level="limited",
    max_cost_per_task=0.50,
)


# ── Coordinator ──────────────────────────────────────────────────


@smn.tool(scopes=["agents:invoke"])
async def delegate_to_support(task_description: str) -> dict:
    """Delegate a task to the support specialist agent."""
    result = await support_agent.run(task_description)
    return {"agent": "support-specialist", "status": result.status, "output": result.output}


@smn.tool(scopes=["agents:invoke"])
async def delegate_to_billing(task_description: str) -> dict:
    """Delegate a task to the billing specialist agent."""
    result = await billing_agent.run(task_description)
    return {"agent": "billing-specialist", "status": result.status, "output": result.output}


coordinator = smn.Agent(
    name="coordinator",
    description=(
        "Routes customer requests to the appropriate specialist agent. "
        "Can delegate to support-specialist and billing-specialist."
    ),
    tools=[delegate_to_support, delegate_to_billing],
    risk_level="limited",
    max_cost_per_task=3.00,
)


# ── Main ─────────────────────────────────────────────────────────


async def main():
    print(f"Coordinator: {coordinator}")
    print(f"Support:     {support_agent}")
    print(f"Billing:     {billing_agent}")
    print()

    result = await coordinator.run(
        "A customer (ID: C-456) is asking about their billing status and also "
        "has a support ticket T-789 about login issues. Handle both."
    )

    print(f"Status: {result.status}")
    print(f"Output: {result.output}")
    print(f"Steps:  {result.steps}")
    print(f"Cost:   ${result.cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
