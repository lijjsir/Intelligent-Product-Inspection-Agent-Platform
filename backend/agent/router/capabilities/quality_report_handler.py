from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from agent.router.contracts import CapabilityContext
from app.core.permissions import ROLE_USER


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")


class QualityReportHandler:
    """Quality report/status query capability handler -- standalone handler with proper error boundaries."""

    async def run(self, context: CapabilityContext):
        from agent.router.executors.base import artifact, observation

        step = context.step
        state = context.state
        request = context.request
        db_session = context.db_session

        if db_session is None:
            return self._empty(step, state, "未提供数据库会话")

        from app.repositories.result_repo import ResultRepository
        from app.repositories.task_repo import TaskRepository

        task_repo = TaskRepository(db_session)
        result_repo = ResultRepository(db_session)
        task_id = self._extract_uuid(state.original_query) or str(request.metadata.get("task_id") or request.ext.get("task_id") or "").strip()
        product_id = str(request.product_id or request.metadata.get("product_id") or request.ext.get("product_id") or "").strip() or None
        owner_user_id = str(request.user_id or "").strip() if str(request.metadata.get("user_role") or "") == ROLE_USER else None

        task = await task_repo.get(request.org_id, task_id) if task_id else None
        result = await result_repo.get_by_task(request.org_id, str(task.id)) if task else None
        tasks: list[Any] = []
        total = 0
        results_by_task_id: dict[str, Any] = {}
        if task is None:
            tasks, total = await task_repo.list_paged(
                request.org_id,
                {"product_id": product_id} if product_id else {},
                page=1,
                size=10,
                owner_user_id=owner_user_id,
                order_by_recent=True,
            )
            task = tasks[0] if tasks else None
            result = await result_repo.get_by_task(request.org_id, str(task.id)) if task else None
            task_ids = [str(item.id) for item in tasks[:10]]
            for item_result in await result_repo.list_by_task_ids(request.org_id, task_ids):
                results_by_task_id[str(item_result.task_id)] = item_result

        if step.capability == "quality.task.status":
            content = (
                self._task_collection_content(tasks, total, product_id, results_by_task_id)
                if not task_id
                else self._task_content(task, result)
            )
            art_type = "task_status"
        else:
            content = self._report_content(task, result)
            art_type = "quality_report"
        found = bool(content.get("found"))
        art = artifact(
            step,
            art_type,
            status="success" if found else "empty",
            empty_result=not found,
            content=content,
            confidence=0.86 if found else 0.35,
            metrics={"report_count": 1 if found else 0, "found": found},
        )
        return (
            observation(
                step,
                status="success",
                summary="只读质量信息查询完成" if content.get("found") else "未找到匹配的质量信息",
                artifact_ids=[art.artifact_id],
                metrics={"found": bool(content.get("found"))},
            ),
            [art],
        )

    def _empty(self, step, state, reason: str):
        from agent.router.executors.base import artifact, observation

        art_type = "task_status" if step.capability == "quality.task.status" else "quality_report"
        art = artifact(
            step,
            art_type,
            status="empty",
            empty_result=True,
            content={"found": False, "query": state.original_query, "readonly": True, "summary": reason},
            confidence=0.2,
            metrics={"report_count": 0, "found": False},
        )
        return observation(step, status="skipped", summary=reason, artifact_ids=[art.artifact_id]), [art]

    @staticmethod
    def _extract_uuid(text: str) -> str | None:
        match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
        return match.group(0) if match else None

    @staticmethod
    def _format_score(value: Any) -> str:
        score = float(value) * 100
        if score.is_integer():
            return f"{score:.1f}"
        return f"{score:.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_verdict(value: Any) -> str:
        raw = str(value or "").strip()
        labels = {
            "pass": "通过",
            "fail": "不通过",
            "uncertain": "待定",
            "manual_required": "待人工审核",
        }
        return labels.get(raw.lower(), raw)

    @staticmethod
    def _format_datetime(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return source.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    @staticmethod
    def _task_content(task, result=None) -> dict[str, Any]:
        if task is None:
            return {"found": False, "readonly": True, "summary": "未找到匹配任务"}
        content = {
            "found": True,
            "readonly": True,
            "task_id": str(task.id),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "status": str(task.status),
            "priority": int(task.priority),
            "created_at": QualityReportHandler._format_datetime(getattr(task, "created_at", None)),
            "updated_at": QualityReportHandler._format_datetime(getattr(task, "updated_at", None)),
            "summary": f"任务 {task.id} 当前状态为 {task.status}",
        }
        if result is not None:
            content.update(
                {
                    "result_found": True,
                    "result_id": str(result.id),
                    "verdict": str(result.verdict),
                    "verdict_label": QualityReportHandler._format_verdict(result.verdict),
                    "overall_score": float(result.overall_score),
                    "result_created_at": QualityReportHandler._format_datetime(getattr(result, "created_at", None)),
                    "summary": (
                        f"任务 {task.id} 当前状态为 {task.status}，检测结果为 {QualityReportHandler._format_verdict(result.verdict)}，"
                        f"综合分 {QualityReportHandler._format_score(result.overall_score)}"
                    ),
                }
            )
        else:
            content["result_found"] = False
        return content

    @staticmethod
    def _task_collection_content(
        tasks: list[Any],
        total: int,
        product_id: str | None = None,
        results_by_task_id: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not tasks:
            return {
                "found": False,
                "readonly": True,
                "product_id": product_id,
                "total": 0,
                "tasks": [],
                "summary": "未找到匹配任务",
            }
        result_map = results_by_task_id or {}
        task_items = [
            QualityReportHandler._task_content(task, result_map.get(str(task.id)))
            for task in tasks
        ]
        status_counts: dict[str, int] = {}
        for item in task_items:
            status = str(item.get("status") or "").strip()
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
        scope_text = f"产品 {product_id} " if product_id else ""
        total_count = int(total or len(task_items))
        detail_lines = [
            f"{idx + 1}. {item.get('task_id')}，产品 {item.get('product_id')}，标准 {item.get('spec_code')}，状态 {item.get('status')}，创建时间 {item.get('created_at')}"
            + (
                f"，结果 {item.get('verdict_label') or item.get('verdict')}，综合分 {QualityReportHandler._format_score(item.get('overall_score'))}，结果时间 {item.get('result_created_at')}"
                if item.get("result_found") and item.get("overall_score") is not None
                else "，暂无检测结果"
            )
            for idx, item in enumerate(task_items[:5])
        ]
        return {
            "found": True,
            "readonly": True,
            "product_id": product_id,
            "total": total_count,
            "status_counts": status_counts,
            "tasks": task_items,
            "summary": f"{scope_text}共找到 {total_count} 条质检任务，最近 {len(task_items)} 条已返回。\n" + "\n".join(detail_lines),
        }

    def _report_content(self, task, result) -> dict[str, Any]:
        if task is None:
            return {"found": False, "readonly": True, "summary": "未找到匹配任务或报告"}
        content = self._task_content(task)
        if result is None:
            content.update({"verdict": None, "result_found": False, "summary": "已找到任务，但尚未找到正式检测结果"})
            return content
        content.update(
            {
                "result_found": True,
                "result_id": str(result.id),
                "verdict": str(result.verdict),
                "verdict_label": self._format_verdict(result.verdict),
                "overall_score": float(result.overall_score),
                "defects": result.defects,
                "citations": result.citations,
                "reasoning_chain": result.reasoning_chain,
                "llm_model": str(result.llm_model),
                "prompt_version": str(result.prompt_version),
                "result_created_at": self._format_datetime(getattr(result, "created_at", None)),
                "summary": f"检测结果为 {self._format_verdict(result.verdict)}，综合分 {self._format_score(result.overall_score)}",
            }
        )
        return content
