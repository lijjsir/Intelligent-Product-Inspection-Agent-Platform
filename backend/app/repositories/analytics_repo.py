from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import select
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
        tasks = await self._list_tasks(org_id, start_date, end_date)
        results = await self._list_results(org_id, start_date, end_date)
        alerts = await self._list_alerts(org_id, start_date, end_date)
        stabilities = await self._list_stabilities(org_id, start_date, end_date)
        ledgers = await self._list_ledgers(org_id, start_date, end_date)

        total_tasks = len(tasks)
        total_alerts = sum(1 for item in alerts if item.status == "open")
        total_results = len(results)
        total_cost = round(sum(float(item.cost_amount or 0.0) for item in ledgers), 4)
        total_pass = sum(1 for item in results if item.verdict == "pass")
        hallucination_count = sum(1 for item in results if self._is_empty_citations(item.citations))
        risk_yellow_count = sum(1 for item in stabilities if item.risk_level == "medium")
        avg_risk_score = round(
            sum(float(item.risk_score or 0.0) for item in stabilities) / len(stabilities),
            4,
        ) if stabilities else 0.0

        latency_values = [int(item.latency_ms or 0) for item in results if item.latency_ms is not None]
        avg_latency_ms = round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0

        return {
            "total_tasks": total_tasks,
            "total_alerts": total_alerts,
            "total_results": total_results,
            "total_cost": total_cost,
            "pass_rate": round(total_pass / total_results, 4) if total_results else 0.0,
            "hallucination_rate": round(hallucination_count / total_results, 4) if total_results else 0.0,
            "risk_yellow_rate": round(risk_yellow_count / len(stabilities), 4) if stabilities else 0.0,
            "avg_risk_score": avg_risk_score,
            "avg_latency_ms": avg_latency_ms,
            "task_trend": self._build_count_trend(tasks, lambda item: item.created_at),
            "pass_rate_trend": self._build_ratio_trend(results, lambda item: item.created_at, lambda item: item.verdict == "pass"),
            "hallucination_trend": self._build_ratio_trend(
                results,
                lambda item: item.created_at,
                lambda item: self._is_empty_citations(item.citations),
            ),
            "risk_distribution_trend": self._build_risk_distribution_trend(stabilities, lambda item: item.created_at),
            "risk_distribution": self._build_distribution(stabilities, lambda item: item.risk_level),
            "alert_distribution": self._build_distribution(alerts, lambda item: item.severity),
            "model_metrics": self._build_model_metrics(results, ledgers),
            "product_line_series": self._build_product_line_series(tasks, results),
        }

    async def get_product_line_drilldown(
        self,
        org_id: str,
        product_line: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        tasks = [item for item in await self._list_tasks(org_id, start_date, end_date) if str(item.product_id) == product_line]
        task_ids = {str(item.id) for item in tasks}
        results = [
            item for item in await self._list_results(org_id, start_date, end_date)
            if str(item.task_id) in task_ids
        ]
        ledgers = [
            item for item in await self._list_ledgers(org_id, start_date, end_date)
            if str(item.task_id) in task_ids
        ]

        total_results = len(results)
        latency_values = [int(item.latency_ms or 0) for item in results if item.latency_ms is not None]
        return {
            "product_line": product_line,
            "total_tasks": len(tasks),
            "total_results": total_results,
            "pass_rate": round(sum(1 for item in results if item.verdict == "pass") / total_results, 4) if total_results else 0.0,
            "hallucination_rate": round(
                sum(1 for item in results if self._is_empty_citations(item.citations)) / total_results,
                4,
            ) if total_results else 0.0,
            "avg_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "total_cost": round(sum(float(item.cost_amount or 0.0) for item in ledgers), 4),
            "task_trend": self._build_count_trend(tasks, lambda item: item.created_at),
            "verdict_distribution": self._build_distribution(results, lambda item: item.verdict),
            "recent_tasks": [
                {
                    "task_id": str(item.id),
                    "status": str(item.status),
                    "spec_id": str(item.spec_id),
                    "created_at": item.created_at,
                }
                for item in sorted(
                    (item for item in tasks if item.created_at is not None),
                    key=lambda item: item.created_at,
                    reverse=True,
                )[:8]
            ],
        }

    async def get_model_drilldown(
        self,
        org_id: str,
        model_key: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        tasks = await self._list_tasks(org_id, start_date, end_date)
        task_by_id = {str(item.id): item for item in tasks}
        results = [
            item for item in await self._list_results(org_id, start_date, end_date)
            if str(item.llm_model or "") == model_key
        ]
        result_ids = {str(item.id) for item in results}
        ledgers = [
            item for item in await self._list_ledgers(org_id, start_date, end_date)
            if str(item.result_id or "") in result_ids
        ]
        latency_values = [int(item.latency_ms or 0) for item in results if item.latency_ms is not None]
        grouped_tokens = defaultdict(list)
        grouped_cost = defaultdict(list)
        for ledger in ledgers:
            grouped_tokens[str(ledger.result_id)].append(int(ledger.total_tokens or 0))
            grouped_cost[str(ledger.result_id)].append(float(ledger.cost_amount or 0.0))

        result_count = len(results)
        return {
            "model_key": model_key,
            "result_count": result_count,
            "pass_rate": round(sum(1 for item in results if item.verdict == "pass") / result_count, 4) if result_count else 0.0,
            "hallucination_rate": round(
                sum(1 for item in results if self._is_empty_citations(item.citations)) / result_count,
                4,
            ) if result_count else 0.0,
            "avg_tokens": round(sum(sum(values) for values in grouped_tokens.values()) / result_count, 2) if result_count else 0.0,
            "total_cost": round(sum(sum(values) for values in grouped_cost.values()), 4),
            "avg_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "product_line_distribution": self._build_distribution(
                results,
                lambda item: (task_by_id.get(str(item.task_id)).product_id if task_by_id.get(str(item.task_id)) else "unknown"),
            ),
            "recent_results": [
                {
                    "result_id": str(item.id),
                    "task_id": str(item.task_id),
                    "product_line": str(task_by_id.get(str(item.task_id)).product_id) if task_by_id.get(str(item.task_id)) else "unknown",
                    "verdict": str(item.verdict),
                    "overall_score": float(item.overall_score or 0.0),
                    "created_at": item.created_at,
                }
                for item in sorted(
                    (item for item in results if item.created_at is not None),
                    key=lambda item: item.created_at,
                    reverse=True,
                )[:8]
            ],
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
