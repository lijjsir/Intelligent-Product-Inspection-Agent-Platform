from __future__ import annotations


class ShortTermMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "SHORT_TERM_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class SharedMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "SHARED_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class GraphMemoryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "GRAPH_MEMORY_FAILED",
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}
