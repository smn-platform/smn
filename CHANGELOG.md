# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-06-09

### Added
- Root `SECURITY.md` with GitHub private vulnerability reporting link
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- GitHub issue templates (bug report, feature request)
- GitHub pull request template
- `[project.urls]` in `pyproject.toml` (Homepage, Docs, Repo, Issues, Changelog)

### Changed
- README: added CI, PyPI, Python, and license badges
- README: quickstart now uses `pip install smn` instead of editable install
- CODEOWNERS: migrated from personal handle to `@smn-platform/maintainers` team
- `community/SECURITY.md`: corrected contact email to `security@leylabs.dev`
- Legal documents: removed draft template disclaimers
- `.gitignore`: restored `package-lock.json` tracking for TypeScript SDK reproducibility
- Version bumped to `0.1.3` across all packages and SDKs

### Removed
- Stale `site/index.html.bak`

## [0.1.2] - 2026-04-19

### Added
- `ListResponse[T]` pagination envelope on all 7 list endpoints (`object`, `data`, `has_more`, `total_count`, `limit`, `offset`)
- `PaginationParams` dependency with validated limits (1-100) and offset (≥0)
- `ListPage[T]` generic type in Python SDK with full pagination metadata
- `ListPage<T>` interface in TypeScript SDK with full pagination metadata
- `py.typed` PEP 561 marker in Python SDK for type-checker support
- 5 new Python SDK pagination tests (`TestPagination` class)
- Caddy reverse proxy configuration (`Caddyfile`) with security headers and TLS
- Production docker-compose overlay (`docker-compose.production.yml`) with resource limits, read-only filesystems, `no-new-privileges`
- Community edition Dockerfile (standalone, SQLite-only)
- `.dockerignore` for cleaner Docker builds

### Changed
- All list endpoints now return paginated envelope instead of bare arrays
- Python SDK list methods return `ListPage[T]` instead of `list[T]`
- TypeScript SDK list methods return `ListPage<T>` instead of `T[]`
- Default pagination limit aligned to 20 across server and both SDKs
- Keys and Admin list methods now accept `limit`/`offset` parameters

### Fixed
- Stale variable reference in `test_list_tasks_with_filters`

## [0.1.1] - 2026-04-19

### Added
- Comprehensive API reference documentation (`docs/api-reference.md`)
- TypeScript SDK README with full usage examples
- 23 integration tests covering all API endpoints
- `Makefile` for common dev tasks (`make test`, `make serve`, `make lint`)
- `py.typed` marker for PEP 561 type-checking support
- TypeScript SDK tests in CI pipeline
- Python SDK tests in CI pipeline
- `CODEOWNERS` for security-sensitive file review

### Changed
- Updated `SECURITY.md` email to `security@leylabs.dev`
- Filled all legal document placeholders (ToS, Privacy Policy, DPA) with Ley Labs Ltd details
- Updated README with dual-repository structure documentation

### Fixed
- Updated all legal contact emails to `@leylabs.dev` domain

### Repository Structure
- Split codebase into `community/` (MIT, open-source) and root (commercial)
- Community repo contains core runtime, SDKs, docs, and free-tier features
- Added `LICENSE-COMMERCIAL.md` for Pro/Enterprise licensing

## [0.1.0] - 2026-04-16

### Added

#### Core Platform
- Agent runtime with governed ReAct loop (5-gate governance per tool call)
- YAML-based policy engine with EU AI Act and NIST AI RMF framework mappings
- Hash-chained immutable audit log with tamper verification
- Identity and scoped permission system with wildcard support
- FinOps cost tracking with per-task budgets and kill switch
- Multi-model LLM connector via litellm (Anthropic, OpenAI, Azure, Google)
- SSRF-protected HTTP connector
- Session and persistent memory services
- Compliance checking engine with structured reports
- Three policy templates (default, high-risk, EU AI Act)

#### API & CLI
- REST API (FastAPI) with full CRUD for agents, tasks, policies, and audit
- CLI (`smn`) with serve, agent, policy, compliance, and audit subcommands
- API key authentication with SHA-256 hashed storage and per-tenant isolation
- Per-tenant rate limiting middleware (Redis-backed with in-memory fallback)
- Admin operations dashboard API (tenant management, billing, health, usage)

#### Production Infrastructure
- PostgreSQL production database support via asyncpg (SQLite retained for dev)
- Alembic database migration framework with initial schema migration
- Celery + Redis task queue for async agent execution at scale
- Stripe Billing integration (subscription management, usage-based invoicing)
- Metering aggregation service (per-tenant usage tallying)
- Docker packaging with non-root user
- Cloud marketplace packaging for AWS, Azure, and GCP

#### State-of-the-Art Agent Features
- LLM reliability layer (automatic retries, fallback model chains, per-model circuit breaker)
- Server-Sent Events (SSE) streaming for real-time task execution observation
- Output guardrails engine (PII detection/redaction, content policy, JSON schema validation)
- OpenTelemetry instrumentation (distributed tracing, metrics export, no-op fallback)
- Multi-agent orchestration (AgentGraph with conditional edges, cycle detection, parallel execution)
- MCP (Model Context Protocol) tool adapter (dynamic tool discovery, governed execution)
- Execution checkpointing and resumability (in-memory and DB-backed state persistence)
- ABAC policy conditions (time windows, day-of-week, context matching, risk-level gating)
- Database-backed memory persistence (cross-session restore, TTL expiration, scoped upsert/delete)

#### DevOps
- GitHub Actions CI/CD (lint, test, security scan, Docker build)
- Bandit SAST integration for security scanning
- 203 passing tests covering all modules

[0.1.0]: https://github.com/smn-platform/smn/releases/tag/v0.1.0
