from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import (
    AgentArtifact,
    AgentObservation,
    AgentPlanStep,
    BusinessAgentEnvelope,
)
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


CAPABILITY_AGENTS = {
    "risk_case.assess": "public_opinion_monitoring",
    "risk_situation.analyze": "market_monitoring",
    "sampling_plan.optimize": "supervision_sampling",
    "inspection_process.assess": "laboratory_testing",
}

ARTIFACT_TYPES = {
    "risk_case.assess": "risk_case_assessment",
    "risk_situation.analyze": "risk_situation_report",
    "sampling_plan.optimize": "sampling_plan",
    "inspection_process.assess": "inspection_process_assessment",
}


def _business_status(value: Any) -> str:
    status = str(value or "completed")
    if status == "infeasible":
        return "insufficient_evidence"
    if status == "paused":
        return "cancelled"
    allowed = {
        "queued",
        "running",
        "completed",
        "insufficient_evidence",
        "awaiting_review",
        "awaiting_approval",
        "awaiting_retest",
        "manual_review_required",
        "stale",
        "cancelled",
        "failed",
    }
    return status if status in allowed else "completed"


def _next_actions(capability: str, status: str, result: dict[str, Any]) -> list[str]:
    if status == "insufficient_evidence" or result.get("missing_inputs"):
        return ["evidence.collect"]
    if capability == "risk_case.assess":
        return ["risk.review"]
    if capability == "risk_situation.analyze":
        return ["sampling.plan.create"]
    if capability == "sampling_plan.optimize":
        return ["sampling.approve"]
    if capability == "inspection_process.assess":
        return ["result.review"]
    return []


class SupervisionExecutor:
    """Adapter that makes supervision agents run through ManagerDispatcher."""

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        del db_session
        from agent.subgraphs.supervision.agents import AGENTS

        agent_name = CAPABILITY_AGENTS[step.capability]
        snapshot = dict((request.ext or {}).get("supervision_snapshot") or {})
        if not snapshot:
            raise ValueError("质监运行缺少冻结业务快照")

        model_call = (request.ext or {}).get("supervision_model_call")
        started_at = datetime.now(timezone.utc)
        result = await AGENTS[agent_name].run(snapshot, model_call)
        finished_at = datetime.now(timezone.utc)
        business_status = _business_status(result.get("status"))
        business_object = {
            "kind": str(snapshot.get("kind") or "unknown"),
            "id": str(snapshot.get("id") or state.task_id or state.workflow_run_id),
            "version": int(snapshot.get("version") or 1),
        }
        consumed_versions = {
            f"{item.get('kind', 'record')}:{item['id']}": int(item.get("version") or 1)
            for key in ("cases", "related_sources", "devices")
            for item in list(snapshot.get(key) or [])
            if isinstance(item, dict) and item.get("id")
        }
        envelope = BusinessAgentEnvelope(
            workflow_run_id=state.workflow_run_id,
            source_agent=agent_name,
            business_object=business_object,
            status=business_status,
            evidence_ids=[str(item) for item in result.get("evidence_ids") or []],
            consumed_versions=consumed_versions,
            knowledge_snapshot_id=snapshot.get("knowledge_snapshot_id"),
            result=result,
            missing_inputs=[str(item) for item in result.get("missing_inputs") or []],
            conflicts=[str(item) for item in result.get("conflicts") or []],
            next_actions=_next_actions(step.capability, business_status, result),
            model_versions=dict(snapshot.get("model_versions") or {}),
            rule_versions={"business_contract": "v2", "evidence_gates": "v1"},
            trace={
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "capability": step.capability,
            },
        )
        item = artifact(
            step,
            ARTIFACT_TYPES[step.capability],
            content=envelope.model_dump(mode="json"),
            status="failed" if business_status == "failed" else "success",
            summary=str(result.get("summary") or "质监业务步骤已完成"),
            metrics={"business_status": business_status},
            error=result.get("error") if business_status == "failed" else None,
        )
        obs_status = "failed" if business_status == "failed" else "success"
        return (
            observation(
                step,
                status=obs_status,
                summary=item.summary,
                artifact_ids=[item.artifact_id],
                metrics={"business_status": business_status},
                error=item.error,
            ),
            [item],
        )


class SupervisionTrustReviewExecutor:
    """Expose the risk agent's evidence gate as a separate Manager step."""

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        del request, db_session
        source = next(
            (item for item in reversed(state.artifacts) if item.type == "risk_case_assessment"),
            None,
        )
        if source is None:
            raise ValueError("可信复核缺少风险案件评估")
        envelope = dict(source.content or {})
        result = dict(envelope.get("result") or {})
        review = dict(result.get("trust_review") or {})
        if not review:
            review = {
                "decision": "request_evidence",
                "issues": ["风险评估未提供独立证据门禁结果"],
                "probability": None,
            }
        item = artifact(
            step,
            "supervision_trust_review",
            content={
                "business_object": envelope.get("business_object"),
                "source_artifact_id": source.artifact_id,
                **review,
            },
            status="success",
            summary="可信复核已完成",
            metrics={"decision": review.get("decision")},
        )
        return (
            observation(
                step,
                status="success",
                summary=item.summary,
                artifact_ids=[item.artifact_id],
                metrics=item.metrics,
            ),
            [item],
        )
