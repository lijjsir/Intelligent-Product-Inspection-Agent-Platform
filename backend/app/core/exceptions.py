from __future__ import annotations

from typing import Any


class AppError(Exception):
    code = "app_error"
    status_code = 400
    message = "应用错误"
    module = "app"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        detail: str | dict | None = None,
        status_code: int | None = None,
        module: str | None = None,
        trace_id: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.code = code or self.code
        self.message = message or self.message
        self.detail = detail
        self.status_code = status_code or self.status_code
        self.module = module or self.module
        self.trace_id = trace_id
        self.suggestion = suggestion
        super().__init__(self.message)

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "module": self.module,
            "trace_id": self.trace_id,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    message = "资源不存在"


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403
    message = "无权访问"


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    message = "资源冲突"


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422
    message = "请求参数错误"


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    status_code = 503
    message = "服务不可用"


class MemoryError(AppError):
    code = "MEMORY_ERROR"
    status_code = 500
    message = "共享记忆模块错误"
    module = "memory"


class MemoryVectorServiceError(MemoryError):
    code = "MEMORY_VECTOR_SERVICE_ERROR"
    status_code = 503
    message = "共享记忆向量服务错误"
    module = "memory_vector"


class MemoryGraphServiceError(MemoryError):
    code = "MEMORY_GRAPH_SERVICE_ERROR"
    status_code = 503
    message = "共享记忆图数据库错误"
    module = "memory_graph"


class MemoryRollbackError(MemoryError):
    code = "MEMORY_ROLLBACK_ERROR"
    status_code = 500
    message = "共享记忆回滚错误"
    module = "memory_rollback"


class MemoryToolContextError(MemoryError):
    code = "MEMORY_TOOL_CONTEXT_MISSING"
    status_code = 400
    message = "共享记忆工具缺少必要上下文"
    module = "memory"


class MemoryConflictPersistError(MemoryError):
    code = "MEMORY_CONFLICT_PERSIST_FAILED"
    status_code = 500
    message = "共享记忆冲突关系持久化失败"
    module = "memory_conflict"
