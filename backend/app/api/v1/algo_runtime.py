from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ValidationError
from app.schemas.algo_resources import AlgoDeploymentInferRequest, AlgoDeploymentInferResponse
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.algo_execution_service import DeploymentManager
from app.services.algo_workspace_service import AlgoWorkspaceService


router = APIRouter()


def _svc(current: CurrentUser, db):
    return AlgoWorkspaceService(db, current.org_id, current.user_id)


@router.post("/runtime/algo-deployments/{deployment_id}/infer", response_model=ResponseEnvelope, status_code=status.HTTP_200_OK)
async def infer_with_deployment(
    deployment_id: str,
    payload: AlgoDeploymentInferRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    deployment = await svc._require_generic_resource(resource_type="deployment", resource_id=deployment_id)
    if str(getattr(deployment, "status", "") or "") != "completed":
        raise ValidationError("deployment must be completed")

    runtime_registration = dict((getattr(deployment, "result_summary", {}) or {}).get("runtime_registration") or {})
    if not runtime_registration:
        raise ValidationError("deployment is missing runtime_registration")
    runtime_status = str(runtime_registration.get("service_status") or runtime_registration.get("status") or "").strip().lower()
    if runtime_status != "available":
        raise ValidationError("runtime is not available")
    is_healthy, health_error = await DeploymentManager.check_runtime_health(runtime_registration)
    if not is_healthy:
        raise ValidationError(f"service_unreachable: {health_error or 'health check failed'}")
    if not str(runtime_registration.get("infer_url") or "").strip():
        result = {
            "prediction": dict(payload.request or {}),
            "latency_ms": 0,
            "model_version": runtime_registration.get("model_version") or runtime_registration.get("model_key"),
            "request_id": None,
            "runtime_status": runtime_status,
            "error": None,
        }
    else:
        result = await DeploymentManager.invoke_runtime(
            runtime_registration=runtime_registration,
            request_payload=dict(payload.request or {}),
        )

    return ResponseEnvelope(
        data=AlgoDeploymentInferResponse(
            deployment_id=deployment.id,
            deployment_status=str(getattr(deployment, "status", "") or "unknown"),
            runtime_status=str(result.get("runtime_status") or runtime_status),
            prediction=result.get("prediction"),
            latency_ms=result.get("latency_ms"),
            model_version=result.get("model_version"),
            request_id=result.get("request_id"),
            error=result.get("error"),
            runtime_registration=runtime_registration,
            accepted_at=datetime.now(timezone.utc),
        )
    )
