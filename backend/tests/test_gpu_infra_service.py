from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.services import gpu_infra_service as gpu_mod


@dataclass
class FakeNode:
    id: str
    org_id: str
    created_by: str | None
    name: str
    host: str
    ssh_port: int
    ssh_username: str
    ssh_password_enc: str | None
    ssh_private_key_enc: str | None
    total_gpu_count: int
    available_gpu_count: int
    gpu_bitmap: str
    cpu_usage: float | None = None
    memory_usage: float | None = None
    gpu_usage: float | None = None
    status: str = "offline"
    last_heartbeat: datetime | None = None
    load_score: float | None = None
    metadata_json: dict | None = None
    deleted_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None


class FakeSession:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1


class FakeNodeRepo:
    def __init__(self, _session):
        self.rows: list[FakeNode] = []

    async def create(self, payload: dict):
        row = FakeNode(id=f"node-{len(self.rows)+1}", **payload)
        self.rows.append(row)
        return row

    async def get(self, *, org_id: str, node_id: str):
        return next((row for row in self.rows if row.org_id == org_id and row.id == node_id and row.deleted_at is None), None)

    async def get_by_name_or_host(self, *, org_id: str, name: str, host: str):
        return next((row for row in self.rows if row.org_id == org_id and row.deleted_at is None and (row.name == name or row.host == host)), None)

    async def list(self, *, org_id: str):
        return [row for row in self.rows if row.org_id == org_id and row.deleted_at is None]

    async def list_online(self, *, org_id: str):
        return [row for row in self.rows if row.org_id == org_id and row.deleted_at is None and row.status == "online"]

    async def save(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def soft_delete(self, obj):
        obj.deleted_at = datetime(2026, 5, 23, 12, 0, 0)


class FakeLeaseRepo:
    def __init__(self, _session):
        self.rows = []

    async def create(self, payload: dict):
        self.rows.append(payload)
        return type("Lease", (), {"id": f"lease-{len(self.rows)}", **payload})

    async def list_active_for_resource(self, *, org_id: str, resource_type: str, resource_id: str):
        return []

    async def save(self, obj, payload: dict):
        return obj


class FakeSshService:
    def __init__(self):
        self.connection_ok = True
        self.connection_message = "SSH connection established"
        self.json_payload = {
            "cpu_usage": 12.3,
            "memory_usage": 45.6,
            "gpu_usage": 78.9,
            "hardware_summary": {"hostname": "gpu-1", "driver_version": "550.54"},
            "gpu_devices": [{"index": 0, "name": "RTX 4090", "memory_total_mb": 24564, "memory_used_mb": 1234, "utilization_gpu": 78.9}],
        }

    def test_connection(self, **kwargs):
        return self.connection_ok, self.connection_message

    def execute_json(self, **kwargs):
        if not self.connection_ok:
            raise ValidationError(self.connection_message)
        return self.json_payload

    def execute(self, **kwargs):
        return {"stdout": "", "stderr": "", "exit_code": 0}

    def read_tail(self, **kwargs):
        return ""

    def exists(self, **kwargs):
        return False


@pytest.fixture
def service(monkeypatch):
    session = FakeSession()
    node_repo = FakeNodeRepo(None)
    lease_repo = FakeLeaseRepo(None)
    ssh = FakeSshService()

    monkeypatch.setattr(gpu_mod, "GpuComputeNodeRepository", lambda session: node_repo)
    monkeypatch.setattr(gpu_mod, "GpuJobLeaseRepository", lambda session: lease_repo)
    monkeypatch.setattr(gpu_mod, "SshExecutionService", lambda: ssh)

    svc = gpu_mod.GpuNodeService(session, "org-1", "user-1")
    return svc, node_repo, ssh, session


@pytest.mark.asyncio
async def test_create_node_requires_successful_ssh_validation(service):
    svc, node_repo, ssh, session = service

    ssh.connection_ok = False
    ssh.connection_message = "auth failed"

    with pytest.raises(ValidationError, match="ssh validation failed"):
        await svc.create_node(
            gpu_mod.GpuComputeNodeCreateRequest(
                name="gpu-1",
                host="10.0.0.10",
                ssh_username="root",
                ssh_password="secret",
                total_gpu_count=2,
            )
        )

    assert not node_repo.rows
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_probe_node_updates_metrics_and_probe_snapshot(service):
    svc, _node_repo, _ssh, session = service
    created = await svc.create_node(
        gpu_mod.GpuComputeNodeCreateRequest(
            name="gpu-1",
            host="10.0.0.10",
            ssh_username="root",
            ssh_password="secret",
            total_gpu_count=2,
        )
    )

    refreshed, metrics = await svc.refresh_metrics(created.id)

    assert refreshed.status == "online"
    assert refreshed.probe_status == "ok"
    assert refreshed.hardware_summary is not None
    assert len(refreshed.gpu_devices) == 1
    assert metrics["gpu_usage"] == 78.9
    row = await svc._nodes.get(org_id="org-1", node_id=created.id)
    assert row is not None
    assert isinstance((row.metadata_json or {}).get("probe", {}).get("last_probe_at"), str)
    assert session.commit_count >= 2


@pytest.mark.asyncio
async def test_create_node_persists_json_safe_probe_metadata(service):
    svc, _node_repo, _ssh, _session = service

    created = await svc.create_node(
        gpu_mod.GpuComputeNodeCreateRequest(
            name="gpu-safe",
            host="10.0.0.20",
            ssh_username="root",
            ssh_password="secret",
            total_gpu_count=1,
        )
    )

    row = await svc._nodes.get(org_id="org-1", node_id=created.id)
    assert row is not None
    assert isinstance((row.metadata_json or {}).get("probe", {}).get("last_probe_at"), str)


@pytest.mark.asyncio
async def test_poll_nodes_skips_disabled_and_marks_offline_on_ssh_failure(service):
    svc, _node_repo, ssh, _session = service
    first = await svc.create_node(
        gpu_mod.GpuComputeNodeCreateRequest(
            name="gpu-1",
            host="10.0.0.10",
            ssh_username="root",
            ssh_password="secret",
            total_gpu_count=1,
        )
    )
    second = await svc.create_node(
        gpu_mod.GpuComputeNodeCreateRequest(
            name="gpu-2",
            host="10.0.0.11",
            ssh_username="root",
            ssh_password="secret",
            total_gpu_count=1,
        )
    )
    second_row = await svc._nodes.get(org_id="org-1", node_id=second.id)
    assert second_row is not None
    second_row.status = "disabled"

    ssh.connection_ok = False
    ssh.connection_message = "network unreachable"
    counts = await svc.poll_nodes()

    first_row = await svc._nodes.get(org_id="org-1", node_id=first.id)
    assert first_row is not None
    assert first_row.status == "offline"
    assert counts["disabled"] == 1
    assert counts["offline"] == 1
