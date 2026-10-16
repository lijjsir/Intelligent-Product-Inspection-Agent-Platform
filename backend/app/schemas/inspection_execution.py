from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator


class ImageViewAssignment(BaseModel):
    model_config=ConfigDict(extra="forbid")
    image_hash:str=Field(min_length=1,max_length=128)
    view:str=Field(min_length=1,max_length=128)


class ExecutionRequirement(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision_id:str
    candidate_id:str


class ObservationReference(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind:Literal["measurement_record","report_attachment"]
    id:str
    measurement_key:str=Field(min_length=1,max_length=128)
    sample_id:str=Field(min_length=1,max_length=128)
    value:float|None=Field(default=None,strict=True,allow_inf_nan=False)
    unit:str=Field(default="",max_length=100)
    method:str=Field(default="",max_length=4000)
    conditions:dict=Field(default_factory=dict)
    uncertainty:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    report_page:int|None=Field(default=None,ge=1)
    report_item:str=Field(default="",max_length=255)


class InspectionExecutionCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=128)
    task_id:str
    session_id:str|None=None
    product_category:str=Field(min_length=1,max_length=100)
    production_date:str
    policy_id:str|None=None
    context_hash:str|None=None
    image_view_assignments:list[ImageViewAssignment]=Field(default_factory=list,max_length=500)
    requirements:list[ExecutionRequirement]=Field(min_length=1,max_length=200)
    sample_ids:list[str]=Field(min_length=1,max_length=500)
    observations:list[ObservationReference]=Field(default_factory=list,max_length=5000)


class InspectionExecutionReview(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_version:int=Field(ge=1)
    request_key:str=Field(min_length=8,max_length=128)
    decision:Literal["accept","reject","request_evidence"]
    reason:str=Field(min_length=4,max_length=4000)
    report_values_verified:bool=False
    evidence_refs:list[str]=Field(default_factory=list,max_length=50)
    verified_evidence_ids:list[str]=Field(default_factory=list,max_length=5000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls,value):
        if len(value.strip())<4:raise ValueError("复核说明至少包含四个有效字符")
        return value.strip()

    @field_validator("evidence_refs", "verified_evidence_ids")
    @classmethod
    def clean_references(cls,value):
        if any(not str(item).strip() for item in value):raise ValueError("复核引用不能仅包含空白")
        return list(dict.fromkeys(item.strip() for item in value))


class PolicyPublish(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=128)
    expected_updated_at:str
    required_fields:list[str]=Field(default_factory=list,max_length=40)
    input_modes:list[Literal["image","measurement","mixed","report"]]=Field(default=["image","measurement","mixed","report"],min_length=1,max_length=4)
    required_image_count:int|None=Field(default=None,ge=0,le=500)
    required_views:list[str]|None=Field(default=None,max_length=100)
    review_on_fail:bool=True
    review_on_report_transcription:bool=True
    reason:str=Field(min_length=4,max_length=4000)

    @field_validator("required_fields")
    @classmethod
    def valid_fields(cls,values):
        from app.services.inspection_execution_policy_service import FIELD_LABELS
        if any(v not in FIELD_LABELS and not (v.startswith("metadata:") and len(v)>9) for v in values):
            raise ValueError("请选择明确的任务字段，扩展字段需使用 metadata: 前缀")
        return list(dict.fromkeys(values))


class TaskReportLink(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=128)
    expected_context_hash:str=Field(min_length=64,max_length=64)
    source_record_id:str
    attachment_id:str
    sample_codes:list[str]=Field(min_length=1,max_length=500)
    reason:str=Field(min_length=4,max_length=4000)

    @field_validator("sample_codes")
    @classmethod
    def meaningful_sample_codes(cls,values):
        if any(not v.strip() or len(v.strip())>128 for v in values):raise ValueError("报告原样品编号需为1至128个有效字符")
        return list(dict.fromkeys(v.strip() for v in values))
