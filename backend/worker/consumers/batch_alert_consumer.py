"""Consume alerts in batch from the pending queue.

Polled periodically (or triggered by a message) to drain alerts:pending
and dispatch each one through its configured notification channels.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from infra.notification.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

DB_URL = os.getenv(
    "PIAP_DB_URL",
    "mysql+aiomysql://piap:piap@127.0.0.1:13306/piap_main",
)

BATCH_SIZE = 50


async def consume_batch_alerts() -> int:
    """Fetch up to BATCH_SIZE undispatched open alerts and dispatch them.

    Returns the number of alerts that were dispatched.
    """
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dispatched = 0

    async with async_session() as session:
        result = await session.execute(
            text(
                "SELECT id, org_id, alert_type, severity, title, detail, "
                "status, channels, created_at FROM alert_events "
                "WHERE status = 'open' AND dispatched_at IS NULL "
                "ORDER BY created_at ASC LIMIT :limit"
            ),
            {"limit": BATCH_SIZE},
        )
        rows = result.mappings().all()

        if not rows:
            await engine.dispose()
            return 0

        dispatcher = Dispatcher()

        for row in rows:
            alert = dict(row)
            alert_id = alert.get("id")
            channels = alert.get("channels") or {}
            if isinstance(channels, str):
                try:
                    channels = json.loads(channels)
                except (json.JSONDecodeError, TypeError):
                    channels = {}

            if not channels:
                continue

            # Simple message (batch consumer uses a compact format).
            severity = alert.get("severity", "")
            title = alert.get("title", "")
            message = f"[{severity}] {title}"

            for channel, enabled in channels.items():
                if not enabled or channel == "in_app":
                    continue
                try:
                    await dispatcher.dispatch(channel, message)
                except Exception:
                    logger.exception(
                        "Batch dispatch failed for alert %s via %s", alert_id, channel
                    )

            if isinstance(alert_id, bytes):
                alert_id_str = alert_id.decode("utf-8")
            else:
                alert_id_str = str(alert_id)

            from datetime import datetime, timezone

            await session.execute(
                text(
                    "UPDATE alert_events SET dispatched_at = :now WHERE id = :id"
                ),
                {
                    "now": datetime.now(timezone.utc),
                    "id": alert_id,
                },
            )
            dispatched += 1

        await session.commit()

    await engine.dispose()
    logger.info("Batch dispatched %d alerts", dispatched)
    return dispatched
