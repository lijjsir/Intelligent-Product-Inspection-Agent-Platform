"""ConflictDetectionService - two-phase conflict detection during memory search.

Phase 1: cosine similarity filtering on recalled items (>0.75 threshold).
Phase 2: LLM judgment classifying each pair as CONTRADICTS/SUPPORTS/UNRELATED/REFINES.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.schemas.memory import ConflictRelation

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75

LLM_JUDGE_PROMPT = """You are evaluating two memory claims from a product inspection system. Output ONLY one word:

- CONTRADICTS: the claims cannot both be true
- SUPPORTS: claim B supports claim A
- REFINES: claim B is a more specific or updated version of claim A
- UNRELATED: no logical relationship between the claims

Claim A ({type_a}): {summary_a}

Claim B ({type_b}): {summary_b}

Relationship:"""


@dataclass
class ConflictPair:
    source_memory_id: str
    target_memory_id: str
    relation: ConflictRelation
    source_score: float = 0.0
    target_score: float = 0.0


@dataclass
class ConflictDetectionResult:
    pairs: list[ConflictPair] = field(default_factory=list)
    contested_ids: set[str] = field(default_factory=set)
    refine_pairs: list[tuple[str, str]] = field(default_factory=list)


class ConflictDetectionService:
    """Detects conflicts among recalled memory items using two-phase approach."""

    def __init__(self, org_id: str, user_id: str | None = None, trace_id: str | None = None):
        self._org_id = org_id
        self._user_id = user_id
        self._trace_id = trace_id

    async def detect(self, items: list[dict]) -> ConflictDetectionResult:
        """Run two-phase conflict detection on recalled items.

        Args:
            items: List of dicts with memory_id, summary, score, memory_type

        Returns:
            ConflictDetectionResult with pairs to mark as conflicted/refined.
        """
        if len(items) < 2:
            return ConflictDetectionResult()

        # Phase 1: Find pairs with high cosine similarity (using Qdrant scores as proxy)
        candidates = self._phase1_similarity_filter(items)
        if not candidates:
            return ConflictDetectionResult()

        # Phase 2: LLM judgment on candidate pairs
        pairs = await self._phase2_llm_judge(candidates)

        result = ConflictDetectionResult()
        for pair in pairs:
            if pair.relation == ConflictRelation.CONTRADICTS:
                result.pairs.append(pair)
                result.contested_ids.add(pair.source_memory_id)
                result.contested_ids.add(pair.target_memory_id)
            elif pair.relation == ConflictRelation.REFINES:
                result.pairs.append(pair)
                result.refine_pairs.append((pair.target_memory_id, pair.source_memory_id))

        return result

    def _phase1_similarity_filter(self, items: list[dict]) -> list[tuple[dict, dict]]:
        """Find pairs with Qdrant score similarity > threshold.

        Since we don't have raw vectors here, use a heuristic: if two items
        both have high scores for the same query, their claim embeddings are
        likely close in vector space. Score product > threshold² is a proxy.
        """
        candidates: list[tuple[dict, dict]] = []
        threshold_sq = SIMILARITY_THRESHOLD * SIMILARITY_THRESHOLD

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                # Only compare items of the same memory_type for efficiency
                if a.get("memory_type") != b.get("memory_type"):
                    continue
                score_a = float(a.get("score", 0))
                score_b = float(b.get("score", 0))
                if score_a * score_b >= threshold_sq:
                    candidates.append((a, b))

        return candidates

    async def _phase2_llm_judge(self, candidates: list[tuple[dict, dict]]) -> list[ConflictPair]:
        """For each candidate pair, ask LLM to classify the relationship."""
        pairs: list[ConflictPair] = []

        for a, b in candidates:
            try:
                relation = await self._judge_pair(a, b)
                pairs.append(ConflictPair(
                    source_memory_id=str(a.get("memory_id", "")),
                    target_memory_id=str(b.get("memory_id", "")),
                    relation=relation,
                    source_score=float(a.get("score", 0)),
                    target_score=float(b.get("score", 0)),
                ))
            except Exception:
                logger.debug("LLM conflict judge failed for pair %s <-> %s",
                             a.get("memory_id"), b.get("memory_id"), exc_info=True)

        return pairs

    async def _judge_pair(self, a: dict, b: dict) -> ConflictRelation:
        """Call LLM to judge relationship between two memory claims."""
        from agent.llm.client import LLMClient
        from agent.llm.gateway import LLMGateway
        from app.services.model_config_service import ModelConfigService
        from infra.database.session import get_session

        prompt = LLM_JUDGE_PROMPT.format(
            type_a=str(a.get("memory_type", "")),
            summary_a=str(a.get("summary", "")),
            type_b=str(b.get("memory_type", "")),
            summary_b=str(b.get("summary", "")),
        )

        async with get_session() as session:
            runtime_models = await ModelConfigService(session, self._org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(runtime_models, model_types={"chat", "text_generation"})
            if not runtime:
                raise RuntimeError("No active LLM model configured for conflict detection")

            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=str(runtime.get("model_id") or ""),
                trace_id=self._trace_id,
                org_id=self._org_id,
                provider=str(runtime.get("provider") or ""),
            )
            response = await client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=8,
                observation_name="memory.conflict_judge",
            )

        raw = str(response.get("content", "")).strip().upper()
        for rel in ConflictRelation:
            if rel.value.upper() in raw:
                return rel
        return ConflictRelation.UNRELATED
