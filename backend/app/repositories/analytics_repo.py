from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.models.result import InspectionResult
from app.models.stability import StabilityReport
from app.models.task import InspectionTask
from app.models.token_ledger import TokenUsageLedger


class AnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_overview(self, org_id: str, start_date: date | None = None, end_date: date | None = None) -> dict:
        summary = await self._get_overview_summary(org_id, start_date, end_date)

        return {
            "total_tasks": int(summary["total_tasks"]),
            "total_alerts": int(summary["total_alerts"]),
            "total_results": int(summary["total_results"]),
            "total_cost": float(summary["total_cost"]),
            "pass_rate": float(summary["pass_rate"]),
            "hallucination_rate": float(summary["hallucination_rate"]),
            "risk_yellow_rate": float(summary["risk_yellow_rate"]),
            "avg_risk_score": float(summary["avg_risk_score"]),
            "avg_latency_ms": float(summary["avg_latency_ms"]),
            "task_trend": await self._get_task_trend(org_id, start_date, end_date),
            "pass_rate_trend": await self._get_pass_rate_trend(org_id, start_date, end_date),
            "hallucination_trend": await self._get_hallucination_trend(org_id, start_date, end_date),
            "risk_distribution_trend": await self._get_risk_distribution_trend(org_id, start_date, end_date),
            "risk_distribution": await self._get_risk_distribution(org_id, start_date, end_date),
            "alert_distribution": await self._get_alert_distribution(org_id, start_date, end_date),
            "model_metrics": await self._get_model_metrics(org_id, start_date, end_date),
            "product_line_series": await self._get_product_line_series(org_id, start_date, end_date),
        }

    async def get_product_line_drilldown(
        self,
        org_id: str,
        product_line: str,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        size: int = 8,
    ) -> dict:
        task_count_stmt = select(func.count()).select_from(InspectionTask).where(
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        task_count_stmt = self._apply_range(task_count_stmt, InspectionTask.created_at, start_date, end_date)
        total_tasks = int((await self._session.scalar(task_count_stmt)) or 0)

        result_summary_stmt = select(
            func.count().label("total_results"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("pass_rate"),
            func.coalesce(func.avg(self._hallucination_case_expr()), 0.0).label("hallucination_rate"),
            func.coalesce(func.avg(InspectionResult.latency_ms), 0.0).label("avg_latency_ms"),
        ).select_from(InspectionResult).join(
            InspectionTask,
            InspectionTask.id == InspectionResult.task_id,
        ).where(
            InspectionResult.org_id == org_id,
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        result_summary_stmt = self._apply_range(result_summary_stmt, InspectionResult.created_at, start_date, end_date)
        result_summary = (await self._session.execute(result_summary_stmt)).one()

        cost_stmt = select(func.coalesce(func.sum(TokenUsageLedger.cost_amount), 0)).where(
            TokenUsageLedger.org_id == org_id,
            TokenUsageLedger.product_line == product_line,
        )
        cost_stmt = self._apply_range(cost_stmt, TokenUsageLedger.created_at, start_date, end_date)
        total_cost = round(float((await self._session.scalar(cost_stmt)) or 0.0), 4)

        trend_stmt = select(
            func.date(InspectionTask.created_at).label("bucket"),
            func.count().label("value"),
        ).where(
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        trend_stmt = self._apply_range(trend_stmt, InspectionTask.created_at, start_date, end_date)
        trend_stmt = trend_stmt.group_by(func.date(InspectionTask.created_at)).order_by(func.date(InspectionTask.created_at))
        task_trend_rows = (await self._session.execute(trend_stmt)).all()

        verdict_stmt = select(
            InspectionResult.verdict.label("name"),
            func.count().label("value"),
        ).select_from(InspectionResult).join(
            InspectionTask,
            InspectionTask.id == InspectionResult.task_id,
        ).where(
            InspectionResult.org_id == org_id,
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        verdict_stmt = self._apply_range(verdict_stmt, InspectionResult.created_at, start_date, end_date)
        verdict_stmt = verdict_stmt.group_by(InspectionResult.verdict).order_by(InspectionResult.verdict)
        verdict_rows = (await self._session.execute(verdict_stmt)).all()

        recent_total_stmt = select(func.count()).select_from(InspectionTask).where(
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        recent_total_stmt = self._apply_range(recent_total_stmt, InspectionTask.created_at, start_date, end_date)
        recent_tasks_total = int((await self._session.scalar(recent_total_stmt)) or 0)

        recent_stmt = select(
            InspectionTask.id,
            InspectionTask.status,
            InspectionTask.spec_code,
            InspectionTask.created_at,
        ).where(
            InspectionTask.org_id == org_id,
            InspectionTask.product_id == product_line,
        )
        recent_stmt = self._apply_range(recent_stmt, InspectionTask.created_at, start_date, end_date)
        recent_stmt = recent_stmt.order_by(InspectionTask.created_at.desc()).offset((page - 1) * size).limit(size)
        recent_rows = (await self._session.execute(recent_stmt)).all()

        return {
            "product_line": product_line,
            "total_tasks": total_tasks,
            "total_results": int(result_summary.total_results or 0),
            "pass_rate": round(float(result_summary.pass_rate or 0.0), 4),
            "hallucination_rate": round(float(result_summary.hallucination_rate or 0.0), 4),
            "avg_latency_ms": round(float(result_summary.avg_latency_ms or 0.0), 2),
            "total_cost": total_cost,
            "task_trend": [
                {"bucket": str(row.bucket), "value": float(row.value or 0)}
                for row in task_trend_rows
            ],
            "verdict_distribution": [
                {"name": str(row.name or "unknown"), "value": float(row.value or 0)}
                for row in verdict_rows
            ],
            "recent_tasks_total": recent_tasks_total,
            "recent_tasks_page": page,
            "recent_tasks_size": size,
            "recent_tasks": [
                {
                    "task_id": str(row.id),
                    "status": str(row.status),
                    "spec_code": str(row.spec_code),
                    "created_at": row.created_at,
                }
                for row in recent_rows
            ],
        }

    async def get_model_drilldown(
        self,
        org_id: str,
        model_key: str,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        size: int = 8,
    ) -> dict:
        ledger_stmt = select(
            TokenUsageLedger.result_id.label("result_id"),
            func.sum(TokenUsageLedger.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLedger.cost_amount).label("total_cost"),
        ).where(TokenUsageLedger.org_id == org_id)
        ledger_stmt = self._apply_range(ledger_stmt, TokenUsageLedger.created_at, start_date, end_date)
        ledger_stmt = ledger_stmt.group_by(TokenUsageLedger.result_id).subquery()

        summary_stmt = select(
            func.count().label("result_count"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("pass_rate"),
            func.coalesce(func.avg(self._hallucination_case_expr()), 0.0).label("hallucination_rate"),
            func.coalesce(func.avg(func.coalesce(ledger_stmt.c.total_tokens, 0)), 0.0).label("avg_tokens"),
            func.coalesce(func.sum(func.coalesce(ledger_stmt.c.total_cost, 0)), 0.0).label("total_cost"),
            func.coalesce(func.avg(InspectionResult.latency_ms), 0.0).label("avg_latency_ms"),
        ).select_from(InspectionResult).outerjoin(
            ledger_stmt,
            ledger_stmt.c.result_id == InspectionResult.id,
        ).where(
            InspectionResult.org_id == org_id,
            InspectionResult.llm_model == model_key,
        )
        summary_stmt = self._apply_range(summary_stmt, InspectionResult.created_at, start_date, end_date)
        summary_row = (await self._session.execute(summary_stmt)).one()

        distribution_stmt = select(
            InspectionTask.product_id.label("name"),
            func.count().label("value"),
        ).select_from(InspectionResult).join(
            InspectionTask,
            InspectionTask.id == InspectionResult.task_id,
        ).where(
            InspectionResult.org_id == org_id,
            InspectionTask.org_id == org_id,
            InspectionResult.llm_model == model_key,
        )
        distribution_stmt = self._apply_range(distribution_stmt, InspectionResult.created_at, start_date, end_date)
        distribution_stmt = distribution_stmt.group_by(InspectionTask.product_id).order_by(InspectionTask.product_id)
        distribution_rows = (await self._session.execute(distribution_stmt)).all()

        recent_total_stmt = select(func.count()).select_from(InspectionResult).where(
            InspectionResult.org_id == org_id,
            InspectionResult.llm_model == model_key,
        )
        recent_total_stmt = self._apply_range(recent_total_stmt, InspectionResult.created_at, start_date, end_date)
        recent_results_total = int((await self._session.scalar(recent_total_stmt)) or 0)

        recent_stmt = select(
            InspectionResult.id,
            InspectionResult.task_id,
            InspectionTask.product_id,
            InspectionResult.verdict,
            InspectionResult.overall_score,
            InspectionResult.created_at,
        ).select_from(InspectionResult).join(
            InspectionTask,
            InspectionTask.id == InspectionResult.task_id,
        ).where(
            InspectionResult.org_id == org_id,
            InspectionTask.org_id == org_id,
            InspectionResult.llm_model == model_key,
        )
        recent_stmt = self._apply_range(recent_stmt, InspectionResult.created_at, start_date, end_date)
        recent_stmt = recent_stmt.order_by(InspectionResult.created_at.desc()).offset((page - 1) * size).limit(size)
        recent_rows = (await self._session.execute(recent_stmt)).all()

        return {
            "model_key": model_key,
            "result_count": int(summary_row.result_count or 0),
            "pass_rate": round(float(summary_row.pass_rate or 0.0), 4),
            "hallucination_rate": round(float(summary_row.hallucination_rate or 0.0), 4),
            "avg_tokens": round(float(summary_row.avg_tokens or 0.0), 2),
            "total_cost": round(float(summary_row.total_cost or 0.0), 4),
            "avg_latency_ms": round(float(summary_row.avg_latency_ms or 0.0), 2),
            "product_line_distribution": [
                {"name": str(row.name or "unknown"), "value": float(row.value or 0)}
                for row in distribution_rows
            ],
            "recent_results_total": recent_results_total,
            "recent_results_page": page,
            "recent_results_size": size,
            "recent_results": [
                {
                    "result_id": str(row.id),
                    "task_id": str(row.task_id),
                    "product_line": str(row.product_id or "unknown"),
                    "verdict": str(row.verdict),
                    "overall_score": float(row.overall_score or 0.0),
                    "created_at": row.created_at,
                }
                for row in recent_rows
            ],
        }

    async def get_task_drilldown(self, org_id: str, task_id: str) -> dict:
        task_stmt = select(InspectionTask).where(
            InspectionTask.org_id == org_id,
            InspectionTask.id == task_id,
        )
        task = (await self._session.execute(task_stmt)).scalar_one_or_none()
        if task is None:
            return {}

        result_stmt = select(InspectionResult).where(
            InspectionResult.org_id == org_id,
            InspectionResult.task_id == task_id,
        ).order_by(InspectionResult.created_at.desc())
        result = (await self._session.execute(result_stmt)).scalars().first()

        stability_stmt = select(StabilityReport).where(
            StabilityReport.org_id == org_id,
            StabilityReport.task_id == task_id,
        ).order_by(StabilityReport.created_at.desc())
        stability = (await self._session.execute(stability_stmt)).scalars().first()

        ledger_stmt = select(TokenUsageLedger).where(
            TokenUsageLedger.org_id == org_id,
            TokenUsageLedger.task_id == task_id,
        )
        ledgers = list((await self._session.execute(ledger_stmt)).scalars().all())

        alert_summaries: list[dict] = []
        open_alert_count = 0
        if stability is not None:
            alerts_stmt = select(AlertEvent).where(
                AlertEvent.org_id == org_id,
                AlertEvent.stability_id == str(stability.id),
            ).order_by(AlertEvent.created_at.desc())
            alerts = list((await self._session.execute(alerts_stmt)).scalars().all())
            open_alert_count = sum(1 for item in alerts if str(item.status).lower() == "open")
            alert_summaries = [
                {
                    "severity": str(item.severity),
                    "title": str(item.title),
                    "status": str(item.status),
                    "created_at": item.created_at,
                }
                for item in alerts[:5]
            ]

        sibling_stmt = (
            select(InspectionTask.id)
            .where(
                InspectionTask.org_id == org_id,
                InspectionTask.product_id == task.product_id,
            )
            .order_by(InspectionTask.created_at.desc())
            .limit(20)
        )
        related_task_ids = [str(item) for item in (await self._session.execute(sibling_stmt)).scalars().all()]

        return {
            "task_id": str(task.id),
            "product_line": str(task.product_id),
            "spec_code": str(task.spec_code),
            "status": str(task.status),
            "priority": int(task.priority or 0),
            "image_count": len(task.image_urls or []),
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "has_result": result is not None,
            "verdict": str(result.verdict) if result is not None else None,
            "overall_score": float(result.overall_score or 0.0) if result is not None else None,
            "hallucination_flag": self._is_empty_citations(result.citations) if result is not None else False,
            "llm_model": str(result.llm_model) if result is not None else None,
            "latency_ms": int(result.latency_ms or 0) if result is not None and result.latency_ms is not None else None,
            "tokens_used": sum(int(item.total_tokens or 0) for item in ledgers),
            "total_cost": round(sum(float(item.cost_amount or 0.0) for item in ledgers), 4),
            "risk_score": float(stability.risk_score or 0.0) if stability is not None else None,
            "risk_level": str(stability.risk_level) if stability is not None else None,
            "open_alert_count": open_alert_count,
            "alert_summaries": alert_summaries,
            "related_task_ids": related_task_ids,
        }

    async def _list_tasks(self, org_id: str, start_date: date | None, end_date: date | None) -> list[InspectionTask]:
        stmt = select(InspectionTask).where(InspectionTask.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionTask.created_at, start_date, end_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _list_results(self, org_id: str, start_date: date | None, end_date: date | None) -> list[InspectionResult]:
        stmt = select(InspectionResult).where(InspectionResult.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionResult.created_at, start_date, end_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _list_alerts(self, org_id: str, start_date: date | None, end_date: date | None) -> list[AlertEvent]:
        stmt = select(AlertEvent).where(AlertEvent.org_id == org_id)
        stmt = self._apply_range(stmt, AlertEvent.created_at, start_date, end_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _list_stabilities(self, org_id: str, start_date: date | None, end_date: date | None) -> list[StabilityReport]:
        stmt = select(StabilityReport).where(StabilityReport.org_id == org_id)
        stmt = self._apply_range(stmt, StabilityReport.created_at, start_date, end_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _list_ledgers(self, org_id: str, start_date: date | None, end_date: date | None) -> list[TokenUsageLedger]:
        stmt = select(TokenUsageLedger).where(TokenUsageLedger.org_id == org_id)
        stmt = self._apply_range(stmt, TokenUsageLedger.created_at, start_date, end_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _get_overview_summary(self, org_id: str, start_date: date | None, end_date: date | None) -> dict:
        task_stmt = select(func.count()).select_from(InspectionTask).where(InspectionTask.org_id == org_id)
        task_stmt = self._apply_range(task_stmt, InspectionTask.created_at, start_date, end_date)

        alert_stmt = select(func.count()).select_from(AlertEvent).where(
            AlertEvent.org_id == org_id,
            AlertEvent.status == "open",
        )
        alert_stmt = self._apply_range(alert_stmt, AlertEvent.created_at, start_date, end_date)

        ledger_stmt = select(func.coalesce(func.sum(TokenUsageLedger.cost_amount), 0)).where(TokenUsageLedger.org_id == org_id)
        ledger_stmt = self._apply_range(ledger_stmt, TokenUsageLedger.created_at, start_date, end_date)

        result_stmt = select(
            func.count().label("total_results"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("pass_rate"),
            func.coalesce(func.avg(InspectionResult.latency_ms), 0.0).label("avg_latency_ms"),
            func.coalesce(func.avg(self._hallucination_case_expr()), 0.0).label("hallucination_rate"),
        ).where(InspectionResult.org_id == org_id)
        result_stmt = self._apply_range(result_stmt, InspectionResult.created_at, start_date, end_date)

        stability_stmt = select(
            func.coalesce(func.avg(case((StabilityReport.risk_level == "medium", 1.0), else_=0.0)), 0.0).label("risk_yellow_rate"),
            func.coalesce(func.avg(StabilityReport.risk_score), 0.0).label("avg_risk_score"),
        ).where(StabilityReport.org_id == org_id)
        stability_stmt = self._apply_range(stability_stmt, StabilityReport.created_at, start_date, end_date)

        total_tasks = int((await self._session.scalar(task_stmt)) or 0)
        total_alerts = int((await self._session.scalar(alert_stmt)) or 0)
        total_cost = round(float((await self._session.scalar(ledger_stmt)) or 0.0), 4)
        result_row = (await self._session.execute(result_stmt)).one()
        stability_row = (await self._session.execute(stability_stmt)).one()

        return {
            "total_tasks": total_tasks,
            "total_alerts": total_alerts,
            "total_results": int(result_row.total_results or 0),
            "total_cost": total_cost,
            "pass_rate": round(float(result_row.pass_rate or 0.0), 4),
            "avg_latency_ms": round(float(result_row.avg_latency_ms or 0.0), 2),
            "hallucination_rate": round(float(result_row.hallucination_rate or 0.0), 4),
            "risk_yellow_rate": round(float(stability_row.risk_yellow_rate or 0.0), 4),
            "avg_risk_score": round(float(stability_row.avg_risk_score or 0.0), 4),
        }

    async def _get_task_trend(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        bucket = func.date(InspectionTask.created_at)
        stmt = select(bucket.label("bucket"), func.count().label("value")).where(InspectionTask.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionTask.created_at, start_date, end_date)
        stmt = stmt.group_by(bucket).order_by(bucket)
        rows = (await self._session.execute(stmt)).all()
        return [{"bucket": str(row.bucket), "value": float(row.value)} for row in rows]

    async def _get_pass_rate_trend(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        bucket = func.date(InspectionResult.created_at)
        stmt = select(
            bucket.label("bucket"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("value"),
        ).where(InspectionResult.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionResult.created_at, start_date, end_date)
        stmt = stmt.group_by(bucket).order_by(bucket)
        rows = (await self._session.execute(stmt)).all()
        return [{"bucket": str(row.bucket), "value": round(float(row.value or 0.0), 4)} for row in rows]

    async def _get_hallucination_trend(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        bucket = func.date(InspectionResult.created_at)
        stmt = select(
            bucket.label("bucket"),
            func.coalesce(func.avg(self._hallucination_case_expr()), 0.0).label("value"),
        ).where(InspectionResult.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionResult.created_at, start_date, end_date)
        stmt = stmt.group_by(bucket).order_by(bucket)
        rows = (await self._session.execute(stmt)).all()
        return [{"bucket": str(row.bucket), "value": round(float(row.value or 0.0), 4)} for row in rows]

    async def _get_risk_distribution(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        stmt = select(
            StabilityReport.risk_level.label("name"),
            func.count().label("value"),
        ).where(StabilityReport.org_id == org_id)
        stmt = self._apply_range(stmt, StabilityReport.created_at, start_date, end_date)
        stmt = stmt.group_by(StabilityReport.risk_level).order_by(StabilityReport.risk_level)
        rows = (await self._session.execute(stmt)).all()
        return [{"name": str(row.name or "unknown"), "value": float(row.value)} for row in rows]

    async def _get_alert_distribution(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        stmt = select(
            AlertEvent.severity.label("name"),
            func.count().label("value"),
        ).where(AlertEvent.org_id == org_id)
        stmt = self._apply_range(stmt, AlertEvent.created_at, start_date, end_date)
        stmt = stmt.group_by(AlertEvent.severity).order_by(AlertEvent.severity)
        rows = (await self._session.execute(stmt)).all()
        return [{"name": str(row.name or "unknown"), "value": float(row.value)} for row in rows]

    async def _get_risk_distribution_trend(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        bucket = func.date(StabilityReport.created_at)
        stmt = select(
            bucket.label("bucket"),
            func.sum(case((StabilityReport.risk_level == "low", 1), else_=0)).label("low"),
            func.sum(case((StabilityReport.risk_level == "medium", 1), else_=0)).label("medium"),
            func.sum(case((StabilityReport.risk_level == "high", 1), else_=0)).label("high"),
            func.sum(case((StabilityReport.risk_level == "critical", 1), else_=0)).label("critical"),
        ).where(StabilityReport.org_id == org_id)
        stmt = self._apply_range(stmt, StabilityReport.created_at, start_date, end_date)
        stmt = stmt.group_by(bucket).order_by(bucket)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "bucket": str(row.bucket),
                "low": float(row.low or 0),
                "medium": float(row.medium or 0),
                "high": float(row.high or 0),
                "critical": float(row.critical or 0),
            }
            for row in rows
        ]

    async def _get_model_metrics(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        ledger_stmt = select(
            TokenUsageLedger.result_id.label("result_id"),
            func.sum(TokenUsageLedger.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLedger.cost_amount).label("total_cost"),
        ).where(TokenUsageLedger.org_id == org_id)
        ledger_stmt = self._apply_range(ledger_stmt, TokenUsageLedger.created_at, start_date, end_date)
        ledger_stmt = ledger_stmt.group_by(TokenUsageLedger.result_id).subquery()

        stmt = select(
            InspectionResult.llm_model.label("model_key"),
            func.count().label("result_count"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("pass_rate"),
            func.coalesce(func.avg(self._hallucination_case_expr()), 0.0).label("hallucination_rate"),
            func.coalesce(func.avg(func.coalesce(ledger_stmt.c.total_tokens, 0)), 0.0).label("avg_tokens"),
            func.coalesce(func.sum(func.coalesce(ledger_stmt.c.total_cost, 0)), 0.0).label("total_cost"),
        ).select_from(InspectionResult).outerjoin(ledger_stmt, ledger_stmt.c.result_id == InspectionResult.id)
        stmt = stmt.where(InspectionResult.org_id == org_id)
        stmt = self._apply_range(stmt, InspectionResult.created_at, start_date, end_date)
        stmt = stmt.group_by(InspectionResult.llm_model).order_by(InspectionResult.llm_model)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "model_key": str(row.model_key or "unknown"),
                "result_count": int(row.result_count or 0),
                "pass_rate": round(float(row.pass_rate or 0.0), 4),
                "hallucination_rate": round(float(row.hallucination_rate or 0.0), 4),
                "avg_tokens": round(float(row.avg_tokens or 0.0), 2),
                "total_cost": round(float(row.total_cost or 0.0), 4),
            }
            for row in rows
        ]

    async def _get_product_line_series(self, org_id: str, start_date: date | None, end_date: date | None) -> list[dict]:
        top_stmt = select(
            InspectionTask.product_id.label("product_id"),
            func.count().label("total_tasks"),
        ).where(InspectionTask.org_id == org_id)
        top_stmt = self._apply_range(top_stmt, InspectionTask.created_at, start_date, end_date)
        top_stmt = top_stmt.group_by(InspectionTask.product_id).order_by(func.count().desc(), InspectionTask.product_id).limit(5)
        top_rows = (await self._session.execute(top_stmt)).all()
        if not top_rows:
            return []

        product_ids = [str(row.product_id or "unknown") for row in top_rows]
        totals = {str(row.product_id or "unknown"): int(row.total_tasks or 0) for row in top_rows}

        pass_stmt = select(
            InspectionTask.product_id.label("product_id"),
            func.coalesce(func.avg(case((InspectionResult.verdict == "pass", 1.0), else_=0.0)), 0.0).label("pass_rate"),
        ).select_from(InspectionTask).join(
            InspectionResult,
            InspectionResult.task_id == InspectionTask.id,
        ).where(
            InspectionTask.org_id == org_id,
            InspectionResult.org_id == org_id,
            InspectionTask.product_id.in_(product_ids),
        )
        pass_stmt = self._apply_range(pass_stmt, InspectionTask.created_at, start_date, end_date)
        pass_stmt = pass_stmt.group_by(InspectionTask.product_id)
        pass_rows = (await self._session.execute(pass_stmt)).all()
        pass_rates = {str(row.product_id or "unknown"): round(float(row.pass_rate or 0.0), 4) for row in pass_rows}

        bucket = func.date(InspectionTask.created_at)
        points_stmt = select(
            InspectionTask.product_id.label("product_id"),
            bucket.label("bucket"),
            func.count().label("value"),
        ).where(
            InspectionTask.org_id == org_id,
            InspectionTask.product_id.in_(product_ids),
        )
        points_stmt = self._apply_range(points_stmt, InspectionTask.created_at, start_date, end_date)
        points_stmt = points_stmt.group_by(InspectionTask.product_id, bucket).order_by(InspectionTask.product_id, bucket)
        point_rows = (await self._session.execute(points_stmt)).all()

        points_by_product: dict[str, list[dict]] = defaultdict(list)
        for row in point_rows:
            product_id = str(row.product_id or "unknown")
            points_by_product[product_id].append(
                {"bucket": str(row.bucket), "value": float(row.value or 0)}
            )

        return [
            {
                "name": product_id,
                "total_tasks": totals.get(product_id, 0),
                "pass_rate": pass_rates.get(product_id, 0.0),
                "points": points_by_product.get(product_id, []),
            }
            for product_id in product_ids
        ]

    @staticmethod
    def _hallucination_case_expr():
        items_len = func.coalesce(func.json_length(func.json_extract(InspectionResult.citations, "$.items")), 0)
        return case(
            (InspectionResult.citations.is_(None), 1.0),
            (items_len == 0, 1.0),
            else_=0.0,
        )

    @staticmethod
    def _apply_range(stmt, column, start_date: date | None, end_date: date | None):
        if start_date:
            stmt = stmt.where(column >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(column <= datetime.combine(end_date, datetime.max.time()))
        return stmt

    @staticmethod
    def _bucket(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d")

    @classmethod
    def _build_count_trend(cls, items, date_getter) -> list[dict]:
        buckets: dict[str, int] = defaultdict(int)
        for item in items:
            bucket = cls._bucket(date_getter(item))
            if bucket is None:
                continue
            buckets[bucket] += 1
        return [{"bucket": bucket, "value": float(value)} for bucket, value in sorted(buckets.items())]

    @classmethod
    def _build_ratio_trend(cls, items, date_getter, positive_predicate) -> list[dict]:
        buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "pos": 0})
        for item in items:
            key = cls._bucket(date_getter(item))
            if key is None:
                continue
            buckets[key]["all"] += 1
            if positive_predicate(item):
                buckets[key]["pos"] += 1
        return [
            {"bucket": bucket, "value": round(values["pos"] / values["all"], 4) if values["all"] else 0.0}
            for bucket, values in sorted(buckets.items())
        ]

    @staticmethod
    def _build_distribution(items, key_getter) -> list[dict]:
        counter = Counter(str(key_getter(item) or "unknown") for item in items)
        return [{"name": key, "value": float(value)} for key, value in sorted(counter.items())]

    @classmethod
    def _build_risk_distribution_trend(cls, items, date_getter) -> list[dict]:
        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0}
        )
        for item in items:
            key = cls._bucket(date_getter(item))
            if key is None:
                continue
            risk_level = str(item.risk_level or "low").lower()
            if risk_level not in buckets[key]:
                risk_level = "low"
            buckets[key][risk_level] += 1
        return [
            {
                "bucket": bucket,
                "low": float(values["low"]),
                "medium": float(values["medium"]),
                "high": float(values["high"]),
                "critical": float(values["critical"]),
            }
            for bucket, values in sorted(buckets.items())
        ]

    @classmethod
    def _build_model_metrics(cls, results: list[InspectionResult], ledgers: list[TokenUsageLedger]) -> list[dict]:
        ledgers_by_result: dict[str, list[TokenUsageLedger]] = defaultdict(list)
        for item in ledgers:
            if item.result_id:
                ledgers_by_result[str(item.result_id)].append(item)

        grouped: dict[str, list[InspectionResult]] = defaultdict(list)
        for item in results:
            grouped[str(item.llm_model or "unknown")].append(item)

        metrics: list[dict] = []
        for model_key, model_results in sorted(grouped.items()):
            result_count = len(model_results)
            hallucinations = sum(1 for item in model_results if cls._is_empty_citations(item.citations))
            total_tokens = sum(
                int(ledger.total_tokens or 0)
                for result in model_results
                for ledger in ledgers_by_result.get(str(result.id), [])
            )
            total_cost = round(
                sum(
                    float(ledger.cost_amount or 0.0)
                    for result in model_results
                    for ledger in ledgers_by_result.get(str(result.id), [])
                ),
                4,
            )
            metrics.append(
                {
                    "model_key": model_key,
                    "result_count": result_count,
                    "pass_rate": round(sum(1 for item in model_results if item.verdict == "pass") / result_count, 4)
                    if result_count else 0.0,
                    "hallucination_rate": round(hallucinations / result_count, 4) if result_count else 0.0,
                    "avg_tokens": round(total_tokens / result_count, 2) if result_count else 0.0,
                    "total_cost": total_cost,
                }
            )
        return metrics

    @classmethod
    def _build_product_line_series(cls, tasks: list[InspectionTask], results: list[InspectionResult]) -> list[dict]:
        task_by_id = {str(item.id): item for item in tasks}
        tasks_by_product: dict[str, list[InspectionTask]] = defaultdict(list)
        results_by_product: dict[str, list[InspectionResult]] = defaultdict(list)

        for task in tasks:
            tasks_by_product[str(task.product_id or "unknown")].append(task)
        for result in results:
            task = task_by_id.get(str(result.task_id))
            if not task:
                continue
            results_by_product[str(task.product_id or "unknown")].append(result)

        ranked_products = sorted(
            tasks_by_product.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:5]

        series: list[dict] = []
        for product_id, product_tasks in ranked_products:
            product_results = results_by_product.get(product_id, [])
            series.append(
                {
                    "name": product_id,
                    "total_tasks": len(product_tasks),
                    "pass_rate": round(
                        sum(1 for item in product_results if item.verdict == "pass") / len(product_results),
                        4,
                    ) if product_results else 0.0,
                    "points": cls._build_count_trend(product_tasks, lambda item: item.created_at),
                }
            )
        return series

    @staticmethod
    def _is_empty_citations(citations: object) -> bool:
        if citations is None:
            return True
        if isinstance(citations, dict):
            items = citations.get("items")
            return not bool(items)
        if isinstance(citations, (list, tuple, set)):
            return len(citations) == 0
        text = str(citations).strip().lower()
        return text in {"", "null", "[]", "{}"}
