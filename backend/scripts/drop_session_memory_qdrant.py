"""Delete the removed short-term session memory Qdrant collection.

Run:
    cd backend
    PYTHONPATH=. python scripts/drop_session_memory_qdrant.py
"""
from __future__ import annotations

import asyncio

import httpx

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings


SESSION_MEMORY_COLLECTION = "piap_session_memory"


def _headers() -> dict[str, str]:
    return {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}


async def main() -> None:
    base_url = resolve_runtime_service_url(
        settings.qdrant_url,
        docker_base_url=settings.qdrant_docker_url,
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{base_url}/collections/{SESSION_MEMORY_COLLECTION}",
            headers=_headers(),
        )
        if resp.status_code == 404:
            print(f"OK: {SESSION_MEMORY_COLLECTION} already absent")
            return
        resp.raise_for_status()
        print(f"OK: deleted {SESSION_MEMORY_COLLECTION}")


if __name__ == "__main__":
    asyncio.run(main())
