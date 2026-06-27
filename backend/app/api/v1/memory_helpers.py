"""Shared helpers for memory API route construction and error mapping."""
from __future__ import annotations

from uuid import UUID

from app.core.exceptions import (
    MemoryError as AppMemoryError,
    MemoryGraphServiceError,
    MemoryVectorServiceError as AppMemoryVectorServiceError,
)
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import MemoryVectorService


def get_memory_service(
    db,
    org_id: str,
    vector_svc: MemoryVectorService | None = None,
    candidate_vector_svc: MemoryVectorService | None = None,
    trace_id: str | None = None,
) -> MemoryService:
    try:
        return MemoryService(
            db,
            org_id,
            vector_service=vector_svc,
            candidate_vector_service=candidate_vector_svc,
        )
    except Exception as exc:
        raise MemoryGraphServiceError(
            message=f"Memory service initialization failed: {exc}",
            code="SHARED_MEMORY_GRAPH_SYNC_FAILED",
            detail={"operation": "memory_service_initialization"},
            trace_id=trace_id,
        ) from exc


def build_vector_service(
    org_id: str,
    user_id: str | None = None,
    trace_id: str | None = None,
    collection: str | None = None,
) -> MemoryVectorService:
    """Build MemoryVectorService with a real Embedder factory."""
    from agent.rag.embedder import Embedder

    async def embedder_factory(text: str) -> list[float]:
        embedder = Embedder(
            org_id=org_id,
            user_id=user_id,
            trace_id=trace_id,
            allow_pseudo_fallback=False,
        )
        return await embedder.embed(text)

    return MemoryVectorService(
        collection=collection or "piap_shared_memory",
        embedder_factory=embedder_factory,
        org_id=org_id,
        user_id=user_id,
        trace_id=trace_id,
    )


def vector_error(exc: Exception, trace_id: str | None, operation: str) -> AppMemoryVectorServiceError:
    return AppMemoryVectorServiceError(
        message=f"{operation} failed: {exc}",
        code="SHARED_MEMORY_VECTOR_OPERATION_FAILED",
        detail={"operation": operation},
        trace_id=trace_id,
    )


def memory_operation_error(exc: Exception, trace_id: str | None, operation: str) -> AppMemoryError:
    message = str(exc)
    if "Memory graph" in message:
        return MemoryGraphServiceError(
            message=f"{operation} failed: {message}",
            code="SHARED_MEMORY_GRAPH_SYNC_FAILED",
            detail={"operation": operation},
            trace_id=trace_id,
        )
    return AppMemoryError(
        message=f"{operation} failed: {message}",
        code="SHARED_MEMORY_OPERATION_FAILED",
        detail={"operation": operation},
        trace_id=trace_id,
    )


def memory_api_error(
    *,
    code: str,
    message: str,
    trace_id: str | None,
    status_code: int,
    detail: dict | None = None,
    suggestion: str | None = None,
) -> AppMemoryError:
    return AppMemoryError(
        message=message,
        code=code,
        detail=detail,
        status_code=status_code,
        trace_id=trace_id,
        suggestion=suggestion,
    )


def invalid_memory_request(message: str, trace_id: str | None, *, detail: dict | None = None) -> AppMemoryError:
    return memory_api_error(
        code="SHARED_MEMORY_INVALID_REQUEST",
        message=message,
        trace_id=trace_id,
        status_code=422,
        detail=detail,
        suggestion="Check request parameters and retry.",
    )


def missing_org_error(trace_id: str | None) -> AppMemoryError:
    return memory_api_error(
        code="SHARED_MEMORY_INVALID_REQUEST",
        message="missing org_id",
        trace_id=trace_id,
        status_code=400,
        detail={"field": "org_id"},
        suggestion="Provide org_id in the request or authenticate with an organization-bound user.",
    )


def scope_forbidden_error(trace_id: str | None) -> AppMemoryError:
    return memory_api_error(
        code="SHARED_MEMORY_SCOPE_FORBIDDEN",
        message="org_id in request does not match current user",
        trace_id=trace_id,
        status_code=403,
        detail={"field": "org_id"},
        suggestion="Use the current user's organization scope.",
    )


def not_found_error(message: str, trace_id: str | None = None) -> AppMemoryError:
    return memory_api_error(
        code="SHARED_MEMORY_NOT_FOUND",
        message=message,
        trace_id=trace_id,
        status_code=404,
        suggestion="Refresh memory governance data and retry.",
    )


def embedder_unavailable_error(
    exc: Exception,
    trace_id: str | None,
    operation: str,
) -> AppMemoryVectorServiceError:
    return AppMemoryVectorServiceError(
        message=f"Embedding service unavailable: {exc}",
        code="SHARED_MEMORY_EMBEDDER_UNAVAILABLE",
        detail={"operation": operation},
        trace_id=trace_id,
        suggestion="Configure a healthy embedding model and API key.",
    )


def require_uuid(value: str | None, field: str, trace_id: str | None) -> None:
    if not value:
        raise invalid_memory_request(
            f"{field} is required",
            trace_id,
            detail={"field": field},
        )
    try:
        UUID(str(value))
    except ValueError as exc:
        raise invalid_memory_request(
            f"{field} must be a UUID",
            trace_id,
            detail={"field": field, "value": value},
        ) from exc


def validate_optional_uuid(value: str | None, field: str, trace_id: str | None) -> None:
    if value:
        require_uuid(value, field, trace_id)
