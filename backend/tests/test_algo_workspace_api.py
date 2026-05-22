from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

import app.api.v1.algo_workspace as workspace_mod
from app.core.exceptions import NotFoundError
from main import create_app


@dataclass
class FakeCurrentUser:
    user_id: str = "user-1"
    org_id: str = "org-1"
    role: str = "agent_operator"


class FakeStorage:
    pass


class FakeWorkspaceService:
    def __init__(self):
        self.payload_args = None

    async def get_export_artifact_download(self, *, dataset_id: str):
        if dataset_id != "ds-1":
            raise NotFoundError("export artifact not found")
        return {
            "bucket": "dataset-exports",
            "object_key": "dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
            "file_name": "annotations.coco.json",
            "storage_backend": "minio",
        }

    def get_export_artifact_payload(self, *, bucket: str, object_key: str, storage_backend: str | None = None):
        self.payload_args = {
            "bucket": bucket,
            "object_key": object_key,
            "storage_backend": storage_backend,
        }
        if bucket == "dataset-exports" and object_key == "dataset-exports/org-1/ds-1/export-1/annotations.coco.json":
            return (b'{"format":"coco"}', "application/json")
        return None


def _build_client(monkeypatch) -> TestClient:
    app = create_app()
    app.dependency_overrides[workspace_mod.get_current_user] = lambda: FakeCurrentUser()

    async def _fake_db():
        yield None

    app.dependency_overrides[workspace_mod.get_db] = _fake_db
    service = FakeWorkspaceService()
    monkeypatch.setattr(workspace_mod, "_svc", lambda current, db: service)
    return TestClient(app), service


def test_download_dataset_export_streams_attachment(monkeypatch):
    client, service = _build_client(monkeypatch)

    response = client.get("/api/v1/datasets/ds-1/exports/download")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="annotations.coco.json"'
    assert response.json() == {"format": "coco"}
    assert service.payload_args == {
        "bucket": "dataset-exports",
        "object_key": "dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
        "storage_backend": "minio",
    }


def test_download_dataset_export_returns_not_found_when_payload_missing(monkeypatch):
    client, service = _build_client(monkeypatch)

    service.get_export_artifact_payload = lambda **_: None
    response = client.get("/api/v1/datasets/ds-1/exports/download")

    assert response.status_code == 404
    assert response.json()["message"] == "export artifact payload not found"
