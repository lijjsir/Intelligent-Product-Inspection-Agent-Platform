from __future__ import annotations

from dataclasses import dataclass, field
import json

from agent.router.contracts import AgentArtifact, AgentObservation, AgentRoutePlan
from agent.router.manager_state import ManagerState


@dataclass
class EvaluationResult:
    satisfied: bool
    score: float
    next_action: str
    reason: str
    missing_inputs: list[str] = field(default_factory=list)
    recommended_next_capabilities: list[str] = field(default_factory=list)


class ManagerEvaluator:
    async def evaluate(
        self,
        state: ManagerState,
        plan: AgentRoutePlan,
        observations: list[AgentObservation],
        artifacts: list[AgentArtifact],
    ) -> EvaluationResult:
        if state.missing_inputs:
            return EvaluationResult(
                satisfied=False,
                score=0.0,
                next_action="ask_user",
                reason="缺少必要输入",
                missing_inputs=list(state.missing_inputs),
            )
        if state.errors:
            return EvaluationResult(
                satisfied=False,
                score=0.0,
                next_action="fail",
                reason=str(state.errors[-1].get("message") or "执行被阻止"),
            )
        if any(item.status == "failed" for item in observations):
            failed_items = [item.capability_key for item in observations if item.status == "failed"]
            return EvaluationResult(False, 0.2, "fail", f"能力执行失败：{', '.join(failed_items)}")
        artifact_types = {item.type for item in [*state.artifacts, *artifacts]}
        if any(step.capability_key == "chat.general" for step in plan.steps):
            return EvaluationResult(True, 1.0, "finish", "普通聊天已生成回复")
        composed_artifacts = [
            item for item in [*state.artifacts, *artifacts] if item.type == "composed_response"
        ]
        if any(str((item.content or {}).get("status") or "completed") != "blocked" for item in composed_artifacts):
            return EvaluationResult(True, 1.0, "finish", "聊天回复已生成")
        if "quality_report" in artifact_types:
            return EvaluationResult(True, 0.86, "finish", "已经找到报告信息")
        if "task_status" in artifact_types:
            return EvaluationResult(True, 0.8, "finish", "已经找到任务状态")
        if "rag_hits" in artifact_types:
            return EvaluationResult(True, 0.76, "finish", "已经完成知识检索")
        if "file_summary" in artifact_types or "file_answer" in artifact_types:
            return EvaluationResult(True, 0.78, "finish", "已经完成文件辅助分析")
        if "image_understanding" in artifact_types:
            return EvaluationResult(True, 0.75, "finish", "已经完成图片辅助分析")
        if "inspection_result" in artifact_types or "inspection_task" in artifact_types:
            return EvaluationResult(True, 0.9, "finish", "正式质检任务已处理")
        if "data_analysis" in artifact_types:
            return EvaluationResult(True, 0.7, "finish", "数据分析能力已返回只读统计结果")
        model_result = await self._model_evaluate_if_available(state, plan, observations, artifacts)
        if model_result is not None:
            return model_result
        return EvaluationResult(False, 0.2, "continue", "当前结果不足以回答用户")

    async def _model_evaluate_if_available(
        self,
        state: ManagerState,
        plan: AgentRoutePlan,
        observations: list[AgentObservation],
        artifacts: list[AgentArtifact],
    ) -> EvaluationResult | None:
        runtime = state.manager_model_runtime or {}
        if not runtime.get("model_id"):
            return None
        try:
            from agent.llm.client import LLMClient

            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                provider=runtime.get("provider"),
                trace_id=state.trace_id or state.workflow_run_id or state.request_id,
                org_id=state.org_id,
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
            state.used_llm_calls += 1
            response = await client.chat(
                [
                    {
                        "role": "system",
                        "content": "你是 PIAP Manager 的评价器，只返回 JSON。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "goal": state.goal,
                                "plan": plan.model_dump(),
                                "observations": [item.model_dump() for item in observations],
                                "artifacts": [item.model_dump() for item in artifacts],
                                "required_schema": {
                                    "satisfied": "boolean",
                                    "score": "number 0..1",
                                    "next_action": "finish|continue|ask_user|fail",
                                    "reason": "string",
                                    "missing_inputs": "string[]",
                                    "recommended_next_capabilities": "string[]",
                                },
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                temperature=0.0,
                observation_name="manager.evaluate",
                observation_metadata={
                    "surface": state.surface,
                    "source_type": "chat",
                    "manager_model": runtime.get("model_id"),
                    "org_id": state.org_id,
                    "session_id": state.session_id,
                    "assistant_message_id": state.assistant_message_id,
                    "workflow_run_id": state.workflow_run_id,
                },
            )
            data = self._extract_json(response)
            if not data:
                return None
            next_action = str(data.get("next_action") or "continue")
            if next_action not in {"finish", "continue", "ask_user", "fail"}:
                next_action = "continue"
            return EvaluationResult(
                satisfied=bool(data.get("satisfied")),
                score=float(data.get("score") or 0.0),
                next_action=next_action,
                reason=str(data.get("reason") or "模型评价完成"),
                missing_inputs=list(data.get("missing_inputs") or []),
                recommended_next_capabilities=list(data.get("recommended_next_capabilities") or []),
            )
        except Exception:
            return None

    @staticmethod
    def _extract_json(response: dict) -> dict | None:
        if isinstance(response, dict):
            content = response.get("content")
            if isinstance(content, dict):
                return content
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except Exception:
                    return None
        return None
