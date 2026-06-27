"""Initialize Qdrant collections for shared memory.

Run:
    cd backend
    PYTHONPATH=. python scripts/init_memory_qdrant.py
"""
from __future__ import annotations

import asyncio

import httpx

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings
from app.services.memory_vector_service import (
    AGENT_LOCAL_MEMORY_COLLECTION,
    CANDIDATE_MEMORY_COLLECTION,
    MEMORY_COLLECTION,
)


PAYLOAD_INDEX_FIELDS = (
    "org_id",
    "user_id",
    "status",
    "memory_type",
    "product_line",
    "rag_space_id",
    "task_id",
    "standard_code",
    "standard_version",
    "target_market",
    "agent_id",
    "task_type",
    "shareable",
)


def _headers() -> dict[str, str]:
    return {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}


async def _ensure_collection(client: httpx.AsyncClient, base_url: str, collection: str, vector_size: int) -> None:
    resp = await client.get(f"{base_url}/collections/{collection}", headers=_headers())
    if resp.status_code == 404:
        create = await client.put(
            f"{base_url}/collections/{collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            headers=_headers(),
        )
        create.raise_for_status()
    else:
        resp.raise_for_status()

    for field in PAYLOAD_INDEX_FIELDS:
        field_schema = "bool" if field == "shareable" else "keyword"
        index = await client.put(
            f"{base_url}/collections/{collection}/index",
            json={"field_name": field, "field_schema": field_schema},
            headers=_headers(),
        )
        if index.status_code not in {200, 409}:
            index.raise_for_status()


async def main() -> None:
    base_url = resolve_runtime_service_url(
        settings.qdrant_url,
        docker_base_url=settings.qdrant_docker_url,
    )
    vector_size = 1536
    async with httpx.AsyncClient(timeout=30.0) as client:
        for collection in (
            MEMORY_COLLECTION,
            CANDIDATE_MEMORY_COLLECTION,
            AGENT_LOCAL_MEMORY_COLLECTION,
        ):
            await _ensure_collection(client, base_url, collection, vector_size)
            print(f"OK: {collection}")


if __name__ == "__main__":
    asyncio.run(main())
