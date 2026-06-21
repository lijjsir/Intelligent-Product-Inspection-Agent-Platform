from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AssessmentState = Literal[
    "normal_so_far",
    "early_abnormal",
    "uncertain_continue",
    "insufficient_data",
    "manual_review_required",
]

RiskLevel = Literal["low", "medium", "high", "critical"]
DeviationType = Literal[
    "above_limit",
    "below_limit",
    "out_of_normal_range",
    "trend_abnormal",
    "instrument_suspected",
    "environment_suspected",
    "unknown",
]


class LabMeasurement(BaseModel):
    item: str = Field(..., description="检测项目名称，例如 水分、pH、重金属、微生物")
    value: float | str | None = Field(default=None, description="检测值")
    unit: str | None = Field(default=None, description="单位")
    normal_range: str | None = Field(default=None, description="历史正常响应范围")
    standard_limit: str | None = Field(default=None, description="标准限值，例如 <=15")
    timestamp: str | None = Field(default=None, description="检测时间")
    instrument_id: str | None = Field(default=None, description="仪器编号")
    method: str | None = Field(default=None, description="检测方法")
    quality_flag: str | None = Field(default=None, description="数据质量标记")
    raw: dict[str, Any] = Field(default_factory=dict)


class LabTestPlan(BaseModel):
    total_items: int = 0
    completed_items: int = 0
    pending_items: list[str] = Field(default_factory=list)
    critical_items: list[str] = Field(default_factory=list)

    def completeness(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return max(0.0, min(1.0, self.completed_items / self.total_items))


class LabNormalProfile(BaseModel):
    similar_samples_count: int = 0
    normal_response_pattern: str | None = None
    abnormal_patterns: list[str] = Field(default_factory=list)
    instrument_baseline: dict[str, Any] = Field(default_factory=dict)


class LabPartialDataContext(BaseModel):
    sample_id: str
    product_id: str | None = None
    product_family: str | None = None
    batch_id: str | None = None
    spec_code: str | None = None

    test_plan: LabTestPlan = Field(default_factory=LabTestPlan)
    partial_measurements: list[LabMeasurement] = Field(default_factory=list)

    historical_baseline: LabNormalProfile = Field(default_factory=LabNormalProfile)
    environment: dict[str, Any] = Field(default_factory=dict)
    standard_context: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LabAnomalyFeature(BaseModel):
    item: str
    value: float | str | None = None
    unit: str | None = None
    expected_range: str | None = None
    standard_limit: str | None = None
    deviation_type: DeviationType = "unknown"
    severity: RiskLevel | str = "low"
    evidence: str | None = None
    confidence: float = 0.0


class LabEarlyRiskAssessment(BaseModel):
    assessment_state: AssessmentState
    abnormal_probability: float = 0.0
    risk_level: RiskLevel = "low"
    data_completeness: float = 0.0

    early_warning: bool = False
    can_make_final_verdict: bool = False

    abnormal_indicators: list[LabAnomalyFeature] = Field(default_factory=list)
    suggested_action: str | None = None
    next_test_priority: list[dict[str, Any]] = Field(default_factory=list)

    explanation: str = ""
    requires_manual_review: bool = False
    confidence: float = 0.0

    raw_llm_output: dict[str, Any] = Field(default_factory=dict)
    deterministic_summary: dict[str, Any] = Field(default_factory=dict)
