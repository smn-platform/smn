"""Studio SQLAlchemy models — workflows, runs, steps, and webhook tokens."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class StudioBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Workflow(StudioBase):
    """A saved workflow definition (nodes + edges + triggers)."""

    __tablename__ = "studio_workflows"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    # Serialised WorkflowDefinition JSON
    definition = Column(Text, nullable=False, default='{"nodes":[],"edges":[]}')
    # Serialised list[WorkflowTrigger] JSON
    triggers = Column(Text, nullable=False, default="[]")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now)


class WorkflowRun(StudioBase):
    """A single execution of a workflow."""

    __tablename__ = "studio_workflow_runs"

    id = Column(String, primary_key=True, default=_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)
    # "manual" | "webhook" | "schedule"
    trigger_type = Column(String(20), default="manual", nullable=False)
    trigger_data = Column(Text, nullable=True)   # JSON
    output = Column(Text, nullable=True)          # JSON
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class WorkflowRunStep(StudioBase):
    """Per-node execution record within a run."""

    __tablename__ = "studio_workflow_run_steps"

    id = Column(String, primary_key=True, default=_uuid)
    run_id = Column(String, nullable=False, index=True)
    node_id = Column(String, nullable=False)
    node_type = Column(String(40), nullable=False)
    node_label = Column(String(200), default="")
    status = Column(String(20), default="pending", nullable=False)
    input_data = Column(Text, nullable=True)   # JSON
    output_data = Column(Text, nullable=True)  # JSON
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)


class WebhookToken(StudioBase):
    """Token authorising inbound webhook calls for a specific workflow."""

    __tablename__ = "studio_webhook_tokens"

    id = Column(String, primary_key=True, default=_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=False)
    token = Column(String(64), nullable=False, unique=True, index=True,
                   default=lambda: secrets.token_urlsafe(32))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
