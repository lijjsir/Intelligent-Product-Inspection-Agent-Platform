from __future__ import annotations

import json
import logging
from datetime import timedelta

from infra.database.session import get_session
from app.core.config import settings
from app.core.datetime import utcnow
from app.repositories.export_job_repo import ExportJobRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.services.object_storage.factory import build_object_storage
from app.services.report_renderers import build_renderer

logger = logging.getLogger(__name__)


async def generate_report(*, job_id: str, org_id: str) -> None:
    async with get_session() as session:
        job_repo = ExportJobRepository(session)
        job = await job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"export job not found: {job_id}")

        await job_repo.update_status(job_id, "running")
        await session.commit()

        try:
            config = _parse_config(job.config_json)
            task_id = config.get("task_id")
            if not task_id:
                raise ValueError("missing task_id in config_json")

            task_repo = TaskRepository(session)
            task = await task_repo.get(org_id, task_id)
            if not task:
                raise ValueError(f"task not found: {task_id}")

            result_repo = ResultRepository(session)
            result = await result_repo.get_by_task(org_id, task_id)

            stability_repo = StabilityRepository(session)
            stability = await stability_repo.get_by_task(org_id, task_id)

            report_data = {
                "report_name": job.report_name,
                "report_type_label": _type_label(job.report_type),
                "task": {
                    "id": getattr(task, "id", None),
                    "product_id": getattr(task, "product_id", None),
                    "spec_code": getattr(task, "spec_code", None),
                },
                "result": {
                    "verdict": getattr(result, "verdict", None) if result else None,
                    "overall_score": getattr(result, "overall_score", None) if result else None,
                    "defects": getattr(result, "defects", None) if result else [],
                    "llm_model": getattr(result, "llm_model", None) if result else None,
                    "tokens_used": getattr(result, "tokens_used", None) if result else None,
                    "latency_ms": getattr(result, "latency_ms", None) if result else None,
                },
                "stability": {
                    "evidence_score": getattr(stability, "evidence_score", None) if stability else None,
                    "consistency_score": getattr(stability, "consistency_score", None) if stability else None,
                    "confidence_score": getattr(stability, "confidence_score", None) if stability else None,
                    "traceability_score": getattr(stability, "traceability_score", None) if stability else None,
                    "anomaly_score": getattr(stability, "anomaly_score", None) if stability else None,
                    "risk_level": getattr(stability, "risk_level", None) if stability else None,
                },
            }

            renderer = build_renderer(job.format)
            pdf_bytes = renderer.render(report_data)

            object_key = f"{org_id}/{job_id}/report.{job.format}"
            storage = build_object_storage()
            bucket = settings.report_export_bucket
            storage.ensure_bucket(bucket)
            stored = storage.put_bytes(
                bucket=bucket,
                object_key=object_key,
                data=pdf_bytes,
                content_type=_content_type(job.format),
            )
            file_url = f"/api/v1/files/{bucket}/{object_key}"

            expires_at = utcnow() + timedelta(days=7)
            await job_repo.update_status(
                job_id,
                "success",
                file_url=file_url,
                file_size=len(pdf_bytes),
                expires_at=expires_at,
            )
            await session.commit()

        except Exception:
            await session.rollback()
            raise


def _parse_config(config_json: str | None) -> dict:
    if not config_json:
        return {}
    try:
        return json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _type_label(report_type: str) -> str:
    m = {
        "single_task": "单任务检测报告",
        "batch_summary": "批量检测汇总报告",
        "quality_analysis": "质量分析报告",
        "feedback_report": "异常反馈报告",
        "evidence_trace": "证据溯源报告",
    }
    return m.get(report_type, report_type)


def _content_type(format: str) -> str:
    m = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    return m.get(format, "application/octet-stream")
