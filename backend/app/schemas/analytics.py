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
    spec_id: str
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
    recent_results: list[ModelRecentResult]


class OverviewStats(BaseModel):
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
