from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagPolicyDecision:
    should_retrieve: bool = False
    rag_space_id: str | None = None
    top_k: int = 4
    filter_conditions: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


RAG_POLICY_MAP = {
    "general_chat": {"retrieve": False, "source": None, "top_k": 0},
    "rag_qa": {"retrieve": True, "source": "selected_space", "top_k": 4},
    "quality_qa": {"retrieve": True, "source": "standard_library + selected_space", "top_k": 6},
    "task_create": {"retrieve": False, "source": None, "top_k": 0},
    "inspection_execute": {"retrieve": True, "source": "spec_code_standard + selected_space", "top_k": 8},
}


class RagPolicy:
    """按 sub_route 决定是否检索、检索哪个空间、top_k、过滤条件。"""

    def decide(
        self,
        *,
        sub_route: str,
        selected_rag_space: dict[str, Any] | None = None,
        spec_code: str | None = None,
    ) -> RagPolicyDecision:
        policy = RAG_POLICY_MAP.get(sub_route, RAG_POLICY_MAP["general_chat"])

        if not policy["retrieve"]:
            return RagPolicyDecision(should_retrieve=False, reason=f"{sub_route} 不需要 RAG 检索")

        rag_space_id = None
        filter_conditions: dict[str, Any] = {}

        if selected_rag_space and selected_rag_space.get("id"):
            rag_space_id = selected_rag_space["id"]
            filter_conditions["rag_space_id"] = rag_space_id

        if sub_route == "inspection_execute" and spec_code:
            filter_conditions["spec_code"] = spec_code

        return RagPolicyDecision(
            should_retrieve=True,
            rag_space_id=rag_space_id,
            top_k=policy["top_k"],
            filter_conditions=filter_conditions,
            reason=f"{sub_route} 需要 RAG 检索，来源: {policy['source']}",
        )
