# smn-client

Official Python SDK for the **SMN** (Secure Multi-agent Network) platform.

## Installation

```bash
pip install smn-client
```

## Quick Start

```python
from smn_client import SMNClient

# Bootstrap a new tenant (one-time setup)
result = SMNClient.bootstrap(tenant_name="Acme Corp")
print(result.api_key)  # smn_live_... (save this!)

# Connect
client = SMNClient(api_key=result.api_key)

# Create an agent
agent = client.agents.create(
    name="analyst",
    model="gpt-4o",
    risk_level="limited",
)

# Run a task
task = client.tasks.create(
    agent_id=agent.id,
    input_text="Summarise Q4 earnings report",
)
print(task.output_text)

# Stream a task
for event in client.tasks.stream(
    agent_id=agent.id,
    input_text="Analyse competitor pricing",
):
    print(f"{event.event}: {event.data}")
```

## Async Usage

```python
from smn_client import AsyncSMNClient

async with AsyncSMNClient(api_key="smn_...") as client:
    agents = await client.agents.list()
    task = await client.tasks.create(
        agent_id=agents[0].id,
        input_text="Hello",
    )
```

## Resources

| Resource          | Methods                                          |
|-------------------|--------------------------------------------------|
| `client.agents`   | `create`, `list`, `get`, `update`, `delete`      |
| `client.tasks`    | `create`, `list`, `get`, `stream`                |
| `client.policies` | `create`, `list`, `get`, `frameworks`            |
| `client.audit`    | `list`, `verify`                                 |
| `client.keys`     | `create`, `list`, `revoke`                       |
| `client.billing`  | `create_customer`, `subscribe`, `status`         |
| `client.admin`    | `tenants`, `update_tenant`, `health`, `usage`, `tenant_usage` |

## Error Handling

```python
from smn_client import SMNClient, AuthenticationError, RateLimitError

client = SMNClient(api_key="smn_...")

try:
    agent = client.agents.get("nonexistent")
except AuthenticationError:
    print("Bad API key")
except RateLimitError as e:
    print(f"Rate limited: {e.message}")
```

## License

MIT
