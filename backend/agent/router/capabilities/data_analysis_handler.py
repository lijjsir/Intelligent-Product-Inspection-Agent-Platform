from __future__ import annotations

from agent.router.contracts import CapabilityContext


class DataAnalysisHandler:
    """Data analysis capability handler -- standalone handler with proper error boundaries."""

    async def run(self, context: CapabilityContext):
        from agent.router.executors.base import artifact, observation

        step = context.step
        state = context.state
        request = context.request
        db_session = context.db_session

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
                from agent.router.contracts import AgentExecutionError
                raise AgentExecutionError(
                    code="DATA_ANALYSIS_FAILED",
                    message="数据分析查询失败，无法完成当前统计分析。",
                    detail={"raw_error": str(exc)},
                    frontend_visible=True,
                ) from exc

        stats = content.get("inspection_task_stats", {})
        art = artifact(
            step,
            "data_analysis",
            content=content,
            confidence=0.72,
            metrics={"total_tasks": stats.get("task_count", 0), "done_tasks": stats.get("done_count", 0), "failed_tasks": stats.get("failed_count", 0)},
        )
        return observation(step, status="success", summary="数据分析只读统计完成", artifact_ids=[art.artifact_id]), [art]
