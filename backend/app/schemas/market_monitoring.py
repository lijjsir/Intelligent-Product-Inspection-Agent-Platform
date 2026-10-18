"""Inputs for source-based market monitoring; no risk verdicts in this layer."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MarketScan(Strict):
    as_of: date | None = None
    object_type: Literal["product", "enterprise"] = "product"


class MarketRule(Strict):
    min_current: int = Field(default=3, ge=1, le=100000)
    min_increase: int = Field(default=3, ge=1, le=100000)
    growth_factor: float = Field(default=2, ge=1, le=100, allow_inf_nan=False)


class MarketRuleUpdate(MarketRule):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class MarketCoverage(Strict):
    source_id: UUID
    record_type: Literal["consumer_complaint", "public_opinion"]
    start_at: datetime
    end_at: datetime
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("start_at", "end_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("覆盖时间必须包含时区")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.end_at <= self.start_at:
            raise ValueError("覆盖结束必须晚于开始")
        return self


class SignalConversion(Strict):
    target_case_id: UUID | None = None


class MarketFocus(Strict):
    object_type: Literal["product", "enterprise"]
    object_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class FocusRemoval(Strict):
    reason: str = Field(min_length=1, max_length=1000)
