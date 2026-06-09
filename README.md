# SMN — Secure Multi-agent Network

[![CI](https://github.com/smn-platform/smn/actions/workflows/ci.yml/badge.svg)](https://github.com/smn-platform/smn/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/smn.svg)](https://pypi.org/project/smn/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT (Community)](https://img.shields.io/badge/License-MIT%20%28Community%29-green.svg)](LICENSE)

**Deploy, govern, and scale AI agents safely.**

SMN is the neutral control and execution layer for production AI agent systems. It wraps every agent action in identity checks, policy enforcement, cost controls, output guardrails, and an immutable audit trail — so you can move from pilot to governed production.

Built by [Ley Labs](https://leylabs.dev) · GitHub: [@smn-platform](https://github.com/smn-platform). Open-core: Community features are MIT-licensed. Pro features require a commercial license.

---

## Quickstart

```bash
# 1. Install
pip install smn

# 2. Initialize project
smn init

# 3. Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# 4. Start the server
smn serve

# 5. Bootstrap your tenant and get an API key
curl -X POST http://localhost:8000/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"tenant_name": "my-org", "key_name": "dev"}'
# → Returns your API key (smn_...). Save it — it won't be shown again.

# 6. Run an agent
curl -X POST http://localhost:8000/api/v1/agents \
  -H "X-API-Key: smn_..." \
  -H "Content-Type: application/json" \
  -d '{"name": "calc", "model": "anthropic/claude-sonnet-4-6-20250415"}'
```

## Five-line agent

```python
import smn

@smn.tool(scopes=["math:read"])
async def add(a: int, b: int) -> dict:
    """Add two numbers."""
    return {"result": a + b}

agent = smn.Agent(name="calc", tools=[add])
result = await agent.run("What is 2 + 2?")
print(result.output)
```

That's it. Identity, policy, cost tracking, guardrails, and audit logging happen automatically.

---

## Authentication

All API endpoints require an API key passed via the `X-API-Key` header (except bootstrap and health).

```bash
# Bootstrap creates a tenant and returns its first API key
curl -X POST http://localhost:8000/api/v1/auth/bootstrap \
  -d '{"tenant_name": "acme", "key_name": "admin"}'

# Use the returned key for all subsequent requests
curl http://localhost:8000/api/v1/agents \
  -H "X-API-Key: smn_..."

# Create additional keys
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: smn_..." \
  -d '{"name": "ci-pipeline", "scopes": ["agents:read", "tasks:write"]}'

# Revoke a key
curl -X DELETE http://localhost:8000/api/v1/auth/keys/{key_id} \
  -H "X-API-Key: smn_..."
```

Keys are SHA-256 hashed at rest. Only the `smn_` prefix is stored for identification.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CONTROL PLANE                     │
│  REST API · CLI · Tenant Mgmt · Policy Lifecycle     │
│  SSE Streaming · Admin Dashboard                     │
├─────────────────────────────────────────────────────┤
│                   EXECUTION PLANE                    │
│  Agent Runtime · Tool Mesh · Memory · LLM Router     │
│  Multi-Agent Orchestration · MCP · Checkpointing     │
├─────────────────────────────────────────────────────┤
│                     TRUST PLANE                      │
│  Policy Engine (ABAC) · Identity · Audit Chain       │
│  Guardrails · Kill Switch · OpenTelemetry            │
└─────────────────────────────────────────────────────┘
```

### Three planes, one principle: every action is governed.

1. **Control Plane** — API server, SSE streaming, agent registry, policy management, metering
2. **Execution Plane** — LLM orchestration (with retries, fallback, circuit breaker), tool calling, multi-agent handoffs, MCP tool integration, memory (with DB persistence), checkpointing
3. **Trust Plane** — ABAC policy evaluation, permission checks, output guardrails (PII, content, schema), hash-chained audit log, cost enforcement, OpenTelemetry observability

---

## Core Concepts

### Tools

Decorate any Python function to make it an agent tool with governed permissions:

```python
@smn.tool(scopes=["tickets:write"], requires_approval=True)
async def close_ticket(ticket_id: str, resolution: str) -> dict:
    """Close a ticket. Requires human approval before execution."""
    ...
```

### Policy

YAML-based policies control what agents can do. Rules support optional ABAC conditions for fine-grained control:

```yaml
name: production
risk_level: limited
rules:
  - action: "*:read"
    effect: allow
  - action: "*:delete"
    effect: deny
    reason: "Destructive operations prohibited"
  - action: "*:write"
    effect: escalate
    reason: "Writes require human approval"
    conditions:
      time_after: "09:00"
      time_before: "17:00"
      day_of_week: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
limits:
  max_cost_per_task_usd: 5.00
  max_steps_per_task: 50
governance:
  require_transparency_disclosure: true
  log_inputs: true
  log_outputs: true
```

#### ABAC Policy Conditions

Rules can include attribute-based conditions that must all be satisfied for the rule to match:

| Condition | Description | Example |
|-----------|-------------|---------|
| `time_after` | Only match after this UTC time (HH:MM) | `"09:00"` |
| `time_before` | Only match before this UTC time (HH:MM) | `"17:00"` |
| `day_of_week` | Only match on these weekdays | `["Monday", "Friday"]` |
| `context_match` | Match key/value pairs in the evaluation context | `{"env": "production"}` |
| `risk_level` | Only match for this risk level in context | `"high"` |

If a rule has conditions that are not met, it is skipped and evaluation continues to the next rule.

### Identity & Permissions

Every agent gets scoped permissions following `resource:action` convention:

```python
agent = smn.Agent(
    name="reader",
    scopes=["tickets:read", "kb:read"],  # Can only read
)
```

### Risk Levels

Aligned with the EU AI Act risk classification:

| Level | Controls | Use Case |
|-------|----------|----------|
| `minimal` | Standard logging | Internal tools, calculators |
| `limited` | + Transparency disclosure | Customer-facing bots |
| `high` | + Human oversight, impact assessment, strict logging | Healthcare, finance, HR |

High-risk agents automatically get human oversight and enhanced logging.

### Audit Trail

Hash-chained, tamper-evident log of every action:

```bash
smn audit verify          # Verify chain integrity
smn audit tail            # View recent entries
```

### Compliance

Built-in checks against EU AI Act and NIST AI RMF:

```bash
smn compliance check my-agent --frameworks eu-ai-act,nist-ai-rmf
```

```
Compliance Report: my-agent
Score: 88%

  ✅ [eu-ai-act] Transparency obligations: enabled
  ✅ [eu-ai-act] Automatic logging: full I/O logging enabled
  ✅ [nist-ai-rmf] Policies and processes: policy loaded
  ⚠️ [nist-ai-rmf] Monitoring: manual review recommended
```

---

## LLM Reliability

The LLM connector wraps every model call in a reliability layer:

- **Automatic retries** with exponential backoff (configurable attempts)
- **Fallback model chains** — if the primary model fails, the system tries alternatives (e.g., `claude-sonnet-4-6-20250415` → `gpt-4o` → `gemini/gemini-1.5-pro`)
- **Per-model circuit breaker** — after repeated failures within a time window, a model is temporarily bypassed to avoid cascading delays
- **Streaming support** — `reliable_completion_stream()` for token-by-token delivery with the same retry/fallback guarantees

```python
from smn.connectors.llm import reliable_completion

response = await reliable_completion(
    model="anthropic/claude-sonnet-4-6-20250415",
    messages=[{"role": "user", "content": "Hello"}],
    max_retries=3,
)
```

---

## Streaming (SSE)

Stream task execution in real time via Server-Sent Events:

```bash
curl -N -X POST http://localhost:8000/api/v1/stream \
  -H "X-API-Key: smn_..." \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my-agent", "input_text": "Summarize Q4 results"}'
```

Events are emitted at each stage of the governed ReAct loop:

| Event | Description |
|-------|-------------|
| `task_start` | Task accepted, execution begins |
| `step_start` | New reasoning step begins |
| `tool_call` | Agent invokes a tool (name + arguments) |
| `tool_result` | Tool execution result |
| `tool_denied` | Policy denied a tool call (with reason) |
| `final_answer` | Agent produced its final output |
| `task_complete` | Task finished (total steps, cost, duration) |
| `task_error` | Task failed (error details) |

```python
from smn.core.runtime import execute_task_stream

async for event in execute_task_stream(agent, task, db):
    print(f"{event.event}: {event.data}")
```

---

## Output Guardrails

The `GuardrailEngine` validates all agent outputs before they reach the user:

```python
from smn.core.guardrails import GuardrailEngine

engine = GuardrailEngine(pii_action="REDACT")
result = engine.check("Contact me at john@example.com")
# result.passed = True (PII was redacted, not blocked)
# result.text = "Contact me at [EMAIL_REDACTED]"
```

### Three layers of protection

1. **PII Detection & Redaction** — Detects emails, SSNs, phone numbers, credit card numbers, and IP addresses. Configurable action: `BLOCK` (reject output), `REDACT` (replace with placeholders), or `WARN` (flag but pass through).

2. **Content Policy** — Blocks outputs containing secrets (API keys, private keys) and enforces maximum output length.

3. **JSON Schema Validation** — When a structured output schema is required, validates that the agent's response conforms before delivery.

---

## Multi-Agent Orchestration

The `AgentGraph` routes work across multiple agents with governed handoffs:

```python
from smn import AgentGraph

graph = AgentGraph()
graph.add_agent("triage", triage_agent)
graph.add_agent("billing", billing_agent)
graph.add_agent("support", support_agent)

graph.add_edge("triage", "billing", condition=lambda out: "billing" in out.lower())
graph.add_edge("triage", "support", condition=lambda out: "support" in out.lower())

result = await graph.execute("triage", task_input="I need a refund", db=db)
```

Features:
- **Conditional edges** — Route to the next agent based on the previous agent's output
- **Cycle detection** — Static graph analysis (DFS) prevents infinite loops before execution
- **Runtime depth limit** — Configurable `max_handoffs` (default 10) prevents runaway chains
- **Parallel execution** — `run_parallel()` fans out to multiple agents concurrently and collects results

---

## MCP Tool Integration

Connect any [Model Context Protocol](https://modelcontextprotocol.io/) server and expose its tools as governed SMN tools:

```python
from smn.connectors.mcp import MCPToolAdapter, MCPServerConfig

config = MCPServerConfig(
    name="filesystem",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    scopes=["fs:read", "fs:write"],
)

adapter = MCPToolAdapter(config)
await adapter.connect()
tools = adapter.get_tools()  # Returns list of ToolSpec callables
```

MCP tools are automatically:
- Prefixed with `mcp_{server_name}_` for namespace isolation
- Wrapped in SMN's governance layer (policy, identity, audit, cost tracking)
- Discovered dynamically via the MCP `tools/list` protocol

---

## Checkpointing & Resumability

Long-running tasks are checkpointed so they can resume after crashes:

```python
from smn.core.checkpoint import CheckpointStore, DBCheckpointStore

store = CheckpointStore()
store.save(checkpoint)  # In-memory store

db_store = DBCheckpointStore()
await db_store.save_to_db(checkpoint, session)  # Persistent store
latest = await db_store.load_from_db(task_id, session)
```

Checkpoints capture:
- Current step number and execution status
- Full message history (LLM context)
- Budget entries consumed so far
- Audit entry IDs for chain reconstruction
- Agent and task identifiers

The `prune()` method retains only the N most recent checkpoints per task to manage storage.

---

## Memory Persistence

Agent memory can be persisted to the database and restored across sessions:

```python
from smn.core.memory import load_memory_from_db, flush_memory_to_db

# Load memory from DB into the in-memory store
data = await load_memory_from_db(session, tenant_id, agent_id, scope, namespace)

# Flush changed keys back to DB (with TTL support)
await flush_memory_to_db(session, tenant_id, agent_id, scope, namespace, current_data)
```

- Scoped by tenant, agent, scope, and namespace
- Expired entries are automatically skipped on load
- Flush performs upserts for changed/new keys and deletes removed keys
- TTL-based expiration for session memory cleanup

---

## OpenTelemetry Observability

Full distributed tracing and metrics with zero-config fallback:

```python
from smn.core.telemetry import trace_task, trace_llm_call, record_tokens

async with trace_task(task_id, agent_id) as span:
    async with trace_llm_call(model="claude-sonnet-4-6-20250415") as llm_span:
        record_tokens(model, prompt_tokens=100, completion_tokens=50)
```

### Metrics exported

| Metric | Type | Description |
|--------|------|-------------|
| `smn.tasks.total` | Counter | Total task executions |
| `smn.tasks.duration_ms` | Histogram | Task execution time |
| `smn.llm.calls` | Counter | LLM API calls by model |
| `smn.llm.tokens` | Counter | Token usage (prompt/completion) |
| `smn.llm.cost_usd` | Counter | LLM spend by model |
| `smn.tools.calls` | Counter | Tool invocations by name |
| `smn.policy.denials` | Counter | Policy-denied actions |
| `smn.guardrails.blocks` | Counter | Guardrail-blocked outputs |

When OpenTelemetry SDK is not installed, all instrumentation silently becomes no-op — zero overhead, no errors.

---

## API Server

```bash
smn serve                 # Start on localhost:8000
```

Endpoints:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/health` | No | Health check |
| **Auth** ||||
| `POST` | `/api/v1/auth/bootstrap` | No | Create tenant + first API key |
| `POST` | `/api/v1/auth/keys` | Yes | Create additional API key |
| `GET` | `/api/v1/auth/keys` | Yes | List API keys |
| `DELETE` | `/api/v1/auth/keys/{id}` | Yes | Revoke API key |
| **Agents** ||||
| `POST` | `/api/v1/agents` | Yes | Register agent |
| `GET` | `/api/v1/agents` | Yes | List agents |
| **Tasks** ||||
| `POST` | `/api/v1/tasks` | Yes | Run a task (sync or async) |
| `GET` | `/api/v1/tasks` | Yes | List task history |
| **Streaming** ||||
| `POST` | `/api/v1/stream` | Yes | Stream task execution via SSE |
| **Audit** ||||
| `GET` | `/api/v1/audit` | Yes | Query audit log |
| `GET` | `/api/v1/audit/verify` | Yes | Verify audit chain |
| **Policies** ||||
| `GET` | `/api/v1/policies` | Yes | List policies |
| `GET` | `/api/v1/policies/frameworks` | Yes | List regulatory frameworks |
| **Billing** ||||
| `POST` | `/api/v1/billing/customer` | Yes | Create Stripe customer |
| `POST` | `/api/v1/billing/subscribe` | Yes | Create subscription |
| `GET` | `/api/v1/billing/status` | Yes | Get billing status |
| `POST` | `/api/v1/billing/webhook` | Stripe | Handle Stripe webhook |
| **Admin** ||||
| `GET` | `/api/v1/admin/tenants` | Yes | List tenants with stats |
| `PATCH` | `/api/v1/admin/tenants/{id}` | Yes | Update tenant settings |
| `GET` | `/api/v1/admin/health` | Yes | System-wide health stats |
| `GET` | `/api/v1/admin/usage` | Yes | Usage across all tenants |
| `GET` | `/api/v1/admin/usage/{tenant_id}` | Yes | Usage for a specific tenant |

Full OpenAPI docs at `/docs` when server is running.

---

## CLI Reference

```bash
smn version                          # Show version
smn init                             # Initialize project
smn serve                            # Start API server

smn agent list                       # List agents
smn agent create my-bot              # Register agent
  --model anthropic/claude-sonnet-4-6-20250415
  --risk-level limited
  --policy default

smn policy list                      # List policy files
smn policy validate my-policy        # Validate a policy

smn compliance check my-bot          # Run compliance check
  --frameworks eu-ai-act,nist-ai-rmf
  --risk-level limited

smn audit verify                     # Verify audit chain
smn audit tail --limit 20            # View recent entries
```

---

## Regulatory Alignment

### EU AI Act (Regulation 2024/1689)

| Article | Requirement | SMN Capability |
|---------|-------------|----------------|
| Art. 5 | Prohibited practices | Policy engine blocks prohibited actions |
| Art. 9 | Risk management | Risk classification + policy controls |
| Art. 12 | Automatic logging | Hash-chained immutable audit trail |
| Art. 13 | Transparency | System prompt disclosure |
| Art. 14 | Human oversight | Approval gates + kill switch |
| Art. 15 | Accuracy/robustness | Cost limits, step limits, guardrails, circuit breakers |
| Art. 52 | Transparency (all AI) | Mandatory disclosure in system prompts |

### NIST AI RMF 1.0

| Function | SMN Mapping |
|----------|-------------|
| GOVERN | Policy engine (ABAC), risk classification, organizational controls |
| MAP | Risk level declaration, context framing per agent |
| MEASURE | Audit trail, cost tracking, compliance scoring, OpenTelemetry metrics |
| MANAGE | Kill switch, budget enforcement, guardrails, corrective actions |

---

## Project Structure

```
SMN/
├── src/smn/
│   ├── __init__.py          # Public API: Agent, tool, Policy, AgentGraph, GuardrailEngine
│   ├── config.py            # Settings (env-based, SMN_ prefix)
│   ├── server.py            # FastAPI application + middleware
│   ├── cli.py               # Typer CLI
│   ├── db.py                # Database setup (async SQLAlchemy)
│   ├── models.py            # SQLAlchemy models (Tenant, Agent, Task, APIKey, Usage, Checkpoint)
│   ├── auth.py              # API key auth (SHA-256 hashing, FastAPI dependency)
│   ├── billing.py           # Stripe billing integration
│   ├── metering.py          # Usage aggregation per tenant per period
│   ├── worker.py            # Celery task queue for async execution
│   ├── core/
│   │   ├── agent.py         # Agent class
│   │   ├── runtime.py       # Execution engine (governed ReAct loop + SSE streaming)
│   │   ├── tools.py         # @tool decorator and schema generation
│   │   ├── identity.py      # Identity and permission checks
│   │   ├── policy.py        # YAML policy engine with ABAC conditions
│   │   ├── memory.py        # Session/persistent memory + DB persistence
│   │   ├── audit.py         # Hash-chained audit log
│   │   ├── finops.py        # Cost tracking and budgets
│   │   ├── guardrails.py    # Output guardrails (PII, content policy, schema)
│   │   ├── telemetry.py     # OpenTelemetry instrumentation (no-op fallback)
│   │   ├── orchestrator.py  # Multi-agent graph orchestration
│   │   └── checkpoint.py    # Execution state checkpointing
│   ├── api/
│   │   ├── agents.py        # Agent CRUD endpoints
│   │   ├── tasks.py         # Task execution (sync + async)
│   │   ├── streaming.py     # SSE streaming endpoint
│   │   ├── policies.py      # Policy management
│   │   ├── audit.py         # Audit log queries
│   │   ├── auth.py          # Bootstrap, key management
│   │   ├── billing.py       # Stripe customer, subscription, webhook
│   │   └── admin.py         # Tenant management, health, usage
│   ├── middleware/
│   │   └── rate_limit.py    # Per-tenant rate limiting (Redis + fallback)
│   ├── governance/
│   │   ├── frameworks.py    # EU AI Act, NIST AI RMF definitions
│   │   └── checks.py        # Compliance check engine
│   └── connectors/
│       ├── base.py          # Connector interface
│       ├── http.py          # SSRF-protected HTTP client
│       ├── llm.py           # Reliable LLM connector (retries, fallback, circuit breaker)
│       ├── mcp.py           # MCP protocol adapter
│       ├── database.py      # Governed SQL connector (read-only default, injection protection)
│       ├── storage.py       # S3/Azure Blob/GCS connector (path traversal protection)
│       ├── webhook.py       # HMAC-signed webhook delivery
│       └── email.py         # Governed email delivery (content validation)
├── alembic/                 # Database migration framework
├── marketplace/             # AWS, Azure, GCP marketplace packaging
├── infra/
│   ├── aws/                 # Terraform — VPC, ECS Fargate, RDS, ElastiCache, ALB
│   └── azure/               # Terraform — VNET, Container Apps, PostgreSQL, Redis, ACR
├── compliance/
│   ├── hipaa.yaml           # HIPAA Technical Safeguards policy pack
│   ├── sox.yaml             # SOX IT General Controls policy pack
│   └── fedramp.yaml         # FedRAMP Moderate baseline policy pack
├── legal/
│   ├── terms-of-service.md  # Terms of Service
│   ├── privacy-policy.md    # Privacy Policy (GDPR + CCPA)
│   └── data-processing-agreement.md  # DPA with SCCs
├── docs/
│   ├── deployment.md        # Production deployment guide + runbook
│   ├── monitoring.md        # Observability stack (OTel, Prometheus, Grafana)
│   └── backup-dr.md         # Backup and disaster recovery plan
├── site/
│   └── index.html           # Landing page
├── policies/                # YAML policy definitions
├── examples/                # Working examples
├── tests/                   # Test suite
│   ├── test_*.py            # Unit + integration tests
│   ├── test_security_hardening.py  # OWASP Top-10 security tests
│   └── load/locustfile.py   # Load testing (Locust)
├── .github/workflows/
│   ├── ci.yml               # CI pipeline (lint, test, security, docker)
│   └── publish.yml          # PyPI publish (trusted publishing)
├── Dockerfile
├── docker-compose.yml
└── .env.example             # All configuration variables
```

---

## Docker

### Development (SQLite, in-memory rate limiting)

```bash
pip install -e ".[dev]"
smn serve --reload
```

### Production (PostgreSQL, Redis, Celery, OpenTelemetry)

```bash
cp .env.example .env
# Edit .env with your configuration:
#   SMN_DATABASE_URL=postgresql+asyncpg://smn:secret@db:5432/smn
#   SMN_REDIS_URL=redis://redis:6379/0
#   SMN_STRIPE_SECRET_KEY=sk_live_...
#   SMN_STRIPE_WEBHOOK_SECRET=whsec_...
#   ANTHROPIC_API_KEY=sk-ant-...
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

docker compose up
```

This starts four services:
- **smn** — FastAPI server on port 8000
- **worker** — Celery worker for async task execution
- **db** — PostgreSQL 16
- **redis** — Redis 7 (rate limiting + task queue broker)

### Database Migrations

```bash
# Generate a migration after model changes
alembic revision --autogenerate -m "describe change"

# Apply migrations
alembic upgrade head
```

---

## Connectors

SMN ships 8 governed connectors. Every connector enforces scopes, audit logging, and policy checks.

| Connector | Description | Key Safety Features |
|-----------|-------------|---------------------|
| HTTP | REST API calls | SSRF protection (blocks internal IPs, metadata endpoints) |
| LLM | Model inference | Retries, fallback chains, per-model circuit breaker |
| MCP | Model Context Protocol tools | Dynamic discovery, namespace isolation |
| Database | SQL queries | Read-only default, parameterised queries, injection blocking |
| Storage | S3 / Azure Blob / GCS | Path traversal prevention, extension blocking, size limits |
| Webhook | Outbound event delivery | HMAC-SHA256 signing, HTTPS-only, domain allowlist |
| Email | SMTP email delivery | Script injection blocking, header injection prevention |

---

## Infrastructure as Code

Production-ready Terraform modules for both AWS and Azure:

```bash
# AWS — VPC, ECS Fargate, RDS PostgreSQL 16, ElastiCache Redis 7.1, ALB
cd infra/aws && terraform init && terraform plan

# Azure — VNET, Container Apps, PostgreSQL Flexible Server, Redis Cache, ACR
cd infra/azure && terraform init && terraform plan
```

See [docs/deployment.md](docs/deployment.md) for the full production deployment guide and runbook.

---

## Monitoring & Observability

Full observability stack with pre-configured dashboards and 22 alert rules:

- **OpenTelemetry Collector** — metrics, traces, and logs pipeline
- **Prometheus + Grafana** — metrics dashboards and alerting
- **Jaeger** — distributed trace visualisation
- **Loki** — log aggregation
- **AlertManager** — PagerDuty, Slack, and email notifications

SLO targets: 99.9% API availability, <200ms p95 latency, <0.1% error rate.

See [docs/monitoring.md](docs/monitoring.md) for configuration and [docs/backup-dr.md](docs/backup-dr.md) for disaster recovery.

---

## Compliance Packs

Vertical compliance policy packs ship ready to deploy:

```bash
# Apply HIPAA controls
smn policy load compliance/hipaa.yaml

# Apply SOX IT General Controls
smn policy load compliance/sox.yaml

# Apply FedRAMP Moderate baseline
smn policy load compliance/fedramp.yaml
```

| Pack | Standard | Rules | Key Controls |
|------|----------|-------|-------------|
| HIPAA | 45 CFR § 164.312 | 8 | Authenticated access, PHI restrictions, encryption, 6-year retention |
| SOX | COSO 2013 / COBIT 2019 | 9 | Segregation of duties, change management, 7-year retention |
| FedRAMP | NIST SP 800-53 Rev 5 | 12 | PIV/CAC auth, MFA, FIPS 140-2, continuous monitoring, CUI protection |

---

## Security

Security testing covers the OWASP Top-10 attack surface:

```bash
pytest tests/test_security_hardening.py -v
```

- Authentication enforcement on all endpoints
- SQL injection pattern scanning across all source files
- SSRF protection (localhost, cloud metadata endpoints)
- No hardcoded secrets or debug mode in production
- Input validation on policy and guardrail engines
- Hash-chained audit integrity verification
- Rate limiting verification
- Dependency version pinning verification

See [SECURITY.md](SECURITY.md) for vulnerability disclosure and security architecture.

---

## Load Testing

Load tests use Locust with 5 weighted user types simulating realistic traffic:

```bash
# Interactive mode
cd tests/load && locust

# Headless CI mode (fails on >5% error rate)
locust -f tests/load/locustfile.py --headless -u 100 -r 10 --run-time 5m
```

---

## Legal

- [Terms of Service](legal/terms-of-service.md)
- [Privacy Policy](legal/privacy-policy.md) (GDPR + CCPA)
- [Data Processing Agreement](legal/data-processing-agreement.md) (SCCs, GDPR Art. 28)

---

## CI/CD

- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) — Lint (Ruff), test matrix (Python 3.11 + 3.12), security scan (Bandit + Safety), Docker build
- **Publish** ([.github/workflows/publish.yml](.github/workflows/publish.yml)) — PyPI trusted publishing (OIDC, no API tokens) triggered on GitHub release

---

## Development

```bash
pip install -e ".[dev]"
pytest                    # Run test suite
smn serve --reload        # Dev server with auto-reload
ruff check src/ tests/    # Lint
```

---

## Repository Structure

SMN uses an **open-core** model with two repositories:

| Repository | Licence | Contents |
|------------|---------|----------|
| **smn** (public) | MIT | Core runtime, single-tenant API, guardrails, audit, SDKs, CLI, SQLite |
| **smn-pro** (private) | [Commercial](LICENSE-COMMERCIAL.md) | Everything in community + multi-tenant admin, billing/Stripe, PostgreSQL, Celery/Redis, rate limiting, orchestrator, MCP, checkpointing, ABAC conditions, compliance packs |

The `community/` directory in this repo is the source for the public repository.

---

## License

Open-core: Community features are [MIT](community/LICENSE) licensed. Pro features require a [commercial license](LICENSE-COMMERCIAL.md). See [LICENSE](LICENSE) for details.
