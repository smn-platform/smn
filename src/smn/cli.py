"""SMN CLI — the command-line interface for managing agents, policies, and compliance.

Usage:
    smn serve                         # Start the API server
    smn agent list                    # List agents
    smn agent create my-bot           # Register an agent
    smn policy list                   # List policies
    smn compliance check my-bot       # Run compliance check
    smn audit verify                  # Verify audit chain integrity
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from smn import __version__

console = Console()
app = typer.Typer(
    name="smn",
    help="SMN — Secure Multi-agent Network. Deploy, govern, and scale AI agents safely.",
    no_args_is_help=True,
)


# ── Top-level commands ───────────────────────────────────────────


@app.command()
def version():
    """Show SMN version."""
    console.print(f"SMN v{__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port number"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
):
    """Start the SMN API server."""
    import uvicorn

    console.print(f"[bold green]Starting SMN server on {host}:{port}[/bold green]")
    uvicorn.run("smn.server:app", host=host, port=port, reload=reload)


@app.command()
def init(
    directory: str = typer.Argument(".", help="Project directory"),
):
    """Initialize a new SMN project with default configuration."""
    base = Path(directory)
    policies_dir = base / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)

    # Create default policy if it doesn't exist
    default_policy = policies_dir / "default.yaml"
    if not default_policy.exists():
        default_policy.write_text(
            "name: default\n"
            "risk_level: limited\n"
            "rules:\n"
            '  - action: "*"\n'
            "    effect: allow\n"
            "limits:\n"
            "  max_cost_per_task_usd: 5.00\n"
            "  max_steps_per_task: 50\n"
            "governance:\n"
            "  require_transparency_disclosure: true\n"
            "  log_inputs: true\n"
            "  log_outputs: true\n"
        )

    # Create .env if it doesn't exist
    env_file = base / ".env"
    if not env_file.exists():
        env_example = base / ".env.example"
        if env_example.exists():
            env_file.write_text(env_example.read_text())
            console.print("[dim].env created from .env.example[/dim]")

    console.print("[bold green]SMN project initialized.[/bold green]")
    console.print(f"  Policies: {policies_dir}")
    console.print("  Next: edit .env with your API keys, then run [bold]smn serve[/bold]")


# ── Agent subcommands ────────────────────────────────────────────


agent_app = typer.Typer(help="Manage agents.")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def agent_list(tenant: str = typer.Option("default", help="Tenant ID")):
    """List registered agents."""
    from smn.db import async_session
    from smn.models import AgentRecord

    async def _run():
        from sqlalchemy import select
        from smn.db import init_db

        await init_db()
        async with async_session() as db:
            result = await db.execute(
                select(AgentRecord).where(AgentRecord.tenant_id == tenant)
            )
            agents = result.scalars().all()

        table = Table(title="Agents")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Model")
        table.add_column("Risk")
        table.add_column("Active")
        for a in agents:
            table.add_row(a.id[:8], a.name, a.model, a.risk_level, "✓" if a.is_active else "✗")
        console.print(table)

    asyncio.run(_run())


@agent_app.command("create")
def agent_create(
    name: str = typer.Argument(..., help="Agent name"),
    model: str = typer.Option(None, help="LLM model"),
    risk_level: str = typer.Option("limited", help="Risk level: minimal|limited|high"),
    policy: str = typer.Option("default", help="Policy name"),
    tenant: str = typer.Option("default", help="Tenant ID"),
):
    """Register a new agent."""
    from smn.config import settings
    from smn.db import async_session
    from smn.models import AgentRecord, Tenant

    async def _run():
        from sqlalchemy import select
        from smn.db import init_db

        await init_db()
        async with async_session() as db:
            # Ensure tenant
            t = await db.execute(select(Tenant).where(Tenant.id == tenant))
            if not t.scalar_one_or_none():
                db.add(Tenant(id=tenant, name=tenant))

            agent = AgentRecord(
                tenant_id=tenant,
                name=name,
                model=model or settings.default_model,
                risk_level=risk_level,
                policy_name=policy,
            )
            db.add(agent)
            await db.commit()
            console.print(f"[bold green]Agent '{name}' created.[/bold green] ID: {agent.id}")

    asyncio.run(_run())


# ── Policy subcommands ───────────────────────────────────────────


policy_app = typer.Typer(help="Manage policies.")
app.add_typer(policy_app, name="policy")


@policy_app.command("list")
def policy_list():
    """List available policy files."""
    from smn.config import settings

    policy_dir = settings.policy_dir
    if not policy_dir.exists():
        console.print("[yellow]No policies directory found.[/yellow]")
        return

    table = Table(title="Policies")
    table.add_column("Name")
    table.add_column("File")
    for f in sorted(policy_dir.glob("*.y*ml")):
        table.add_row(f.stem, str(f))
    console.print(table)


@policy_app.command("validate")
def policy_validate(name: str = typer.Argument(..., help="Policy name")):
    """Validate a policy file."""
    from smn.core.policy import load_policy

    try:
        p = load_policy(name)
        console.print(f"[bold green]Policy '{p.name}' is valid.[/bold green]")
        console.print(f"  Risk level: {p.risk_level}")
        console.print(f"  Rules: {len(p.rules)}")
        console.print(f"  Max cost/task: ${p.limits.max_cost_per_task_usd:.2f}")
        console.print(f"  Max steps: {p.limits.max_steps_per_task}")
        console.print(f"  Transparency: {p.governance.require_transparency_disclosure}")
        console.print(f"  Human oversight: {p.governance.require_human_oversight}")
    except Exception as e:
        console.print(f"[bold red]Policy validation failed:[/bold red] {e}")
        raise typer.Exit(1)


# ── Compliance subcommands ───────────────────────────────────────


compliance_app = typer.Typer(help="Run compliance checks.")
app.add_typer(compliance_app, name="compliance")


@compliance_app.command("check")
def compliance_check(
    agent_name: str = typer.Argument(..., help="Agent name to check"),
    frameworks: str = typer.Option(
        "eu-ai-act,nist-ai-rmf", help="Comma-separated framework IDs"
    ),
    risk_level: str = typer.Option("limited", help="Risk level to assess"),
):
    """Run compliance assessment for an agent configuration."""
    from smn.core.agent import Agent
    from smn.governance.checks import check_compliance

    agent = Agent(name=agent_name, risk_level=risk_level)
    fw_list = [f.strip() for f in frameworks.split(",")]
    report = check_compliance(agent, frameworks=fw_list)

    console.print(f"\n[bold]Compliance Report: {report.agent_name}[/bold]")
    console.print(f"Risk Level: {report.risk_level}")
    console.print(f"Score: {report.score:.0%}\n")

    table = Table()
    table.add_column("Status", width=8)
    table.add_column("Framework")
    table.add_column("Requirement")
    table.add_column("Message")

    status_style = {"pass": "green", "fail": "red", "warning": "yellow", "not_applicable": "dim"}
    for item in report.items:
        style = status_style.get(item.status, "")
        table.add_row(
            f"[{style}]{item.status.upper()}[/{style}]",
            item.framework,
            item.requirement_name,
            item.message,
        )
    console.print(table)

    if report.failed > 0:
        console.print(f"\n[bold red]{report.failed} failures require attention.[/bold red]")


# ── Audit subcommands ────────────────────────────────────────────


audit_app = typer.Typer(help="Audit log operations.")
app.add_typer(audit_app, name="audit")


@audit_app.command("verify")
def audit_verify(tenant: str = typer.Option("default", help="Tenant ID")):
    """Verify the integrity of the audit hash chain."""
    from smn.core.audit import verify_chain
    from smn.db import async_session

    async def _run():
        from smn.db import init_db

        await init_db()
        async with async_session() as db:
            is_valid, message = await verify_chain(db, tenant)
            if is_valid:
                console.print(f"[bold green]✓ Chain intact:[/bold green] {message}")
            else:
                console.print(f"[bold red]✗ Chain broken:[/bold red] {message}")

    asyncio.run(_run())


@audit_app.command("tail")
def audit_tail(
    tenant: str = typer.Option("default", help="Tenant ID"),
    limit: int = typer.Option(20, help="Number of entries"),
):
    """Show recent audit entries."""
    from smn.core.audit import get_audit_trail
    from smn.db import async_session

    async def _run():
        from smn.db import init_db

        await init_db()
        async with async_session() as db:
            entries = await get_audit_trail(db, tenant, limit=limit)

        table = Table(title="Recent Audit Entries")
        table.add_column("Time", style="dim")
        table.add_column("Event")
        table.add_column("Action")
        table.add_column("Decision")
        table.add_column("Cost")
        for e in entries:
            table.add_row(
                e.timestamp.strftime("%H:%M:%S"),
                e.event_type,
                e.action,
                e.policy_decision,
                f"${e.cost_usd:.4f}",
            )
        console.print(table)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
