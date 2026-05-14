from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import PageParams


class ModelConfigCreate(BaseModel):
    org_id: Optional[str] = None
    provider: str
    model_key: str
    display_name: str
    endpoint: str
    api_key: Optional[str] = None
    model_type: str = "chat"
    priority: int = 100
    rpm_limit: Optional[int] = None
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    is_active: bool = True


class ModelConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model_type: Optional[str] = None
    priority: Optional[int] = None
    rpm_limit: Optional[int] = None
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    is_active: Optional[bool] = None
    health_status: Optional[str] = None
    health_message: Optional[str] = None


class ModelConfigResponse(BaseModel):
    id: str
    org_id: Optional[str] = None
    provider: str
    model_key: str
    display_name: str
    endpoint: str
    model_type: str
    priority: int
    rpm_limit: Optional[int] = None
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    is_active: bool
    health_status: str
    health_message: Optional[str] = None
    has_api_key: bool = False

    model_config = {"from_attributes": True}


class BillingQuery(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    granularity: str = Field(default="day", pattern="^(day|week|month)$")
    model_key: Optional[str] = None
    product_line: Optional[str] = None


class BillingBucket(BaseModel):
    bucket: str
    total_tokens: int
    total_cost: float
    request_count: int


class TokenLedgerResponse(BaseModel):
    id: str
    user_id: str | None = None
    model_key: str
    product_line: Optional[str] = None
    total_tokens: int
    cost_amount: float
    trace_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BillingSummaryResponse(BaseModel):
    granularity: str
    total_tokens: int
    total_cost: float
    buckets: list[BillingBucket]
    ledger_items: list[TokenLedgerResponse]
    user_summaries: list["UserTokenUsageSummaryResponse"] = []


class UserTokenUsageSummaryResponse(BaseModel):
    user_id: str
    org_id: str
    username: str
    role: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost: float
    request_count: int
    last_ledger_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CurrentUserTokenUsageResponse(BaseModel):
    user_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0
    request_count: int = 0
    last_ledger_at: Optional[datetime] = None


class FeedbackSubmit(BaseModel):
    feedback_type: str = Field(pattern="^(up|down)$")
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    category: Optional[str] = None
    comment: Optional[str] = None


class FeedbackQuery(PageParams):
    result_id: Optional[str] = None
    feedback_type: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    org_id: str
    result_id: str
    actor_id: str
    feedback_type: str
    rating: Optional[int] = None
    category: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrendPoint(BaseModel):
    bucket: str
    value: float


class ModelQualityMetric(BaseModel):
    model_key: str
    result_count: int
    pass_rate: float
    hallucination_rate: float
    thumbs_down_rate: float


class QualityReportResponse(BaseModel):
    total_results: int
    hallucination_rate: float
    thumbs_down_rate: float
    avg_risk_score: float
    feedback_distribution: dict[str, int]
    hallucination_trend: list[TrendPoint]
    thumbs_down_trend: list[TrendPoint]
    model_metrics: list[ModelQualityMetric]
    chat_score_count: int = 0
    chat_avg_trust_score: float = 0.0
    chat_hallucination_rate: float = 0.0
    chat_overconfidence_rate: float = 0.0
    chat_citation_rate: float = 0.0
    chat_trust_trend: list[TrendPoint] = []


class QualityTraceItem(BaseModel):
    source_type: str = "inspection"
    trace_id: str
    trace_url: Optional[str] = None
    result_id: Optional[str] = None
    task_id: Optional[str] = None
    assistant_message_id: Optional[str] = None
    session_id: Optional[str] = None
    observation_id: Optional[str] = None
    verdict: Optional[str] = None
    model_key: Optional[str] = None
    total_tokens: int = 0
    feedback_count: int = 0
    thumbs_down_count: int = 0
    last_score_value: Optional[float] = None
    last_score_at: Optional[datetime] = None
    trust_score: Optional[float] = None
    hallucination_risk: Optional[float] = None
    overconfidence: Optional[float] = None
    has_citation: Optional[bool] = None
    score_status: Optional[str] = None
    review_model: Optional[str] = None
    langfuse_status: Optional[str] = None
    langfuse_synced: Optional[bool] = None
    created_at: Optional[datetime] = None
