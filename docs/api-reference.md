# SMN API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints (except health and bootstrap) require `X-API-Key` header.
All responses include `X-Request-ID` header.

---

## Health

### `GET /health`

No auth required. Returns system health.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-04-19T12:00:00Z",
  "database": "ok",
  "redis": "ok"
}
```

---

## Authentication

### `POST /auth/bootstrap`

Create a tenant and first API key. No auth required. One-time operation per tenant name.

**Request:**
```json
{
  "tenant_name": "my-org",
  "key_name": "admin"
}
```

**Response (201):**
```json
{
  "tenant_id": "uuid",
  "api_key": "smn_...",
  "key_id": "uuid",
  "message": "Save this key — it will not be shown again."
}
```

### `POST /auth/keys`

Create an additional API key.

**Request:**
```json
{
  "name": "ci-pipeline",
  "scopes": ["agents:read", "tasks:write"]
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "ci-pipeline",
  "api_key": "smn_...",
  "scopes": ["agents:read", "tasks:write"],
  "created_at": "2026-04-19T12:00:00Z"
}
```

### `GET /auth/keys`

List all API keys for the authenticated tenant. Keys are returned without the secret.

### `DELETE /auth/keys/{key_id}`

Revoke an API key. Returns 204 on success.

---

## Agents

### `POST /agents`

Register a new agent.

**Request:**
```json
{
  "name": "calc",
  "model": "anthropic/claude-sonnet-4-6-20250415",
  "system_prompt": "You are a calculator.",
  "risk_level": "minimal",
  "policy_name": "default",
  "scopes": ["math:read"]
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "calc",
  "model": "anthropic/claude-sonnet-4-6-20250415",
  "risk_level": "minimal",
  "status": "active",
  "created_at": "2026-04-19T12:00:00Z"
}
```

### `GET /agents`

List agents. Supports `?skip=0&limit=20`.

### `GET /agents/{agent_id}`

Get a single agent by ID.

### `PATCH /agents/{agent_id}`

Update agent fields (name, model, system_prompt, risk_level, status).

### `DELETE /agents/{agent_id}`

Delete an agent. Returns 204.

---

## Tasks

### `POST /tasks`

Run a task synchronously or asynchronously.

**Request:**
```json
{
  "agent_id": "uuid",
  "input_text": "What is 2 + 2?",
  "async": false
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "status": "completed",
  "input_text": "What is 2 + 2?",
  "output": "4",
  "steps": 1,
  "cost_usd": 0.001,
  "created_at": "2026-04-19T12:00:00Z",
  "completed_at": "2026-04-19T12:00:01Z"
}
```

### `GET /tasks`

List tasks. Supports `?skip=0&limit=20`.

### `GET /tasks/{task_id}`

Get a single task by ID.

---

## Streaming

### `POST /stream`

Stream task execution via Server-Sent Events.

**Request:** Same as `POST /tasks`.

**Response:** `text/event-stream` with events:

| Event | Description |
|-------|-------------|
| `task_start` | Task accepted |
| `step_start` | New reasoning step |
| `tool_call` | Agent invokes a tool |
| `tool_result` | Tool execution result |
| `tool_denied` | Policy denied a tool call |
| `final_answer` | Agent produced output |
| `task_complete` | Task finished |
| `task_error` | Task failed |

---

## Policies

### `POST /policies`

Create or update a policy from YAML.

**Request:**
```json
{
  "name": "production",
  "yaml_content": "name: production\nrisk_level: limited\nrules: ..."
}
```

### `GET /policies`

List all policies.

### `GET /policies/{policy_id}`

Get a single policy.

### `GET /policies/frameworks`

List available regulatory frameworks (EU AI Act, NIST AI RMF).

---

## Audit

### `GET /audit`

Query the audit log. Supports `?skip=0&limit=50`.

### `GET /audit/verify`

Verify the integrity of the hash-chained audit log.

**Response:**
```json
{
  "valid": true,
  "entries_checked": 142,
  "first_entry": "2026-04-01T00:00:00Z",
  "last_entry": "2026-04-19T12:00:00Z"
}
```

---

## Billing (Pro)

### `POST /billing/customer`

Create a Stripe customer for the tenant.

### `POST /billing/subscribe`

Create a subscription. Request includes `price_id`.

### `GET /billing/status`

Get current billing status (plan, usage, next invoice).

### `POST /billing/webhook`

Stripe webhook endpoint. Authenticated via Stripe signature header.

---

## Admin (Pro)

### `GET /admin/tenants`

List all tenants with stats.

### `PATCH /admin/tenants/{tenant_id}`

Update tenant settings (plan, limits).

### `GET /admin/health`

System-wide health stats (DB connections, queue depth, memory).

### `GET /admin/usage`

Aggregate usage across all tenants.

### `GET /admin/usage/{tenant_id}`

Usage breakdown for a specific tenant.

---

## Error Responses

All errors follow a consistent format:

```json
{
  "error": {
    "type": "not_found",
    "message": "Agent not found.",
    "request_id": "req_abc123",
    "detail": {}
  }
}
```

| Status | Type | Description |
|--------|------|-------------|
| 400 | `bad_request` | Invalid input |
| 401 | `authentication_error` | Missing or invalid API key |
| 403 | `authorization_error` | Insufficient permissions |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | Duplicate resource or idempotency conflict |
| 422 | `validation_error` | Request body validation failed |
| 429 | `rate_limit_exceeded` | Too many requests |
| 500 | `internal_error` | Server error |

---

## Idempotency

Mutating endpoints (`POST`, `PATCH`, `DELETE`) accept an `Idempotency-Key` header. If provided, the server guarantees at-most-once execution for that key within 24 hours.

```bash
curl -X POST /api/v1/agents \
  -H "X-API-Key: smn_..." \
  -H "Idempotency-Key: unique-id-123" \
  -d '{"name": "calc", "model": "anthropic/claude-sonnet-4-6-20250415"}'
```

---

## Pagination

List endpoints support `skip` and `limit` query parameters:

```
GET /api/v1/agents?skip=0&limit=20
```

Default: `skip=0`, `limit=20`. Maximum `limit=100`.

---

## Rate Limiting (Pro)

Pro deployments enforce per-tenant rate limits via Redis. Headers returned:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Requests allowed per window |
| `X-RateLimit-Remaining` | Requests remaining |
| `X-RateLimit-Reset` | Window reset time (Unix epoch) |
