"""Task Worker — Celery-based async task execution.

Enables long-running agent tasks to execute outside the HTTP request cycle.
Tasks are dispatched from the API and executed by background workers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery

from smn.config import settings

logger = logging.getLogger(__name__)

# ── Celery app ───────────────────────────────────────────────────

celery_app = Celery(
    "smn",
    broker=settings.task_queue_backend,
    backend=settings.task_queue_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)


def _run_async(coro):
    """Run an async coroutine in a new event loop (for Celery tasks)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="smn.execute_task", max_retries=2)
def execute_task_async(self, task_id: str, agent_id: str, input_text: str):
    """Execute an agent task asynchronously via Celery.

    This is the Celery task that runs the governed ReAct loop
    outside the HTTP request lifecycle.
    """
    _run_async(_execute_task_impl(self, task_id, agent_id, input_text))


async def _execute_task_impl(self, task_id: str, agent_id: str, input_text: str):
    """Async implementation of the Celery task."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from smn.core.agent import Agent
    from smn.core.policy import load_policy
    from smn.models import AgentRecord, TaskRecord

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        try:
            # Load agent
            result = await db.execute(select(AgentRecord).where(AgentRecord.id == agent_id))
            agent_rec = result.scalar_one_or_none()
            if not agent_rec:
                logger.error("Agent %s not found for task %s", agent_id, task_id)
                return

            # Update task status
            result = await db.execute(select(TaskRecord).where(TaskRecord.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error("Task %s not found", task_id)
                return

            task.status = "running"
            await db.flush()

            # Build runtime agent
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

            # Execute
            agent_result = await agent.run(input_text, db_session=db)

            # Update task record
            task.status = agent_result.status
            task.output_text = agent_result.output
            task.error = agent_result.error
            task.total_cost_usd = agent_result.cost_usd
            task.total_steps = agent_result.steps
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Task %s completed: status=%s, cost=$%.4f",
                task_id,
                agent_result.status,
                agent_result.cost_usd,
            )

        except Exception as exc:
            # Update task as failed
            result = await db.execute(select(TaskRecord).where(TaskRecord.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error = str(exc)
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()

            logger.exception("Task %s failed: %s", task_id, exc)

            # Retry if applicable
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))

    await engine.dispose()
