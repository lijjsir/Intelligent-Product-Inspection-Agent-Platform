from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TrendPoint(BaseModel):
    bucket: str
    value: float


class RiskTrendPoint(BaseModel):
    bucket: str
    low: float
    medium: float
    high: float
    critical: float


class NamedValue(BaseModel):
    name: str
    value: float


class ModelAnalyticsMetric(BaseModel):
    model_key: str
    result_count: int
    pass_rate: float
    hallucination_rate: float
    avg_tokens: float
    total_cost: float


class ProductLineSeries(BaseModel):
    name: str
    total_tasks: int
    pass_rate: float
    points: list[TrendPoint]


class ProductLineRecentTask(BaseModel):
    task_id: str
    status: str
    spec_code: str
    created_at: datetime


class ProductLineDrilldown(BaseModel):
    product_line: str
    total_tasks: int
    total_results: int
    pass_rate: float
    hallucination_rate: float
    avg_latency_ms: float
    total_cost: float
    task_trend: list[TrendPoint]
    verdict_distribution: list[NamedValue]
    recent_tasks_total: int
    recent_tasks_page: int
    recent_tasks_size: int
    recent_tasks: list[ProductLineRecentTask]


class ModelRecentResult(BaseModel):
    result_id: str
    task_id: str
    product_line: str
    verdict: str
    overall_score: float
    created_at: datetime


class ModelDrilldown(BaseModel):
    model_key: str
    result_count: int
    pass_rate: float
    hallucination_rate: float
    avg_tokens: float
    total_cost: float
    avg_latency_ms: float
    product_line_distribution: list[NamedValue]
    recent_results_total: int
    recent_results_page: int
    recent_results_size: int
    recent_results: list[ModelRecentResult]


class TaskAlertSummary(BaseModel):
    severity: str
    title: str
    status: str
    created_at: datetime


class TaskDrilldown(BaseModel):
    task_id: str
    product_line: str
    spec_code: str
    status: str
    priority: int
    image_count: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    has_result: bool
    verdict: str | None = None
    overall_score: float | None = None
    hallucination_flag: bool = False
    llm_model: str | None = None
    latency_ms: int | None = None
    tokens_used: int = 0
    total_cost: float = 0.0
    risk_score: float | None = None
    risk_level: str | None = None
    open_alert_count: int = 0
    alert_summaries: list[TaskAlertSummary]
    related_task_ids: list[str]


class OverviewStats(BaseModel):
    scope_kind: str = "org"
    total_tasks: int
    total_alerts: int
    total_results: int
    total_cost: float
    pass_rate: float
    hallucination_rate: float
    risk_yellow_rate: float
    avg_risk_score: float
    avg_latency_ms: float
    task_trend: list[TrendPoint]
    pass_rate_trend: list[TrendPoint]
    hallucination_trend: list[TrendPoint]
    risk_distribution_trend: list[RiskTrendPoint]
    risk_distribution: list[NamedValue]
    alert_distribution: list[NamedValue]
    model_metrics: list[ModelAnalyticsMetric]
    product_line_series: list[ProductLineSeries]
