"""Example 1: Hello Agent — the simplest possible SMN agent.

Run:
    python examples/01_hello_agent.py

Requires: ANTHROPIC_API_KEY in your environment or .env file.
"""

import asyncio

import smn


# 1. Define a tool — just a decorated Python function.
@smn.tool(scopes=["math:read"])
async def add(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}


@smn.tool(scopes=["math:read"])
async def multiply(a: int, b: int) -> dict:
    """Multiply two numbers together."""
    return {"result": a * b}


# 2. Create an agent — one line of config.
agent = smn.Agent(
    name="calculator",
    description="A simple calculator that can add and multiply numbers.",
    tools=[add, multiply],
    risk_level="minimal",
    max_cost_per_task=0.50,
)


# 3. Run it.
async def main():
    print(f"Agent: {agent}")
    print()

    result = await agent.run("What is 42 * 17, then add 100 to the result?")

    print(f"Status: {result.status}")
    print(f"Output: {result.output}")
    print(f"Steps:  {result.steps}")
    print(f"Cost:   ${result.cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
