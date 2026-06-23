from __future__ import annotations

from typing import Any

from agent.contracts import AgentOutput
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, AgentRouteDecision
from agent.router.errors import AgentRuntimeError, make_agent_error
from agent.router.executors.chat_executor import ChatExecutor
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


class QualityAnalysisExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"quality.final_analyze", "quality.inspection.execute"}

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ):
        if step.capability not in self.SUPPORTED_CAPABILITIES:
            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                detail={"capability": step.capability, "executor": "quality_analysis"},
                source="quality_analysis.executor",
            )
        if step.capability == "quality.inspection.execute":
            return await self._execute_inspection(step, state, request)
        # Use the LangGraph-based quality analysis when opted in;
        # otherwise keep the battle-tested ChatExecutor path.
        if (request.ext or {}).get("use_quality_analysis_graph"):
            return await self._run_quality_analysis_graph(step, state, request, db_session)
        return await self._final_analyze(step, state, request)

    async def _final_analyze(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
    ):
        chat = ChatExecutor()
        prompt = chat._compose_prompt(state) if state.artifacts else chat._general_prompt(state)
        try:
            answer = await chat._call_model(
                state,
                request,
                prompt,
                use_tools=False,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "CHAT_COMPOSE_MODEL_UNAVAILABLE",
                message="质量分析模型调用失败，无法生成最终回复。",
                detail={"raw_error": str(exc)},
                debug={"raw_error": str(exc)},
                source="quality.final_analyze",
                cause=exc,
            ) from exc
        if answer is None:
            raise make_agent_error(
                "CHAT_COMPOSE_MODEL_UNAVAILABLE",
                detail={"capability": step.capability, "route_reason": state.route_plan.reason if state.route_plan else None},
                source="quality.final_analyze",
            )

        composed = chat._compose_from_model(state, answer)
        composed["message_type"] = "quality_answer"
        composed["status"] = "completed"
        composed["agent"] = "quality_analysis"
        composed["summary"] = str(composed.get("summary") or answer[:200])
        quality_artifact = self._artifact(
            step,
            "quality_final_assessment",
            content={
                "answer": composed.get("answer", answer),
                "summary": composed.get("summary"),
                "input_artifact_types": [item.type for item in state.artifacts],
            },
            citations=list(composed.get("citations") or []),
            summary=composed["summary"],
        )
        composed_artifact = self._artifact(step, "composed_response", content=composed, summary=composed["summary"])
        return self._observation(
            step,
            status="success",
            summary=composed["summary"],
            artifacts=[quality_artifact, composed_artifact],
        ), [quality_artifact, composed_artifact]

    async def _run_quality_analysis_graph(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        db_session,
    ):
        try:
            from agent.subgraphs.quality_analysis import QualityAnalysisGraph

            graph_state = self.base_graph_state(step, state, request)
            graph_state["db_session"] = db_session
            graph_state["org_id"] = request.org_id
            graph_state["user_id"] = request.user_id
            graph_state["session_id"] = getattr(state, "session_id", None)
            graph_state["workflow_run_id"] = getattr(state, "workflow_run_id", "")
            graph_state["query"] = getattr(state, "original_query", "") or request.query
            graph_state["capability"] = step.capability
            graph_state["surface"] = getattr(state, "surface", "chat")

            artifacts_data = []
            for item in list(getattr(state, "artifacts", []) or []):
                if hasattr(item, "model_dump"):
                    artifacts_data.append(item.model_dump())
                else:
                    artifacts_data.append(dict(item))
            graph_state["artifacts"] = artifacts_data

            result = await QualityAnalysisGraph().run(graph_state)

            status = result.get("status", "success")
            summary = result.get("summary") or result.get("answer") or "质量分析完成"
            answer = result.get("answer") or ""
            needs_user_input = result.get("needs_user_input", False)

            quality_artifact = self._artifact(
                step,
                "quality_final_assessment",
                status="blocked" if needs_user_input else status,
                content={
                    "answer": answer,
                    "summary": summary,
                    "final_verdict": result.get("final_assessment", {}).get("final_verdict"),
                    "overall_score": result.get("final_assessment", {}).get("overall_score"),
                    "risk_level": result.get("final_assessment", {}).get("risk_level"),
                    "evidence_used": result.get("final_assessment", {}).get("evidence_used") or [],
                    "conflicts": result.get("final_assessment", {}).get("conflicts") or [],
                    "limitations": result.get("final_assessment", {}).get("limitations") or [],
                    "recommended_action": result.get("final_assessment", {}).get("recommended_action") or [],
                },
                citations=list(result.get("citations") or []),
                summary=summary,
                needs_user_input=needs_user_input,
                confidence=float(result.get("confidence") or 0.0),
            )

            composed = {
                "answer": answer,
                "summary": summary,
                "message_type": result.get("message_type", "quality_answer"),
                "status": "completed" if not needs_user_input else "blocked",
                "agent": "quality_analysis",
                "citations": result.get("citations") or [],
            }
            composed_artifact = self._artifact(
                step,
                "composed_response",
                status="blocked" if needs_user_input else status,
                content=composed,
                summary=summary,
                needs_user_input=needs_user_input,
            )

            return self._observation(
                step,
                status="blocked" if needs_user_input else status,
                summary=summary,
                artifacts=[quality_artifact, composed_artifact],
            ), [quality_artifact, composed_artifact]

        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "CHAT_COMPOSE_MODEL_UNAVAILABLE",
                message="质量分析图执行失败。",
                debug={"raw_error": str(exc)},
                source="quality.final_analyze",
                cause=exc,
            ) from exc

    async def _execute_inspection(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
    ):
        try:
            from agent.subgraphs.inspection_task import InspectionTaskGraph

            output = await InspectionTaskGraph().run(
                request,
                AgentRouteDecision(
                    selected_agent="quality_analysis",
                    sub_route="inspection_execute",
                    intent="inspection_execute",
                    reason="inspection_execute",
                    route_source="manager",
                ),
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "INSPECTION_TASK_FAILED",
                message="正式质检任务执行失败。",
                debug={"raw_error": str(exc)},
                source="quality.inspection.execute",
                cause=exc,
            ) from exc

        if not isinstance(output, AgentOutput):
            output = AgentOutput.model_validate(output)
        action_state = str(output.action_state or "").strip()
        structured_result = bool(output.persistable_output and output.persistable_output.result)
        if action_state == "failed" and not structured_result:
            raise make_agent_error(
                "INSPECTION_TASK_FAILED",
                message=output.summary or output.answer or "正式质检任务执行失败。",
                source="quality.inspection.execute",
            )
        content = output.model_dump()
        status = "blocked" if action_state.startswith("awaiting_") else "success"
        art = self._artifact(
            step,
            "inspection_result",
            status=status,
            needs_user_input=status == "blocked",
            content=content,
            summary=output.summary or output.answer,
            citations=list(output.citations or []),
        )
        return self._observation(
            step,
            status=status,
            summary=art.summary,
            artifacts=[art],
        ), [art]
