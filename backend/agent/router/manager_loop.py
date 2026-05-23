from __future__ import annotations

import hashlib
import json
import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.capability_registry import CAPABILITIES, capability_allowed
from agent.router.contracts import AgentRouteDecision, AgentRoutePlan, AgentRouterOutput
from agent.router.manager_dispatcher import ManagerDispatcher
from agent.router.manager_evaluator import EvaluationResult, ManagerEvaluator
from agent.router.manager_policy import ManagerPolicy
from agent.router.manager_state import ManagerState
from agent.llm.gateway import LLMGateway
from app.services.model_config_service import ModelConfigService


@dataclass
class ValidationResult:
    allowed: bool
    message: str = ""
    need_user_input: bool = False
    missing_inputs: list[str] | None = None

    def to_error(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "need_user_input": self.need_user_input,
            "missing_inputs": list(self.missing_inputs or []),
        }


class ManagerLoop:
    def __init__(self) -> None:
        self._policy = ManagerPolicy()
        self._dispatcher = ManagerDispatcher()
        self._evaluator = ManagerEvaluator()
        self._gateway = LLMGateway()

    async def run(self, request: NormalizedRequest, db_session=None) -> AgentRouterOutput:
        state = self._policy.initialize_state(request)
        state.manager_model = await self._resolve_manager_model(state, db_session=db_session)
        blocked_by_missing_inputs = False
        started_at = perf_counter()

        while self._can_continue(state):
            remaining_timeout = (state.timeout_ms / 1000) - (perf_counter() - started_at)
            if remaining_timeout <= 0:
                state.errors.append({"message": "Manager Agent 执行超时", "need_user_input": False, "missing_inputs": []})
                state.final_action = "fail"
                break
            understanding = await self._policy.understand(state)
            plan = await self._policy.plan(state, understanding)
            state.route_plan = plan
            state.route_plan_hashes.append(self._plan_hash(plan))

            validation = self._validate_plan(state, plan)
            if not validation.allowed:
                state.errors.append(validation.to_error())
                state.final_action = "ask_user" if validation.need_user_input else "fail"
                state.missing_inputs = list(validation.missing_inputs or [])
                blocked_by_missing_inputs = validation.need_user_input
                break

            state.iteration += 1
            try:
                observations, artifacts = await asyncio.wait_for(
                    self._dispatcher.dispatch(
                        plan,
                        state,
                        request,
                        db_session=db_session,
                    ),
                    timeout=max(0.1, remaining_timeout),
                )
            except asyncio.TimeoutError:
                state.errors.append({"message": "Manager Agent dispatch 超时", "need_user_input": False, "missing_inputs": []})
                state.final_action = "fail"
                break
            state.last_artifact_counts.append(len(state.artifacts))

            evaluation = await self._evaluator.evaluate(state, plan, observations, artifacts)
            state.satisfied = evaluation.satisfied
            state.satisfaction_score = evaluation.score
            state.final_action = evaluation.next_action

            if evaluation.satisfied or evaluation.next_action in {"ask_user", "fail"}:
                break
            if self._no_progress(state, evaluation):
                break
            state = self._refine_for_next_round(state, evaluation)

        return self._compose_final(state, blocked_by_missing_inputs=blocked_by_missing_inputs)

    def _validate_plan(self, state: ManagerState, plan: AgentRoutePlan) -> ValidationResult:
        if state.missing_inputs:
            return ValidationResult(
                allowed=False,
                message=f"缺少必要输入：{', '.join(state.missing_inputs)}",
                need_user_input=True,
                missing_inputs=list(state.missing_inputs),
            )
        if len(plan.steps) > max(0, state.max_tool_calls - state.used_tool_calls):
            return ValidationResult(False, "route_plan 超出工具调用预算")
        for step in plan.steps:
            capability = CAPABILITIES.get(step.capability_key)
            if capability is None:
                return ValidationResult(False, f"未知 capability：{step.capability_key}")
            if step.mode in state.forbidden_modes:
                return ValidationResult(False, f"当前页面已禁止模式：{step.mode}")
            if state.surface == "chat" and step.mode == "action":
                return ValidationResult(False, "聊天页面不允许执行正式业务动作")
            if not capability_allowed(capability, state.surface, state.allowed_modes):
                return ValidationResult(False, f"当前页面不允许调用 capability：{step.capability_key}")
            if capability.key == "quality.inspection.execute" and state.action_intent != "quality_inspection_execute":
                return ValidationResult(
                    allowed=False,
                    message="正式质量检测缺少 action_intent=quality_inspection_execute",
                    need_user_input=True,
                    missing_inputs=["action_intent"],
                )
        return ValidationResult(True)

    @staticmethod
    def _can_continue(state: ManagerState) -> bool:
        if state.satisfied:
            return False
        if state.iteration >= state.max_iterations:
            return False
        if state.used_tool_calls >= state.max_tool_calls:
            return False
        if state.used_llm_calls >= state.max_llm_calls:
            return False
        if state.final_action in {"finish", "ask_user", "fail"}:
            return False
        return True

    @staticmethod
    def _no_progress(state: ManagerState, evaluation: EvaluationResult) -> bool:
        if evaluation.next_action == "continue" and len(state.last_artifact_counts) >= 2:
            return state.last_artifact_counts[-1] == state.last_artifact_counts[-2]
        if len(state.route_plan_hashes) >= 2:
            return state.route_plan_hashes[-1] == state.route_plan_hashes[-2]
        return False

    @staticmethod
    def _refine_for_next_round(state: ManagerState, evaluation: EvaluationResult) -> ManagerState:
        state.constraints.append(evaluation.reason)
        return state

    async def _resolve_manager_model(self, state: ManagerState, *, db_session=None) -> dict[str, Any] | None:
        if db_session is None:
            return None
        try:
            models = await ModelConfigService(db_session, state.org_id).list_runtime_models()
            runtime = await self._gateway.select_runtime(
                models=models,
                model_types={"chat"},
                reserve=False,
            )
        except Exception:
            return None
        if not runtime:
            return None
        state.manager_model_runtime = runtime
        return {
            "logical_name": "manager_model",
            "model_type": "chat",
            "model_config_id": runtime.get("model_config_id"),
            "model_id": runtime.get("model_id"),
            "provider": runtime.get("provider"),
            "runtime_key": runtime.get("runtime_key"),
            "failover_depth": runtime.get("failover_depth"),
        }

    def _compose_final(self, state: ManagerState, *, blocked_by_missing_inputs: bool) -> AgentRouterOutput:
        composed = self._find_composed(state)
        plan = state.route_plan
        sub_route = self._sub_route(state)
        selected_agent = self._selected_agent(state)
        status = composed.get("status", "completed") if composed else self._status(state, blocked_by_missing_inputs=blocked_by_missing_inputs)
        composed_status = "blocked" if status == "blocked" else "completed"
        answer = composed.get("answer", "") if composed else self._answer(state, status=composed_status)
        message_type = composed.get("message_type", "assistant_text") if composed else self._message_type(state, sub_route, composed_status)
        summary = composed.get("summary", "") if composed else self._summary(state, composed_status)
        raw_payload = self._payload(state, answer=answer, message_type=message_type)
        persistable_output = self._persistable_output(state, answer=answer, sub_route=sub_route)
        agent_output = {
            "message_type": message_type,
            "answer": answer,
            "summary": summary,
            "citations": self._citations(state),
            "quality": {},
            "rag_summary": self._rag_summary(state),
            "action_state": "blocked" if status == "blocked" else state.final_action,
            "task_draft": None,
            "created_task": None,
            "persistable_output": persistable_output,
            "raw_state": {"response_payload": raw_payload, "manager_state": self._state_dump(state)},
            **raw_payload,
        }
        decision = AgentRouteDecision(
            selected_agent=selected_agent,
            sub_route=sub_route,
            intent=sub_route,
            confidence=plan.confidence if plan else 0.0,
            reason=plan.reason if plan else "",
            requires_confirmation=blocked_by_missing_inputs,
            route_source="manager",
            fallback_agent=None,
        )
        return AgentRouterOutput(
            route_decision=decision,
            agent_output=agent_output,
            status=status,
            degrade_reason=state.errors[-1]["message"] if state.errors else None,
        )

    @staticmethod
    def _find_composed(state: ManagerState) -> dict[str, Any] | None:
        for art in reversed(state.artifacts):
            if art.type == "composed_response":
                return dict(art.content or {})
        return None

    def _payload(self, state: ManagerState, *, answer: str, message_type: str) -> dict[str, Any]:
        artifacts = [item.model_dump() for item in state.artifacts]
        steps = [step.model_dump() for step in (state.route_plan.steps if state.route_plan else [])]
        capabilities_used = [
            item.capability_key
            for item in state.observations
            if item.status in {"success", "skipped"} and item.capability_key != "chat.response.compose"
        ]
        if state.route_plan and any(step.capability_key == "chat.response.compose" for step in state.route_plan.steps):
            capabilities_used.append("chat.response.compose")
        route_trace = {
            "iterations": state.iteration,
            "capabilities_used": capabilities_used,
            "satisfied": state.satisfied,
            "score": state.satisfaction_score,
            "surface": state.surface,
            "manager_model": state.manager_model,
            "steps": steps,
            "observations": [item.model_dump() for item in state.observations],
            "errors": list(state.errors),
        }
        return {
            "answer": answer,
            "summary": self._summary(state, self._status(state, blocked_by_missing_inputs=bool(state.missing_inputs))),
            "message_type": message_type,
            "artifacts": artifacts,
            "citations": self._citations(state),
            "route_trace": route_trace,
            "ui_schema": "chat_answer_v2",
            "capabilities_used": capabilities_used,
            "satisfied": state.satisfied,
            "selected_rag_space": state.selected_rag_space,
            "rag_summary": self._rag_summary(state),
            "created_task": None,
        }

    @staticmethod
    def _selected_agent(state: ManagerState) -> str:
        if state.route_plan and state.route_plan.steps:
            action_steps = [step for step in state.route_plan.steps if step.agent == "inspection_task"]
            if action_steps:
                return "inspection_task"
        return "chat"

    @staticmethod
    def _sub_route(state: ManagerState) -> str:
        if state.errors and state.surface == "chat":
            return "action_blocked"
        if state.route_plan:
            reason = state.route_plan.reason
            mapping = {
                "general_chat": "general_chat",
                "rag_qa": "rag_qa",
                "rag_ingest": "rag_ingest",
                "image_understanding": "image_understanding",
                "file_summary": "file_summary",
                "file_qa": "file_qa",
                "quality_report_query": "quality_report_query",
                "quality_task_status": "quality_task_status",
                "inspection_execute": "inspection_execute",
                "action_blocked": "action_blocked",
                "data_analysis": "data_analysis",
            }
            return mapping.get(reason, reason or "general_chat")
        return "general_chat"

    @staticmethod
    def _status(state: ManagerState, *, blocked_by_missing_inputs: bool) -> str:
        if state.errors or blocked_by_missing_inputs:
            return "blocked"
        if state.route_plan and state.route_plan.reason == "action_blocked":
            return "blocked"
        if state.final_action == "fail":
            return "failed"
        return "completed"

    @staticmethod
    def _message_type(state: ManagerState, sub_route: str, status: str) -> str:
        if status == "blocked":
            return "action_blocked"
        if sub_route == "image_understanding":
            return "image_analysis"
        if sub_route in {"file_summary", "file_qa"}:
            return "file_answer"
        if sub_route == "quality_task_status":
            return "task_status"
        if sub_route == "quality_report_query":
            return "report_answer"
        if sub_route == "inspection_execute":
            return "task_result"
        return "assistant_text"

    @staticmethod
    def _summary(state: ManagerState, status: str) -> str:
        if status == "blocked":
            return "请求被页面边界阻止"
        if state.observations:
            return state.observations[-1].summary
        return state.goal or "Manager Agent 已完成处理"

    @staticmethod
    def _answer(state: ManagerState, *, status: str) -> str:
        if status == "blocked":
            error_message = state.errors[-1]["message"] if state.errors else ""
            if "action_intent" in error_message:
                return "正式质量检测需要由质量检测任务页面显式提交，并携带 action_intent=quality_inspection_execute。"
            return "这个操作需要在质量检测任务页面中执行。请前往质量检测任务页面创建或执行正式检测任务。"
        if state.route_plan and state.route_plan.reason == "action_blocked":
            return "聊天页面不能创建或执行正式质量检测任务。请前往质量检测任务页面提交正式检测。"
        if state.route_plan and state.route_plan.reason == "image_understanding":
            return "这是基于聊天图片理解的初步判断，不等同于正式质检结果。如需正式检测，请到质量检测任务页面创建任务。"
        if state.route_plan and state.route_plan.reason in {"file_summary", "file_qa"}:
            artifact = ManagerLoop._latest_artifact(state, {"file_summary", "file_answer"})
            if artifact:
                summary = str((artifact.content or {}).get("summary") or "").strip()
                if summary:
                    return f"{summary}\n\n该结果仅作为聊天页辅助分析，不会写入正式质检任务或结果表。"
            return "文件已作为聊天上下文完成辅助分析。该结果不会写入正式质检任务或结果表。"
        if state.route_plan and state.route_plan.reason == "rag_qa":
            rag = ManagerLoop._latest_artifact(state, {"rag_hits"})
            if rag:
                content = dict(rag.content or {})
                return f"已完成知识库检索，命中 {int(content.get('hit_count') or 0)} 条证据，并整理为聊天回答。"
            return "已根据当前可用知识源完成检索，并整理为聊天回答。"
        if state.route_plan and state.route_plan.reason == "rag_ingest":
            return "RAG 入库需要在知识库或管理入口中显式确认后执行，聊天页不会直接写入知识库。"
        if state.route_plan and state.route_plan.reason in {"quality_report_query", "quality_task_status"}:
            artifact = ManagerLoop._latest_artifact(state, {"quality_report", "task_status"})
            if artifact:
                summary = str((artifact.content or {}).get("summary") or "").strip()
                if summary:
                    return f"{summary}\n\n这是只读查询结果，聊天页不会写入正式检测结果。"
            return "已执行只读查询。聊天页只展示已有信息，不写入正式检测结果。"
        if state.route_plan and state.route_plan.reason == "inspection_execute":
            for observation in reversed(state.observations):
                if observation.summary:
                    return observation.summary
            return "正式质量检测任务已提交处理。"
        if state.route_plan and state.route_plan.reason == "data_analysis":
            return "已完成当前可用的只读数据分析。"
        for observation in reversed(state.observations):
            if observation.capability_key == "chat.general" and observation.summary:
                return observation.summary
        return "我已收到你的请求。"

    @staticmethod
    def _latest_artifact(state: ManagerState, artifact_types: set[str]):
        for artifact in reversed(state.artifacts):
            if artifact.type in artifact_types:
                return artifact
        return None

    @staticmethod
    def _citations(state: ManagerState) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for artifact in state.artifacts:
            citations.extend(artifact.citations)
        return citations

    @staticmethod
    def _rag_summary(state: ManagerState) -> dict[str, Any] | None:
        for artifact in reversed(state.artifacts):
            if artifact.type == "rag_hits":
                content = dict(artifact.content or {})
                hits = [dict(item) for item in list(content.get("hits") or []) if isinstance(item, dict)]
                top_sources = ManagerLoop._top_sources(hits, artifact.citations)
                hit_count = int(content.get("hit_count") or len(hits))
                citation_coverage = min(1.0, len(artifact.citations) / hit_count) if hit_count else 0.0
                return {
                    "rag_space_id": content.get("rag_space_id"),
                    "rag_space_name": content.get("rag_space_name"),
                    "hit_count": hit_count,
                    "citation_coverage": citation_coverage,
                    "top_sources": top_sources,
                    "source_graph": "manager",
                }
        return None

    @staticmethod
    def _persistable_output(state: ManagerState, *, answer: str, sub_route: str) -> dict[str, Any]:
        rag_queries: list[dict[str, Any]] = []
        for artifact in state.artifacts:
            if artifact.type != "rag_hits":
                continue
            content = dict(artifact.content or {})
            hits = [dict(item) for item in list(content.get("hits") or []) if isinstance(item, dict)]
            hit_count = int(content.get("hit_count") or len(hits))
            top_k = max(int(content.get("top_k") or 5), 1)
            citations = [dict(item) for item in list(artifact.citations or []) if isinstance(item, dict)]
            top_sources = ManagerLoop._top_sources(hits, citations)
            coverage = min(1.0, len(citations) / hit_count) if hit_count else 0.0
            trace_id = str(state.workflow_run_id or state.request_id or "")
            rag_queries.append(
                {
                    "query": state.original_query,
                    "rag_space_id": content.get("rag_space_id"),
                    "top_k": top_k,
                    "hit_count": hit_count,
                    "hit_rate": round(min(1.0, hit_count / top_k), 4) if hit_count else 0.0,
                    "citation_coverage": round(coverage, 4),
                    "latency_ms": int(content.get("latency_ms") or 0),
                    "source_graph": "manager",
                    "agent_name": "chat",
                    "sub_route": sub_route,
                    "trace_id": trace_id,
                    "top_score": float(content.get("top_score") or 0.0),
                    "metadata": {
                        "intent": state.route_plan.reason if state.route_plan else sub_route,
                        "empty_recall": hit_count == 0,
                        "top_score": float(content.get("top_score") or 0.0),
                        "top_sources": top_sources[:5],
                        "evidence_found": hit_count > 0,
                        "evidence_used": bool(citations),
                        "verdict_impacted": False,
                        "retrieval_config": {
                            "rag_space_id": content.get("rag_space_id"),
                            "rag_space_name": content.get("rag_space_name"),
                            "top_k": top_k,
                            "scope_node_ids": list((state.rag_scope or {}).get("scope_node_ids") or []),
                        },
                        "retrieved_chunks": hits,
                        "used_citations": citations,
                        "answer": answer or None,
                    },
                }
            )
        return {"rag_queries": rag_queries}

    @staticmethod
    def _top_sources(hits: list[dict[str, Any]], citations: list[dict[str, Any]]) -> list[str]:
        sources: list[str] = []
        for item in [*hits, *citations]:
            source = str(item.get("source") or item.get("full_path") or item.get("title") or "").strip()
            if source and source not in sources:
                sources.append(source)
        return sources

    @staticmethod
    def _plan_hash(plan: AgentRoutePlan) -> str:
        return hashlib.sha256(plan.model_dump_json().encode("utf-8")).hexdigest()

    @staticmethod
    def _state_dump(state: ManagerState) -> dict[str, Any]:
        return json.loads(state.model_dump_json())
