"""SMN configuration — single source of truth for all settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMN_", env_file=".env", extra="ignore")

    # ── Core ──────────────────────────────────────────────────────
    app_name: str = "SMN"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # ── Database ──────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./smn.db"

    # ── LLM ───────────────────────────────────────────────────────
    default_model: str = "anthropic/claude-sonnet-4-6-20250415"

    # ── Policy ────────────────────────────────────────────────────
    policy_dir: Path = Path("policies")
    default_policy: str = "default"

    # ── Governance ────────────────────────────────────────────────
    max_cost_per_task_usd: float = 5.00
    require_human_approval_above_usd: float = 1.00
    audit_retention_days: int = 2555  # ~7 years — EU AI Act Art. 12
    enable_kill_switch: bool = True

    # ── Server ────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000

    # ── Stripe Billing ────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_core: str = ""  # Stripe Price ID for Core subscription
    stripe_price_id_growth: str = ""  # Stripe Price ID for Growth subscription
    stripe_price_id_usage: str = ""  # Stripe Price ID for metered usage

    # ── Redis (rate limiting + task queue) ─────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Rate Limiting ─────────────────────────────────────────────
    rate_limit_default_rpm: int = 60  # requests per minute
    rate_limit_burst: int = 10  # burst allowance above RPM

    # ── Task Queue ────────────────────────────────────────────────
    task_queue_backend: str = "redis://localhost:6379/1"


settings = Settings()
