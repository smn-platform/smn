"""Streaming API — Server-Sent Events endpoint for real-time task execution."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smn.auth import get_current_tenant
from smn.core.agent import Agent
from smn.core.policy import load_policy
from smn.core.runtime import execute_task_stream
from smn.db import get_db
from smn.models import AgentRecord, Tenant

router = APIRouter(prefix="/stream")


class StreamTaskRequest(BaseModel):
    agent_id: str
    input_text: str


@router.post("")
async def stream_task(
    body: StreamTaskRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Execute a task with real-time SSE streaming of governance events."""
    result = await db.execute(
        select(AgentRecord).where(
            AgentRecord.id == body.agent_id,
            AgentRecord.tenant_id == tenant.id,
        )
    )
    agent_rec = result.scalar_one_or_none()
    if not agent_rec:
        raise HTTPException(404, "Agent not found")
    if not agent_rec.is_active:
        raise HTTPException(400, "Agent is deactivated")

    policy = load_policy(agent_rec.policy_name)
    agent = Agent(
        name=agent_rec.name,
        description=agent_rec.description,
        model=agent_rec.model,
        scopes=agent_rec.scope_list,
        risk_level=agent_rec.risk_level,
        policy=policy,
        max_cost_per_task=agent_rec.max_cost_per_task,
        tenant_id=agent_rec.tenant_id,
    )

    async def _sse_generator():
        async for event in execute_task_stream(agent, body.input_text, db_session=db):
            payload = json.dumps(event.data, default=str)
            yield f"event: {event.event}\ndata: {payload}\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
