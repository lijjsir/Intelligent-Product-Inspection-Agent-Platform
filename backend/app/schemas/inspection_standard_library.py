from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectionStandardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    product_family: str | None = Field(default=None, min_length=1, max_length=128)
    domain: str | None = Field(default=None, max_length=100)
    product_category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    rag_space_ids: list[str] = Field(..., min_length=1)
    qdrant_collection: str | None = Field(default=None, max_length=128)
    pdf_root_dir: str | None = Field(default=None, max_length=1000)
    file_glob: str = Field(default="*.pdf", max_length=64)
    chunk_strategy: str = Field(default="heading_then_size", max_length=32)
    standard_status: str = Field(default="现行", max_length=32)
    import_mode: str = Field(default="scan_and_index", max_length=32)
    auto_reindex: bool = False
    is_active: bool = True


class InspectionStandardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    product_family: str | None = Field(default=None, min_length=1, max_length=128)
    domain: str | None = Field(default=None, max_length=100)
    product_category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    rag_space_ids: list[str] | None = Field(default=None, min_length=1)
    qdrant_collection: str | None = Field(default=None, max_length=128)
    pdf_root_dir: str | None = Field(default=None, max_length=1000)
    file_glob: str | None = Field(default=None, max_length=64)
    chunk_strategy: str | None = Field(default=None, max_length=32)
    standard_status: str | None = Field(default=None, max_length=32)
    import_mode: str | None = Field(default=None, max_length=32)
    auto_reindex: bool | None = None
    is_active: bool | None = None


class InspectionStandardRagSpaceSummary(BaseModel):
    id: str
    name: str
    document_count: int = 0
    status: str | None = None


class InspectionStandardResponse(BaseModel):
    id: str
    org_id: str | None = None
    name: str
    product_family: str
    domain: str | None = None
    product_category: str | None = None
    description: str | None = None
    rag_space_ids: list[str]
    rag_spaces: list[InspectionStandardRagSpaceSummary] = Field(default_factory=list)
    total_document_count: int = 0
    qdrant_collection: str | None = None
    pdf_root_dir: str | None = None
    file_glob: str = "*.pdf"
    chunk_strategy: str = "heading_then_size"
    standard_status: str = "现行"
    auto_reindex: bool = False
    pdf_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    import_status: str = "not_scanned"
    last_scanned_at: datetime | None = None
    last_indexed_at: datetime | None = None
    error_message: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StandardDocumentResponse(BaseModel):
    id: str
    library_id: str
    standard_no: str
    standard_name: str
    domain: str
    product_category: str | None = None
    standard_level: str
    standard_status: str = "现行"
    file_name: str
    file_path: str
    file_hash: str | None = None
    file_size: int | None = None
    page_count: int | None = None
    chunk_count: int = 0
    qdrant_collection: str | None = None
    import_status: str = "pending"
    last_indexed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StandardDocumentChunkResponse(BaseModel):
    id: str
    document_id: str
    library_id: str
    chunk_index: int
    page_from: int | None = None
    page_to: int | None = None
    section_title: str | None = None
    chunk_text: str
    payload_json: dict | None = None
    qdrant_point_id: str
    token_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StandardLibraryScanResult(BaseModel):
    library_id: str
    scanned_count: int
    created_count: int
    updated_count: int
    documents: list[StandardDocumentResponse] = Field(default_factory=list)


class StandardLibraryIndexResult(BaseModel):
    library_id: str
    document_count: int
    indexed_document_count: int
    chunk_count: int
    failed_count: int


class StandardRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    domain: str | None = None
    product_category: str | None = None
    defect_keywords: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=20)
    only_active: bool = True


class StandardRetrieveHit(BaseModel):
    id: str
    title: str
    source: str
    quote: str
    score: float
    standard_no: str | None = None
    standard_name: str | None = None
    domain: str | None = None
    product_category: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    payload: dict = Field(default_factory=dict)


class StandardRetrieveResponse(BaseModel):
    hits: list[StandardRetrieveHit]
    hit_count: int
    candidate_count: int
    latency_ms: float


class PaginatedInspectionStandards(BaseModel):
    items: list[InspectionStandardResponse]
    total: int
    page: int
    size: int


class PaginatedDocuments(BaseModel):
    items: list[StandardDocumentResponse]
    total: int
    page: int
    size: int


class StandardDocumentUpdate(BaseModel):
    standard_no: str | None = Field(default=None, max_length=100)
    standard_name: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=100)
    product_category: str | None = Field(default=None, max_length=100)
    standard_level: str | None = Field(default=None, max_length=32)
    standard_status: str | None = Field(default=None, max_length=32)
    error_message: str | None = Field(default=None, max_length=2000)
