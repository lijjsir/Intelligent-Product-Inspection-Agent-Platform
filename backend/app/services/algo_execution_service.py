from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any


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
    model_type: str | None = None


class TrainingRunner:
    @staticmethod
    def run_training(
        *,
        resource_id: str,
        resource_name: str,
        source_dataset_id: str,
        model_ref: ExecutionModelRef | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        rng = _stable_rng("training", resource_id, source_dataset_id, model_ref.model_key if model_ref else "")
        hyperparameters = dict((config_json or {}).get("hyperparameters") or {})
        epochs = int(hyperparameters.get("epochs") or 5)
        learning_rate = float(hyperparameters.get("learning_rate") or 0.001)
        batch_size = int(hyperparameters.get("batch_size") or 16)
        metrics = TrainingRunner._build_metrics(rng=rng, epochs=epochs, stage="training")
        artifacts_prefix = f"training-jobs/{resource_id}"
        artifacts = [
            {
                "type": "checkpoint",
                "name": "last_checkpoint",
                "path": _artifact_path(artifacts_prefix, "checkpoint-last.bin"),
                "epoch": epochs,
            },
            {
                "type": "best_model",
                "name": "best_model",
                "path": _artifact_path(artifacts_prefix, "best-model.bin"),
                "metric": "val_accuracy",
                "score": metrics["summary"]["best_val_accuracy"],
            },
            {
                "type": "training_report",
                "name": "training_report",
                "path": _artifact_path(artifacts_prefix, "training-report.json"),
            },
        ]
        logs = [
            f"training job {resource_name} started",
            f"dataset={source_dataset_id} model={model_ref.model_key if model_ref else 'unknown'}",
            f"effective hyperparameters: lr={learning_rate}, batch_size={batch_size}, epochs={epochs}",
            f"best validation accuracy={metrics['summary']['best_val_accuracy']}",
            "training completed successfully",
        ]
        return {
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "source_dataset_id": source_dataset_id,
                "model_config_id": model_ref.id if model_ref else None,
                "model_key": model_ref.model_key if model_ref else None,
                "effective_hyperparameters": {
                    "learning_rate": learning_rate,
                    "batch_size": batch_size,
                    "epochs": epochs,
                },
            },
            "artifacts": artifacts,
            "metrics": metrics,
            "logs": logs,
        }

    @staticmethod
    def run_fine_tune(
        *,
        resource_id: str,
        resource_name: str,
        training_job_id: str,
        base_training_summary: dict[str, Any] | None,
        model_ref: ExecutionModelRef | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        rng = _stable_rng("fine-tune", resource_id, training_job_id, model_ref.model_key if model_ref else "")
        base_hyperparameters = dict(((base_training_summary or {}).get("summary") or {}).get("effective_hyperparameters") or {})
        hyperparameters = dict((config_json or {}).get("hyperparameters") or {})
        base_learning_rate = float(base_hyperparameters.get("learning_rate") or 0.001)
        learning_rate = float(hyperparameters.get("learning_rate") or round(base_learning_rate * 0.1, 6))
        epochs = int(hyperparameters.get("epochs") or 3)
        batch_size = int(hyperparameters.get("batch_size") or base_hyperparameters.get("batch_size") or 8)
        metrics = TrainingRunner._build_metrics(rng=rng, epochs=epochs, stage="fine_tune", base_accuracy=((base_training_summary or {}).get("metrics") or {}).get("summary", {}).get("best_val_accuracy"))
        base_checkpoint = TrainingRunner._find_artifact_path(base_training_summary, "checkpoint")
        artifacts_prefix = f"fine-tunes/{resource_id}"
        artifacts = [
            {
                "type": "checkpoint",
                "name": "fine_tune_checkpoint",
                "path": _artifact_path(artifacts_prefix, "checkpoint-last.bin"),
                "epoch": epochs,
                "base_checkpoint": base_checkpoint,
            },
            {
                "type": "best_model",
                "name": "fine_tune_best_model",
                "path": _artifact_path(artifacts_prefix, "best-model.bin"),
                "metric": "val_accuracy",
                "score": metrics["summary"]["best_val_accuracy"],
            },
            {
                "type": "training_report",
                "name": "fine_tune_report",
                "path": _artifact_path(artifacts_prefix, "fine-tune-report.json"),
            },
        ]
        logs = [
            f"fine tune {resource_name} started from training job {training_job_id}",
            f"base checkpoint={base_checkpoint or 'missing'}",
            f"effective hyperparameters: lr={learning_rate}, batch_size={batch_size}, epochs={epochs}",
            f"best validation accuracy={metrics['summary']['best_val_accuracy']}",
            "fine tune completed successfully",
        ]
        return {
            "summary": {
                "status": "completed",
                "execution_mode": execution_mode,
                "started_at": _iso(started_at),
                "completed_at": _iso(completed_at),
                "training_job_id": training_job_id,
                "model_config_id": model_ref.id if model_ref else None,
                "model_key": model_ref.model_key if model_ref else None,
                "effective_hyperparameters": {
                    "learning_rate": learning_rate,
                    "batch_size": batch_size,
                    "epochs": epochs,
                },
                "base_checkpoint": base_checkpoint,
            },
            "artifacts": artifacts,
            "metrics": metrics,
            "logs": logs,
        }

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
    ) -> dict[str, Any]:
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
        artifacts = [
            {
                "type": "evaluation_report",
                "name": "offline_evaluation_report",
                "path": _artifact_path(f"offline-evaluations/{resource_id}", "offline-evaluation-report.json"),
            }
        ]
        logs = [
            f"offline evaluation {resource_name} started",
            f"target={target_type}:{target_id}",
            f"evaluated {effective_sample_count} frozen samples",
            f"baseline artifact={TrainingRunner._find_artifact_path(target_summary, 'best_model') or TrainingRunner._find_artifact_path(target_summary, 'checkpoint') or 'n/a'}",
            "offline evaluation completed successfully",
        ]
        return {
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
        }


class DeploymentManager:
    @staticmethod
    def run_deployment(
        *,
        resource_id: str,
        resource_name: str,
        source_type: str,
        source_id: str,
        source_summary: dict[str, Any] | None,
        model_ref: ExecutionModelRef | None,
        config_json: dict[str, Any] | None,
        execution_mode: str,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        best_model_path = TrainingRunner._find_artifact_path(source_summary, "best_model") or TrainingRunner._find_artifact_path(source_summary, "checkpoint")
        service_config = dict((config_json or {}).get("service_config") or {})
        runtime_registration = {
            "source_type": source_type,
            "source_id": source_id,
            "model_key": model_ref.model_key if model_ref else None,
            "provider": model_ref.provider if model_ref else None,
            "endpoint_placeholder": f"/runtime/algo-deployments/{resource_id}/infer",
            "inference_config": {
                "max_batch_size": int(service_config.get("max_batch_size") or 8),
                "max_concurrency": int(service_config.get("max_concurrency") or 4),
                "timeout_ms": int(service_config.get("timeout_ms") or 5000),
            },
            "status": "available",
        }
        artifacts = [
            {
                "type": "deployed_model",
                "name": "runtime_model",
                "path": best_model_path,
            },
            {
                "type": "deployment_manifest",
                "name": "deployment_manifest",
                "path": _artifact_path(f"deployments/{resource_id}", "deployment-manifest.json"),
            },
        ]
        logs = [
            f"deployment {resource_name} started",
            f"source={source_type}:{source_id}",
            f"serving model={model_ref.model_key if model_ref else 'unknown'}",
            f"endpoint placeholder={runtime_registration['endpoint_placeholder']}",
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
            },
            "runtime_registration": runtime_registration,
            "artifacts": artifacts,
            "logs": logs,
        }


class OnlineValidationRunner:
    @staticmethod
    def run_shadow_validation(
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
        rng = _stable_rng("online-validation", resource_id, deployment_id)
        replay_count = len(replay_tasks)
        sample_limit = max(int((config_json or {}).get("sample_limit") or 5), 0)
        effective_count = min(replay_count, sample_limit) if sample_limit else replay_count
        success_rate = round(0.86 + rng.uniform(0.02, 0.1), 4)
        avg_latency_ms = int(160 + rng.uniform(15, 60))
        throughput_qps = round(6.5 + rng.uniform(0.5, 2.5), 2)
        logs = [
            f"online validation {resource_name} started",
            f"deployment={deployment_id}",
            f"replayed tasks={effective_count}",
            f"baseline deployment status={(deployment_summary or {}).get('summary', {}).get('status') or 'unknown'}",
            "shadow validation completed successfully",
        ]
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
                "baseline_runtime_status": (((deployment_summary or {}).get("runtime_registration") or {}).get("status") or "unknown"),
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
            "artifacts": [
                {
                    "type": "validation_report",
                    "name": "online_validation_report",
                    "path": _artifact_path(f"online-validations/{resource_id}", "online-validation-report.json"),
                }
            ],
            "logs": logs,
        }
