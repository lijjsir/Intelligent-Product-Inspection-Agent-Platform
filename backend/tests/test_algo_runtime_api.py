from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import app.api.v1.algo_runtime as runtime_mod
from app.core.exceptions import NotFoundError, ValidationError
from main import create_app


@dataclass
class FakeCurrentUser:
    user_id: str = "user-1"
    org_id: str = "org-1"
    role: str = "agent_operator"


@dataclass
class FakeDeployment:
    id: str
    status: str
    result_summary: dict


class FakeWorkspaceService:
    def __init__(self, deployment: FakeDeployment | None):
        self._deployment = deployment

    async def _require_generic_resource(self, *, resource_type: str, resource_id: str):
        assert resource_type == "deployment"
        if self._deployment is None or self._deployment.id != resource_id:
            raise NotFoundError("deployment not found")
        return self._deployment


def _build_client(monkeypatch, deployment: FakeDeployment | None) -> TestClient:
    app = create_app()
    app.dependency_overrides[runtime_mod.get_current_user] = lambda: FakeCurrentUser()
    async def _fake_db():
        yield None
    app.dependency_overrides[runtime_mod.get_db] = _fake_db
    monkeypatch.setattr(runtime_mod, "_svc", lambda current, db: FakeWorkspaceService(deployment))
    return TestClient(app)


def test_infer_with_completed_available_deployment(monkeypatch):
    client = _build_client(
        monkeypatch,
        FakeDeployment(
            id="dp-1",
            status="completed",
            result_summary={
                "runtime_registration": {
                    "endpoint": "http://localhost/api/v1/runtime/algo-deployments/dp-1/infer",
                    "status": "available",
                    "model_key": "demo-model",
                }
            },
        ),
    )

    response = client.post("/api/v1/runtime/algo-deployments/dp-1/infer", json={"request": {"input": "ok"}})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["deployment_id"] == "dp-1"
    assert payload["deployment_status"] == "completed"
    assert payload["runtime_status"] == "available"
    assert payload["prediction"] == {"input": "ok"}


def test_infer_rejects_non_completed_deployment(monkeypatch):
    client = _build_client(
        monkeypatch,
        FakeDeployment(id="dp-2", status="queued", result_summary={"runtime_registration": {"status": "available"}}),
    )

    response = client.post("/api/v1/runtime/algo-deployments/dp-2/infer", json={"request": {}})

    assert response.status_code == 422
    assert "deployment must be completed" in response.text


def test_infer_rejects_missing_runtime_registration(monkeypatch):
    client = _build_client(monkeypatch, FakeDeployment(id="dp-3", status="completed", result_summary={}))

    response = client.post("/api/v1/runtime/algo-deployments/dp-3/infer", json={"request": {}})

    assert response.status_code == 422
    assert "runtime_registration" in response.text


def test_infer_rejects_unavailable_runtime(monkeypatch):
    client = _build_client(
        monkeypatch,
        FakeDeployment(id="dp-4", status="completed", result_summary={"runtime_registration": {"status": "registered"}}),
    )

    response = client.post("/api/v1/runtime/algo-deployments/dp-4/infer", json={"request": {}})

    assert response.status_code == 422
    assert "runtime is not available" in response.text


def test_infer_returns_404_for_missing_deployment(monkeypatch):
    client = _build_client(monkeypatch, None)

    response = client.post("/api/v1/runtime/algo-deployments/missing/infer", json={"request": {}})

    assert response.status_code == 404
