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

    SUCCESS_RULES = {
        "rag.retrieve": lambda a: (
            a.type == "rag_hits"
            and a.status in {"success", "empty"}
            and "hit_count" in a.metrics
        ),
        "image.understanding": lambda a: (
            a.type == "image_understanding"
            and a.status == "success"
            and (a.confidence or 0) >= 0.5
        ),
        "file.paper_format_check": lambda a: (
            a.type == "paper_format_report"
            and a.status == "success"
        ),
        "quality.inspection.execute": lambda a: (
            a.type in {"inspection_result", "inspection_task"}
            and a.status == "success"
            and not a.needs_user_input
        ),
        "file.summary": lambda a: (
            a.type in {"file_summary", "file_answer"}
            and a.status == "success"
        ),
        "file.qa": lambda a: (
            a.type in {"file_summary", "file_answer"}
            and a.status == "success"
        ),
        "quality.report.query": lambda a: (
            a.type == "quality_report"
            and a.status in {"success", "empty"}
            and "report_count" in a.metrics
        ),
        "quality.task.status": lambda a: (
            a.type == "task_status"
            and a.status in {"success", "empty"}
            and "found" in a.metrics
        ),
        "data.analysis": lambda a: (
            a.type == "data_analysis"
            and a.status == "success"
        ),
        "chat.general": lambda a: (
            a.type in {"composed_response", "chat_response"}
            and a.status == "success"
        ),
        "chat.response.compose": lambda a: (
            a.type == "composed_response"
            and a.status == "success"
        ),
    }

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

        # FAILED ARTIFACTS FIRST — Section 9.3 of spec
        all_artifacts = self._dedupe_artifacts([*state.artifacts, *artifacts])
        if any(a.status == "failed" for a in all_artifacts):
            failed_artifacts = [a for a in all_artifacts if a.status == "failed"]
            reasons = [f"{a.type}: {a.summary}" for a in failed_artifacts if a.summary]
            return EvaluationResult(
                satisfied=False,
                score=0.0,
                next_action="fail",
                reason=f"能力执行失败：{'; '.join(reasons)}" if reasons else "Artifact 状态为 failed",
            )

        # BLOCKED artifacts that need user input — ask_user
        if any(a.status == "blocked" for a in all_artifacts) and any(a.needs_user_input for a in all_artifacts):
            blocked = [a for a in all_artifacts if a.status == "blocked"]
            return EvaluationResult(
                satisfied=False,
                score=0.0,
                next_action="ask_user",
                reason="缺少用户输入",
                missing_inputs=[a.summary for a in blocked if a.summary],
            )

        # --- Rule-driven evaluation per plan step (Section 9.2 of spec) ---
        # Check each plan step against its SUCCESS_RULE
        all_steps_satisfied = True
        any_rule_matched = False
        for step in plan.steps:
            cap = step.capability
            rule = self.SUCCESS_RULES.get(cap)
            if rule is None:
                continue
            any_rule_matched = True
            matching = [a for a in all_artifacts if rule(a)]
            if not matching:
                all_steps_satisfied = False
                break

        # chat.general is a special case: no artifact needed if model replied
        if any(s.capability == "chat.general" for s in plan.steps):
            return EvaluationResult(True, 1.0, "finish", "普通聊天已生成回复")

        # composed_response signals completion
        composed_artifacts = [item for item in all_artifacts if item.type == "composed_response"]
        if composed_artifacts and any(
            str((item.content or {}).get("status") or "completed") != "blocked"
            for item in composed_artifacts
        ):
            return EvaluationResult(True, 1.0, "finish", "聊天回复已生成")
        # If all composed_responses are blocked, the action was blocked
        if composed_artifacts:
            return EvaluationResult(False, 0.2, "continue", "回复已被阻止，等待用户处理")

        # If rules were checked and all satisfied
        if any_rule_matched and all_steps_satisfied:
            return EvaluationResult(True, 0.85, "finish", "所有能力步骤已按规则完成")

        # If rules were checked but some not satisfied
        if any_rule_matched and not all_steps_satisfied:
            return EvaluationResult(False, 0.3, "continue", "能力步骤尚未全部满足成功条件")

        # Fallback: model evaluator or continue
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
        except Exception as exc:
            import logging
            _log = logging.getLogger(__name__)
            _log.warning("ManagerEvaluator model evaluation failed: %s", exc)
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

    @staticmethod
    def _dedupe_artifacts(artifacts: list[AgentArtifact]) -> list[AgentArtifact]:
        seen: set[str] = set()
        result: list[AgentArtifact] = []
        for item in artifacts:
            if item.artifact_id in seen:
                continue
            seen.add(item.artifact_id)
            result.append(item)
        return result
