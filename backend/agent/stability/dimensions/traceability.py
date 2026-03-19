from __future__ import annotations


def score_traceability(reasoning_chain: dict, citation_count: int) -> float:
    has_chain = bool(reasoning_chain)
    if has_chain and citation_count > 0:
        return 0.88
    if has_chain:
        return 0.6
    return 0.3
