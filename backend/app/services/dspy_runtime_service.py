from __future__ import annotations

from app.services.runtime_profile_service import RuntimeProfileMeta, resolve_runtime_profile


async def resolve_dspy_runtime_profile(org_id: str, subgraph_key: str) -> RuntimeProfileMeta:
    return await resolve_runtime_profile(org_id, subgraph_key)
