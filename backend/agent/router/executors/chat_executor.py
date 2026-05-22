from __future__ import annotations

import json
from typing import Any

from agent.llm.client import LLMClient
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class ChatExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        if step.capability_key == "chat.general":
            answer = await self._call_model(state, request, self._general_prompt(state))
            if answer is None:
                return observation(step, status="failed", summary="聊天模型不可用，请检查后台模型配置"), []
            return observation(step, status="success", summary=answer), []

        if step.capability_key == "chat.response.compose":
            answer = await self._call_model(state, request, self._compose_prompt(state))
            if answer is None:
                fallback = self._build_fallback(state)
                art = artifact("composed_response", "chat", {"answer": fallback, "summary": fallback, "message_type": "assistant_text", "status": "degraded", "surface": state.surface, "blocked": False})
                return observation(step, status="success", summary=fallback, artifact_ids=[art.artifact_id]), [art]
            composed = self._compose_from_model(state, answer)
            art = artifact("composed_response", "chat", composed)
            return observation(step, status="success", summary=composed.get("summary", answer), artifact_ids=[art.artifact_id]), [art]

        return observation(step, status="failed", summary=f"未知 capability: {step.capability_key}"), []

    # ── model helpers ──

    async def _call_model(self, state: ManagerState, request: NormalizedRequest, user_prompt: str) -> str | None:
        runtime = state.manager_model_runtime or {}
        if not runtime.get("model_id"):
            return None
        try:
            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                provider=runtime.get("provider"),
                org_id=request.org_id,
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
            state.used_llm_calls += 1
            response = await client.chat(
                [
                    {"role": "system", "content": "你是智能助手。用中文简洁准确回答。返回 JSON：{\"answer\":\"...\"}。"},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                observation_name="chat",
                observation_metadata={"surface": state.surface},
            )
            return self._extract_answer(response)
        except Exception:
            return None

    @staticmethod
    def _extract_answer(response: dict) -> str | None:
        if isinstance(response, dict) and "answer" in response:
            return str(response["answer"]).strip() or None
        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, dict):
            answer = content.get("answer") or content.get("text") or ""
            return str(answer).strip() or None
        choices = response.get("choices") if isinstance(response, dict) else None
        if isinstance(choices, list) and choices:
            content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            try:
                data = json.loads(content)
                answer = data.get("answer") or data.get("text") or ""
                return str(answer).strip() or None
            except Exception:
                return content.strip()[:1000] or None
        return None

    # ── prompts ──

    @staticmethod
    def _history_text(state: ManagerState) -> str:
        if not state.history_messages:
            return ""
        lines = []
        for m in state.history_messages[-10:]:
            role = "用户" if m.get("role") == "user" else "助手"
            content = str(m.get("content") or "")[:300]
            if content:
                lines.append(f"{role}：{content}")
        return "\n".join(lines) if lines else ""

    @staticmethod
    def _general_prompt(state: ManagerState) -> str:
        parts = []
        hist = ChatExecutor._history_text(state)
        if hist:
            parts.append(f"对话历史：\n{hist}")
        parts.append(f"用户问题：{state.original_query}")
        return "\n\n".join(parts)

    @staticmethod
    def _compose_prompt(state: ManagerState) -> str:
        parts = []
        hist = ChatExecutor._history_text(state)
        if hist:
            parts.append(f"对话历史：\n{hist}")
        parts.append(f"用户问题：{state.original_query}")
        parts.append(f"场景：{state.surface}")
        if state.observations:
            obs_text = "\n".join(
                f"- [{o.capability_key}] {o.status}: {o.summary}"
                for o in state.observations
                if o.capability_key != "chat.response.compose"
            )
            parts.append(f"执行步骤：\n{obs_text}")
        if state.artifacts:
            for art in state.artifacts:
                if art.type == "composed_response":
                    continue
                content = json.dumps(art.content or {}, ensure_ascii=False, default=str)[:2000]
                parts.append(f"{art.type} 结果：{content}")
        if state.errors:
            parts.append(f"错误：{'; '.join(e.get('message', '') for e in state.errors)}")
        parts.append("请根据以上所有信息，生成最终的自然语言回复。")
        return "\n\n".join(parts)

    # ── compose helpers ──

    @staticmethod
    def _compose_from_model(state: ManagerState, answer: str) -> dict[str, Any]:
        status, blocked = ChatExecutor._resolve_status(state)
        reason = state.route_plan.reason if state.route_plan else ""
        mt = "assistant_text"
        if status == "blocked":
            mt = "action_blocked"
        elif reason == "image_understanding":
            mt = "image_analysis"
        elif reason in {"file_summary", "file_qa"}:
            mt = "file_answer"
        elif reason == "quality_report_query":
            mt = "report_answer"
        elif reason == "quality_task_status":
            mt = "task_status"
        elif reason == "inspection_execute":
            mt = "task_result"
        return {
            "answer": answer,
            "summary": answer[:200] if answer else "",
            "message_type": mt,
            "surface": state.surface,
            "status": status,
            "blocked": blocked,
        }

    @staticmethod
    def _resolve_status(state: ManagerState) -> tuple[str, bool]:
        if state.errors or state.missing_inputs:
            return "blocked", True
        if state.route_plan and state.route_plan.reason == "action_blocked":
            return "blocked", True
        if state.final_action == "fail":
            return "failed", False
        return "completed", False

    @staticmethod
    def _build_fallback(state: ManagerState) -> str:
        if state.errors or state.missing_inputs:
            return "模型暂不可用，无法完成请求。请检查后台模型配置。"
        if state.observations:
            for obs in reversed(state.observations):
                if obs.summary and obs.capability_key != "chat.response.compose":
                    return obs.summary[:500]
        return "模型暂不可用，请稍后重试或检查后台配置。"
