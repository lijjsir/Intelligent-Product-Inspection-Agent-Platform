# RAG MinIO + Qdrant Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace local-file RAG storage/retrieval with real MinIO + Qdrant, add formal `deploy/` deployment assets, and verify the full system end to end.

**Architecture:** Keep the existing RAG tree model, add a true object-storage abstraction for MinIO, persist chunk/job metadata in MySQL, and route chat + quality retrieval through a shared Qdrant-backed retrieval service. Use the repo-root compose for local development and add a Windows-first formal deployment flow under `deploy/`.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Qdrant, MinIO/S3, Docker Compose, PowerShell, pytest, Vue.

---

### Task 1: Add Red Tests for Formal RAG Storage and Retrieval

**Files:**
- Modify: `backend/tests/test_rag_space_service.py`
- Modify: `backend/tests/test_chat_flow.py`
- Modify: `backend/tests/test_quality_judgement.py`
- Create: `backend/tests/test_rag_retrieval_service.py`
- Create: `backend/tests/test_object_storage_service.py`
- Create: `backend/tests/test_deploy_health_contract.py`

- [ ] **Step 1: Write the failing storage abstraction tests**

Add tests that expect an object storage abstraction with MinIO-shaped metadata:

```python
def test_object_storage_factory_uses_minio_backend(monkeypatch):
    monkeypatch.setenv("PIAP_OBJECT_STORAGE_BACKEND", "minio")
    service = build_object_storage()
    assert service.backend_name == "minio"


def test_minio_storage_returns_bucket_and_object_key():
    payload = fake_minio_storage().put_bytes(
        bucket="rag-docs",
        object_key="rag/org/space/doc.txt",
        data=b"hello",
        content_type="text/plain",
    )
    assert payload["bucket"] == "rag-docs"
    assert payload["object_key"] == "rag/org/space/doc.txt"
```

- [ ] **Step 2: Run storage tests to verify RED**

Run: `pytest backend/tests/test_object_storage_service.py -q`

Expected: failure because the object storage module and factory do not exist yet.

- [ ] **Step 3: Write the failing RAG upload and retrieval tests**

Add tests that require:

- `RagSpaceService` to store `bucket/object_key/storage_backend`
- `RagRetrievalService` to retrieve from persisted chunk metadata rather than local file reads
- quality judgement to consume the shared retrieval service instead of local overlap retrieval

```python
@pytest.mark.asyncio
async def test_upload_documents_persists_minio_metadata(monkeypatch):
    service, *_rest = build_service(monkeypatch)
    monkeypatch.setattr("app.services.rag_space_service.build_object_storage", lambda: fake_object_storage())
    rows = await service.upload_documents(rag_space_id="space-1", files=[FakeUpload("spec.txt")])
    assert rows[0].document.storage_backend == "minio"
    assert rows[0].document.object_key.startswith("rag/")


@pytest.mark.asyncio
async def test_rag_retrieval_service_returns_chunk_hits_without_file_reads(monkeypatch):
    service = build_retrieval_service(monkeypatch)
    result = await service.search(rag_space_id="space-1", query="scratch defect", top_k=3)
    assert result["hit_count"] == 1
    assert result["hits"][0]["chunk_index"] == 1
```

- [ ] **Step 4: Run targeted tests to verify RED**

Run:

```bash
pytest backend/tests/test_rag_space_service.py backend/tests/test_rag_retrieval_service.py backend/tests/test_quality_judgement.py -q
```

Expected: failures showing missing object storage, missing chunk repositories, and old retrieval contracts.

- [ ] **Step 5: Checkpoint**

Record the failing-test checkpoint in the worklog and keep the worktree uncommitted unless the user later asks for a commit.

### Task 2: Implement Phase 2 Object Storage and RAG File Persistence

**Files:**
- Create: `backend/app/services/object_storage/base.py`
- Create: `backend/app/services/object_storage/local.py`
- Create: `backend/app/services/object_storage/minio.py`
- Create: `backend/app/services/object_storage/factory.py`
- Modify: `backend/app/services/rag_space_service.py`
- Modify: `backend/app/models/rag_space.py`
- Modify: `backend/app/repositories/rag_space_repo.py`
- Modify: `backend/requirements.txt`
- Create: `backend/migrations/versions/0030_rag_object_storage_fields.py`

- [ ] **Step 1: Implement the minimal object storage interface**

Create a focused interface:

```python
class ObjectStorage(Protocol):
    backend_name: str

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None) -> dict[str, Any]: ...
    def get_bytes(self, *, bucket: str, object_key: str) -> tuple[bytes, str | None] | None: ...
    def delete_object(self, *, bucket: str, object_key: str) -> None: ...
    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str: ...
    def ensure_bucket(self, bucket: str) -> None: ...
```

- [ ] **Step 2: Add the MinIO implementation and dependency**

Add `minio>=7.2.0` to `backend/requirements.txt` and implement:

```python
class MinioObjectStorage:
    backend_name = "minio"
```

The implementation should build object URLs from configured endpoint and bucket/object key, and create buckets idempotently.

- [ ] **Step 3: Update RAG uploads to use object storage**

In `RagSpaceService.upload_documents`, replace `FileStorageService.save_bytes(...)` with object storage:

```python
stored = self._storage.put_bytes(
    bucket=self._bucket,
    object_key=object_key,
    data=content,
    content_type=upload.content_type,
)
```

Persist:

- `storage_backend`
- `bucket`
- `object_key`
- `file_url`

- [ ] **Step 4: Add and run the migration**

Run:

```bash
alembic upgrade head
```

Expected: new columns for object storage metadata are available without breaking existing tree data.

- [ ] **Step 5: Run focused tests to verify GREEN**

Run:

```bash
pytest backend/tests/test_object_storage_service.py backend/tests/test_rag_space_service.py -q
```

Expected: green, proving upload paths now persist object-storage metadata.

- [ ] **Step 6: Checkpoint**

Record the Phase 2 checkpoint and continue without creating a commit by default.

### Task 3: Implement Phase 3 Chunk Metadata and Unified Qdrant Retrieval

**Files:**
- Create: `backend/migrations/versions/0031_rag_chunks_and_index_jobs.py`
- Modify: `backend/app/models/rag_space.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/repositories/rag_space_repo.py`
- Modify: `backend/app/services/rag_space_service.py`
- Modify: `backend/app/services/rag_retrieval_service.py`
- Modify: `backend/agent/rag/knowledge_indexer.py`
- Modify: `backend/agent/rag/retriever.py`

- [ ] **Step 1: Add red tests for chunk/job persistence**

Add tests that require:

- chunk rows to be created after indexing
- Qdrant point payload to include `full_path`, `node_id`, and `ancestor_node_ids`
- `RagRetrievalService` to return chunk metadata fields

```python
assert hit["full_path"] == "机械/spec.txt"
assert hit["chunk_index"] == 1
assert hit["page_number"] is None
```

- [ ] **Step 2: Create the new tables and ORM models**

Add:

```python
class RagDocumentChunk(Base, TimestampMixin): ...
class RagIndexJob(Base, TimestampMixin): ...
```

Keep the schema focused on:

- document identity
- chunk order
- preview/content
- qdrant point id
- job status and errors

- [ ] **Step 3: Refactor indexing to persist chunks**

Update the indexing path so it:

1. reads bytes from object storage
2. parses text
3. chunks content
4. upserts one Qdrant point per chunk
5. saves rows to `rag_document_chunks`
6. updates `rag_documents.chunk_count/index_status`

- [ ] **Step 4: Replace local-file overlap retrieval**

Replace the current implementation in `RagRetrievalService` with a Qdrant-backed retrieval flow that reads citations from Qdrant payload and MySQL chunk metadata instead of re-parsing local files.

```python
return {
    "title": payload["file_name"],
    "source": payload["full_path"],
    "full_path": payload["full_path"],
    "chunk_index": payload["chunk_index"],
    "page_number": payload.get("page_number"),
    "quote": text[:220],
    "score": score,
}
```

- [ ] **Step 5: Run focused tests to verify GREEN**

Run:

```bash
pytest backend/tests/test_rag_retrieval_service.py backend/tests/test_rag_space_service.py -q
```

Expected: green, proving retrieval no longer depends on local-file overlap logic.

- [ ] **Step 6: Checkpoint**

Record the Phase 3 checkpoint and continue without creating a commit by default.

### Task 4: Implement Phase 4 Shared Retrieval for Chat and Quality

**Files:**
- Modify: `backend/agent/subgraphs/quality_chat/graph.py`
- Modify: `backend/agent/subgraphs/quality_judgement/graph.py`
- Modify: `backend/agent/graph/nodes/knowledge.py`
- Modify: `backend/tests/test_chat_flow.py`
- Modify: `backend/tests/test_quality_judgement.py`

- [ ] **Step 1: Add red integration tests for shared retrieval**

Add tests that assert:

- quality chat uses `rag_space_id` and optional `scope_node_ids`
- quality judgement uses the shared retrieval service
- citations include `full_path` and `chunk_index`

```python
assert citation["source"] == "机械/spec.txt"
assert citation["chunk_index"] == 1
```

- [ ] **Step 2: Route quality chat through the shared retrieval contract**

Preserve the existing `Retriever`-backed flow where appropriate, but normalize the returned hit shape so the rest of the pipeline sees one citation contract.

- [ ] **Step 3: Replace quality judgement local retrieval usage**

Remove `RagRetrievalService`'s old local-overlap semantics from the structured inspection path and use the unified service instead.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```bash
pytest backend/tests/test_chat_flow.py backend/tests/test_quality_judgement.py -q
```

Expected: green, proving chat and quality now consume the same retrieval semantics.

- [ ] **Step 5: Checkpoint**

Record the Phase 4 checkpoint and continue without creating a commit by default.

### Task 5: Add Formal `deploy/` Assets for Windows Deployment

**Files:**
- Create: `deploy/compose/docker-compose.deploy.yml`
- Create: `deploy/env/deploy.env.example`
- Create: `deploy/scripts/start.ps1`
- Create: `deploy/scripts/stop.ps1`
- Create: `deploy/scripts/init-minio.ps1`
- Create: `deploy/scripts/init-qdrant.ps1`
- Create: `deploy/scripts/health-check.ps1`
- Create: `deploy/scripts/verify-rag-e2e.ps1`
- Create: `deploy/docs/deployment.md`
- Create: `deploy/docs/operations.md`
- Create: `deploy/docs/backup-restore.md`
- Modify: `docker-compose.yml`
- Modify: `backend/app/api/...` or `backend/app/main.py` if a health endpoint must be extended

- [ ] **Step 1: Write the failing deployment contract test**

Create a test that asserts the backend health contract includes MinIO and Qdrant readiness fields:

```python
def test_rag_health_contract_includes_minio_and_qdrant():
    payload = build_health_payload(...)
    assert payload["services"]["minio"] == "ok"
    assert payload["services"]["qdrant"] == "ok"
```

- [ ] **Step 2: Add the formal compose stack**

Define services for:

- mysql
- redis
- minio
- qdrant
- backend
- frontend

Make persistence explicit for:

- MySQL
- MinIO
- Qdrant

- [ ] **Step 3: Add PowerShell orchestration and init scripts**

Implement scripts that:

- require an env file
- start infra first
- initialize bucket and collection idempotently
- start app services
- stop without deleting data by default

- [ ] **Step 4: Extend health checking**

Add or extend a backend health endpoint so `health-check.ps1` can validate:

- backend up
- MinIO reachable and bucket exists
- Qdrant reachable and collection exists
- embedding runtime is usable

- [ ] **Step 5: Run focused verification**

Run:

```bash
pytest backend/tests/test_deploy_health_contract.py -q
```

Expected: green, proving the deployment contract is visible to automation.

- [ ] **Step 6: Checkpoint**

Record the deployment-assets checkpoint and continue without creating a commit by default.

### Task 6: Run Migrations and Verify End to End

**Files:**
- Modify only if verification uncovers defects in any of the files above

- [ ] **Step 1: Run all backend tests**

Run:

```bash
pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend verification if any API contract changed**

Run:

```bash
cd frontend
npm run typecheck
npm test -- --run
npm run build
```

Expected: all commands succeed.

- [ ] **Step 3: Run migrations**

Run:

```bash
cd backend
alembic upgrade head
alembic current
```

Expected: current revision is the new head.

- [ ] **Step 4: Verify local development flow**

Run the repo-root compose path and confirm local services still start:

```bash
docker compose up -d minio qdrant mysql redis backend
```

Expected: root compose remains usable for development.

- [ ] **Step 5: Verify formal deploy flow**

Run:

```bash
powershell -ExecutionPolicy Bypass -File deploy/scripts/start.ps1
powershell -ExecutionPolicy Bypass -File deploy/scripts/health-check.ps1
powershell -ExecutionPolicy Bypass -File deploy/scripts/verify-rag-e2e.ps1
```

Expected:

- bucket auto-created
- collection auto-created
- upload/index/retrieve/delete succeeds through real MinIO + Qdrant

- [ ] **Step 6: Fix any verification failures and re-run**

Use the exact failing command as the loop boundary until all checks are green.

- [ ] **Step 7: Complete development**

After all verifications pass, use the finishing workflow and report the exact verification evidence in the final update.
