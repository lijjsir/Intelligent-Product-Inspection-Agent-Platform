from __future__ import annotations

from typing import Any

__all__ = ["QualityChatGraph", "QualityJudgementSubgraph"]


def __getattr__(name: str) -> Any:
    if name == "QualityChatGraph":
        from agent.subgraphs.quality_chat import QualityChatGraph

        return QualityChatGraph
    if name == "QualityJudgementSubgraph":
        from agent.subgraphs.quality_judgement import QualityJudgementSubgraph

        return QualityJudgementSubgraph
    raise AttributeError(name)
