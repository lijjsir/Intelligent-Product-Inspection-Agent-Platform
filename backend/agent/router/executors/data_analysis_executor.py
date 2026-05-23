from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class DataAnalysisExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        content = {
            "implemented": True,
            "readonly": True,
            "summary": "当前数据分析 Agent 已接入只读统计入口。正式分析执行器可在后续扩展更复杂的数据集分析。",
            "query": state.original_query,
        }
        if db_session is not None:
            try:
                from sqlalchemy import text

                rows = (await db_session.execute(text(
                    """
                    SELECT
                      COUNT(*) AS task_count,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done_count,
                      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count
                    FROM inspection_tasks
                    WHERE org_id = UNHEX(REPLACE(:org_id, '-', ''))
                      AND deleted_at IS NULL
                    """
                ), {"org_id": request.org_id})).mappings().first()
                if rows:
                    content["inspection_task_stats"] = {
                        "task_count": int(rows["task_count"] or 0),
                        "done_count": int(rows["done_count"] or 0),
                        "failed_count": int(rows["failed_count"] or 0),
                    }
            except Exception as exc:
                content["warning"] = str(exc)
        art = artifact("data_analysis", "data_analysis", content, confidence=0.72)
        return observation(step, status="success", summary="数据分析只读统计完成", artifact_ids=[art.artifact_id]), [art]
