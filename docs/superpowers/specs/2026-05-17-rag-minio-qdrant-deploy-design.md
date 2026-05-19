# RAG MinIO + Qdrant Deploy Design

**Date:** 2026-05-17
**Status:** Draft for review
**Scope:** Windows-first formal deployment under `deploy/`, while preserving the existing root `docker-compose.yml` for local development and quick debugging.

## Goal

Implement the four phases described in `docs/rag_space_tree_minio_qdrant_design.md` so that:

- local development can still use the current root `docker-compose.yml`
- formal deployment uses a dedicated `deploy/` entrypoint
- MinIO stores original RAG files for real
- Qdrant stores real chunk vectors for retrieval
- bucket and collection are auto-initialized
- chat and quality pipelines both consume the same retrieval path
- data survives container recreation

## Non-Goals

- introducing a third node type such as `category`
- replacing the local development compose flow
- adding Kubernetes or non-Docker deployment
- redesigning unrelated frontend pages

## Constraints

- node types remain only `folder` and `file`
- `deploy/` is the preferred formal deployment path
- target deployment environment is Windows with Docker Desktop / Docker Compose
- the implementation must be test-driven and validated end to end

## Current State Summary

The current repo already has most of Phase 1:

- `rag_spaces`, `rag_nodes`, and `rag_documents` exist
- the RAG tree page supports folder/file hierarchy
- rename/move/delete have already been added

But Phases 2 to 4 are still incomplete:

- file upload still relies on local filesystem storage in application code
- MinIO exists in compose but is not the true storage source of record
- retrieval is split between a Qdrant path and a local-file overlap path
- chat and quality do not consistently share one RAG retrieval contract
- deployment assets under `deploy/` are not yet the formal source of truth

## Recommended Architecture

### Deployment Split

Two deployment paths remain in the repo:

1. Root `docker-compose.yml`
   Use for local development and quick debugging.

2. `deploy/`
   Use for formal deployment on Windows machines and handoff to other users.

### Storage and Indexing Responsibilities

- MySQL is the source of truth for metadata, tree structure, indexing status, and jobs.
- MinIO is the source of truth for original uploaded files.
- Qdrant is the source of truth for semantic chunk retrieval.
- Retrieval must not read original files at query time.

## Phase Breakdown

### Phase 1: Tree Model Baseline

Keep the existing RAG tree model and harden it for formal deployment:

- `rag_spaces` remains the logical top-level container
- `rag_nodes` represents only `folder` and `file`
- `rag_documents` remains the file-metadata table

The current UI/API behavior should remain valid after the deployment upgrade.

### Phase 2: Real MinIO Integration

Introduce a true object storage abstraction and make MinIO the default formal backend.

#### Backend structure

Create:

- `backend/app/services/object_storage/base.py`
- `backend/app/services/object_storage/local.py`
- `backend/app/services/object_storage/minio.py`
- `backend/app/services/object_storage/factory.py`

#### Required capabilities

- upload bytes
- download bytes
- delete object
- build presigned download URL
- ensure bucket exists

#### Data model expectations

`rag_documents` must store enough information to reconstruct object location:

- `storage_backend`
- `bucket`
- `object_key`
- `size_bytes`
- `checksum_sha256`

All RAG uploads and attachment reads that belong to RAG storage should go through the object storage abstraction instead of direct local-path file access.

### Phase 3: Unified Qdrant Chunk Retrieval

Replace local-file keyword overlap retrieval with a unified chunk-based Qdrant flow.

#### New database tables

Add:

- `rag_document_chunks`
- `rag_index_jobs`

#### `rag_document_chunks`

Suggested fields:

- `id`
- `org_id`
- `rag_space_id`
- `document_id`
- `node_id`
- `chunk_index`
- `content_text`
- `content_preview`
- `page_number`
- `token_count`
- `qdrant_point_id`
- `created_at`

#### `rag_index_jobs`

Suggested fields:

- `id`
- `org_id`
- `rag_space_id`
- `document_id`
- `status`
- `error_message`
- `started_at`
- `finished_at`

#### Indexing workflow

1. Upload original file to MinIO
2. Create `rag_documents`
3. Create index job
4. Background worker downloads file from MinIO
5. Parse content
6. Split into chunks
7. Embed chunks
8. Upsert to Qdrant
9. Persist chunk metadata in MySQL
10. Mark document/job status

#### Qdrant payload requirements

Each point should include enough metadata for filtering and citation:

- `org_id`
- `rag_space_id`
- `document_id`
- `node_id`
- `ancestor_node_ids`
- `file_name`
- `full_path`
- `chunk_index`
- `page_number`

### Phase 4: Shared RAG Pipeline for Chat and Quality

Unify retrieval so chat and quality use the same context-building path.

#### Requirements

- support `rag_space_id`
- support optional `scope_node_ids`
- return uniform citations
- stop using local-file retrieval logic at query time

#### Citation shape

Each retrieval hit should be able to provide:

- `title`
- `full_path`
- `quote`
- `chunk_index`
- `page_number`
- `score`

#### Integration targets

- `quality_chat` graph
- quality judgement / structured inspection path
- RAG search/debug API

## Formal `deploy/` Layout

```text
deploy/
  compose/
    docker-compose.deploy.yml
  env/
    deploy.env.example
  scripts/
    start.ps1
    stop.ps1
    init-minio.ps1
    init-qdrant.ps1
    health-check.ps1
    verify-rag-e2e.ps1
  docs/
    deployment.md
    operations.md
    backup-restore.md
```

## Formal Deployment Behavior

### `docker-compose.deploy.yml`

The formal compose stack should define:

- mysql
- redis
- qdrant
- minio
- backend
- frontend

with durable host-mounted or named-volume persistence for:

- MySQL data
- Redis data if already relied upon operationally
- MinIO data
- Qdrant storage

### Environment Template

`deploy/env/deploy.env.example` must document:

- ports
- usernames/passwords
- data directories
- bucket name
- collection name
- backend service URLs
- embedding model configuration

### Startup Contract

`deploy/scripts/start.ps1` should:

1. ensure a real env file exists
2. start core infra
3. initialize MinIO bucket
4. initialize Qdrant collection
5. start app services
6. optionally run health checks

### Shutdown Contract

`deploy/scripts/stop.ps1` should:

- stop services
- preserve volumes by default
- optionally accept a destructive flag only if explicitly requested by the operator

## Health Checks

### MinIO

Health check must validate:

- service reachable
- credentials valid
- bucket exists

### Qdrant

Health check must validate:

- service reachable
- collection exists
- vector config matches expected dimension/distance

### Backend

Add or extend a backend health endpoint so it can report:

```json
{
  "status": "ok",
  "services": {
    "mysql": "ok",
    "redis": "ok",
    "minio": "ok",
    "qdrant": "ok",
    "rag_storage": "ok",
    "rag_index": "ok"
  }
}
```

## Data Durability

Deleting or recreating containers must not remove RAG data by default.

This requires durable mapping for:

- MinIO object data
- Qdrant vector storage
- MySQL metadata

The deployment docs must explicitly explain which directories/volumes hold each category of data.

## API and Service Impact

Expected implementation changes include:

- replace direct `FileStorageService` usage in RAG storage paths with object storage abstraction
- replace local-file overlap retrieval with unified Qdrant-backed retrieval
- preserve current RAG tree APIs where already correct
- add or refine health endpoints and deployment checks

## Testing Strategy

### Unit and service tests

- object storage abstraction behavior
- MinIO initialization logic
- Qdrant initialization logic
- chunk metadata persistence
- scope-node filtering

### Integration tests

- upload file -> stored in MinIO
- index file -> chunks persisted and points written to Qdrant
- retrieve query -> citations include real path/chunk metadata
- delete file -> MinIO object and Qdrant points removed

### Deployment verification

Verify the `deploy/` scripts on Windows:

- `start.ps1`
- `init-minio.ps1`
- `init-qdrant.ps1`
- `health-check.ps1`
- `verify-rag-e2e.ps1`

### End-to-end acceptance

The feature is only considered complete when all of the following succeed:

- local development still works with the root compose flow
- formal deployment works through `deploy/`
- bucket auto-initializes
- collection auto-initializes
- upload/index/retrieve/delete works through real MinIO + Qdrant
- chat can consume the selected RAG scope
- quality pipeline can consume the selected RAG scope

## Risks and Mitigations

### Risk: Existing local-file behavior lingers in one code path

Mitigation:

- locate and remove all RAG-time local retrieval branches
- add regression tests around shared retrieval service usage

### Risk: Embedding config may be present but unusable

Mitigation:

- keep strict embedding mode
- include embedding runtime verification in deployment health checks

### Risk: Collection dimension mismatch

Mitigation:

- make initialization validate expected dimension before writing
- fail clearly instead of silently degrading

### Risk: Windows path and volume differences

Mitigation:

- make `deploy/` PowerShell-first
- keep data directory configuration explicit in env template and docs

## Success Criteria

The implementation is successful when:

- the app uses MinIO as the real file backend for RAG documents
- the app uses Qdrant as the real chunk retrieval backend
- deployment under `deploy/` is the recommended formal path
- the four phases in the design doc are reflected in code, migrations, scripts, and docs
- the system passes fresh automated verification and a real end-to-end RAG flow
