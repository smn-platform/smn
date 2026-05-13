# @smn/sdk

Official TypeScript SDK for the [SMN](https://leylabs.dev) (Secure Multi-agent Network) platform.

- Zero dependencies — uses native `fetch`
- Full TypeScript types
- SSE streaming support
- Node.js 18+, Deno, Bun, edge runtimes

## Install

```bash
npm install @smn/sdk
```

## Quick Start

```typescript
import { SMNClient } from "@smn/sdk";

const smn = new SMNClient({
  baseUrl: "http://localhost:8000",
  apiKey: "smn_...",
});

// Create an agent
const agent = await smn.agents.create({
  name: "calc",
  model: "anthropic/claude-sonnet-4-6-20250415",
});

// Run a task
const task = await smn.tasks.create({
  agent_id: agent.id,
  input_text: "What is 2 + 2?",
});

console.log(task.output);
```

## Bootstrap

Create a new tenant (no API key required):

```typescript
const result = await SMNClient.bootstrap("http://localhost:8000", {
  tenant_name: "my-org",
  key_name: "admin",
});
console.log(result.api_key); // smn_... (save this)
```

## Streaming

Stream task execution via Server-Sent Events:

```typescript
const stream = smn.tasks.stream({
  agent_id: "my-agent",
  input_text: "Summarise Q4 results",
});

for await (const event of stream) {
  console.log(`${event.event}: ${JSON.stringify(event.data)}`);
}
```

## API Reference

### `SMNClient`

```typescript
const smn = new SMNClient({ baseUrl, apiKey });
```

#### Resources

| Resource | Methods |
|----------|---------|
| `smn.agents` | `create()`, `list()`, `get(id)`, `update(id, data)`, `delete(id)` |
| `smn.tasks` | `create()`, `list()`, `get(id)`, `stream()` |
| `smn.policies` | `create()`, `list()`, `get(id)`, `frameworks()` |
| `smn.audit` | `list()`, `verify()` |
| `smn.keys` | `create()`, `list()`, `revoke(id)` |
| `smn.billing` | `createCustomer()`, `subscribe()`, `status()` |
| `smn.admin` | `tenants()`, `updateTenant()`, `health()`, `usage()`, `tenantUsage(id)` |

### Error Handling

```typescript
import { SMNClient, AuthenticationError, RateLimitError } from "@smn/sdk";

try {
  await smn.agents.list();
} catch (e) {
  if (e instanceof RateLimitError) {
    // Back off and retry
  }
  if (e instanceof AuthenticationError) {
    // Invalid or expired API key
  }
}
```

Error classes: `AuthenticationError`, `AuthorizationError`, `NotFoundError`, `BadRequestError`, `RateLimitError`, `APIError`.

All errors include `status`, `message`, `requestId`, and optional `detail`.

### Idempotency

Pass an idempotency key for safe retries on mutating operations:

```typescript
const agent = await smn.agents.create(
  { name: "calc", model: "anthropic/claude-sonnet-4-6-20250415" },
  "unique-request-id-123"
);
```

## License

MIT — [Ley Labs Ltd](https://leylabs.dev)
