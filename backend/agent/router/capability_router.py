from __future__ import annotations

from typing import Any

from agent.router.contracts import (
    AgentArtifact,
    AgentCapabilityError,
    AgentObservation,
    CapabilityContext,
)


class CapabilityRouter:
    """Routes capability calls to their registered handlers.

    This is the SINGLE entry point for all capability execution.
    Business executors (Chat/File/InspectionTask) call this instead of
    directly importing and instantiating old executor classes.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, capability_key: str, handler: Any) -> None:
        self._handlers[capability_key] = handler

    async def call(
        self,
        capability: str,
        context: CapabilityContext,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        handler = self._handlers.get(capability)
        if handler is None:
            raise AgentCapabilityError(
                code="UNKNOWN_CAPABILITY",
                message=f"未知能力：{capability}",
                frontend_visible=True,
            )
        try:
            return await handler.run(context)
        except AgentCapabilityError:
            raise
        except Exception as exc:
            raise AgentCapabilityError(
                code="CAPABILITY_EXECUTION_FAILED",
                message=f"能力 {capability} 执行失败：{exc}",
                detail={"raw_error": str(exc)},
                frontend_visible=True,
            ) from exc


# Singleton instance
_capability_router: CapabilityRouter | None = None


def get_capability_router() -> CapabilityRouter:
    global _capability_router
    if _capability_router is None:
        _capability_router = _build_default_router()
    return _capability_router


def _build_default_router() -> CapabilityRouter:
    router = CapabilityRouter()

    # Register all capability handlers
    from agent.router.capabilities.rag_handler import RagRetrieveHandler
    from agent.router.capabilities.vision_handler import VisionUnderstandingHandler
    from agent.router.capabilities.quality_report_handler import QualityReportHandler
    from agent.router.capabilities.data_analysis_handler import DataAnalysisHandler
    from agent.router.capabilities.web_search_handler import WebSearchHandler

    router.register("rag.retrieve", RagRetrieveHandler())
    router.register("rag.ingest", RagRetrieveHandler())  # ingest handled by same handler
    router.register("image.understanding", VisionUnderstandingHandler())
    router.register("quality.report.query", QualityReportHandler())
    router.register("quality.task.status", QualityReportHandler())
    router.register("data.analysis", DataAnalysisHandler())
    router.register("web.search", WebSearchHandler())

    return router
