from __future__ import annotations

from agent.rag.embedder import Embedder
from app.core.config import settings
from app.repositories.memory_repo import MemorySyncOutboxRepository
from app.services.memory_graph_factory import build_memory_graph_store
from app.services.memory_graph_store import MemoryGraphEdge, MemoryGraphNode
from app.services.memory_vector_service import MEMORY_COLLECTION, MemoryVectorService
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.memory_sync_outbox_task.process_memory_sync_outbox")
def process_memory_sync_outbox(org_id: str) -> dict:
    return run_celery_async(_process_memory_sync_outbox(org_id))


@celery_app.task(name="worker.tasks.memory_sync_outbox_task.dispatch_memory_sync_outbox")
def dispatch_memory_sync_outbox() -> dict:
    return run_celery_async(_dispatch_memory_sync_outbox())


async def _dispatch_memory_sync_outbox() -> dict:
    if not settings.memory_sync_outbox_enabled:
        return {"orgs": 0, "queued": [], "disabled": True}
    async with get_session() as session:
        org_ids = await MemorySyncOutboxRepository.list_pending_org_ids(
            session,
            max_retries=settings.memory_sync_outbox_max_retries,
        )
    queued: list[str] = []
    for org_id in org_ids:
        process_memory_sync_outbox.delay(org_id)
        queued.append(org_id)
    return {"orgs": len(queued), "queued": queued}


async def _process_memory_sync_outbox(org_id: str) -> dict:
    processed = 0
    failed = 0
    async with get_session() as session:
        repo = MemorySyncOutboxRepository(session, org_id)
        rows = await repo.claim_pending(
            limit=settings.memory_sync_outbox_batch_size,
            max_retries=settings.memory_sync_outbox_max_retries,
        )
        for row in rows:
            try:
                await _replay_outbox_row(session, org_id, row.target_backend, row.action, row.payload_json or {})
                await repo.mark_success(row.id)
                processed += 1
            except Exception as exc:
                await repo.mark_failed(row.id, str(exc))
                failed += 1
        await session.commit()
    return {"processed": processed, "failed": failed}


async def _replay_outbox_row(session, org_id: str, target_backend: str, action: str, payload: dict) -> None:
    backend = str(target_backend or "").lower()
    if backend == "qdrant":
        await _replay_qdrant(org_id, action, payload)
        return
    if backend == "neo4j":
        await _replay_neo4j(session, org_id, action, payload)
        return
    raise ValueError(f"Unsupported memory sync target_backend: {target_backend}")


async def _replay_qdrant(org_id: str, action: str, payload: dict) -> None:
    async def embedder_factory(text: str) -> list[float]:
        embedder = Embedder(
            org_id=org_id,
            user_id=str(payload.get("user_id") or "") or None,
            trace_id=str(payload.get("trace_id") or "") or None,
            allow_pseudo_fallback=False,
        )
        return await embedder.embed(text)

    vector = MemoryVectorService(
        collection=str(payload.get("collection") or MEMORY_COLLECTION),
        embedder_factory=embedder_factory,
        org_id=org_id,
        user_id=str(payload.get("user_id") or "") or None,
        trace_id=str(payload.get("trace_id") or "") or None,
    )
    if action == "upsert_memory":
        kwargs = dict(payload)
        kwargs.pop("collection", None)
        await vector.upsert_memory(**kwargs)
        return
    if action == "delete_memory":
        await vector.delete_memory(str(payload["memory_id"]))
        return
    raise ValueError(f"Unsupported qdrant outbox action: {action}")


async def _replay_neo4j(session, org_id: str, action: str, payload: dict) -> None:
    graph = build_memory_graph_store(session, org_id)
    if action == "upsert_memory_node":
        await graph.upsert_memory_node(MemoryGraphNode(**payload))
        return
    if action == "create_memory_edge":
        await graph.create_memory_edge(MemoryGraphEdge(**payload))
        return
    raise ValueError(f"Unsupported neo4j outbox action: {action}")
