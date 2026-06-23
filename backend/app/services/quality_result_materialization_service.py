from __future__ import annotations

from typing import Any


class QualityResultMaterializationService:
    """质量检测结果落库服务 — 从 QualityAnalysisGraph 调用。

    封装 ResultRepository、StabilityRepository、TaskRepository、
    TaskExecutionEventRepository 的写入逻辑。
    """

    def __init__(self, db_session):
        self.db = db_session

    async def build_persistable_output(
        self,
        *,
        org_id: str,
        workflow_run_id: str,
        final_state: dict[str, Any],
        standard_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        """构建可用于持久化的结构化输出。"""
        assessment = final_state.get("final_assessment") or {}
        answer = final_state.get("answer") or ""
        report = final_state.get("report") or ""

        return {
            "org_id": org_id,
            "workflow_run_id": workflow_run_id,
            "verdict": assessment.get("final_verdict", "uncertain"),
            "overall_score": assessment.get("overall_score", 0.0),
            "risk_level": assessment.get("risk_level", "low"),
            "report": report,
            "answer": answer,
            "standard_evaluation": standard_evaluation,
            "defects": assessment.get("defects") or [],
            "citations": final_state.get("citations") or [],
            "stability": final_state.get("standard_evaluation") or {},
        }

    async def persist_success(
        self,
        *,
        task_id: str,
        org_id: str,
        final_state: dict[str, Any],
        standard_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        """任务成功时持久化结果。"""
        try:
            from app.repositories.result_repo import ResultRepository
            from app.repositories.task_repo import TaskRepository

            persistable = await self.build_persistable_output(
                org_id=org_id,
                workflow_run_id=final_state.get("workflow_run_id", ""),
                final_state=final_state,
                standard_evaluation=standard_evaluation,
            )

            await ResultRepository(self.db).upsert_by_task(
                org_id=org_id,
                task_id=task_id,
                result_data=persistable,
            )

            await TaskRepository(self.db).update_status(
                org_id=org_id,
                task_id=task_id,
                status="done",
            )

            return {"status": "persisted", "task_id": task_id}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def persist_failure(
        self,
        *,
        task_id: str,
        org_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        """任务失败时记录错误。"""
        try:
            from app.repositories.task_repo import TaskRepository

            await TaskRepository(self.db).update_status(
                org_id=org_id,
                task_id=task_id,
                status="failed",
                error=error_message,
            )

            return {"status": "failed_logged", "task_id": task_id}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def emit_event(
        self,
        *,
        task_id: str,
        org_id: str,
        event_type: str,
        message: str,
        stage: str | None = None,
    ) -> None:
        """发送 SSE 事件。"""
        try:
            from app.repositories.task_execution_event_repo import TaskExecutionEventRepository

            await TaskExecutionEventRepository(self.db).create(
                org_id=org_id,
                task_id=task_id,
                event_type=event_type,
                message=message,
                stage=stage,
            )
        except Exception:
            pass
