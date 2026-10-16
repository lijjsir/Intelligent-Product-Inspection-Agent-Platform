from pydantic import BaseModel, ConfigDict, Field


class StandardApplicabilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_category: str = Field(default="", max_length=100)
    production_date: str | None = None
    conditions: str = Field(default="", max_length=4000)
