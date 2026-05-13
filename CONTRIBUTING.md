# Contributing to SMN

Thank you for considering contributing to SMN. This document explains the process for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and professional environment for all contributors.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/smn-platform/smn.git
cd smn

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Verify everything works
pytest
```

### Project Structure

```
src/smn/
├── core/           # Runtime, policy, memory, audit, guardrails, orchestrator
├── api/            # FastAPI endpoints
├── connectors/     # LLM, HTTP, MCP connectors
├── middleware/      # Rate limiting
└── governance/     # Compliance frameworks and checks
```

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates.
2. Open a new issue with:
   - Python version and OS
   - Steps to reproduce
   - Expected vs. actual behavior
   - Error messages or logs

### Suggesting Features

Open a discussion or issue with:
- The problem your feature solves
- A proposed solution
- Whether you'd be willing to implement it

### Submitting Code

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write code** following the conventions below.

3. **Write tests** for all new functionality. We target >90% coverage on new code.

4. **Run the full check suite:**
   ```bash
   # Lint
   ruff check src/ tests/
   ruff format --check src/ tests/

   # Tests
   pytest

   # Security (optional, requires bandit)
   pip install bandit[toml]
   bandit -r src/smn/ -c pyproject.toml
   ```

5. **Commit** with a clear message:
   ```
   Add ABAC time-window conditions to policy engine

   - Support time_after/time_before conditions on policy rules
   - Add day_of_week filtering for weekday-only policies
   - Include 19 tests covering all condition types
   ```

6. **Open a pull request** against `main`.

## Code Conventions

### Style

- **Formatter:** Ruff (configured in `pyproject.toml`)
- **Line length:** 100 characters
- **Target Python:** 3.11+
- **Type hints:** Use throughout; prefer `X | None` over `Optional[X]`

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Architecture Principles

1. **Every agent action is governed.** If you add a new execution path, it must pass through the policy engine, identity checks, and audit log.

2. **Tools declare their permissions.** Tool scopes are explicit — no ambient authority.

3. **Audit everything.** New features that perform actions should emit audit entries.

4. **Fail secure.** When in doubt, deny. Unknown policy conditions, missing permissions, and untrusted inputs should result in denial or escalation.

5. **No secrets in code.** Configuration goes through `smn.config.Settings` with the `SMN_` env prefix. Never hardcode API keys, passwords, or tokens.

### Testing

- Use `pytest` with `pytest-asyncio` for async tests.
- Place tests in `tests/test_{module}.py`.
- Use the shared `conftest.py` fixtures for database sessions and event loops.
- Mock external services (LLM calls, Stripe, Redis) — never make real API calls in tests.
- Test both success and failure paths. For governance features, test that denials work correctly.

### Connectors

New connectors should:
1. Extend `BaseConnector` from `smn.connectors.base`
2. Implement `connect()`, `disconnect()`, and `health_check()`
3. Accept `ConnectorConfig` with typed parameters
4. Include SSRF protections where applicable
5. Include tests with mocked external calls

## Pull Request Review

PRs are reviewed for:
- Correctness and test coverage
- Security implications (especially for governance and auth code)
- API compatibility (breaking changes require a version bump)
- Documentation updates (README, docstrings)
- Performance impact

## Release Process

1. Version bumps follow [Semantic Versioning](https://semver.org/).
2. All changes are documented in `CHANGELOG.md`.
3. Releases are tagged and published to PyPI.

## Questions?

Open a discussion on GitHub or reach out to the maintainers.
