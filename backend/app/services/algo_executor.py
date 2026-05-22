from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.object_storage.base import ObjectStorage


@dataclass(slots=True)
class ExecutionArtifact:
    type: str
    name: str
    path: str
    download_url: str | None = None
    meta: dict[str, Any] | None = None


class LocalAlgoExecutor:
    def __init__(self, storage: ObjectStorage):
        self._storage = storage
        self._bucket = settings.model_artifact_bucket
        self._workdir = settings.algo_runner_workdir

    def run_job(
        self,
        *,
        resource_type: str,
        resource_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        job_workdir = os.path.join(self._workdir, resource_type, resource_id)
        os.makedirs(job_workdir, exist_ok=True)
        script = (
            "import json,os,sys,time;"
            "payload=json.loads(sys.stdin.read());"
            "workdir=os.environ.get('ALGO_RUNNER_WORKDIR') or os.getcwd();"
            "time.sleep(0.02);"
            "print(json.dumps({'resource_type': payload['resource_type'], 'resource_id': payload['resource_id'], 'status': 'ok', 'workdir': workdir}))"
        )
        proc = subprocess.run(
            ["python3", "-c", script],
            input=json.dumps({"resource_type": resource_type, "resource_id": resource_id, "payload": payload}).encode("utf-8"),
            capture_output=True,
            check=True,
            cwd=job_workdir,
            env={**os.environ, "ALGO_RUNNER_WORKDIR": job_workdir},
        )
        stdout = proc.stdout.decode("utf-8").strip()
        if stdout:
            return json.loads(stdout)
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": "ok",
            "workdir": job_workdir,
        }

    def upload_json_artifact(
        self,
        *,
        resource_type: str,
        resource_id: str,
        file_name: str,
        payload: dict[str, Any],
    ) -> ExecutionArtifact:
        self._storage.ensure_bucket(self._bucket)
        object_key = f"{resource_type}/{resource_id}/{file_name}"
        stored = self._storage.put_bytes(
            bucket=self._bucket,
            object_key=object_key,
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )
        return ExecutionArtifact(
            type="report",
            name=file_name,
            path=f"{stored.get('bucket')}:{stored.get('object_key')}",
            download_url=stored.get("url") or self._storage.presign_download_url(bucket=self._bucket, object_key=object_key),
            meta={"bucket": stored.get("bucket"), "object_key": stored.get("object_key"), "size_bytes": stored.get("size_bytes")},
        )
