"""Checkpointing — persist and resume agent execution state.

Enables:
- Automatic checkpoint after each ReAct step
- Resume from any checkpoint after crash/restart
- Checkpoint pruning to manage storage

Each checkpoint captures the full execution state:
messages, step count, budget, audit IDs, and tool results.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Serializable snapshot of task execution state."""

    task_id: str
    agent_id: str
    step: int
    messages: list[dict[str, Any]]
    budget_entries: list[dict[str, Any]]
    audit_ids: list[str]
    status: str = "in_progress"  # in_progress | completed | failed
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, data: str) -> "Checkpoint":
        d = json.loads(data)
        return cls(**d)


class CheckpointStore:
    """In-memory checkpoint store (can be backed by DB).

    Stores checkpoints keyed by task_id. The most recent checkpoint
    for each task is the resumption point.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[Checkpoint]] = {}

    def save(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint for a task."""
        self._store.setdefault(checkpoint.task_id, []).append(checkpoint)
        logger.debug(
            "checkpoint saved: task=%s step=%d", checkpoint.task_id, checkpoint.step
        )

    def get_latest(self, task_id: str) -> Checkpoint | None:
        """Get the most recent checkpoint for a task."""
        checkpoints = self._store.get(task_id, [])
        return checkpoints[-1] if checkpoints else None

    def get_all(self, task_id: str) -> list[Checkpoint]:
        """Get all checkpoints for a task, ordered by step."""
        return list(self._store.get(task_id, []))

    def prune(self, task_id: str, keep_last: int = 3) -> int:
        """Remove old checkpoints, keeping only the most recent N.

        Returns the number of pruned checkpoints.
        """
        checkpoints = self._store.get(task_id, [])
        if len(checkpoints) <= keep_last:
            return 0
        pruned = len(checkpoints) - keep_last
        self._store[task_id] = checkpoints[-keep_last:]
        return pruned

    def delete(self, task_id: str) -> None:
        """Remove all checkpoints for a completed task."""
        self._store.pop(task_id, None)

    @property
    def task_ids(self) -> list[str]:
        return list(self._store.keys())


# ── DB-backed checkpoint store ───────────────────────────────────


class DBCheckpointStore(CheckpointStore):
    """Checkpoint store backed by SQLAlchemy async sessions.

    Falls back to in-memory when no DB session is provided.
    """

    async def save_to_db(self, checkpoint: Checkpoint, db_session: Any) -> None:
        """Persist a checkpoint to the database."""
        from smn.models import CheckpointRecord

        record = CheckpointRecord(
            task_id=checkpoint.task_id,
            agent_id=checkpoint.agent_id,
            step=checkpoint.step,
            state_json=checkpoint.to_json(),
            status=checkpoint.status,
        )
        db_session.add(record)
        await db_session.flush()
        # Also keep in memory for fast access
        self.save(checkpoint)

    async def load_from_db(self, task_id: str, db_session: Any) -> Checkpoint | None:
        """Load the latest checkpoint from the database."""
        from sqlalchemy import select

        from smn.models import CheckpointRecord

        result = await db_session.execute(
            select(CheckpointRecord)
            .where(CheckpointRecord.task_id == task_id)
            .order_by(CheckpointRecord.step.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        checkpoint = Checkpoint.from_json(record.state_json)
        return checkpoint
