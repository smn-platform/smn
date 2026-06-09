"""Studio Pydantic schemas — request/response models for the workflow API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Workflow definition (mirrors React Flow's data model) ─────────


class NodePosition(BaseModel):
    x: float = 0.0
    y: float = 0.0


class NodeData(BaseModel):
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowNode(BaseModel):
    id: str
    type: str  # "agent" | "llm_prompt" | "http" | "condition" | "delay" | "trigger"
    position: NodePosition = Field(default_factory=NodePosition)
    data: NodeData = Field(default_factory=NodeData)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class WorkflowDefinition(BaseModel):
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class WorkflowTrigger(BaseModel):
    type: Literal["manual", "webhook", "schedule"]
    config: dict[str, Any] = Field(default_factory=dict)


# ── Workflow CRUD ─────────────────────────────────────────────────


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    definition: WorkflowDefinition = Field(default_factory=WorkflowDefinition)
    triggers: list[WorkflowTrigger] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: WorkflowDefinition | None = None
    triggers: list[WorkflowTrigger] | None = None
    is_active: bool | None = None


class WorkflowResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    definition: WorkflowDefinition
    triggers: list[WorkflowTrigger]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Execution ─────────────────────────────────────────────────────


class RunTriggerRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunStepResponse(BaseModel):
    id: str
    node_id: str
    node_type: str
    node_label: str
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    tenant_id: str
    status: str
    trigger_type: str
    trigger_data: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    steps: list[WorkflowRunStepResponse] = Field(default_factory=list)


class WebhookCreateResponse(BaseModel):
    id: str
    token: str
    url: str
