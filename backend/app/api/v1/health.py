from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.schemas.common import ResponseEnvelope
from infra.database.session import get_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=ResponseEnvelope[dict[str, Any]])
async def live() -> ResponseEnvelope[dict[str, Any]]:
    return ResponseEnvelope(data={"status": "ok"})


@router.get("/ready", response_model=ResponseEnvelope[dict[str, Any]])
async def ready() -> ResponseEnvelope[dict[str, Any]]:
    checks: dict[str, str] = {}
    try:
        async with get_session() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"failed: {exc}"

    redis_client = Redis.from_url(settings.redis_url, socket_timeout=2.0, socket_connect_timeout=2.0)
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"failed: {exc}"
    finally:
        await redis_client.aclose()

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return ResponseEnvelope(data={"status": status, "checks": checks})
