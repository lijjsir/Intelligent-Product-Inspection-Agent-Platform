from __future__ import annotations

from datetime import datetime
import traceback

from agent.graph.inspection_graph import InspectionGraph
from agent.graph.state import InspectionState
from agent.llm.client import LLMClient
from agent.stability.alert_trigger import should_trigger
from agent.stability.analyzer import analyze
from app.core.ids import uuid7
from app.models.task import InspectionTask
from app.repositories.alert_repo import AlertRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.services.stream_service import stream_broker
from infra.database.session import get_session


async def run_inspection_pipeline(task_id: str, org_id: str) -> dict:
    async with get_session() as session:
        task_repo = TaskRepository(session)
        result_repo = ResultRepository(session)
        stability_repo = StabilityRepository(session)
        alert_repo = AlertRepository(session)

        task = await task_repo.get(org_id, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        await task_repo.update_status(org_id, task_id, "running")
        await session.commit()
        await stream_broker.publish(task_id, {"type": "status", "status": "running", "ts": datetime.utcnow().isoformat()})

        async def emit(event: dict) -> None:
            event.setdefault("ts", datetime.utcnow().isoformat())
            await stream_broker.publish(task_id, event)

        try:
            state: InspectionState = {
                "task_id": task.id,
                "org_id": task.org_id,
                "product_id": task.product_id,
                "spec_id": task.spec_id,
                "image_urls": task.image_urls or [],
                "model_id": LLMClient().model_id,
                "timeline": [],
            }
            graph = InspectionGraph()
            state = await graph.run(state, on_event=emit)

            conclusion = state.get("conclusion") or {}
            result_payload = {
                "id": str(uuid7()),
                "task_id": task.id,
                "org_id": task.org_id,
                "verdict": conclusion.get("verdict") or "uncertain",
                "overall_score": float(conclusion.get("overall_score") or 0.5),
                "defects": state.get("defects") or [],
                "citations": {"items": state.get("citations") or []},
                "reasoning_chain": state.get("reasoning_chain") or {},
                "llm_model": state.get("model_id") or "volcengine",
                "prompt_version": "phase3-v1",
                "tokens_used": None,
                "latency_ms": None,
            }
            result = await result_repo.upsert_by_task(result_payload)

            stability = await analyze(
                {
                    "defects": state.get("defects") or [],
                    "citations": state.get("citations") or [],
                    "conclusion": conclusion,
                }
            )
            stability_payload = {
                "id": str(uuid7()),
                "result_id": result.id,
                "task_id": task.id,
                "org_id": task.org_id,
                "evidence_score": stability["evidence_score"],
                "consistency_score": stability["consistency_score"],
                "confidence_score": stability["confidence_score"],
                "traceability_score": stability["traceability_score"],
                "anomaly_score": stability["anomaly_score"],
                "risk_score": stability["risk_score"],
                "risk_level": stability["risk_level"],
                "dimension_detail": stability.get("dimension_detail"),
                "sampling_results": {"timeline": state.get("timeline") or []},
                "root_cause": None,
                "created_at": datetime.utcnow(),
            }
            stability_obj = await stability_repo.upsert_by_task(stability_payload)

            if should_trigger(stability):
                severity = "critical" if stability.get("risk_level") == "critical" else "warning"
                await alert_repo.create(
                    {
                        "id": str(uuid7()),
                        "org_id": task.org_id,
                        "stability_id": stability_obj.id,
                        "alert_type": "stability_risk",
                        "severity": severity,
                        "title": f"任务 {task.id} 稳定性风险 {stability.get('risk_level')}",
                        "detail": {
                            "risk_level": stability.get("risk_level"),
                            "risk_score": stability.get("risk_score_100"),
                        },
                        "status": "open",
                        "channels": {"in_app": True},
                        "created_at": datetime.utcnow(),
                    }
                )
                await emit({"type": "alert", "message": "已触发稳定性风险告警"})

            await task_repo.update_status(org_id, task_id, "done")
            await session.commit()

            await emit({"type": "status", "status": "done"})
            await emit({"type": "result", "verdict": result.verdict, "overall_score": float(result.overall_score)})
            await emit(
                {
                    "type": "stability",
                    "risk_level": stability_obj.risk_level,
                    "risk_score": float(stability_obj.risk_score),
                }
            )
            return {"task_id": task_id, "status": "done"}
        except Exception as exc:
            await task_repo.update_status(org_id, task_id, "failed")
            await session.commit()
            await emit(
                {
                    "type": "error",
                    "status": "failed",
                    "message": str(exc),
                    "trace": traceback.format_exc(limit=2),
                }
            )
            raise
