"""Tests for checkpointing — save, load, prune, and resume."""

from __future__ import annotations

import json

import pytest

from smn.core.checkpoint import Checkpoint, CheckpointStore, DBCheckpointStore


class TestCheckpoint:
    def test_create(self):
        cp = Checkpoint(
            task_id="t1", agent_id="a1", step=3,
            messages=[{"role": "user", "content": "hi"}],
            budget_entries=[], audit_ids=["aud1"],
        )
        assert cp.task_id == "t1"
        assert cp.step == 3
        assert cp.status == "in_progress"
        assert cp.created_at  # auto-populated

    def test_to_json_and_back(self):
        cp = Checkpoint(
            task_id="t1", agent_id="a1", step=2,
            messages=[{"role": "system", "content": "sys"}],
            budget_entries=[{"amount": 0.01}],
            audit_ids=["x", "y"],
        )
        json_str = cp.to_json()
        restored = Checkpoint.from_json(json_str)
        assert restored.task_id == cp.task_id
        assert restored.step == cp.step
        assert restored.messages == cp.messages
        assert restored.audit_ids == cp.audit_ids

    def test_created_at_default(self):
        cp = Checkpoint(
            task_id="t1", agent_id="a1", step=0,
            messages=[], budget_entries=[], audit_ids=[],
        )
        assert "T" in cp.created_at  # ISO format


class TestCheckpointStore:
    def test_save_and_get_latest(self):
        store = CheckpointStore()
        cp1 = Checkpoint("t1", "a1", 1, [], [], [])
        cp2 = Checkpoint("t1", "a1", 2, [], [], [])
        store.save(cp1)
        store.save(cp2)

        latest = store.get_latest("t1")
        assert latest is not None
        assert latest.step == 2

    def test_get_latest_empty(self):
        store = CheckpointStore()
        assert store.get_latest("nonexistent") is None

    def test_get_all(self):
        store = CheckpointStore()
        for i in range(5):
            store.save(Checkpoint("t1", "a1", i, [], [], []))
        assert len(store.get_all("t1")) == 5

    def test_prune_keeps_latest(self):
        store = CheckpointStore()
        for i in range(10):
            store.save(Checkpoint("t1", "a1", i, [], [], []))
        pruned = store.prune("t1", keep_last=3)
        assert pruned == 7
        remaining = store.get_all("t1")
        assert len(remaining) == 3
        assert remaining[0].step == 7  # kept the last 3

    def test_prune_no_op_when_few(self):
        store = CheckpointStore()
        store.save(Checkpoint("t1", "a1", 0, [], [], []))
        assert store.prune("t1", keep_last=5) == 0

    def test_delete(self):
        store = CheckpointStore()
        store.save(Checkpoint("t1", "a1", 0, [], [], []))
        store.delete("t1")
        assert store.get_latest("t1") is None

    def test_task_ids(self):
        store = CheckpointStore()
        store.save(Checkpoint("t1", "a1", 0, [], [], []))
        store.save(Checkpoint("t2", "a1", 0, [], [], []))
        assert set(store.task_ids) == {"t1", "t2"}


class TestDBCheckpointStore:
    @pytest.mark.asyncio
    async def test_save_and_load_from_db(self, db):
        store = DBCheckpointStore()
        cp = Checkpoint(
            task_id="t1", agent_id="a1", step=5,
            messages=[{"role": "user", "content": "test"}],
            budget_entries=[{"cost": 0.01}],
            audit_ids=["aud1"],
        )
        await store.save_to_db(cp, db)

        loaded = await store.load_from_db("t1", db)
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.step == 5
        assert loaded.messages == [{"role": "user", "content": "test"}]

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, db):
        store = DBCheckpointStore()
        assert await store.load_from_db("nonexistent", db) is None

    @pytest.mark.asyncio
    async def test_latest_is_highest_step(self, db):
        store = DBCheckpointStore()
        for i in range(3):
            cp = Checkpoint("t1", "a1", i, [], [], [])
            await store.save_to_db(cp, db)

        loaded = await store.load_from_db("t1", db)
        assert loaded is not None
        assert loaded.step == 2
