from typing import Literal
from pydantic import BaseModel,ConfigDict,Field


class KnowledgeSource(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind: Literal["rag_document","task_result","meeting_message","intake_record","standard_revision","inspection_execution"]
    id: str
    quote: str = Field(default="",max_length=8000)


class KnowledgeSubmit(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8,max_length=128)
    claim: str = Field(min_length=4,max_length=4000)
    product_category: str = Field(min_length=1,max_length=128)
    applicability: str = Field(min_length=4,max_length=4000)
    limitations: str = Field(min_length=4,max_length=4000)
    sources: list[KnowledgeSource] = Field(min_length=1,max_length=20)
    consent_to_review: bool = False
    requested_scope: Literal["private","organization"] = "private"
    consent_to_share: bool = False
    qdl: dict|None = None
    related_memory_ids: list[str] = Field(default_factory=list,max_length=20)


class KnowledgeAction(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    request_key: str = Field(min_length=8,max_length=128)
    reason: str = Field(min_length=4,max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list,max_length=30)


class KnowledgeReview(KnowledgeAction):
    decision: Literal["approve","needs_information","dispute","reject"]


class KnowledgePublish(KnowledgeAction):
    mapping_rules: dict = Field(default_factory=dict)
    mapping_version: str = Field(default="explicit-v1",min_length=4,max_length=128)


class KnowledgeShare(KnowledgeAction):
    decision: Literal["approve","reject"]


class SpaceShare(BaseModel):
    model_config=ConfigDict(extra="forbid")
    user_id: str
    expected_version: int = Field(default=0,ge=0)
    reason: str = Field(min_length=4,max_length=2000)
    allow_knowledge_submission: bool = False


class KnowledgeSourceRequest(BaseModel):
    kind: Literal["rag_document","task_result","meeting_message","intake_record","standard_revision","inspection_execution"]
    id: str
