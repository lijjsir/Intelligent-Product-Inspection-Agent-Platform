from __future__ import annotations

from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.errors import make_agent_error
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState
from agent.subgraphs.lab_detection.graph import LabDetectionGraph


class LabDetectionExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"lab.early_risk.assess"}

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
                detail={"capability": step.capability, "executor": "lab_detection"},
                source="lab_detection.executor",
            )

        input_context = self._input_context(request)
        if not input_context:
            raise make_agent_error(
                "LAB_DETECTION_FAILED",
                message="已路由到实验室检测 Agent，但请求中没有 lab_context、equipment_data 或 environment。",
                source="lab.early_risk.assess",
            )

        result = await LabDetectionGraph().run(
            {
                "request_id": state.request_id,
                "workflow_run_id": state.workflow_run_id,
                "session_id": state.session_id,
                "org_id": state.org_id,
                "user_id": state.user_id,
                "input_context": input_context,
            }
        )
        validation_errors = list(result.get("validation_errors") or [])
        if validation_errors:
            raise make_agent_error(
                "LAB_DETECTION_FAILED",
                message="实验室检测输入校验失败。",
                detail={"validation_errors": validation_errors},
                source="lab.early_risk.assess",
            )
        assessment = dict(result.get("assessment") or {})
        if not assessment:
            raise make_agent_error(
                "LAB_DETECTION_FAILED",
                message="实验室检测图未生成 assessment。",
                detail={"graph_state": result},
                source="lab.early_risk.assess",
            )

        content = {
            "sample_id": input_context.get("sample_id"),
            "assessment_state": assessment.get("assessment_state") or assessment.get("state"),
            "abnormal_probability": assessment.get("abnormal_probability"),
            "risk_level": assessment.get("risk_level"),
            "data_completeness": assessment.get("data_completeness"),
            "early_warning": bool(assessment.get("early_warning") or False),
            "can_make_final_verdict": bool(assessment.get("can_make_final_verdict") or False),
            "abnormal_indicators": list(result.get("anomaly_features") or []),
            "next_test_priority": list(result.get("next_test_priority") or []),
            "suggested_action": assessment.get("suggested_action") or assessment.get("recommended_action"),
            "confidence": assessment.get("confidence"),
            "raw": {
                "assessment": assessment,
                "deterministic_summary": dict(result.get("deterministic_summary") or {}),
                "metadata": dict(result.get("metadata") or {}),
            },
        }
        metrics = {
            "abnormal_probability": assessment.get("abnormal_probability"),
            "confidence": assessment.get("confidence"),
            "data_completeness": assessment.get("data_completeness"),
        }
        art = self._artifact(
            step,
            "lab_detection_result",
            content=content,
            confidence=assessment.get("confidence"),
            metrics={k: v for k, v in metrics.items() if v is not None},
            summary=str(assessment.get("explanation") or "实验室早期风险研判完成"),
        )
        return self._observation(step, status="success", summary=art.summary, artifacts=[art], metrics=art.metrics), [art]

    @staticmethod
    def _input_context(request: NormalizedRequest) -> dict[str, Any]:
        metadata = dict(request.metadata or {})
        ext = dict(request.ext or {})
        lab_context = ext.get("lab_context") or metadata.get("lab_context") or {}
        equipment_data = ext.get("equipment_data") or metadata.get("equipment_data")
        environment = ext.get("environment") or metadata.get("environment")
        if not any([lab_context, equipment_data, environment]):
            return {}
        context = dict(lab_context) if isinstance(lab_context, dict) else {"raw_lab_context": lab_context}
        if equipment_data is not None:
            context.setdefault("metadata", {})
            context["metadata"]["equipment_data"] = equipment_data
        if environment is not None:
            context["environment"] = environment if isinstance(environment, dict) else {"raw": environment}
        context.setdefault("sample_id", str(metadata.get("sample_id") or request.request_id))
        context.setdefault("product_id", request.product_id or metadata.get("product_id"))
        context.setdefault("spec_code", request.spec_code or metadata.get("spec_code"))
        return context
