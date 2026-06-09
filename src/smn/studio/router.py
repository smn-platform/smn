"""Studio FastAPI router — workflow CRUD, execution, webhooks.

Mounted at ``/studio/api/v1`` on the main SMN FastAPI application.
All endpoints (except ``POST /studio/webhooks/{token}``) require the standard
SMN API key via ``X-API-Key``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.auth import get_current_tenant
from smn.models import Tenant
from smn.studio.db import get_studio_db, studio_async_session
from smn.studio.executor import execute_workflow
from smn.studio.models import WebhookToken, Workflow, WorkflowRun, WorkflowRunStep
from smn.studio.schemas import (
    RunTriggerRequest,
    WebhookCreateResponse,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowResponse,
    WorkflowRunResponse,
    WorkflowRunStepResponse,
    WorkflowTrigger,
    WorkflowUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio/api/v1")

_NOW = lambda: datetime.now(timezone.utc)


# ── Serialisation helpers ─────────────────────────────────────────


def _to_response(w: Workflow) -> WorkflowResponse:
    definition = WorkflowDefinition.model_validate_json(w.definition)
    triggers_raw: list[dict] = json.loads(w.triggers or "[]")
    triggers = [WorkflowTrigger.model_validate(t) for t in triggers_raw]
    return WorkflowResponse(
        id=w.id,
        tenant_id=w.tenant_id,
        name=w.name,
        description=w.description or "",
        definition=definition,
        triggers=triggers,
        is_active=bool(w.is_active),
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


def _steps_to_response(steps: list[WorkflowRunStep]) -> list[WorkflowRunStepResponse]:
    return [
        WorkflowRunStepResponse(
            id=s.id,
            node_id=s.node_id,
            node_type=s.node_type,
            node_label=s.node_label or "",
            status=s.status,
            input_data=json.loads(s.input_data) if s.input_data else None,
            output_data=json.loads(s.output_data) if s.output_data else None,
            error=s.error,
            started_at=s.started_at,
            completed_at=s.completed_at,
            duration_ms=s.duration_ms,
        )
        for s in steps
    ]


def _run_to_response(
    run: WorkflowRun,
    steps: list[WorkflowRunStep],
) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        tenant_id=run.tenant_id,
        status=run.status,
        trigger_type=run.trigger_type,
        trigger_data=json.loads(run.trigger_data) if run.trigger_data else None,
        output=json.loads(run.output) if run.output else None,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        steps=_steps_to_response(steps),
    )


# ── Background execution (own session so request lifecycle is irrelevant) ──


async def _exec_bg(
    workflow_id: str,
    run_id: str,
    definition: WorkflowDefinition,
    trigger_data: dict[str, Any],
) -> None:
    async with studio_async_session() as db:
        try:
            await execute_workflow(workflow_id, run_id, definition, trigger_data, db)
        except Exception:
            logger.exception(
                "Unhandled error in workflow %s run %s", workflow_id, run_id
            )


# ── Workflow CRUD ─────────────────────────────────────────────────


@router.post("/workflows", status_code=201, response_model=WorkflowResponse, tags=["studio"])
async def create_workflow(
    body: WorkflowCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WorkflowResponse:
    w = Workflow(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
        definition=body.definition.model_dump_json(),
        triggers=json.dumps([t.model_dump() for t in body.triggers]),
        created_at=_NOW(),
        updated_at=_NOW(),
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return _to_response(w)


@router.get("/workflows", response_model=list[WorkflowResponse], tags=["studio"])
async def list_workflows(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> list[WorkflowResponse]:
    result = await db.execute(
        select(Workflow)
        .where(Workflow.tenant_id == tenant.id)
        .order_by(Workflow.created_at.desc())
    )
    return [_to_response(w) for w in result.scalars()]


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["studio"])
async def get_workflow(
    workflow_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WorkflowResponse:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")
    return _to_response(w)


@router.put("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["studio"])
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WorkflowResponse:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")

    if body.name is not None:
        w.name = body.name
    if body.description is not None:
        w.description = body.description
    if body.definition is not None:
        w.definition = body.definition.model_dump_json()
    if body.triggers is not None:
        w.triggers = json.dumps([t.model_dump() for t in body.triggers])
    if body.is_active is not None:
        w.is_active = body.is_active

    w.updated_at = _NOW()
    await db.commit()
    await db.refresh(w)
    return _to_response(w)


@router.delete("/workflows/{workflow_id}", status_code=204, tags=["studio"])
async def delete_workflow(
    workflow_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> None:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")
    await db.delete(w)
    await db.commit()


# ── Execution ─────────────────────────────────────────────────────


@router.post(
    "/workflows/{workflow_id}/run",
    status_code=202,
    response_model=WorkflowRunResponse,
    tags=["studio"],
)
async def trigger_workflow(
    workflow_id: str,
    body: RunTriggerRequest,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WorkflowRunResponse:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")
    if not w.is_active:
        raise HTTPException(409, "Workflow is inactive")

    definition = WorkflowDefinition.model_validate_json(w.definition)
    run_id = str(uuid.uuid4())

    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        tenant_id=tenant.id,
        status="pending",
        trigger_type="manual",
        trigger_data=json.dumps(body.input),
        created_at=_NOW(),
    )
    db.add(run)
    await db.commit()

    background_tasks.add_task(_exec_bg, workflow_id, run_id, definition, body.input)
    return _run_to_response(run, [])


@router.get(
    "/workflows/{workflow_id}/runs",
    response_model=list[WorkflowRunResponse],
    tags=["studio"],
)
async def list_runs(
    workflow_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> list[WorkflowRunResponse]:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")

    rows = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(50)
    )
    out = []
    for run in rows.scalars():
        step_rows = await db.execute(
            select(WorkflowRunStep).where(WorkflowRunStep.run_id == run.id)
        )
        out.append(_run_to_response(run, list(step_rows.scalars())))
    return out


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse, tags=["studio"])
async def get_run(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WorkflowRunResponse:
    run = await db.get(WorkflowRun, run_id)
    if not run or run.tenant_id != tenant.id:
        raise HTTPException(404, "Run not found")

    step_rows = await db.execute(
        select(WorkflowRunStep).where(WorkflowRunStep.run_id == run_id)
    )
    return _run_to_response(run, list(step_rows.scalars()))


# ── Webhooks ──────────────────────────────────────────────────────


@router.post(
    "/workflows/{workflow_id}/webhooks",
    status_code=201,
    response_model=WebhookCreateResponse,
    tags=["studio"],
)
async def create_webhook(
    workflow_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_studio_db),
) -> WebhookCreateResponse:
    w = await db.get(Workflow, workflow_id)
    if not w or w.tenant_id != tenant.id:
        raise HTTPException(404, "Workflow not found")

    token = WebhookToken(
        workflow_id=workflow_id,
        tenant_id=tenant.id,
        created_at=_NOW(),
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    return WebhookCreateResponse(
        id=token.id,
        token=token.token,
        url=f"/studio/webhooks/{token.token}",
    )


@router.post("/webhooks/{token}", status_code=202, tags=["studio"])
async def receive_webhook(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_studio_db),
) -> dict[str, str]:
    """Inbound webhook trigger — no API key required, token is the auth."""
    result = await db.execute(
        select(WebhookToken).where(
            WebhookToken.token == token,
            WebhookToken.is_active == True,  # noqa: E712
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")

    w = await db.get(Workflow, wh.workflow_id)
    if not w or not w.is_active:
        raise HTTPException(409, "Workflow is inactive")

    try:
        body: Any = await request.json()
    except Exception:
        body = {}

    definition = WorkflowDefinition.model_validate_json(w.definition)
    run_id = str(uuid.uuid4())
    trigger_data = {"body": body, "headers": dict(request.headers)}

    run = WorkflowRun(
        id=run_id,
        workflow_id=w.id,
        tenant_id=wh.tenant_id,
        status="pending",
        trigger_type="webhook",
        trigger_data=json.dumps(trigger_data),
        created_at=_NOW(),
    )
    db.add(run)
    await db.commit()

    background_tasks.add_task(_exec_bg, w.id, run_id, definition, trigger_data)
    return {"run_id": run_id, "status": "accepted"}
