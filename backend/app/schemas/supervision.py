from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def normalize_datetime(cls, value):
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class RegionData(Strict):
    parent_id: UUID | None = None
    dictionary_version: str = "2026"


class ProductDetails(Strict):
    product_category: str | None = None
    brand: str | None = None
    model: str | None = None
    enterprise_id: UUID | None = None
    production_region_id: UUID | None = None
    sales_region_ids: list[UUID] = Field(default_factory=list)


class StandardApplicability(Strict):
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    transition_until: datetime | None = None
    region_ids: list[UUID] = Field(default_factory=list)
    production_from: datetime | None = None
    production_to: datetime | None = None
    clause_version: str | None = None
    notes: str | None = None


class EnterpriseData(Strict):
    credit_code: str | None = Field(default=None, max_length=32)
    role: Literal["manufacturer", "seller", "both"] = "manufacturer"
    address: str | None = Field(default=None, max_length=500)
    region_id: UUID | None = None
    product_sku_ids: list[UUID] = Field(default_factory=list)


class TestItem(Strict):
    item: str = Field(min_length=1, max_length=128)
    unit: str = Field(min_length=1, max_length=32)
    method: str = Field(min_length=1, max_length=128)
    lower_limit: float | None = Field(default=None, allow_inf_nan=False)
    upper_limit: float | None = Field(default=None, allow_inf_nan=False)
    standard_ref: str | None = None
    normal_lower: float | None = Field(default=None, allow_inf_nan=False)
    normal_upper: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_ranges(self):
        for low, high in (
            (self.lower_limit, self.upper_limit),
            (self.normal_lower, self.normal_upper),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError("检测或正常响应下限不能超过上限")
        return self


class DeviceData(Strict):
    device_type: str = Field(min_length=1, max_length=128)
    region_id: UUID | None = None
    location: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    calibration_status: Literal["valid", "expired", "unknown"] = "unknown"
    calibration_expires_at: datetime | None = None
    online_status: Literal["online", "offline", "unknown"] = "unknown"
    capacity: int = Field(default=1, ge=0, le=100000)
    connection_description: str | None = None
    baseline_version: str | None = None


class Evidence(Strict):
    evidence_id: str = Field(min_length=1, max_length=128)
    source_type: Literal[
        "complaint",
        "public_opinion",
        "inspection",
        "enterprise",
        "image",
        "standard",
        "device",
        "expert",
    ]
    source_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    text: str = Field(min_length=1, max_length=16000)
    attachment_url: str | None = None
    source_hash: str | None = None
    nature: Literal["observed", "inferred", "synthetic"] = "observed"


class CaseData(Strict):
    product_sku_id: UUID | None = None
    batch_id: UUID | None = None
    enterprise_id: UUID | None = None
    product_category: str | None = None
    production_region_id: UUID | None = None
    sales_region_ids: list[UUID] = Field(default_factory=list)
    complaint_region_id: UUID | None = None
    sampling_region_id: UUID | None = None
    description: str = Field(min_length=1, max_length=16000)
    occurred_at: datetime
    evidence: list[Evidence] = Field(default_factory=list, max_length=200)
    inspection_standard_id: UUID | None = None
    assigned_to: UUID | None = None


class Candidate(Strict):
    case_id: UUID
    sample_count: int = Field(default=1, ge=1, le=10000)
    unit_cost: float = Field(default=0, ge=0, allow_inf_nan=False)
    device_id: UUID | None = None
    region_id: UUID | None = None
    test_items: list[TestItem] = Field(default_factory=list)
    required_items: list[TestItem] = Field(default_factory=list)
    candidate_items: list[TestItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_adaptive_items(self):
        if self.test_items and not self.required_items and not self.candidate_items:
            self.required_items = list(self.test_items)
        elif not self.test_items and (self.required_items or self.candidate_items):
            self.test_items = [*self.required_items, *self.candidate_items]
        identifiers = [
            (item.item, item.unit, item.method)
            for item in [*self.required_items, *self.candidate_items]
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("必检项与候选项不能重复")
        return self


class PlanData(Strict):
    candidates: list[Candidate] = Field(default_factory=list, max_length=200)
    budget: float = Field(default=0, ge=0, allow_inf_nan=False)
    max_samples: int = Field(default=10, ge=1, le=10000)
    max_staff_hours: float = Field(default=8, gt=0, allow_inf_nan=False)
    hours_per_sample: float = Field(default=1, gt=0, allow_inf_nan=False)
    required_categories: list[str] = Field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class SessionData(Strict):
    input_mode: Literal["image", "measurement", "mixed"] = "measurement"
    task_id: UUID
    case_id: UUID | None = None
    plan_id: UUID | None = None
    sample_ids: list[UUID] = Field(default_factory=list)
    device_ids: list[UUID] = Field(default_factory=list)
    test_items: list[TestItem] = Field(default_factory=list)
    required_items: list[TestItem] = Field(default_factory=list)
    candidate_items: list[TestItem] = Field(default_factory=list)
    goal_id: UUID | None = None
    adaptive_enabled: bool = False
    baseline_version: str | None = None

    @model_validator(mode="after")
    def normalize_adaptive_items(self):
        if self.test_items and not self.required_items and not self.candidate_items:
            self.required_items = list(self.test_items)
        elif not self.test_items and (self.required_items or self.candidate_items):
            self.test_items = [*self.required_items, *self.candidate_items]
        identifiers = [
            (item.item, item.unit, item.method)
            for item in [*self.required_items, *self.candidate_items]
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("必检项与候选项不能重复")
        return self


class MarketMonitoringReportData(Strict):
    window_start: datetime
    window_end: datetime
    case_versions: dict[str, int] = Field(default_factory=dict)
    exposure_ids: list[UUID] = Field(default_factory=list)
    denominator_kind: Literal["sales_volume", "in_use_volume", "inspection_count"] | None = None
    dimensions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_window(self):
        if self.window_start >= self.window_end:
            raise ValueError("市场监控时间窗起点必须早于终点")
        return self


class PublicOpinionMonitoringReportData(Strict):
    risk_case_id: UUID
    evidence_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    standard_snapshot_id: str | None = None
    knowledge_snapshot_id: str | None = None


class RiskAssessmentData(Strict):
    market_report_id: UUID | None = None
    public_opinion_report_id: UUID | None = None
    risk_level: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    standard_snapshot_id: str | None = None
    knowledge_snapshot_id: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class StopPolicy(Strict):
    rule_version: str = Field(min_length=1, max_length=64)
    evidence_sufficiency_threshold: float = Field(
        default=0.8, ge=0, le=1, allow_inf_nan=False
    )
    max_rounds: int = Field(default=20, ge=1, le=1000)
    allow_early_stop: bool = True
    require_expert_approval: bool = True


class InspectionGoalCreate(Strict):
    plan_id: UUID | None = None
    session_version: int = Field(ge=1)
    request_key: str = Field(min_length=1, max_length=128)
    risk_hypotheses: list[str] = Field(default_factory=list)
    required_items: list[TestItem] = Field(default_factory=list)
    candidate_items: list[TestItem] = Field(default_factory=list)
    success_criteria: dict = Field(default_factory=dict)
    stop_policy: StopPolicy
    max_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_duration_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_items(self):
        items = [*self.required_items, *self.candidate_items]
        if not items:
            raise ValueError("检测目标必须包含必检项或候选项")
        identities = [(item.item, item.unit, item.method) for item in items]
        if len(identities) != len(set(identities)):
            raise ValueError("必检项与候选项不能重复")
        return self


class DeviceTrustState(Strict):
    status: Literal["trusted", "suspect", "invalid", "unknown"] = "unknown"
    device_ids: list[UUID] = Field(default_factory=list)
    calibration_valid: bool = False
    quality_issues: list[str] = Field(default_factory=list)


class ProductQualityState(Strict):
    status: Literal["normal", "abnormal", "uncertain"] = "uncertain"
    supported_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)


class EvidenceStateResponse(Strict):
    id: UUID
    session_id: UUID
    round: int = Field(ge=0)
    device_trust_state: DeviceTrustState
    product_quality_state: ProductQualityState
    supported_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    evidence_sufficiency: float = Field(ge=0, le=1, allow_inf_nan=False)
    remaining_uncertainty: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_ids: list[str] = Field(default_factory=list)


class NextTestDecisionCreate(Strict):
    evidence_state_id: UUID
    request_key: str = Field(min_length=1, max_length=128)
    rule_version: str = Field(min_length=1, max_length=64)


class StopDecisionCreate(Strict):
    evidence_state_id: UUID
    request_key: str = Field(min_length=1, max_length=128)
    rule_version: str = Field(min_length=1, max_length=64)


class AdaptiveDecisionReview(Strict):
    decision: Literal["approve", "reject"]
    comment: str = Field(min_length=1, max_length=4000)


class DeviceObservation(Strict):
    event_id: str = Field(min_length=1, max_length=128)
    session_id: UUID
    sample_id: UUID
    device_id: UUID
    command_id: UUID | None = None
    sequence_no: int | None = Field(default=None, ge=0)
    item: str = Field(min_length=1, max_length=128)
    measured_at: datetime
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)
    method: str = Field(min_length=1, max_length=128)
    quality_flag: Literal["valid", "suspect", "invalid"] = "valid"
    calibration_version: str | None = Field(default=None, max_length=64)


class SampleData(Strict):
    task_id: UUID
    product_sku_id: UUID
    batch_id: UUID
    sampled_at: datetime | None = None
    sampling_region_id: UUID | None = None


class ExposureData(Strict):
    region_id: UUID
    product_category: str
    period_start: datetime
    period_end: datetime
    sales_volume: int | None = Field(default=None, ge=0)
    in_use_volume: int | None = Field(default=None, ge=0)
    inspection_count: int | None = Field(default=None, ge=0)
    source_id: str = Field(min_length=1)


class BaselineData(Strict):
    device_ids: list[UUID] = Field(default_factory=list)
    product_category: str
    version_label: str
    source_id: str = Field(min_length=1)
    test_items: list[TestItem] = Field(min_length=1)
    conditions: str = Field(min_length=1)


DATA_SCHEMAS = {
    "regions": RegionData,
    "enterprises": EnterpriseData,
    "devices": DeviceData,
    "risk-cases": CaseData,
    "market-monitoring-reports": MarketMonitoringReportData,
    "public-opinion-reports": PublicOpinionMonitoringReportData,
    "risk-assessments": RiskAssessmentData,
    "sampling-plans": PlanData,
    "inspection-sessions": SessionData,
    "samples": SampleData,
    "exposures": ExposureData,
    "baselines": BaselineData,
}


class RecordCreate(Strict):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    data: dict = Field(default_factory=dict)


class RecordUpdate(Strict):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    data: dict | None = None
    status: Literal["active", "inactive", "archived"] | None = None


class RunRequest(Strict):
    version: int = Field(ge=1)
    request_key: str = Field(min_length=1, max_length=128)
    operation: Literal["risk_monitoring", "sampling", "laboratory"]


class Measurement(Strict):
    event_id: str = Field(min_length=1, max_length=128)
    sample_id: UUID
    device_id: UUID
    item: str = Field(min_length=1, max_length=128)
    measured_at: datetime
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)
    method: str = Field(min_length=1, max_length=128)
    quality_flag: Literal["valid", "suspect", "invalid"] = "valid"
    command_id: UUID | None = None
    sequence_no: int | None = Field(default=None, ge=0)
    calibration_version: str | None = Field(default=None, max_length=64)


class MeasurementIngest(Strict):
    session_id: UUID
    source_key: str = Field(min_length=1, max_length=128)
    measurements: list[Measurement] = Field(min_length=1, max_length=5000)

    @field_validator("source_key")
    @classmethod
    def reserved_preview_key(cls, value):
        if value.startswith("preview:"):
            raise ValueError("来源批次编号不能使用系统预览前缀")
        return value


class ReviewRequest(Strict):
    version: int = Field(ge=1)
    operation: Literal["risk.review", "sampling.approve", "result.review", "result.signoff"]


class ReviewDecision(Strict):
    decision: Literal["accept", "revise", "request_evidence", "escalate"]
    comment: str = Field(min_length=1, max_length=4000)


class FeedbackData(Strict):
    version: int = Field(ge=1)
    outcome: Literal[
        "confirmed", "false_positive", "false_negative", "inconclusive", "new_evidence"
    ]
    text: str = Field(min_length=1, max_length=8000)
    occurred_at: datetime


class AgentConfig(Strict):
    enabled: bool = True
    timeout_seconds: int = Field(default=600, ge=30, le=600)
    max_rounds: int = Field(default=2, ge=1, le=2)


class AgentConfigUpdate(Strict):
    agents: dict[
        Literal[
            "market_monitoring",
            "public_opinion_monitoring",
            "supervision_sampling",
            "laboratory_testing",
        ],
        AgentConfig,
    ]
