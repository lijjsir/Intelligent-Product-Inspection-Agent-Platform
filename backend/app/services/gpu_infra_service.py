from __future__ import annotations

import base64
import hashlib
import io
import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from string import Formatter
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.gpu_infra import GpuComputeNode
from app.repositories.gpu_infra_repo import GpuComputeNodeRepository, GpuJobLeaseRepository
from app.schemas.gpu_infra import (
    GpuComputeNodeCreateRequest,
    GpuComputeNodeResponse,
    GpuComputeNodeUpdateRequest,
    GpuNodeHeartbeatRequest,
)
from app.services.base import TenantAwareService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fernet() -> Fernet:
    seed = getattr(settings, "governance_secret", settings.jwt_private_key or settings.jwt_public_key or "piap-governance")
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


@dataclass(slots=True)
class GpuLeaseRecord:
    lease_ids: list[str]
    node_ids: list[str]
    gpu_indices_by_node: dict[str, list[int]]
    leased_at: str
    released_at: str | None = None


@dataclass(slots=True)
class RemoteExecutionRecord:
    host: str
    workdir: str
    command_preview: str
    remote_pid: str | None
    log_path: str
    status_path: str
    service_pid_path: str | None = None
    exit_code: int | None = None


class SshExecutionService:
    def __init__(self) -> None:
        self._connect_timeout = settings.gpu_ssh_connect_timeout_sec
        self._command_timeout = settings.gpu_ssh_command_timeout_sec

    @staticmethod
    def _paramiko():
        try:
            return import_module("paramiko")
        except ModuleNotFoundError as exc:
            raise ValidationError(
                "paramiko is not installed; install backend dependencies or disable gpu_ssh execution"
            ) from exc

    def _build_client(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None):
        paramiko = self._paramiko()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if private_key:
            key_stream = io.StringIO(private_key)
            key_errors: list[Exception] = []
            for key_loader in (
                paramiko.RSAKey.from_private_key,
                paramiko.Ed25519Key.from_private_key,
                paramiko.ECDSAKey.from_private_key,
            ):
                key_stream.seek(0)
                try:
                    pkey = key_loader(key_stream)
                    break
                except Exception as exc:  # pragma: no cover - loader compatibility
                    key_errors.append(exc)
            if pkey is None and key_errors:
                raise ValidationError(f"invalid ssh private key: {key_errors[-1]}")
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            pkey=pkey,
            timeout=self._connect_timeout,
            banner_timeout=self._connect_timeout,
            auth_timeout=self._connect_timeout,
        )
        return client

    def test_connection(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None) -> tuple[bool, str]:
        client = None
        try:
            client = self._build_client(host=host, port=port, username=username, password=password, private_key=private_key)
            return True, "SSH connection established"
        except Exception as exc:
            return False, str(exc)
        finally:
            if client is not None:
                client.close()

    def execute(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None, command: str, timeout: int | None = None) -> dict[str, Any]:
        client = self._build_client(host=host, port=port, username=username, password=password, private_key=private_key)
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout or self._command_timeout)
            _ = stdin
            exit_code = stdout.channel.recv_exit_status()
            return {
                "stdout": stdout.read().decode("utf-8", errors="ignore").strip(),
                "stderr": stderr.read().decode("utf-8", errors="ignore").strip(),
                "exit_code": exit_code,
            }
        finally:
            client.close()

    def execute_detached(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None, command: str) -> dict[str, Any]:
        wrapped = f"bash -lc {shlex.quote(command)}"
        return self.execute(host=host, port=port, username=username, password=password, private_key=private_key, command=wrapped)

    def execute_json(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None, command: str) -> dict[str, Any]:
        result = self.execute(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key=private_key,
            command=command,
        )
        if int(result.get("exit_code") or 0) != 0:
            raise ValidationError(result.get("stderr") or result.get("stdout") or "remote command failed")
        try:
            return json.loads(str(result.get("stdout") or "{}") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid remote json payload: {exc}") from exc

    def read_tail(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None, path: str, lines: int = 40) -> str:
        result = self.execute(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key=private_key,
            command=f"tail -n {int(lines)} {shlex.quote(path)}",
        )
        return str(result.get("stdout") or "")

    def exists(self, *, host: str, port: int, username: str, password: str | None, private_key: str | None, path: str) -> bool:
        result = self.execute(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key=private_key,
            command=f"test -f {shlex.quote(path)}",
        )
        return int(result.get("exit_code") or 1) == 0


class GpuSchedulingService:
    def __init__(self, node_repo: GpuComputeNodeRepository, lease_repo: GpuJobLeaseRepository):
        self._node_repo = node_repo
        self._lease_repo = lease_repo

    @staticmethod
    def _available_indices(node: GpuComputeNode) -> list[int]:
        bitmap = str(node.gpu_bitmap or "0" * max(int(node.total_gpu_count or 0), 1))
        return [index for index, value in enumerate(bitmap) if value == "0"]

    @staticmethod
    def _write_bitmap(bitmap: str, indices: list[int], value: str) -> str:
        chars = list(bitmap)
        for idx in indices:
            if idx < len(chars):
                chars[idx] = value
        return "".join(chars)

    @staticmethod
    def _compute_load_score(*, cpu_usage: float | None, memory_usage: float | None, total_gpu_count: int, available_gpu_count: int) -> float:
        cpu = max(0.0, min(100.0, float(cpu_usage or 0.0)))
        memory = max(0.0, min(100.0, float(memory_usage or 0.0)))
        gpu_pressure = 0.0
        if total_gpu_count > 0:
            gpu_pressure = (1 - (max(available_gpu_count, 0) / total_gpu_count)) * 100
        return round(cpu * 0.3 + memory * 0.3 + gpu_pressure * 0.4, 2)

    async def allocate(
        self,
        *,
        org_id: str,
        resource_type: str,
        resource_id: str,
        requested_gpu_count: int,
    ) -> GpuLeaseRecord:
        nodes = await self._node_repo.list_online(org_id=org_id)
        if not nodes:
            raise ValidationError("no online gpu nodes available")
        requested = max(int(requested_gpu_count or 0), 1)
        strategy = str(settings.gpu_scheduling_strategy or "load_balance").strip().lower()
        ordered = list(nodes)
        if strategy == "pack":
            ordered.sort(key=lambda item: (-(item.available_gpu_count or 0), item.load_score or 0, item.name))
        else:
            ordered.sort(key=lambda item: (item.load_score or 0, -(item.available_gpu_count or 0), item.name))

        remaining = requested
        lease_ids: list[str] = []
        node_ids: list[str] = []
        gpu_indices_by_node: dict[str, list[int]] = {}
        leased_at = _utcnow()
        for node in ordered:
            if remaining <= 0:
                break
            available = self._available_indices(node)
            if not available:
                continue
            take = min(len(available), remaining)
            selected = available[:take]
            bitmap = str(node.gpu_bitmap or "0" * max(int(node.total_gpu_count or 0), 1))
            await self._node_repo.save(
                node,
                {
                    "gpu_bitmap": self._write_bitmap(bitmap, selected, "1"),
                    "available_gpu_count": max(int(node.available_gpu_count or 0) - take, 0),
                    "load_score": self._compute_load_score(
                        cpu_usage=node.cpu_usage,
                        memory_usage=node.memory_usage,
                        total_gpu_count=int(node.total_gpu_count or 0),
                        available_gpu_count=max(int(node.available_gpu_count or 0) - take, 0),
                    ),
                },
            )
            lease = await self._lease_repo.create(
                {
                    "org_id": org_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "node_id": node.id,
                    "gpu_indices": selected,
                    "status": "leased",
                    "leased_at": leased_at,
                    "released_at": None,
                }
            )
            lease_ids.append(lease.id)
            node_ids.append(node.id)
            gpu_indices_by_node[node.id] = selected
            remaining -= take

        if remaining > 0:
            await self.release(org_id=org_id, resource_type=resource_type, resource_id=resource_id)
            raise ValidationError(f"gpu resource insufficient, requested={requested}, allocated={requested - remaining}")

        return GpuLeaseRecord(
            lease_ids=lease_ids,
            node_ids=node_ids,
            gpu_indices_by_node=gpu_indices_by_node,
            leased_at=leased_at.isoformat(),
        )

    async def release(self, *, org_id: str, resource_type: str, resource_id: str) -> None:
        leases = await self._lease_repo.list_active_for_resource(org_id=org_id, resource_type=resource_type, resource_id=resource_id)
        released_at = _utcnow()
        for lease in leases:
            node = await self._node_repo.get(org_id=org_id, node_id=lease.node_id)
            if node is not None:
                bitmap = str(node.gpu_bitmap or "0" * max(int(node.total_gpu_count or 0), 1))
                indices = [int(item) for item in list(lease.gpu_indices or [])]
                available_count = min(int(node.total_gpu_count or 0), int(node.available_gpu_count or 0) + len(indices))
                await self._node_repo.save(
                    node,
                    {
                        "gpu_bitmap": self._write_bitmap(bitmap, indices, "0"),
                        "available_gpu_count": available_count,
                        "load_score": self._compute_load_score(
                            cpu_usage=node.cpu_usage,
                            memory_usage=node.memory_usage,
                            total_gpu_count=int(node.total_gpu_count or 0),
                            available_gpu_count=available_count,
                        ),
                    },
                )
            await self._lease_repo.save(lease, {"status": "released", "released_at": released_at})


class GpuNodeService(TenantAwareService):
    def __init__(self, session, org_id: str, user_id: str):
        super().__init__(session, org_id)
        self._user_id = user_id
        self._nodes = GpuComputeNodeRepository(session)
        self._leases = GpuJobLeaseRepository(session)
        self._ssh = SshExecutionService()
        self._scheduling = GpuSchedulingService(self._nodes, self._leases)

    @staticmethod
    def encrypt_secret(value: str | None) -> str | None:
        if not value:
            return None
        return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decrypt_secret(value: str | None) -> str | None:
        if not value:
            return None
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _build_bitmap(total_gpu_count: int) -> str:
        count = max(int(total_gpu_count or 1), 1)
        return "0" * count

    @staticmethod
    def _status_from_timestamp(last_heartbeat: datetime | None, current_status: str) -> str:
        if current_status == "disabled":
            return "disabled"
        if last_heartbeat is None:
            return current_status or "offline"
        elapsed = (_utcnow() - last_heartbeat).total_seconds()
        if elapsed > settings.gpu_heartbeat_timeout_sec:
            return "offline"
        return current_status or "online"

    @staticmethod
    def _probe_metadata(metadata_json: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(metadata_json, dict):
            return {}
        value = metadata_json.get("probe")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _merge_probe_metadata(metadata_json: dict[str, Any] | None, probe: dict[str, Any]) -> dict[str, Any]:
        merged = dict(metadata_json or {})
        merged["probe"] = _json_safe(probe)
        return merged

    def _serialize_node(self, node: GpuComputeNode) -> GpuComputeNodeResponse:
        data = GpuComputeNodeResponse.model_validate(node).model_dump()
        data["status"] = self._status_from_timestamp(node.last_heartbeat, str(node.status or "offline"))
        data["has_ssh_password"] = bool(getattr(node, "ssh_password_enc", None))
        data["has_ssh_private_key"] = bool(getattr(node, "ssh_private_key_enc", None))
        probe = self._probe_metadata(getattr(node, "metadata_json", None))
        data["last_probe_at"] = probe.get("last_probe_at")
        data["last_probe_error"] = probe.get("last_probe_error")
        data["probe_status"] = probe.get("probe_status")
        data["hardware_summary"] = probe.get("hardware_summary")
        data["gpu_devices"] = list(probe.get("gpu_devices") or [])
        return GpuComputeNodeResponse(**data)

    async def list_nodes(self) -> list[GpuComputeNodeResponse]:
        rows = await self._nodes.list(org_id=self._org_id)
        return [self._serialize_node(row) for row in rows]

    async def get_node(self, node_id: str) -> GpuComputeNodeResponse:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        return self._serialize_node(row)

    async def create_node(self, payload: GpuComputeNodeCreateRequest) -> GpuComputeNodeResponse:
        existing = await self._nodes.get_by_name_or_host(org_id=self._org_id, name=payload.name, host=payload.host)
        if existing is not None:
            raise ValidationError("gpu node name or host already exists")
        if not payload.ssh_password and not payload.ssh_private_key:
            raise ValidationError("ssh_password or ssh_private_key is required")
        success, message = self._ssh.test_connection(
            host=payload.host,
            port=payload.ssh_port,
            username=payload.ssh_username,
            password=payload.ssh_password,
            private_key=payload.ssh_private_key,
        )
        if not success:
            raise ValidationError(f"ssh validation failed: {message}")
        bitmap = self._build_bitmap(payload.total_gpu_count)
        created = await self._nodes.create(
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name,
                "host": payload.host,
                "ssh_port": payload.ssh_port,
                "ssh_username": payload.ssh_username,
                "ssh_password_enc": self.encrypt_secret(payload.ssh_password),
                "ssh_private_key_enc": self.encrypt_secret(payload.ssh_private_key),
                "total_gpu_count": payload.total_gpu_count,
                "available_gpu_count": payload.total_gpu_count,
                "gpu_bitmap": bitmap,
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "gpu_usage": 0.0,
                "status": "offline",
                "last_heartbeat": None,
                "load_score": 0.0,
                "metadata_json": self._merge_probe_metadata(
                    payload.metadata_json or {},
                    {
                        "probe_status": "validated",
                        "last_probe_at": _utcnow(),
                        "last_probe_error": None,
                        "hardware_summary": None,
                        "gpu_devices": [],
                    },
                ),
            }
        )
        await self._session.commit()
        return self._serialize_node(created)

    async def update_node(self, node_id: str, payload: GpuComputeNodeUpdateRequest) -> GpuComputeNodeResponse:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        updates = payload.model_dump(exclude_unset=True)
        if "total_gpu_count" in updates and updates["total_gpu_count"] is not None:
            total_gpu_count = int(updates["total_gpu_count"])
            if "1" in str(row.gpu_bitmap or "") and total_gpu_count < int(row.total_gpu_count or 0):
                raise ValidationError("cannot shrink total_gpu_count while gpu leases are active")
            updates["gpu_bitmap"] = self._build_bitmap(total_gpu_count)
            updates["available_gpu_count"] = total_gpu_count
        if "ssh_password" in updates:
            updates["ssh_password_enc"] = self.encrypt_secret(updates.pop("ssh_password"))
        if "ssh_private_key" in updates:
            updates["ssh_private_key_enc"] = self.encrypt_secret(updates.pop("ssh_private_key"))
        await self._nodes.save(row, updates)
        await self._session.commit()
        return self._serialize_node(row)

    async def delete_node(self, node_id: str) -> None:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        if "1" in str(row.gpu_bitmap or ""):
            raise ValidationError("cannot delete gpu node with active leases")
        await self._nodes.soft_delete(row)
        await self._session.commit()

    async def set_node_enabled(self, node_id: str, *, enabled: bool) -> GpuComputeNodeResponse:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        status = "offline" if enabled else "disabled"
        await self._nodes.save(row, {"status": status})
        await self._session.commit()
        return self._serialize_node(row)

    async def test_connection(self, node_id: str) -> tuple[bool, str]:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        return self._ssh.test_connection(
            host=row.host,
            port=row.ssh_port,
            username=row.ssh_username,
            password=self.decrypt_secret(row.ssh_password_enc),
            private_key=self.decrypt_secret(row.ssh_private_key_enc),
        )

    async def heartbeat(self, node_id: str, payload: GpuNodeHeartbeatRequest) -> GpuComputeNodeResponse:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        gpu_bitmap = payload.gpu_bitmap or row.gpu_bitmap or self._build_bitmap(row.total_gpu_count)
        available_gpu_count = gpu_bitmap.count("0")
        await self._nodes.save(
            row,
            {
                "cpu_usage": payload.cpu_usage if payload.cpu_usage is not None else row.cpu_usage,
                "memory_usage": payload.memory_usage if payload.memory_usage is not None else row.memory_usage,
                "gpu_usage": payload.gpu_usage if payload.gpu_usage is not None else row.gpu_usage,
                "gpu_bitmap": gpu_bitmap,
                "available_gpu_count": available_gpu_count,
                "last_heartbeat": _utcnow(),
                "status": "online",
                "load_score": GpuSchedulingService._compute_load_score(
                    cpu_usage=payload.cpu_usage if payload.cpu_usage is not None else row.cpu_usage,
                    memory_usage=payload.memory_usage if payload.memory_usage is not None else row.memory_usage,
                    total_gpu_count=int(row.total_gpu_count or 0),
                    available_gpu_count=available_gpu_count,
                ),
            },
        )
        await self._session.commit()
        return self._serialize_node(row)

    async def refresh_metrics(self, node_id: str) -> tuple[GpuComputeNodeResponse, dict[str, Any]]:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        return await self.probe_node(node_id)

    def _probe_node(self, *, row: GpuComputeNode) -> dict[str, Any]:
        password = self.decrypt_secret(row.ssh_password_enc)
        private_key = self.decrypt_secret(row.ssh_private_key_enc)
        success, message = self._ssh.test_connection(
            host=row.host,
            port=row.ssh_port,
            username=row.ssh_username,
            password=password,
            private_key=private_key,
        )
        probe_time = _utcnow()
        if not success:
            return {
                "ok": False,
                "probe_time": probe_time,
                "status": "offline",
                "probe_status": "ssh_failed",
                "error": message,
            }
        probe_script = r"""python3 - <<'PY'
import json
import platform
import socket
import subprocess

def run(command: str) -> str:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or command)
    return proc.stdout.strip()

def run_optional(command: str, default: str = "") -> str:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        return default
    return proc.stdout.strip()

payload = {
    "cpu_usage": float(run("top -bn1 | awk '/Cpu\\(s\\)/ {print 100 - $8}'") or 0.0),
    "memory_usage": float(run("free | awk '/Mem:/ {printf(\"%.2f\", $3/$2*100)}'") or 0.0),
    "gpu_usage": 0.0,
    "hardware_summary": {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "driver_version": run_optional("nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1", ""),
        "cuda_version": run_optional("nvidia-smi | awk -F'CUDA Version: ' 'NF>1 {print $2}' | awk '{print $1}' | head -n 1", ""),
    },
    "gpu_devices": [],
}

gpu_lines = run_optional("nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits", "")
if gpu_lines:
    total = 0.0
    count = 0
    devices = []
    for line in gpu_lines.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        util = float(parts[4] or 0.0)
        total += util
        count += 1
        devices.append({
            "index": int(parts[0]),
            "name": parts[1],
            "memory_total_mb": float(parts[2] or 0.0),
            "memory_used_mb": float(parts[3] or 0.0),
            "utilization_gpu": util,
        })
    payload["gpu_devices"] = devices
    payload["gpu_usage"] = round(total / count, 2) if count else 0.0

print(json.dumps(payload, ensure_ascii=False))
PY"""
        try:
            payload = self._ssh.execute_json(
                host=row.host,
                port=row.ssh_port,
                username=row.ssh_username,
                password=password,
                private_key=private_key,
                command=probe_script,
            )
        except ValidationError as exc:
            return {
                "ok": False,
                "probe_time": probe_time,
                "status": "error",
                "probe_status": "probe_failed",
                "error": str(exc),
            }
        return {
            "ok": True,
            "probe_time": probe_time,
            "status": "online",
            "probe_status": "ok",
            "error": None,
            "payload": payload,
        }

    async def probe_node(self, node_id: str) -> tuple[GpuComputeNodeResponse, dict[str, Any]]:
        row = await self._nodes.get(org_id=self._org_id, node_id=node_id)
        if row is None:
            raise NotFoundError("gpu node not found")
        result = self._probe_node(row=row)
        probe_meta = {
            "last_probe_at": result["probe_time"],
            "last_probe_error": result.get("error"),
            "probe_status": result.get("probe_status"),
            "hardware_summary": (result.get("payload") or {}).get("hardware_summary"),
            "gpu_devices": list((result.get("payload") or {}).get("gpu_devices") or []),
        }
        update_payload: dict[str, Any] = {
            "status": result["status"],
            "metadata_json": self._merge_probe_metadata(row.metadata_json, probe_meta),
        }
        if result.get("ok"):
            payload = result.get("payload") or {}
            gpu_bitmap = row.gpu_bitmap or self._build_bitmap(row.total_gpu_count)
            available_gpu_count = gpu_bitmap.count("0")
            update_payload.update(
                {
                    "cpu_usage": round(float(payload.get("cpu_usage") or 0.0), 2),
                    "memory_usage": round(float(payload.get("memory_usage") or 0.0), 2),
                    "gpu_usage": round(float(payload.get("gpu_usage") or 0.0), 2),
                    "last_heartbeat": result["probe_time"],
                    "load_score": GpuSchedulingService._compute_load_score(
                        cpu_usage=float(payload.get("cpu_usage") or 0.0),
                        memory_usage=float(payload.get("memory_usage") or 0.0),
                        total_gpu_count=int(row.total_gpu_count or 0),
                        available_gpu_count=available_gpu_count,
                    ),
                }
            )
        await self._nodes.save(row, update_payload)
        await self._session.commit()
        return self._serialize_node(row), {
            "probe_status": result.get("probe_status"),
            "error": result.get("error"),
            **((result.get("payload") or {}) if result.get("ok") else {}),
        }

    async def poll_nodes(self) -> dict[str, int]:
        rows = await self._nodes.list(org_id=self._org_id)
        counts = {"online": 0, "offline": 0, "error": 0, "disabled": 0}
        for row in rows:
            if str(row.status or "").lower() == "disabled":
                counts["disabled"] += 1
                continue
            serialized, _ = await self.probe_node(row.id)
            key = str(serialized.status or "offline")
            counts[key] = counts.get(key, 0) + 1
        return counts

    async def poll_all_nodes(self) -> dict[str, int]:
        rows = await self._nodes.list_all()
        counts = {"online": 0, "offline": 0, "error": 0, "disabled": 0}
        for row in rows:
            if str(row.status or "").lower() == "disabled":
                counts["disabled"] += 1
                continue
            scoped = GpuNodeService(self._session, str(row.org_id), self._user_id or str(row.created_by or "system"))
            serialized, _ = await scoped.probe_node(row.id)
            key = str(serialized.status or "offline")
            counts[key] = counts.get(key, 0) + 1
        return counts

    async def allocate_leases(self, *, resource_type: str, resource_id: str, requested_gpu_count: int) -> GpuLeaseRecord:
        record = await self._scheduling.allocate(
            org_id=self._org_id,
            resource_type=resource_type,
            resource_id=resource_id,
            requested_gpu_count=requested_gpu_count,
        )
        await self._session.commit()
        return record

    async def release_leases(self, *, resource_type: str, resource_id: str) -> None:
        await self._scheduling.release(org_id=self._org_id, resource_type=resource_type, resource_id=resource_id)
        await self._session.commit()


class GpuJobRunner:
    def __init__(self, service: GpuNodeService):
        self._service = service
        self._ssh = service._ssh

    @staticmethod
    def _safe_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _status_payload(*, resource_id: str, status: str, started_at: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "resource_id": resource_id,
            "status": status,
            "started_at": started_at,
            "completed_at": None,
            "exit_code": None,
            "error": None,
            "metrics": {},
            "artifacts": [],
            "metadata": {},
            "updated_at": _utcnow().isoformat(),
        }
        return payload

    @staticmethod
    def _render_command(template: str, context: dict[str, Any]) -> str:
        fields = {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}
        missing = sorted(field for field in fields if field not in context)
        if missing:
            raise ValidationError(f"gpu command template missing fields: {', '.join(missing)}")
        return template.format(**context)

    async def launch_remote_job(
        self,
        *,
        resource_type: str,
        resource_id: str,
        requested_gpu_count: int,
        node_command_template: str,
        runtime_env: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> tuple[GpuLeaseRecord, RemoteExecutionRecord]:
        lease = await self._service.allocate_leases(resource_type=resource_type, resource_id=resource_id, requested_gpu_count=requested_gpu_count)
        first_node_id = lease.node_ids[0]
        node = await self._service._nodes.get(org_id=self._service._org_id, node_id=first_node_id)
        if node is None:
            await self._service.release_leases(resource_type=resource_type, resource_id=resource_id)
            raise ValidationError("allocated gpu node not found")
        gpu_indices = lease.gpu_indices_by_node.get(first_node_id) or []
        base_workdir = str((runtime_env or {}).get("workdir") or f"/tmp/piap-gpu-jobs/{resource_type}/{resource_id}")
        artifact_root = str((runtime_env or {}).get("artifact_root") or f"{base_workdir}/artifacts")
        log_path = f"{base_workdir}/job.log"
        status_path = f"{base_workdir}/status.json"
        service_pid_path = f"{base_workdir}/service.pid" if resource_type == "deployment" else None
        env_exports = []
        for key, value in dict((runtime_env or {}).get("env") or {}).items():
            env_exports.append(f"export {key}={shlex.quote(str(value))}")
        env_exports.append(f"export CUDA_VISIBLE_DEVICES={','.join(str(idx) for idx in gpu_indices)}")
        env_exports.append(f"export PIAP_RESOURCE_TYPE={shlex.quote(resource_type)}")
        env_exports.append(f"export PIAP_RESOURCE_ID={shlex.quote(resource_id)}")
        env_exports.append(f"export PIAP_STATUS_PATH={shlex.quote(status_path)}")
        env_exports.append(f"export PIAP_LOG_PATH={shlex.quote(log_path)}")
        env_exports.append(f"export PIAP_ARTIFACT_ROOT={shlex.quote(artifact_root)}")
        if service_pid_path:
            env_exports.append(f"export PIAP_SERVICE_PID_PATH={shlex.quote(service_pid_path)}")
        render_context = {
            **context,
            "artifact_output_dir": artifact_root,
            "gpu_indices": ",".join(str(idx) for idx in gpu_indices),
            "node_host": node.host,
            "config_json": self._safe_json(context.get("config_json") or {}),
            "status_path": status_path,
            "log_path": log_path,
            "service_pid_path": service_pid_path or "",
        }
        rendered = self._render_command(node_command_template, render_context)
        started_at = _utcnow().isoformat()
        status_bootstrap = (
            f"mkdir -p {shlex.quote(base_workdir)} {shlex.quote(artifact_root)} && "
            f": > {shlex.quote(log_path)} && "
            + (
                f"rm -f {shlex.quote(service_pid_path)} && " if service_pid_path else ""
            )
            + f"cat > {shlex.quote(status_path)} <<'JSON'\n"
            + json.dumps(self._status_payload(resource_id=resource_id, status="running", started_at=started_at), ensure_ascii=False)
            + "\nJSON\n"
        )
        final_status_command = (
            "exit_code=$?; "
            f"python3 - <<'PY'\n"
            "import json, os\n"
            f"path = {status_path!r}\n"
            "try:\n"
            "    with open(path, 'r', encoding='utf-8') as fh:\n"
            "        payload = json.load(fh)\n"
            "except Exception:\n"
            "    payload = {}\n"
            "exit_code = int(os.environ.get('PIAP_EXIT_CODE', '0') or 0)\n"
            "payload.setdefault('resource_id', os.environ.get('PIAP_RESOURCE_ID'))\n"
            "payload.setdefault('started_at', payload.get('started_at'))\n"
            "payload['completed_at'] = payload.get('completed_at') or __import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None).isoformat()\n"
            "payload['updated_at'] = payload['completed_at']\n"
            "payload['exit_code'] = exit_code\n"
            "status = str(payload.get('status') or '').strip().lower()\n"
            "if status == 'running':\n"
            "    payload['status'] = 'succeeded' if exit_code == 0 else 'failed'\n"
            "if exit_code != 0 and not payload.get('error'):\n"
            "    payload['error'] = 'remote command failed'\n"
            "with open(path, 'w', encoding='utf-8') as fh:\n"
            "    json.dump(payload, fh, ensure_ascii=False)\n"
            "PY\n"
        )
        final_command = (
            "set +e; "
            + " && ".join(env_exports)
            + " && "
            + status_bootstrap
            + f"bash -lc {shlex.quote(rendered)} >> {shlex.quote(log_path)} 2>&1; "
            + "PIAP_EXIT_CODE=$?; export PIAP_EXIT_CODE; "
            + final_status_command
            + "exit ${PIAP_EXIT_CODE}"
        )
        password = self._service.decrypt_secret(node.ssh_password_enc)
        private_key = self._service.decrypt_secret(node.ssh_private_key_enc)
        remote_pid = None
        if settings.gpu_enable_real_execution:
            result = self._ssh.execute_detached(
                host=node.host,
                port=node.ssh_port,
                username=node.ssh_username,
                password=password,
                private_key=private_key,
                command=f"nohup bash -lc {shlex.quote(final_command)} >/dev/null 2>&1 & echo $!",
            )
            if int(result.get("exit_code") or 0) != 0:
                await self._service.release_leases(resource_type=resource_type, resource_id=resource_id)
                raise ValidationError(result.get("stderr") or result.get("stdout") or "failed to launch remote job")
            remote_pid = str(result.get("stdout") or "").strip() or None
        else:
            remote_pid = "simulated"
        return lease, RemoteExecutionRecord(
            host=node.host,
            workdir=base_workdir,
            command_preview=rendered,
            remote_pid=remote_pid,
            log_path=log_path,
            status_path=status_path,
            service_pid_path=service_pid_path,
            exit_code=None,
        )

    async def collect_remote_status(self, *, node: GpuComputeNode, remote: RemoteExecutionRecord) -> dict[str, Any]:
        if not settings.gpu_enable_real_execution:
            return {
                "status": "succeeded",
                "exit_code": 0,
                "log_tail": "simulated execution complete",
                "status_file_state": "ok",
                "poll_error": None,
            }
        password = self._service.decrypt_secret(node.ssh_password_enc)
        private_key = self._service.decrypt_secret(node.ssh_private_key_enc)
        status_result = self._ssh.execute(
            host=node.host,
            port=node.ssh_port,
            username=node.ssh_username,
            password=password,
            private_key=private_key,
            command=f"cat {shlex.quote(remote.status_path)}",
        )
        if int(status_result.get("exit_code") or 0) != 0:
            return {
                "status": "missing",
                "exit_code": status_result.get("exit_code"),
                "error": status_result.get("stderr") or "missing status file",
                "status_file_state": "missing",
                "poll_error": status_result.get("stderr") or "missing status file",
            }
        try:
            data = json.loads(str(status_result.get("stdout") or "{}") or "{}")
        except json.JSONDecodeError as exc:
            return {
                "status": "running",
                "exit_code": None,
                "error": f"invalid status file: {exc}",
                "status_file_state": "invalid_json",
                "poll_error": f"invalid status file: {exc}",
                "log_tail": "",
            }
        if self._ssh.exists(
            host=node.host,
            port=node.ssh_port,
            username=node.ssh_username,
            password=password,
            private_key=private_key,
            path=remote.log_path,
        ):
            data["log_tail"] = self._ssh.read_tail(
                host=node.host,
                port=node.ssh_port,
                username=node.ssh_username,
                password=password,
                private_key=private_key,
                path=remote.log_path,
            )
        else:
            data["log_tail"] = ""
        data["status_file_state"] = "ok"
        data["poll_error"] = data.get("error") if str(data.get("status") or "").strip().lower() not in {"running", "succeeded", "completed"} else None
        return data

    async def terminate_remote_job(self, *, node: GpuComputeNode, remote: RemoteExecutionRecord) -> None:
        password = self._service.decrypt_secret(node.ssh_password_enc)
        private_key = self._service.decrypt_secret(node.ssh_private_key_enc)
        kill_targets: list[str] = []
        if remote.service_pid_path:
            kill_targets.append(
                f"if [ -f {shlex.quote(remote.service_pid_path)} ]; then kill $(cat {shlex.quote(remote.service_pid_path)}) 2>/dev/null || true; fi"
            )
        if remote.remote_pid:
            kill_targets.append(f"kill {shlex.quote(str(remote.remote_pid))} 2>/dev/null || true")
        status_update = (
            f"python3 - <<'PY'\n"
            "import json\n"
            f"path = {remote.status_path!r}\n"
            "try:\n"
            "    with open(path, 'r', encoding='utf-8') as fh:\n"
            "        payload = json.load(fh)\n"
            "except Exception:\n"
            "    payload = {}\n"
            "payload['status'] = 'cancelled'\n"
            "payload['completed_at'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None).isoformat()\n"
            "payload['updated_at'] = payload['completed_at']\n"
            "payload['error'] = payload.get('error') or 'cancelled by user'\n"
            "with open(path, 'w', encoding='utf-8') as fh:\n"
            "    json.dump(payload, fh, ensure_ascii=False)\n"
            "PY"
        )
        self._ssh.execute(
            host=node.host,
            port=node.ssh_port,
            username=node.ssh_username,
            password=password,
            private_key=private_key,
            command="bash -lc " + shlex.quote(" && ".join([*kill_targets, status_update]) if kill_targets else status_update),
        )
