"""RAG vs Memory conflict detector — rule-based + LLM fallback."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

ALLOW_TERMS = ["可以", "允许", "直接", "应当", "建议", "可", "能", "能够", "肯定"]
DENY_TERMS = ["不得", "禁止", "不能", "不允许", "需复核", "必须复检", "不可", "不应", "严禁"]


def _keyword_overlap(text_a: str, text_b: str) -> int:
    set_a = set(text_a)
    set_b = set(text_b)
    return len(set_a & set_b)


def _roughly_related(memory_summary: str, rag_quote: str) -> bool:
    return _keyword_overlap(memory_summary, rag_quote) >= 3


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


def rule_judge_rag_memory(memory_summary: str, rag_quote: str) -> dict | None:
    """Rule-based conflict detection for RAG vs Memory.

    Returns a verdict dict if a clear rule match is found, None otherwise.
    """
    if not _roughly_related(memory_summary, rag_quote):
        return None

    mem_allow = _contains_any(memory_summary, ALLOW_TERMS)
    mem_deny = _contains_any(memory_summary, DENY_TERMS)
    rag_allow = _contains_any(rag_quote, ALLOW_TERMS)
    rag_deny = _contains_any(rag_quote, DENY_TERMS)

    if mem_allow and rag_deny:
        return {
            "verdict": "conflict",
            "confidence": 0.85,
            "reason": "Memory expresses allow/direct handling, but RAG standard requires deny/recheck.",
        }
    if mem_deny and rag_allow:
        return {
            "verdict": "conflict",
            "confidence": 0.80,
            "reason": "Memory expresses deny/forbid, but RAG standard allows/permit.",
        }

    mem_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|px|℃|度|秒|分钟|小时|%)?", memory_summary)
    rag_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|px|℃|度|秒|分钟|小时|%)?", rag_quote)
    if mem_nums and rag_nums:
        for mv, mu in mem_nums:
            for rv, ru in rag_nums:
                if mu == ru and abs(float(mv) - float(rv)) / max(float(rv), 0.001) > 0.2:
                    return {
                        "verdict": "conflict",
                        "confidence": 0.75,
                        "reason": f"Numeric threshold mismatch: memory={mv}{mu} vs RAG={rv}{ru}.",
                    }

    if _roughly_related(memory_summary, rag_quote):
        return {
            "verdict": "refine",
            "confidence": 0.55,
            "reason": "Memory and RAG are related; LLM judge recommended for fine-grained check.",
        }

    return None


LLM_RAG_MEMORY_JUDGE_PROMPT = """Determine whether the following two pieces of content conflict.

User question:
{query}

Shared memory:
{memory_summary}

RAG evidence:
{rag_quote}

Output ONLY valid JSON:
{{"verdict": "support|conflict|refine|unrelated|uncertain", "confidence": 0.0-1.0, "reason": "one sentence explanation"}}"""


class RagMemoryDetector:
    """Detects conflicts between RAG evidence and shared memory items."""

    def __init__(self, org_id: str, user_id: str | None = None, trace_id: str | None = None):
        self._org_id = org_id
        self._user_id = user_id
        self._trace_id = trace_id

    async def detect(
        self,
        query: str,
        rag_hits: list[dict],
        memory_hits: list[dict],
    ) -> dict:
        """Check top-3 RAG hits against top-5 memory items (max 15 pairs)."""
        conflicts: list[dict] = []
        suppressed: set[str] = set()
        downranked: set[str] = set()

        rags = rag_hits[:3]
        mems = memory_hits[:5]

        for rag in rags:
            rag_quote = str(rag.get("quote", "") or rag.get("text", ""))
            if not rag_quote:
                continue
            for mem in mems:
                mem_summary = str(mem.get("summary", ""))
                if not mem_summary:
                    continue

                rule_result = rule_judge_rag_memory(mem_summary, rag_quote)
                if rule_result and rule_result["verdict"] == "conflict" and rule_result["confidence"] >= 0.75:
                    conflicts.append({
                        "type": "rag_vs_memory",
                        "rag_chunk_id": rag.get("id", rag.get("chunk_id", "")),
                        "memory_id": mem.get("memory_id", ""),
                        "verdict": rule_result["verdict"],
                        "confidence": rule_result["confidence"],
                        "reason": rule_result["reason"],
                        "source": "rule",
                    })
                    suppressed.add(mem.get("memory_id", ""))
                    continue
                if rule_result and rule_result["verdict"] == "refine":
                    downranked.add(mem.get("memory_id", ""))
                    continue
                if rule_result:
                    continue

                if _roughly_related(mem_summary, rag_quote):
                    llm_result = await self._llm_judge(query, mem_summary, rag_quote)
                    verdict = llm_result.get("verdict", "uncertain")
                    confidence = float(llm_result.get("confidence", 0.5))
                    if verdict == "conflict" and confidence >= 0.75:
                        conflicts.append({
                            "type": "rag_vs_memory",
                            "rag_chunk_id": rag.get("id", rag.get("chunk_id", "")),
                            "memory_id": mem.get("memory_id", ""),
                            "verdict": verdict,
                            "confidence": confidence,
                            "reason": llm_result.get("reason", ""),
                            "source": "llm",
                        })
                        suppressed.add(mem.get("memory_id", ""))
                    elif verdict == "refine":
                        downranked.add(mem.get("memory_id", ""))

        return {
            "conflicts": conflicts,
            "suppressed_memory_ids": list(suppressed),
            "downranked_memory_ids": list(downranked),
        }

    async def _llm_judge(self, query: str, memory_summary: str, rag_quote: str) -> dict:
        from agent.llm.client import LLMClient
        from agent.llm.gateway import LLMGateway
        from app.services.model_config_service import ModelConfigService
        from infra.database.session import get_session

        prompt = LLM_RAG_MEMORY_JUDGE_PROMPT.format(
            query=query,
            memory_summary=memory_summary,
            rag_quote=rag_quote,
        )

        async with get_session() as session:
            runtime_models = await ModelConfigService(session, self._org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(runtime_models, model_types={"chat", "text_generation"})
            if not runtime:
                return {"verdict": "uncertain", "confidence": 0.0, "reason": "no LLM runtime"}

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
                max_tokens=128,
                observation_name="memory.rag_memory_conflict_judge",
            )

        raw = str(response.get("content", "")).strip()
        return json.loads(raw)
