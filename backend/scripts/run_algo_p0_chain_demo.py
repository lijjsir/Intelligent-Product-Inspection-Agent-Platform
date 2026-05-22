from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


DEMO_PREFIX = "[DEMO] Algo P0 Chain"
DEMO_DATASET_NAME = f"{DEMO_PREFIX} Dataset"
DEMO_EVAL_SET_NAME = f"{DEMO_PREFIX} EvalSet"
DEMO_SAMPLE_DEFS = [
    {
        "sample_name": f"{DEMO_PREFIX} Sample 1",
        "text_content": "产品外壳边缘存在细微划痕，建议判定为外观缺陷。",
        "annotation_data": {"label": "scratch", "severity": "minor"},
        "related_entities": ["外壳", "划痕"],
        "source_metadata": {"product_line": "housing", "scene": "appearance"},
    },
    {
        "sample_name": f"{DEMO_PREFIX} Sample 2",
        "text_content": "屏幕贴合区域出现亮斑，可能与背光模组装配偏差有关。",
        "annotation_data": {"label": "bright_spot", "severity": "major"},
        "related_entities": ["屏幕", "亮斑", "背光模组"],
        "source_metadata": {"product_line": "display", "scene": "screen"},
    },
    {
        "sample_name": f"{DEMO_PREFIX} Sample 3",
        "text_content": "接口焊点周边检测到虚焊风险，需要进一步复检确认。",
        "annotation_data": {"label": "cold_solder", "severity": "critical"},
        "related_entities": ["接口", "焊点", "虚焊"],
        "source_metadata": {"product_line": "connector", "scene": "soldering"},
    },
]
DEMO_MODEL_ENDPOINT = "https://demo.invalid/runtime"
REQUEST_TIMEOUT = 30.0


class DemoError(RuntimeError):
    pass


@dataclass
class AuthContext:
    access_token: str
    org_id: str
    username: str | None = None


class ApiClient:
    def __init__(self, *, base_url: str, auth: AuthContext):
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Authorization": f"Bearer {auth.access_token}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def patch(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, params=params, json=json_body)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise DemoError(f"{method} {path} returned non-JSON response: {response.text[:300]}") from exc

        if response.status_code >= 400:
            message = payload.get("message") or payload.get("detail") or response.text
            raise DemoError(f"{method} {path} failed with {response.status_code}: {message}")
        if payload.get("code") != "ok":
            raise DemoError(f"{method} {path} returned unexpected envelope: {payload}")
        return payload.get("data")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise DemoError(f"missing required environment variable: {name}")
    return value


async def resolve_auth(base_url: str) -> AuthContext:
    token = os.getenv("ACCESS_TOKEN", "").strip()
    org_id = os.getenv("ORG_ID", "").strip()
    username = os.getenv("USERNAME", "").strip() or None
    if token:
        if not org_id:
            raise DemoError("ACCESS_TOKEN mode also requires ORG_ID")
        return AuthContext(access_token=token, org_id=org_id, username=username)

    org_id = _require_env("ORG_ID")
    username = _require_env("USERNAME")
    password = _require_env("PASSWORD")
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            "/auth/token",
            headers={"X-Org-Id": org_id, "Content-Type": "application/json"},
            json={"username": username, "password": password},
        )
        payload = response.json()
        if response.status_code >= 400 or payload.get("code") != "ok" or not payload.get("data"):
            raise DemoError(f"login failed: {payload}")
        data = payload["data"]
        return AuthContext(
            access_token=str(data["access_token"]),
            org_id=str(data["org_id"]),
            username=str(data.get("username") or username),
        )


async def ensure_model_configs(api: ApiClient) -> tuple[dict[str, Any], dict[str, Any]]:
    configs = await api.get("/model-configs")
    active = [cfg for cfg in configs if cfg.get("is_active")]
    eligible = [
        cfg for cfg in active
        if str(cfg.get("model_type") or "").lower() in {"chat", "multimodal"}
    ]
    training = next((cfg for cfg in eligible if str(cfg.get("model_type")).lower() == "chat"), None)
    if training is None:
        training = next((cfg for cfg in eligible if str(cfg.get("model_type")).lower() == "multimodal"), None)
    fine_tune = next((cfg for cfg in eligible if str(cfg.get("model_type")).lower() == "multimodal"), None)
    if fine_tune is None:
        fine_tune = training

    if training is None and fine_tune is None:
        training = await api.post(
            "/model-configs",
            json_body={
                "provider": "demo-local",
                "model_key": "demo-p0-train-chat",
                "display_name": f"{DEMO_PREFIX} Train Chat Model",
                "endpoint": DEMO_MODEL_ENDPOINT,
                "model_type": "chat",
                "priority": 10,
                "is_active": True,
            },
        )
        fine_tune = await api.post(
            "/model-configs",
            json_body={
                "provider": "demo-local",
                "model_key": "demo-p0-finetune-mm",
                "display_name": f"{DEMO_PREFIX} Fine Tune Multimodal Model",
                "endpoint": DEMO_MODEL_ENDPOINT,
                "model_type": "multimodal",
                "priority": 20,
                "is_active": True,
            },
        )
    elif training is None:
        training = fine_tune
    elif fine_tune is None:
        fine_tune = training
    return training, fine_tune


async def find_dataset_by_name(api: ApiClient, name: str) -> dict[str, Any] | None:
    page = await api.get("/datasets", params={"page": 1, "size": 100, "keyword": name})
    return next((item for item in page.get("items", []) if item.get("name") == name), None)


async def ensure_dataset(api: ApiClient) -> dict[str, Any]:
    dataset = await find_dataset_by_name(api, DEMO_DATASET_NAME)
    if dataset is None:
        dataset = await api.post(
            "/datasets",
            json_body={
                "name": DEMO_DATASET_NAME,
                "description": "HTTP demo dataset for algo workspace P0 chain.",
                "modality": "image_text",
                "tags": ["demo", "algo-workspace", "p0-chain"],
            },
        )
    if dataset.get("status") != "active":
        dataset = await api.patch(f"/datasets/{dataset['id']}", json_body={"status": "active"})
    return dataset


async def list_all_samples(api: ApiClient, dataset_id: str) -> list[dict[str, Any]]:
    page = await api.get(f"/datasets/{dataset_id}/samples", params={"page": 1, "size": 100})
    return list(page.get("items", []))


async def ensure_dataset_samples(api: ApiClient, dataset_id: str) -> list[dict[str, Any]]:
    existing = await list_all_samples(api, dataset_id)
    by_name = {str(item.get("sample_name") or ""): item for item in existing}
    created_or_existing: list[dict[str, Any]] = []
    for sample_def in DEMO_SAMPLE_DEFS:
        sample = by_name.get(sample_def["sample_name"])
        if sample is None:
            sample = await api.post(
                f"/datasets/{dataset_id}/samples/text",
                json_body=sample_def,
            )
        created_or_existing.append(sample)
    return created_or_existing


async def find_eval_set_by_name(api: ApiClient, name: str) -> dict[str, Any] | None:
    page = await api.get("/eval-datasets", params={"page": 1, "size": 100, "keyword": name})
    return next((item for item in page.get("items", []) if item.get("name") == name), None)


async def ensure_eval_set(api: ApiClient, dataset_id: str, sample_ids: list[str]) -> dict[str, Any]:
    eval_set = await find_eval_set_by_name(api, DEMO_EVAL_SET_NAME)
    if eval_set is None:
        eval_set = await api.post(
            "/eval-datasets",
            json_body={
                "name": DEMO_EVAL_SET_NAME,
                "description": "Snapshot eval set for algo workspace P0 chain demo.",
                "source_dataset_id": dataset_id,
                "sample_ids": sample_ids,
            },
        )
        return eval_set

    items = await api.get(f"/eval-datasets/{eval_set['id']}/samples", params={"page": 1, "size": 100})
    current_sample_ids = {item.get("dataset_sample_id") for item in items.get("items", [])}
    missing = [sample_id for sample_id in sample_ids if sample_id not in current_sample_ids]
    if missing:
        await api.post(
            f"/eval-datasets/{eval_set['id']}/samples",
            json_body={"sample_ids": missing},
        )
        eval_set = await api.get(f"/eval-datasets/{eval_set['id']}")
    return eval_set


async def create_experiment(api: ApiClient) -> dict[str, Any]:
    return await api.post(
        "/experiments",
        json_body={
            "name": f"{DEMO_PREFIX} {_timestamp()}",
            "description": "End-to-end local demo experiment for algo workspace P0 chain.",
            "config_json": {"source": "run_algo_p0_chain_demo.py"},
        },
    )


async def create_training_job(
    api: ApiClient,
    *,
    experiment_id: str,
    dataset_id: str,
    eval_set_id: str,
    model_config_id: str,
) -> dict[str, Any]:
    return await api.post(
        "/training-jobs",
        json_body={
            "name": f"{DEMO_PREFIX} Training {_timestamp()}",
            "description": "Demo training job.",
            "source_dataset_id": dataset_id,
            "model_config_id": model_config_id,
            "eval_set_id": eval_set_id,
            "experiment_id": experiment_id,
            "config_json": {
                "epochs": 3,
                "batch_size": 4,
                "learning_rate": 1e-4,
                "scheduler": "cosine",
            },
        },
    )


async def create_fine_tune(
    api: ApiClient,
    *,
    experiment_id: str,
    training_job_id: str,
    model_config_id: str,
) -> dict[str, Any]:
    return await api.post(
        "/fine-tunes",
        json_body={
            "name": f"{DEMO_PREFIX} Fine Tune {_timestamp()}",
            "description": "Demo fine-tune run.",
            "training_job_id": training_job_id,
            "model_config_id": model_config_id,
            "experiment_id": experiment_id,
            "config_json": {
                "epochs": 2,
                "batch_size": 2,
            },
        },
    )


async def create_offline_evaluation(
    api: ApiClient,
    *,
    experiment_id: str,
    eval_set_id: str,
    target_id: str,
) -> dict[str, Any]:
    return await api.post(
        "/offline-evaluations",
        json_body={
            "name": f"{DEMO_PREFIX} Offline Eval {_timestamp()}",
            "description": "Demo offline evaluation run.",
            "eval_set_id": eval_set_id,
            "target_type": "fine_tune",
            "target_id": target_id,
            "experiment_id": experiment_id,
            "config_json": {
                "metrics": ["accuracy", "f1", "mAP", "IoU", "AR"],
            },
        },
    )


async def create_deployment(
    api: ApiClient,
    *,
    experiment_id: str,
    source_id: str,
) -> dict[str, Any]:
    return await api.post(
        "/deployments",
        json_body={
            "name": f"{DEMO_PREFIX} Deployment {_timestamp()}",
            "description": "Demo deployment run.",
            "source_type": "fine_tune",
            "source_id": source_id,
            "experiment_id": experiment_id,
            "config_json": {
                "inference_config": {
                    "batch_size": 4,
                    "max_concurrency": 2,
                }
            },
        },
    )


async def launch_and_wait(
    api: ApiClient,
    *,
    resource_type: str,
    resource_id: str,
    launch_path: str,
    get_path: str,
    poll_interval: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    await api.post(launch_path)
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        detail = await api.get(get_path)
        status = str(detail.get("status") or "")
        if status == "completed":
            return detail
        if status in {"failed", "cancelled"}:
            raise DemoError(
                f"{resource_type} {resource_id} ended with status={status}: "
                f"{json.dumps(detail, ensure_ascii=False, default=str)}"
            )
        if asyncio.get_running_loop().time() >= deadline:
            raise DemoError(
                f"timed out waiting for {resource_type} {resource_id}: "
                f"{json.dumps(detail, ensure_ascii=False, default=str)}"
            )
        await asyncio.sleep(poll_interval)


def print_summary(
    *,
    base_origin: str,
    dataset: dict[str, Any],
    eval_set: dict[str, Any],
    experiment: dict[str, Any],
    training: dict[str, Any],
    fine_tune: dict[str, Any],
    offline: dict[str, Any],
    deployment: dict[str, Any],
) -> None:
    training_summary = (training.get("result_summary") or {}).get("metrics") or {}
    fine_tune_summary = (fine_tune.get("result_summary") or {}).get("metrics") or {}
    offline_summary = offline.get("result_summary") or {}
    deployment_summary = deployment.get("result_summary") or {}
    lines = [
        {"dataset_id": dataset.get("id"), "status": dataset.get("status")},
        {"eval_set_id": eval_set.get("id"), "status": eval_set.get("status")},
        {"experiment_id": experiment.get("id"), "status": experiment.get("status")},
        {"training_job_id": training.get("id"), "status": training.get("status")},
        {"fine_tune_id": fine_tune.get("id"), "status": fine_tune.get("status")},
        {"offline_evaluation_id": offline.get("id"), "status": offline.get("status")},
        {"deployment_id": deployment.get("id"), "status": deployment.get("status")},
    ]
    print(json.dumps({"resources": lines}, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "training_metrics": training_summary.get("summary") or training_summary,
                "training_artifacts": (training.get("result_summary") or {}).get("artifacts") or [],
                "fine_tune_metrics": fine_tune_summary.get("summary") or fine_tune_summary,
                "fine_tune_artifacts": (fine_tune.get("result_summary") or {}).get("artifacts") or [],
                "offline_metrics": offline_summary.get("metrics") or {},
                "offline_error_cases_count": len(offline_summary.get("error_cases") or []),
                "deployment_runtime_registration": deployment_summary.get("runtime_registration") or {},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("Suggested frontend paths:")
    print(f"{base_origin}/ops/data/import/{dataset.get('id')}")
    print(f"{base_origin}/ops/data/eval-sets/{eval_set.get('id')}")
    print(f"{base_origin}/ops/training/jobs/{training.get('id')}")
    print(f"{base_origin}/ops/training/fine-tune/{fine_tune.get('id')}")
    print(f"{base_origin}/ops/eval/offline/{offline.get('id')}")
    print(f"{base_origin}/ops/deployments/{deployment.get('id')}")
    print(f"{base_origin}/ops/experiments/{experiment.get('id')}")


async def ensure_experiment_related_resources(
    api: ApiClient,
    experiment_id: str,
    *,
    training_id: str,
    fine_tune_id: str,
    offline_id: str,
    deployment_id: str,
) -> dict[str, Any]:
    detail = await api.get(f"/experiments/{experiment_id}")
    related = detail.get("related_resources") or {}
    expected = {
        "training_jobs": training_id,
        "fine_tunes": fine_tune_id,
        "offline_evaluations": offline_id,
        "deployments": deployment_id,
    }
    for key, resource_id in expected.items():
        items = related.get(key) or []
        if not any(item.get("id") == resource_id for item in items):
            raise DemoError(f"experiment {experiment_id} missing related resource in {key}: {resource_id}")
    return detail


async def run(args: argparse.Namespace) -> None:
    auth = await resolve_auth(args.base_url)
    api = ApiClient(base_url=args.base_url, auth=auth)
    try:
        training_model, fine_tune_model = await ensure_model_configs(api)
        dataset = await ensure_dataset(api)
        samples = await ensure_dataset_samples(api, str(dataset["id"]))
        sample_ids = [str(sample["id"]) for sample in samples]
        eval_set = await ensure_eval_set(api, str(dataset["id"]), sample_ids)
        experiment = await create_experiment(api)

        training_created = await create_training_job(
            api,
            experiment_id=str(experiment["id"]),
            dataset_id=str(dataset["id"]),
            eval_set_id=str(eval_set["id"]),
            model_config_id=str(training_model["id"]),
        )
        training = await launch_and_wait(
            api,
            resource_type="training_job",
            resource_id=str(training_created["id"]),
            launch_path=f"/training-jobs/{training_created['id']}/launch",
            get_path=f"/training-jobs/{training_created['id']}",
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )

        fine_tune_created = await create_fine_tune(
            api,
            experiment_id=str(experiment["id"]),
            training_job_id=str(training["id"]),
            model_config_id=str(fine_tune_model["id"]),
        )
        fine_tune = await launch_and_wait(
            api,
            resource_type="fine_tune",
            resource_id=str(fine_tune_created["id"]),
            launch_path=f"/fine-tunes/{fine_tune_created['id']}/launch",
            get_path=f"/fine-tunes/{fine_tune_created['id']}",
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )

        offline_created = await create_offline_evaluation(
            api,
            experiment_id=str(experiment["id"]),
            eval_set_id=str(eval_set["id"]),
            target_id=str(fine_tune["id"]),
        )
        offline = await launch_and_wait(
            api,
            resource_type="offline_evaluation",
            resource_id=str(offline_created["id"]),
            launch_path=f"/offline-evaluations/{offline_created['id']}/launch",
            get_path=f"/offline-evaluations/{offline_created['id']}",
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )

        deployment_created = await create_deployment(
            api,
            experiment_id=str(experiment["id"]),
            source_id=str(fine_tune["id"]),
        )
        deployment = await launch_and_wait(
            api,
            resource_type="deployment",
            resource_id=str(deployment_created["id"]),
            launch_path=f"/deployments/{deployment_created['id']}/launch",
            get_path=f"/deployments/{deployment_created['id']}",
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )

        experiment_detail = await ensure_experiment_related_resources(
            api,
            str(experiment["id"]),
            training_id=str(training["id"]),
            fine_tune_id=str(fine_tune["id"]),
            offline_id=str(offline["id"]),
            deployment_id=str(deployment["id"]),
        )
        print_summary(
            base_origin=args.frontend_base.rstrip("/"),
            dataset=dataset,
            eval_set=eval_set,
            experiment=experiment_detail,
            training=training,
            fine_tune=fine_tune,
            offline=offline,
            deployment=deployment,
        )
    finally:
        await api.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run algo workspace P0 chain demo via local HTTP API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="Backend API base URL")
    parser.add_argument("--frontend-base", default="http://127.0.0.1:5173", help="Frontend base URL for summary links")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval in seconds")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="Per-stage timeout in seconds")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except DemoError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
