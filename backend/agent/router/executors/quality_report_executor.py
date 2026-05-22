from __future__ import annotations

import re
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class QualityReportExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        if db_session is None:
            return self._empty(step, state, "未提供数据库会话")
        from app.repositories.result_repo import ResultRepository
        from app.repositories.task_repo import TaskRepository

        task_repo = TaskRepository(db_session)
        result_repo = ResultRepository(db_session)
        task_id = self._extract_uuid(state.original_query) or str(request.metadata.get("task_id") or request.ext.get("task_id") or "").strip()
        product_id = str(request.product_id or request.metadata.get("product_id") or request.ext.get("product_id") or "").strip() or None

        task = await task_repo.get(request.org_id, task_id) if task_id else None
        result = await result_repo.get_by_task(request.org_id, str(task.id)) if task else None
        if task is None:
            tasks, _ = await task_repo.list_paged(
                request.org_id,
                {"product_id": product_id} if product_id else {},
                page=1,
                size=1,
            )
            task = tasks[0] if tasks else None
            result = await result_repo.get_by_task(request.org_id, str(task.id)) if task else None

        if step.capability_key == "quality.task.status":
            content = self._task_content(task)
            art_type = "task_status"
        else:
            content = self._report_content(task, result)
            art_type = "quality_report"
        art = artifact(art_type, "quality_report", content, confidence=0.86 if content.get("found") else 0.35)
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

    def _empty(self, step: AgentPlanStep, state: ManagerState, reason: str) -> tuple[AgentObservation, list[AgentArtifact]]:
        art_type = "task_status" if step.capability_key == "quality.task.status" else "quality_report"
        art = artifact(
            art_type,
            "quality_report",
            {"found": False, "query": state.original_query, "readonly": True, "summary": reason},
            confidence=0.2,
        )
        return observation(step, status="skipped", summary=reason, artifact_ids=[art.artifact_id]), [art]

    @staticmethod
    def _extract_uuid(text: str) -> str | None:
        match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
        return match.group(0) if match else None

    @staticmethod
    def _task_content(task) -> dict[str, Any]:
        if task is None:
            return {"found": False, "readonly": True, "summary": "未找到匹配任务"}
        return {
            "found": True,
            "readonly": True,
            "task_id": str(task.id),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "status": str(task.status),
            "priority": int(task.priority),
            "created_at": str(task.created_at),
            "updated_at": str(task.updated_at),
            "summary": f"任务 {task.id} 当前状态为 {task.status}",
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
                "overall_score": float(result.overall_score),
                "defects": result.defects,
                "citations": result.citations,
                "reasoning_chain": result.reasoning_chain,
                "llm_model": str(result.llm_model),
                "prompt_version": str(result.prompt_version),
                "summary": f"检测结果为 {result.verdict}，综合分 {float(result.overall_score):.4f}",
            }
        )
        return content
