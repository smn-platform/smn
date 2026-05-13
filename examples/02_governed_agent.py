"""Example 2: Governed Agent — policy enforcement and compliance checking.

Demonstrates:
- EU AI Act policy with prohibited practices
- Compliance scoring
- Human-in-the-loop approval for sensitive actions
- Full audit trail

Run:
    python examples/02_governed_agent.py
"""

import asyncio

import smn
from smn.core.policy import load_policy
from smn.governance.checks import check_compliance


# ── Define tools with varying risk levels ────────────────────────


@smn.tool(scopes=["tickets:read"])
async def search_tickets(query: str) -> list:
    """Search support tickets by keyword."""
    # Simulated response
    return [
        {"id": "T-001", "subject": "Login issues", "priority": "P1"},
        {"id": "T-002", "subject": "Payment failed", "priority": "P2"},
    ]


@smn.tool(scopes=["tickets:read"])
async def get_ticket(ticket_id: str) -> dict:
    """Get a single ticket by ID."""
    return {"id": ticket_id, "subject": "Login issues", "status": "open", "priority": "P1"}


@smn.tool(scopes=["tickets:write"], requires_approval=True, cost_estimate_usd=0.01)
async def close_ticket(ticket_id: str, resolution: str) -> dict:
    """Close a ticket with a resolution note. Requires human approval."""
    return {"id": ticket_id, "status": "closed", "resolution": resolution}


# ── Approval callback ────────────────────────────────────────────


async def cli_approval(action: str, detail: dict) -> bool:
    """Simple CLI-based approval prompt."""
    print(f"\n{'='*50}")
    print(f"🔐 APPROVAL REQUIRED")
    print(f"   Action: {action}")
    print(f"   Detail: {detail}")
    response = input("   Approve? [y/N]: ").strip().lower()
    print(f"{'='*50}\n")
    return response == "y"


# ── Main ─────────────────────────────────────────────────────────


async def main():
    # Load the EU AI Act policy
    policy = load_policy("eu_ai_act")

    # Create a governed agent
    agent = smn.Agent(
        name="support-agent",
        description="Handles customer support tickets with full governance.",
        tools=[search_tickets, get_ticket, close_ticket],
        risk_level="limited",
        policy=policy,
        max_cost_per_task=1.00,
    )

    # Run compliance check BEFORE deploying
    print("=" * 60)
    print("COMPLIANCE CHECK")
    print("=" * 60)
    report = check_compliance(agent, frameworks=["eu-ai-act", "nist-ai-rmf"])
    print(f"Agent:  {report.agent_name}")
    print(f"Risk:   {report.risk_level}")
    print(f"Score:  {report.score:.0%}")
    print()
    for item in report.items:
        icon = {"pass": "✅", "fail": "❌", "warning": "⚠️", "not_applicable": "➖"}.get(
            item.status, "?"
        )
        print(f"  {icon} [{item.framework}] {item.requirement_name}: {item.message}")
    print()

    # Run the agent with approval callback
    print("=" * 60)
    print("RUNNING AGENT TASK")
    print("=" * 60)
    result = await agent.run(
        "Find all P1 tickets and close them with resolution 'Resolved via automation'",
        approval_callback=cli_approval,
    )
    print(f"\nStatus: {result.status}")
    print(f"Output: {result.output}")
    print(f"Steps:  {result.steps}")
    print(f"Cost:   ${result.cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
