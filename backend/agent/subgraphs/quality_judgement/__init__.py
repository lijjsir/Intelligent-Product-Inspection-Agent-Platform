from __future__ import annotations

from typing import Any

__all__ = ["QualityJudgementSubgraph"]


def __getattr__(name: str) -> Any:
    if name == "QualityJudgementSubgraph":
        from agent.subgraphs.quality_judgement.graph import QualityJudgementSubgraph

        return QualityJudgementSubgraph
    raise AttributeError(name)
