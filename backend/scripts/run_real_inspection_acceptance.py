from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_ORG_SLUG = "cqupt"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"
DEFAULT_EXPERT_USERNAME = "expert"
DEFAULT_EXPERT_PASSWORD = "123456"
DEFAULT_PRODUCT_FAMILY = "screw"
DEFAULT_PRODUCT_ID = "screw"
DEFAULT_TIMEOUT = 30.0
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_POLL_ATTEMPTS = 60
SCRIPT_PREFIX = "[ACCEPT] Screw Inspection"
ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_PATH = ROOT_DIR / "Snipaste_2026-05-20_15-36-36.png"
SYSTEM_DOC_TEXT = """
螺丝国家标准摘要：
1. 外观应完整，不得出现裂纹、断裂、明显碰伤。
2. 表面不得出现明显划伤、油污、镀层脱落、锈蚀。
3. 螺纹应连续完整，不得缺牙、乱牙、压伤。
4. 满足外观完整、无缺陷、证据可追溯时，可判定为合格。
""".strip()
USER_DOC_TEXT = """
当前批次验收说明：
1. 本批次样件为螺丝 screw，目标是验证系统标准 RAG 与用户 RAG 同时参与。
2. 合格样例要求：无裂纹、无表面划伤、无涂层缺陷、无螺纹损伤、无油污。
3. 若命中系统标准与批次说明双来源证据，且门槛满足，可自动 PASS。
""".strip()


class AcceptanceError(RuntimeError):
    pass


@dataclass
class SessionContext:
    org_id: str
    username: str
    role: str
    access_token: str


class ApiClient:
    def __init__(self, *, base_url: str, session: SessionContext):
        self._session = session
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=DEFAULT_TIMEOUT,
            headers={
                "Authorization": f"Bearer {session.access_token}",
                "X-Org-Id": session.org_id,
            },
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._request("POST", path, json_body=json_body, files=files, headers=headers)

    def patch(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, json_body=json_body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = dict(headers or {})
        response = self._client.request(
            method,
            path,
            params=params,
            json=json_body,
            files=files,
            headers=request_headers or None,
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AcceptanceError(f"{method} {path} returned non-JSON response: {response.text[:300]}") from exc
        if response.status_code >= 400:
            detail = payload.get("message") or payload.get("detail") or response.text
            raise AcceptanceError(f"{method} {path} failed with {response.status_code}: {detail}")
        return payload.get("data")


def log(message: str) -> None:
    print(message, flush=True)


def read_text_file(path: Path) -> bytes:
    return path.read_bytes()


def login(base_url: str, *, org_slug: str, username: str, password: str) -> SessionContext:
    response = httpx.post(
        f"{base_url.rstrip('/')}/auth/token",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json", "X-Org-Id": org_slug},
        timeout=DEFAULT_TIMEOUT,
    )
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"Login response for {username} is not JSON: {response.text[:300]}") from exc
    if response.status_code >= 400:
        detail = payload.get("message") or payload.get("detail") or response.text
        raise AcceptanceError(f"Login failed for {username}: {detail}")
    data = payload.get("data") or {}
    return SessionContext(
        org_id=str(data.get("org_id") or ""),
        username=str(data.get("username") or username),
        role=str(data.get("role") or ""),
        access_token=str(data.get("access_token") or ""),
    )


def ensure_file_exists(path: Path) -> None:
    if not path.is_file():
        raise AcceptanceError(f"image file not found: {path}")


def unique_suffix() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def maybe_create_embedding_model(admin_api: ApiClient) -> dict[str, Any] | None:
    models = admin_api.get("/model-configs")
    active_embedding = next(
        (item for item in models if item.get("is_active") and str(item.get("model_type") or "").lower() in {"embedding", "embed", "text_embedding"}),
        None,
    )
    if active_embedding:
        return active_embedding

    multimodal = next(
        (item for item in models if item.get("is_active") and str(item.get("model_type") or "").lower() == "multimodal" and item.get("has_api_key")),
        None,
    )
    if not multimodal:
        raise AcceptanceError("No active embedding model exists, and no reusable multimodal model with API key is available.")

    body = {
        "provider": str(multimodal.get("provider") or "volcengine"),
        "model_key": str(multimodal.get("model_key") or ""),
        "display_name": f"{SCRIPT_PREFIX} Embedding Runtime",
        "source_type": str(multimodal.get("source_type") or "external"),
        "source_uri": str(multimodal.get("source_uri") or multimodal.get("model_key") or ""),
        "endpoint": str(multimodal.get("endpoint") or ""),
        "model_type": "embedding",
        "priority": int(multimodal.get("priority") or 100) + 1,
        "rpm_limit": multimodal.get("rpm_limit"),
        "input_price_per_million": multimodal.get("input_price_per_million"),
        "output_price_per_million": 0,
        "is_active": True,
    }
    log("No active embedding model found. Creating a temporary acceptance embedding runtime from current multimodal config.")
    return admin_api.post("/model-configs", json_body=body)


def create_rag_space(api: ApiClient, *, name: str, description: str) -> dict[str, Any]:
    return api.post(
        "/rag-spaces",
        json_body={
            "name": name,
            "description": description,
        },
    )


def upload_rag_document(api: ApiClient, *, rag_space_id: str, file_name: str, content: str) -> Any:
    files = {
        "files": (file_name, content.encode("utf-8"), "text/plain"),
    }
    return api.post(
        f"/rag-spaces/{rag_space_id}/documents",
        files=files,
        headers={},
    )


def upload_task_image(expert_api: ApiClient, image_path: Path) -> str:
    files = {
        "files": (image_path.name, image_path.read_bytes(), "image/png"),
    }
    data = expert_api.post("/chat/uploads", files=files, headers={})
    items = list(data.get("items") or [])
    if not items:
        raise AcceptanceError("chat upload succeeded but returned no attachment items")
    return str(items[0].get("url") or "").strip()


def create_inspection_standard_binding(admin_api: ApiClient, *, name: str, rag_space_id: str) -> dict[str, Any]:
    return admin_api.post(
        "/inspection-standards",
        json_body={
            "name": name,
            "product_family": DEFAULT_PRODUCT_FAMILY,
            "description": "Real acceptance binding for screw standard RAG.",
            "rag_space_ids": [rag_space_id],
            "is_active": True,
        },
    )


def create_test_spec(admin_api: ApiClient, *, spec_code: str, name: str) -> dict[str, Any]:
    items = [
        {"defect_type": "crack", "severity": "critical", "disposition": "fail", "confidence_threshold": 0.55, "description": "Crack is not allowed."},
        {"defect_type": "surface_scratch", "severity": "major", "disposition": "fail", "confidence_threshold": 0.55, "description": "Surface scratch is not allowed."},
        {"defect_type": "coating_defect", "severity": "major", "disposition": "fail", "confidence_threshold": 0.55, "description": "Coating defect is not allowed."},
        {"defect_type": "thread_damage", "severity": "major", "disposition": "fail", "confidence_threshold": 0.55, "description": "Thread damage is not allowed."},
        {"defect_type": "oil_stain", "severity": "minor", "disposition": "fail", "confidence_threshold": 0.55, "description": "Oil stain is not allowed."},
    ]
    return admin_api.post(
        "/inspection-specs",
        json_body={
            "spec_code": spec_code,
            "name": name,
            "version": "v1",
            "product_id": DEFAULT_PRODUCT_ID,
            "product_family": DEFAULT_PRODUCT_FAMILY,
            "applicable_skus": [],
            "required_views": [],
            "required_image_count": 1,
            "ai_gate_confidence_threshold": 0.70,
            "ai_gate_evidence_threshold": 0.50,
            "ai_gate_traceability_threshold": 0.50,
            "aggregation_rules": {},
            "ai_gate_rules": {},
            "manual_review_policies": {},
            "auto_pass_enabled": True,
            "is_active": True,
            "items": items,
        },
    )


def wait_until_spec_visible(admin_api: ApiClient, *, spec_code: str, attempts: int = 10, interval_sec: float = 0.5) -> dict[str, Any]:
    last_items: list[dict[str, Any]] = []
    for _ in range(attempts):
        items = list(admin_api.get("/inspection-specs") or [])
        last_items = items
        found = next((item for item in items if str(item.get("spec_code") or "") == spec_code), None)
        if found:
            return found
        time.sleep(interval_sec)
    raise AcceptanceError(
        f"Created inspection spec {spec_code} is not visible yet. Latest spec codes: "
        f"{[str(item.get('spec_code') or '') for item in last_items[:20]]}"
    )


def create_task(
    expert_api: ApiClient,
    *,
    spec_code: str,
    image_url: str,
    user_rag_space: dict[str, Any],
) -> dict[str, Any]:
    structured_record = {
        "product_id": DEFAULT_PRODUCT_ID,
        "product_family": DEFAULT_PRODUCT_FAMILY,
        "spec_code": spec_code,
        "crack_count": 0,
        "surface_scratch_count": 0,
        "coating_defect_count": 0,
        "thread_damage_count": 0,
        "oil_stain_count": 0,
        "expected_decision": "PASS",
        "image_urls": [image_url],
    }
    metadata = {
        "source": "acceptance_script",
        "source_graph": "inspection_task",
        "product_family": DEFAULT_PRODUCT_FAMILY,
        "selected_rag_space_id": str(user_rag_space["id"]),
        "selected_rag_space_name": str(user_rag_space["name"]),
        "selected_rag_space": {
            "id": str(user_rag_space["id"]),
            "name": str(user_rag_space["name"]),
            "description": user_rag_space.get("description"),
        },
        "selected_rag_scope_node_ids": [],
        "structured_record": structured_record,
    }
    return expert_api.post(
        "/tasks",
        json_body={
            "product_id": DEFAULT_PRODUCT_ID,
            "spec_code": spec_code,
            "image_urls": [image_url],
            "priority": 5,
            "metadata": metadata,
        },
    )


def run_task(expert_api: ApiClient, *, task_id: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(5):
        try:
            return expert_api.post(f"/agent/tasks/{task_id}/run", json_body={})
        except AcceptanceError as exc:
            last_error = exc
            message = str(exc)
            if "404" not in message:
                raise
            try:
                expert_api.get(f"/tasks/{task_id}")
            except Exception:
                pass
            time.sleep(0.5)
    if last_error is not None:
        raise last_error
    raise AcceptanceError(f"failed to run task {task_id}")


def poll_task_and_result(expert_api: ApiClient, *, task_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    last_task = {}
    for _ in range(DEFAULT_POLL_ATTEMPTS):
        task = expert_api.get(f"/tasks/{task_id}")
        events = expert_api.get(f"/tasks/{task_id}/events")
        last_task = task
        status = str(task.get("status") or "").lower()
        if status == "done":
            result = expert_api.get(f"/results/by-task/{task_id}")
            return task, result, events
        if status == "failed":
            raise AcceptanceError(f"Task {task_id} failed. Latest task payload: {json.dumps(task, ensure_ascii=False)}")
        time.sleep(DEFAULT_POLL_SECONDS)
    raise AcceptanceError(f"Task {task_id} did not reach done status. Latest task payload: {json.dumps(last_task, ensure_ascii=False)}")


def validate_result(
    *,
    task: dict[str, Any],
    result: dict[str, Any],
    binding_name: str,
    user_rag_space_id: str,
    system_rag_space_id: str,
) -> None:
    verdict = str(result.get("verdict") or "").lower()
    if verdict != "pass":
        raise AcceptanceError(f"Expected PASS, got {verdict}. Result: {json.dumps(result, ensure_ascii=False)}")
    reasoning_chain = dict(result.get("reasoning_chain") or {})
    rag_summary = dict(reasoning_chain.get("rag_summary") or {})
    citations = result.get("citations") or {}
    standard_evaluation = dict(reasoning_chain.get("standard_evaluation") or {})
    ai_gate = dict(standard_evaluation.get("ai_gate") or {})
    rag_space_ids = [str(item) for item in list(rag_summary.get("rag_space_ids") or [])]
    system_rag_space_ids = [str(item) for item in list(rag_summary.get("system_rag_space_ids") or [])]
    if system_rag_space_id not in system_rag_space_ids:
        raise AcceptanceError(f"System RAG not found in rag_summary: {json.dumps(rag_summary, ensure_ascii=False)}")
    if user_rag_space_id not in rag_space_ids or system_rag_space_id not in rag_space_ids:
        raise AcceptanceError(f"Expected both user/system RAG ids in rag_summary: {json.dumps(rag_summary, ensure_ascii=False)}")
    if int(rag_summary.get("merged_rag_source_count") or 0) < 2:
        raise AcceptanceError(f"Expected merged_rag_source_count >= 2: {json.dumps(rag_summary, ensure_ascii=False)}")
    if str(rag_summary.get("standard_binding_name") or "") != binding_name:
        raise AcceptanceError(f"Unexpected standard binding name: {json.dumps(rag_summary, ensure_ascii=False)}")
    if not list(citations.get("items") or []):
        raise AcceptanceError(f"Expected non-empty citations: {json.dumps(result, ensure_ascii=False)}")
    if not bool(ai_gate.get("passed")):
        raise AcceptanceError(f"AI gate did not pass: {json.dumps(standard_evaluation, ensure_ascii=False)}")
    log(f"Validation passed for task {task.get('id')}, result {result.get('id')}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real acceptance flow for screw inspection task.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--org-slug", default=DEFAULT_ORG_SLUG)
    parser.add_argument("--admin-username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument("--expert-username", default=DEFAULT_EXPERT_USERNAME)
    parser.add_argument("--expert-password", default=DEFAULT_EXPERT_PASSWORD)
    parser.add_argument("--image-path", default=str(DEFAULT_IMAGE_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = Path(args.image_path).resolve()
    ensure_file_exists(image_path)
    suffix = unique_suffix()
    admin_session = login(
        args.base_url,
        org_slug=args.org_slug,
        username=args.admin_username,
        password=args.admin_password,
    )
    expert_session = login(
        args.base_url,
        org_slug=args.org_slug,
        username=args.expert_username,
        password=args.expert_password,
    )
    log(f"Logged in admin={admin_session.username}/{admin_session.role} expert={expert_session.username}/{expert_session.role}")
    admin_api = ApiClient(base_url=args.base_url, session=admin_session)
    expert_api = ApiClient(base_url=args.base_url, session=expert_session)
    try:
        embedding_model = maybe_create_embedding_model(admin_api)
        if embedding_model:
            log(f"Embedding runtime ready: {embedding_model.get('model_key')} ({embedding_model.get('id')})")

        expert_rag = create_rag_space(
            expert_api,
            name=f"{SCRIPT_PREFIX} User RAG {suffix}",
            description="User-selected RAG for real acceptance run.",
        )
        upload_rag_document(
            expert_api,
            rag_space_id=str(expert_rag["id"]),
            file_name=f"accept-user-{suffix}.txt",
            content=USER_DOC_TEXT,
        )
        log(f"Created user RAG: {expert_rag['id']}")

        system_rag = create_rag_space(
            admin_api,
            name=f"{SCRIPT_PREFIX} System RAG {suffix}",
            description="System standard RAG for real acceptance run.",
        )
        upload_rag_document(
            admin_api,
            rag_space_id=str(system_rag["id"]),
            file_name=f"accept-system-{suffix}.txt",
            content=SYSTEM_DOC_TEXT,
        )
        log(f"Created system RAG: {system_rag['id']}")

        binding = create_inspection_standard_binding(
            admin_api,
            name=f"{SCRIPT_PREFIX} Binding {suffix}",
            rag_space_id=str(system_rag["id"]),
        )
        log(f"Created inspection standard binding: {binding['id']}")

        spec_code = f"SCREW-ACCEPT-{suffix}"
        spec = create_test_spec(
            admin_api,
            spec_code=spec_code,
            name=f"{SCRIPT_PREFIX} Gate {suffix}",
        )
        spec = wait_until_spec_visible(admin_api, spec_code=spec_code)
        log(f"Created inspection spec: {spec['id']} spec_code={spec_code}")

        image_url = upload_task_image(expert_api, image_path)
        log(f"Uploaded task image: {image_url}")

        task = create_task(
            expert_api,
            spec_code=spec_code,
            image_url=image_url,
            user_rag_space=expert_rag,
        )
        log(f"Created task: {task['id']}")

        run_payload = run_task(expert_api, task_id=str(task["id"]))
        log(f"Triggered task execution: {json.dumps(run_payload, ensure_ascii=False)}")

        final_task, result, events = poll_task_and_result(expert_api, task_id=str(task["id"]))
        log(f"Task finished with status={final_task.get('status')} result_id={result.get('id')}")
        log(f"Collected {len(events)} task events.")

        validate_result(
            task=final_task,
            result=result,
            binding_name=str(binding["name"]),
            user_rag_space_id=str(expert_rag["id"]),
            system_rag_space_id=str(system_rag["id"]),
        )

        summary = {
            "task_id": final_task.get("id"),
            "task_status": final_task.get("status"),
            "result_id": result.get("id"),
            "verdict": result.get("verdict"),
            "user_rag_space_id": expert_rag.get("id"),
            "system_rag_space_id": system_rag.get("id"),
            "inspection_standard_binding_id": binding.get("id"),
            "inspection_spec_id": spec.get("id"),
            "inspection_spec_code": spec_code,
            "rag_summary": (result.get("reasoning_chain") or {}).get("rag_summary"),
            "ai_gate": ((result.get("reasoning_chain") or {}).get("standard_evaluation") or {}).get("ai_gate"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        admin_api.close()
        expert_api.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        log(f"[ERROR] {exc}")
        raise SystemExit(1)
