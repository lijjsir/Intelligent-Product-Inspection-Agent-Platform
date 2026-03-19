from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.graph.state import InspectionState
from agent.llm.client import LLMClient


def _fallback_conclusion(defects: list[dict[str, Any]]) -> dict[str, Any]:
    max_conf = max([float(d.get("confidence") or 0.0) for d in defects], default=0.0)
    verdict = "pass" if max_conf < 0.55 else "fail"
    score = 1.0 - min(max_conf, 1.0)
    return {
        "verdict": verdict,
        "overall_score": round(score, 4),
        "reasoning_chain": {
            "summary": "基于缺陷置信度的保守策略输出结论",
            "max_confidence": max_conf,
        },
    }


async def run_reasoning(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    defects = state.get("defects") or []
    docs = state.get("knowledge_docs") or []
    prompt = {
        "task_id": state.get("task_id"),
        "defects": defects,
        "docs": [{"id": d.get("id"), "score": d.get("score"), "text": (d.get("text") or "")[:300]} for d in docs],
        "instruction": '输出 JSON: {"verdict":"pass|fail|uncertain","overall_score":0-1,"reasoning_chain":{...}}',
    }
    client = LLMClient()
    conclusion: dict[str, Any]
    try:
        data = await client.chat([{"role": "user", "content": str(prompt)}], temperature=0.1)
        verdict = str(data.get("verdict") or "uncertain")
        overall_score = float(data.get("overall_score") or 0.5)
        reasoning_chain = data.get("reasoning_chain") if isinstance(data.get("reasoning_chain"), dict) else {}
        conclusion = {
            "verdict": verdict,
            "overall_score": max(0.0, min(overall_score, 1.0)),
            "reasoning_chain": reasoning_chain,
        }
    except Exception:
        conclusion = _fallback_conclusion(defects)

    state["reasoning_chain"] = conclusion.get("reasoning_chain") or {}
    state["conclusion"] = conclusion
    state.setdefault("timeline", []).append(
        {"stage": "reasoning", "message": f"推理完成，结论 {conclusion['verdict']}", "ts": now}
    )
    return state
