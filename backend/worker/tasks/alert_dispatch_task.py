"""Dispatch a created alert event through its configured notification channels.

Called asynchronously via Celery after an alert is persisted so notification
delivery (email, wecom, dingtalk) never blocks the inspection/quality pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Ensure the backend package is importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from worker.celery_app import celery_app
from infra.notification.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

DB_URL = os.getenv(
    "PIAP_DB_URL",
    "mysql+aiomysql://piap:piap@127.0.0.1:13306/piap_main",
)

SEVERITY_LABELS: dict[str, str] = {
    "critical": "严重",
    "error": "错误",
    "warning": "警告",
    "info": "提示",
}

ALERT_TYPE_LABELS: dict[str, str] = {
    "stability_risk": "稳定性风险",
    "quality_review": "质检审查",
}


def _format_alert_message(alert: dict[str, Any]) -> str:
    """Build a human-readable notification message from an alert row."""
    severity_label = SEVERITY_LABELS.get(alert.get("severity", ""), alert.get("severity", ""))
    type_label = ALERT_TYPE_LABELS.get(alert.get("alert_type", ""), alert.get("alert_type", ""))
    title = alert.get("title", "")
    detail = alert.get("detail") or {}
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (json.JSONDecodeError, TypeError):
            detail = {}

    lines: list[str] = []
    lines.append(f"[{severity_label}] {type_label}告警")
    lines.append(f"标题: {title}")

    risk_score = detail.get("risk_score") or detail.get("risk_level")
    if risk_score:
        lines.append(f"风险评分: {risk_score}")

    message = detail.get("message")
    if message:
        lines.append(f"详情: {message}")

    lines.append(f"时间: {alert.get('created_at', '')}")

    return "\n".join(lines)


async def _dispatch_alert_async(alert_id: str) -> None:
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            text(
                "SELECT id, org_id, alert_type, severity, title, detail, "
                "status, channels, created_at FROM alert_events WHERE id = :id"
            ),
            {"id": alert_id.encode() if isinstance(alert_id, str) else alert_id},
        )
        row = result.mappings().first()
        if not row:
            logger.warning("Alert %s not found, skipping dispatch", alert_id)
            await engine.dispose()
            return

        alert = dict(row)
        channels = alert.get("channels") or {}
        if isinstance(channels, str):
            try:
                channels = json.loads(channels)
            except (json.JSONDecodeError, TypeError):
                channels = {}

        if not channels:
            logger.info("Alert %s has no channels configured, skipping dispatch", alert_id)
            await engine.dispose()
            return

        message = _format_alert_message(alert)
        dispatcher = Dispatcher()

        for channel, enabled in channels.items():
            if not enabled or channel == "in_app":
                continue
            try:
                await dispatcher.dispatch(channel, message)
                logger.info("Dispatched alert %s via %s", alert_id, channel)
            except Exception:
                logger.exception("Failed to dispatch alert %s via %s", alert_id, channel)

        # Mark as dispatched.
        now = datetime.now(timezone.utc)
        await session.execute(
            text("UPDATE alert_events SET dispatched_at = :now WHERE id = :id"),
            {
                "now": now,
                "id": alert_id.encode() if isinstance(alert_id, str) else alert_id,
            },
        )
        await session.commit()

    await engine.dispose()


@celery_app.task
def dispatch_alert(alert_id: str) -> None:
    """Celery task: dispatch a single alert through its notification channels."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            future = asyncio.run_coroutine_threadsafe(
                _dispatch_alert_async(alert_id), loop
            )
            future.result(timeout=30)
        else:
            asyncio.run(_dispatch_alert_async(alert_id))
    except Exception:
        logger.exception("dispatch_alert failed for alert_id=%s", alert_id)
