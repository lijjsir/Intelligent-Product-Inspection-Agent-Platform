from __future__ import annotations

from typing import Any

__all__ = [
    "QualityChatGraph",
    "QualityJudgementSubgraph",
    "EvidenceArbitrationGraph",
    "QualityAnalysisGraph",
    "VisionInspectionGraph",
    "MemoryGovernanceGraph",
]


def __getattr__(name: str) -> Any:
    if name == "QualityChatGraph":
        from agent.subgraphs.quality_chat import QualityChatGraph

        return QualityChatGraph
    if name == "QualityJudgementSubgraph":
        from agent.subgraphs.quality_judgement import QualityJudgementSubgraph

        return QualityJudgementSubgraph
    if name == "EvidenceArbitrationGraph":
        from agent.subgraphs.evidence_arbitration import EvidenceArbitrationGraph

        return EvidenceArbitrationGraph
    if name == "QualityAnalysisGraph":
        from agent.subgraphs.quality_analysis import QualityAnalysisGraph

        return QualityAnalysisGraph
    if name == "VisionInspectionGraph":
        from agent.subgraphs.vision_inspection import VisionInspectionGraph

        return VisionInspectionGraph
    if name == "MemoryGovernanceGraph":
        from agent.subgraphs.memory_governance import MemoryGovernanceGraph

        return MemoryGovernanceGraph
    raise AttributeError(name)
