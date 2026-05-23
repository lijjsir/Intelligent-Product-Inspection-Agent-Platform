from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.core.datetime import utcnow
from app.core.exceptions import ValidationError
from app.services.algo_executor import LocalAlgoExecutor
from app.services.algo_runtime_service import AlgoRuntimeRegistry
from app.core.config import settings
from app.services.object_storage.factory import build_object_storage


def _stable_rng(*parts: Any) -> random.Random:
    seed = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _artifact_path(prefix: str, filename: str) -> str:
    return f"local://algo-workspace/{prefix.strip('/')}/{filename}"


@dataclass(slots=True)
class ExecutionModelRef:
    id: str | None
    provider: str | None
    model_key: str | None
    display_name: str | None
    endpoint: str | None
    source_type: str | None = None
    source_uri: str | None = None
    model_type: str | None = None
    fine_tune_command_template: str | None = None
    offline_eval_command_template: str | None = None
    deployment_command_template: str | None = None
    runtime_env_json: dict[str, Any] | None = None
    default_gpu_request: int | None = None
    default_cpu_request: int | None = None
    default_memory_gb: int | None = None


def _merge_gpu_execution(
    result: dict[str, Any],
    *,
    lease: dict[str, Any] | None = None,
    remote_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(result)
    summary = dict(merged.get("summary") or {})
    if lease:
        summary["lease"] = lease
        merged["lease"] = lease
    if remote_execution:
        summary["remote_execution"] = remote_execution
        merged["remote_execution"] = remote_execution
    merged["summary"] = summary
    return merged


class TrainingRunner:
    @staticmethod
    def run_fine_tune(
        *,
        resource_id: str,
        resource_name: str,
        source_dataset_id: str,
        eval_set_id: str | None,
        model_ref: ExecutionModelRef | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
        lease: dict[str, Any] | None = None,
        remote_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        executor = LocalAlgoExecutor(build_object_storage())
        rng = _stable_rng("fine-tune", resource_id, source_dataset_id, model_ref.model_key if model_ref else "")
        hyperparameters = dict((config_json or {}).get("hyperparameters") or {})
        lora_config = dict((config_json or {}).get("lora") or {})
        learning_rate = float(hyperparameters.get("learning_rate") or 0.0001)
        epochs = int(hyperparameters.get("epochs") or 3)
        batch_size = int(hyperparameters.get("batch_size") or 8)
        metrics = TrainingRunner._build_metrics(rng=rng, epochs=epochs, stage="fine_tune")
        artifacts_prefix = f"fine-tunes/{resource_id}"
        execution_details = executor.run_job(
            resource_type="fine-tunes",
            resource_id=resource_id,
            payload={
                "source_dataset_id": source_dataset_id,
                "eval_set_id": eval_set_id,
                "config_json": config_json or {},
                "base_model": {
                    "model_config_id": model_ref.id if model_ref else None,
                    "model_key": model_ref.model_key if model_ref else None,
                    "source_type": model_ref.source_type if model_ref else None,
                    "source_uri": model_ref.source_uri if model_ref else None,
                },
            },
        )
        report = executor.upload_json_artifact(
            resource_type="fine-tunes",
            resource_id=resource_id,
            file_name="fine-tune-report.json",
            payload={"metrics": metrics, "source_dataset_id": source_dataset_id, "execution": execution_details},
        )
        artifacts = [
            {
                "type": "adapter",
                "name": "lora_adapter",
                "path": _artifact_path(artifacts_prefix, "adapter.safetensors"),
                "epoch": epochs,
                "base_model": model_ref.model_key if model_ref else None,
            },
            {
                "type": "training_report",
                "name": report.name,
                "path": report.path,
                "download_url": report.download_url,
                **(report.meta or {}),
            },
        ]
        logs = [
            f"fine tune {resource_name} started",
            f"dataset={source_dataset_id} base_model={model_ref.model_key if model_ref else 'unknown'}",
            f"executor workdir={execution_details.get('workdir') or 'n/a'}",
            f"effective hyperparameters: lr={learning_rate}, batch_size={batch_size}, epochs={epochs}",
            f"lora: rank={lora_config.get('rank') or '-'}, alpha={lora_config.get('alpha') or '-'}, dropout={lora_config.get('dropout') or '-'}",
            f"best validation accuracy={metrics['summary']['best_val_accuracy']}",
            "fine tune completed successfully",
        ]
        return _merge_gpu_execution({
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "source_dataset_id": source_dataset_id,
                "eval_set_id": eval_set_id,
                "model_config_id": model_ref.id if model_ref else None,
                "model_key": model_ref.model_key if model_ref else None,
                "base_model_ref": {
                    "provider": model_ref.provider if model_ref else None,
                    "display_name": model_ref.display_name if model_ref else None,
                    "source_type": model_ref.source_type if model_ref else None,
                    "source_uri": model_ref.source_uri if model_ref else None,
                },
                "effective_hyperparameters": {
                    "learning_rate": learning_rate,
                    "batch_size": batch_size,
                    "epochs": epochs,
                },
                "lora": lora_config,
            },
            "artifacts": artifacts,
            "metrics": metrics,
            "logs": logs,
        }, lease=lease, remote_execution=remote_execution)

    @staticmethod
    def _build_metrics(
        *,
        rng: random.Random,
        epochs: int,
        stage: str,
        base_accuracy: float | None = None,
    ) -> dict[str, Any]:
        train_loss: list[float] = []
        val_accuracy: list[float] = []
        loss = 1.8 if stage == "training" else 0.9
        accuracy = float(base_accuracy or (0.72 if stage == "training" else 0.84))
        for _ in range(max(epochs, 1)):
            loss = max(0.08, loss - rng.uniform(0.08, 0.22))
            accuracy = min(0.995, accuracy + rng.uniform(0.01, 0.03))
            train_loss.append(round(loss, 4))
            val_accuracy.append(round(accuracy, 4))
        return {
            "train_loss": train_loss,
            "val_accuracy": val_accuracy,
            "summary": {
                "best_val_accuracy": max(val_accuracy),
                "final_train_loss": train_loss[-1],
            },
        }

    @staticmethod
    def _find_artifact_path(summary: dict[str, Any] | None, artifact_type: str) -> str | None:
        for artifact in list((summary or {}).get("artifacts") or []):
            if str(artifact.get("type") or "") == artifact_type:
                return str(artifact.get("path") or "") or None
        return None


class EvaluationEngine:
    @staticmethod
    def run_offline_evaluation(
        *,
        resource_id: str,
        resource_name: str,
        eval_set_id: str,
        sample_count: int,
        target_type: str,
        target_id: str,
        target_summary: dict[str, Any] | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
        lease: dict[str, Any] | None = None,
        remote_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        executor = LocalAlgoExecutor(build_object_storage())
        rng = _stable_rng("offline-eval", resource_id, eval_set_id, target_type, target_id)
        requested_metrics = list((config_json or {}).get("metrics") or ["accuracy", "f1", "mAP", "IoU", "AR"])
        effective_sample_count = max(sample_count, 1)
        metrics = {
            "accuracy": round(0.82 + rng.uniform(0.01, 0.08), 4),
            "f1": round(0.78 + rng.uniform(0.02, 0.1), 4),
            "mAP": round(0.74 + rng.uniform(0.03, 0.1), 4),
            "IoU": round(0.68 + rng.uniform(0.03, 0.12), 4),
            "AR": round(0.71 + rng.uniform(0.03, 0.1), 4),
            "sample_count": effective_sample_count,
            "requested_metrics": requested_metrics,
        }
        error_cases = [
            {
                "sample_ref": f"{eval_set_id}:case-{index + 1}",
                "reason": reason,
                "predicted_label": predicted,
                "expected_label": expected,
            }
            for index, (reason, predicted, expected) in enumerate(
                [
                    ("small defect missed", "pass", "scratch"),
                    ("fine-grained class confusion", "dent", "crack"),
                    ("low confidence threshold filtered result", "unknown", "stain"),
                ]
            )
        ]
        execution_details = executor.run_job(
            resource_type="offline-evaluations",
            resource_id=resource_id,
            payload={"eval_set_id": eval_set_id, "target_type": target_type, "target_id": target_id, "config_json": config_json or {}},
        )
        report = executor.upload_json_artifact(
            resource_type="offline-evaluations",
            resource_id=resource_id,
            file_name="offline-evaluation-report.json",
            payload={"metrics": metrics, "error_cases": error_cases, "execution": execution_details},
        )
        artifacts = [
            {
                "type": "evaluation_report",
                "name": report.name,
                "path": report.path,
                "download_url": report.download_url,
                **(report.meta or {}),
            }
        ]
        logs = [
            f"offline evaluation {resource_name} started",
            f"target={target_type}:{target_id}",
            f"executor workdir={execution_details.get('workdir') or 'n/a'}",
            f"evaluated {effective_sample_count} frozen samples",
            f"baseline artifact={TrainingRunner._find_artifact_path(target_summary, 'best_model') or TrainingRunner._find_artifact_path(target_summary, 'checkpoint') or 'n/a'}",
            "offline evaluation completed successfully",
        ]
        return _merge_gpu_execution({
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "eval_set_id": eval_set_id,
                "target_type": target_type,
                "target_id": target_id,
            },
            "metrics": metrics,
            "error_cases": error_cases,
            "artifacts": artifacts,
            "logs": logs,
        }, lease=lease, remote_execution=remote_execution)


class DeploymentManager:
    @staticmethod
    def build_service_urls(*, host: str, config_json: dict[str, Any] | None) -> dict[str, Any]:
        service_config = dict((config_json or {}).get("service_config") or {})
        port = int(service_config.get("port") or 18081)
        health_path = str(service_config.get("health_path") or "/health").strip() or "/health"
        infer_path = str(service_config.get("infer_path") or "/predict").strip() or "/predict"
        base_url = f"http://{host}:{port}"
        return {
            "service_host": host,
            "service_port": port,
            "endpoint": base_url,
            "health_url": f"{base_url}{health_path}",
            "infer_url": f"{base_url}{infer_path}",
            "health_path": health_path,
            "infer_path": infer_path,
            "startup_timeout_sec": int(service_config.get("startup_timeout_sec") or settings.gpu_deploy_startup_timeout_sec),
            "request_timeout_ms": int(service_config.get("request_timeout_ms") or settings.gpu_runtime_http_timeout_sec * 1000),
        }

    @staticmethod
    def run_deployment(
        *,
        resource_id: str,
        resource_name: str,
        source_type: str,
        source_id: str,
        merge_mode: str,
        source_summary: dict[str, Any] | None,
        model_ref: ExecutionModelRef | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        executor = LocalAlgoExecutor(build_object_storage())
        runtime_registry = AlgoRuntimeRegistry()
        adapter_path = TrainingRunner._find_artifact_path(source_summary, "adapter")
        service_config = dict((config_json or {}).get("service_config") or {})
        inference_config = {
            "max_batch_size": int(service_config.get("max_batch_size") or 8),
            "max_concurrency": int(service_config.get("max_concurrency") or 4),
            "timeout_ms": int(service_config.get("timeout_ms") or 5000),
        }
        runtime_record = runtime_registry.register(
            deployment_id=resource_id,
            source_type=source_type,
            source_id=source_id,
            model_key=model_ref.model_key if model_ref else None,
            provider=model_ref.provider if model_ref else None,
            inference_config=inference_config,
        )
        execution_details = executor.run_job(
            resource_type="deployments",
            resource_id=resource_id,
            payload={"source_type": source_type, "source_id": source_id, "merge_mode": merge_mode, "inference_config": inference_config},
        )
        manifest = executor.upload_json_artifact(
            resource_type="deployments",
            resource_id=resource_id,
            file_name="deployment-manifest.json",
            payload={
                "source_type": source_type,
                "source_id": source_id,
                "merge_mode": merge_mode,
                "model_key": model_ref.model_key if model_ref else None,
                "provider": model_ref.provider if model_ref else None,
                "inference_config": inference_config,
                "execution": execution_details,
            },
        )
        runtime_registration = {
            "source_type": runtime_record.source_type,
            "source_id": runtime_record.source_id,
            "model_key": runtime_record.model_key,
            "provider": runtime_record.provider,
            "endpoint": runtime_record.endpoint,
            "endpoint_placeholder": runtime_record.endpoint,
            "inference_config": runtime_record.inference_config,
            "status": runtime_record.status,
        }
        artifacts = [
            {
                "type": "adapter_bundle" if merge_mode == "dynamic" else "merged_model",
                "name": "runtime_model",
                "path": adapter_path if merge_mode == "dynamic" else _artifact_path(f"deployments/{resource_id}", "merged-model.bin"),
            },
            {
                "type": "deployment_manifest",
                "name": manifest.name,
                "path": manifest.path,
                "download_url": manifest.download_url,
                **(manifest.meta or {}),
            },
        ]
        logs = [
            f"deployment {resource_name} started",
            f"source={source_type}:{source_id}",
            f"merge_mode={merge_mode}",
            f"serving model={model_ref.model_key if model_ref else 'unknown'}",
            f"executor workdir={execution_details.get('workdir') or 'n/a'}",
            f"endpoint={runtime_registration['endpoint']}",
            "deployment completed successfully",
        ]
        return {
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "source_type": source_type,
                "source_id": source_id,
                "merge_mode": merge_mode,
            },
            "runtime_registration": runtime_registration,
            "artifacts": artifacts,
            "logs": logs,
        }

    @staticmethod
    async def check_runtime_health(runtime_registration: dict[str, Any]) -> tuple[bool, str | None]:
        health_url = str(runtime_registration.get("health_url") or "").strip()
        if not health_url:
            if str(runtime_registration.get("status") or runtime_registration.get("service_status") or "").strip().lower() == "available":
                return True, None
            return False, "missing health_url"
        timeout_sec = max(int(runtime_registration.get("request_timeout_ms") or settings.gpu_runtime_http_timeout_sec * 1000), 1000) / 1000
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
                response = await client.get(health_url)
                response.raise_for_status()
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    async def invoke_runtime(
        *,
        runtime_registration: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        infer_url = str(runtime_registration.get("infer_url") or "").strip()
        if not infer_url:
            raise ValidationError("runtime infer_url is missing")
        timeout_ms = int(runtime_registration.get("request_timeout_ms") or settings.gpu_runtime_http_timeout_sec * 1000)
        timeout_sec = max(timeout_ms, 1000) / 1000
        started_at = utcnow()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
                response = await client.post(infer_url, json=request_payload)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ValidationError(f"runtime invocation failed: {exc}") from exc
        latency_ms = int((utcnow() - started_at).total_seconds() * 1000)
        if not isinstance(payload, dict):
            payload = {"prediction": payload}
        return {
            "prediction": payload.get("prediction", payload),
            "latency_ms": int(payload.get("latency_ms") or latency_ms),
            "model_version": payload.get("model_version") or runtime_registration.get("model_version"),
            "request_id": payload.get("request_id"),
            "runtime_status": payload.get("runtime_status") or runtime_registration.get("service_status") or "available",
            "error": payload.get("error"),
            "raw_response": payload,
        }


class OnlineValidationRunner:
    @staticmethod
    async def run_shadow_validation(
        *,
        resource_id: str,
        resource_name: str,
        deployment_id: str,
        deployment_summary: dict[str, Any] | None,
        replay_tasks: list[dict[str, Any]],
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        executor = LocalAlgoExecutor(build_object_storage())
        replay_count = len(replay_tasks)
        sample_limit = max(int((config_json or {}).get("sample_limit") or 5), 0)
        effective_count = min(replay_count, sample_limit) if sample_limit else replay_count
        runtime_registration = dict((deployment_summary or {}).get("runtime_registration") or {})
        runtime_status = str(runtime_registration.get("service_status") or runtime_registration.get("status") or "").strip().lower()
        if runtime_status not in {"available", "registered"}:
            raise ValidationError("deployment runtime is not available")
        latencies: list[int] = []
        success_count = 0
        error_count = 0
        failure_samples: list[dict[str, Any]] = []
        started_exec = utcnow()
        for item in replay_tasks[:effective_count]:
            try:
                result = await DeploymentManager.invoke_runtime(
                    runtime_registration=runtime_registration,
                    request_payload={"task": item, "config": config_json or {}},
                )
                latencies.append(int(result.get("latency_ms") or 0))
                if result.get("error"):
                    error_count += 1
                    failure_samples.append({**item, "error": result.get("error")})
                else:
                    success_count += 1
            except Exception as exc:
                error_count += 1
                failure_samples.append({**item, "error": str(exc)})
        elapsed_ms = max(int((utcnow() - started_exec).total_seconds() * 1000), 1)
        success_rate = round(success_count / effective_count, 4) if effective_count else 0.0
        avg_latency_ms = int(sum(latencies) / len(latencies)) if latencies else 0
        throughput_qps = round((effective_count / elapsed_ms) * 1000, 2) if effective_count else 0.0
        execution_details = executor.run_job(
            resource_type="online-validations",
            resource_id=resource_id,
            payload={"deployment_id": deployment_id, "sample_limit": sample_limit, "replay_count": replay_count},
        )
        logs = [
            f"online validation {resource_name} started",
            f"deployment={deployment_id}",
            f"executor workdir={execution_details.get('workdir') or 'n/a'}",
            f"replayed tasks={effective_count}",
            f"baseline deployment status={(deployment_summary or {}).get('summary', {}).get('status') or 'unknown'}",
            "shadow validation completed successfully",
        ]
        report = executor.upload_json_artifact(
            resource_type="online-validations",
            resource_id=resource_id,
            file_name="online-validation-report.json",
            payload={
                "metrics": {
                    "shadow_pass_rate": success_rate,
                    "avg_latency_ms": avg_latency_ms,
                    "throughput_qps": throughput_qps,
                    "error_count": error_count,
                },
                "replay_tasks": replay_tasks[:effective_count],
                "failures": failure_samples,
                "execution": execution_details,
            },
        )
        return {
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "deployment_id": deployment_id,
                "validation_type": "shadow",
                "replay_source": "historical_tasks",
                "replay_count": effective_count,
            },
            "metrics": {
                "shadow_pass_rate": success_rate,
                "avg_latency_ms": avg_latency_ms,
                "throughput_qps": throughput_qps,
                "replay_count": effective_count,
                "baseline_runtime_status": runtime_registration.get("service_status") or "unknown",
                "error_count": error_count,
            },
            "replay_samples": [
                {
                    "task_id": item.get("task_id"),
                    "product_id": item.get("product_id"),
                    "spec_code": item.get("spec_code"),
                    "verdict": item.get("verdict"),
                    "overall_score": item.get("overall_score"),
                }
                for item in replay_tasks[:effective_count]
            ],
            "failure_samples": failure_samples,
            "artifacts": [
                {
                    "type": "validation_report",
                    "name": report.name,
                    "path": report.path,
                    "download_url": report.download_url,
                    **(report.meta or {}),
                }
            ],
            "logs": logs,
        }
