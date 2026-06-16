"""MySQLCheckpointer — LangGraph-compatible checkpoint saver backed by MySQL.

Stores graph state snapshots in graph_checkpoints table.
Only used for MemoryManagerGraph governance replay and long workflow recovery.
Chat history stays on chat_messages.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Sequence

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

logger = logging.getLogger(__name__)

THREAD_PREFIX_MEMORY = "memory"


class MySQLCheckpointer(BaseCheckpointSaver):
    """LangGraph-compatible checkpointer using MySQL graph_checkpoints table."""

    def __init__(self, session_factory):
        super().__init__(serde=JsonPlusSerializer())
        self._session_factory = session_factory

    @staticmethod
    def thread_id_memory(org_id: str, trace_id: str) -> str:
        return f"{THREAD_PREFIX_MEMORY}:{org_id}:{trace_id}"

    # ---- async LangGraph interface ----

    async def aget(self, config: dict) -> CheckpointTuple | None:
        thread_id = str(config.get("configurable", {}).get("thread_id", ""))
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if not thread_id:
            return None

        from sqlalchemy import select, desc
        from app.models.graph_checkpoint import GraphCheckpoint

        async with self._session_factory() as session:
            stmt = select(GraphCheckpoint).where(
                GraphCheckpoint.thread_id == thread_id
            ).order_by(desc(GraphCheckpoint.id))
            if checkpoint_id:
                stmt = stmt.where(GraphCheckpoint.checkpoint_id == checkpoint_id)
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if not row:
            return None

        try:
            checkpoint = self.serde.loads_typed(json.loads(row.checkpoint))
        except Exception:
            logger.debug("Failed to decode checkpoint %s", row.checkpoint_id, exc_info=True)
            return None

        metadata: CheckpointMetadata = json.loads(row.metadata_json) if row.metadata_json else {}
        parent_config = (
            {"configurable": {"thread_id": thread_id, "checkpoint_id": row.parent_checkpoint_id}}
            if row.parent_checkpoint_id else None
        )
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_id": row.checkpoint_id}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        thread_id = str(config.get("configurable", {}).get("thread_id", ""))
        checkpoint_ns = str(config.get("configurable", {}).get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint.get("id", ""))
        parent_checkpoint_id = str(
            config.get("configurable", {}).get("checkpoint_id", "")
        ) or None

        serialized = self.serde.dumps_typed(checkpoint)
        row_data = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id if parent_checkpoint_id else None,
            "type": "checkpoint",
            "checkpoint": json.dumps(serialized, ensure_ascii=False),
            "metadata_json": json.dumps(metadata, ensure_ascii=False, default=str) if metadata else None,
            "created_at": datetime.now(timezone.utc),
        }

        from app.models.graph_checkpoint import GraphCheckpoint

        async with self._session_factory() as session:
            session.add(GraphCheckpoint(**row_data))
            await session.flush()
            await session.commit()

        return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}

    async def aput_writes(
        self,
        config: dict,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        raise NotImplementedError(
            "MySQLCheckpointer.aput_writes is intentionally unsupported; "
            "memory graph workflows must not silently drop intermediate writes."
        )

    async def alist(
        self,
        config: dict | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        from sqlalchemy import select, desc
        from app.models.graph_checkpoint import GraphCheckpoint

        thread_id = str(config.get("configurable", {}).get("thread_id", "")) if config else ""

        async with self._session_factory() as session:
            stmt = select(GraphCheckpoint).order_by(desc(GraphCheckpoint.id))
            if thread_id:
                stmt = stmt.where(GraphCheckpoint.thread_id == thread_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        for row in rows:
            try:
                checkpoint = self.serde.loads_typed(json.loads(row.checkpoint))
            except Exception:
                continue
            metadata: CheckpointMetadata = json.loads(row.metadata_json) if row.metadata_json else {}
            yield CheckpointTuple(
                config={"configurable": {"thread_id": row.thread_id, "checkpoint_id": row.checkpoint_id}},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
            )

    async def adelete_thread(self, thread_id: str) -> None:
        from sqlalchemy import delete
        from app.models.graph_checkpoint import GraphCheckpoint

        async with self._session_factory() as session:
            await session.execute(
                delete(GraphCheckpoint).where(GraphCheckpoint.thread_id == thread_id)
            )
            await session.commit()
