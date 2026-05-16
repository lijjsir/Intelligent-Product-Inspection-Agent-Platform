# RAG Space Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat RAG space document list with a real folder/file tree backed by new backend tables and APIs.

**Architecture:** Keep `rag_spaces` as the top-level container, introduce `rag_nodes` for folder/file hierarchy, and introduce `rag_documents` for file metadata and storage/indexing status. The frontend consumes a tree payload and manages folder creation, file upload, node selection, and recursive deletion in one page.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Vue 3, Pinia, Element Plus, Tailwind, MySQL, local file storage abstraction, Qdrant indexing.

---

### Task 1: Add Tree Data Model and Migration

**Files:**
- Create: `backend/migrations/versions/0026_rag_tree_nodes_and_documents.py`
- Modify: `backend/app/models/rag_space.py`
- Test: `backend/tests/test_rag_space_service.py`

- [ ] **Step 1: Write the failing model/service test expectations**

```python
def test_rag_tree_node_response_can_represent_nested_folder_and_file():
    node = {
        "id": "node-1",
        "node_type": "folder",
        "children": [
            {
                "id": "node-2",
                "node_type": "file",
                "document": {"id": "doc-1", "file_name": "spec.pdf"},
            }
        ],
    }
    assert node["children"][0]["document"]["file_name"] == "spec.pdf"
```

- [ ] **Step 2: Run targeted backend tests to establish the current baseline**

Run: `pytest backend/tests/test_rag_space_service.py -q`
Expected: Existing flat RAG tests pass before schema work begins.

- [ ] **Step 3: Add migration for `rag_nodes`, `rag_documents`, and new `rag_spaces` summary fields**

```python
op.add_column("rag_spaces", sa.Column("folder_count", sa.Integer(), nullable=False, server_default="0"))
op.add_column("rag_spaces", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
op.create_table("rag_nodes", ...)
op.create_table("rag_documents", ...)
```

- [ ] **Step 4: Update SQLAlchemy models to match the new schema**

```python
class RagNode(Base, TimestampMixin):
    __tablename__ = "rag_nodes"
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    parent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

class RagDocument(Base, TimestampMixin):
    __tablename__ = "rag_documents"
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    node_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 5: Run the RAG service test file again**

Run: `pytest backend/tests/test_rag_space_service.py -q`
Expected: Failures now point at service/repository/schema mismatch rather than migration syntax issues.


### Task 2: Replace Flat Repositories and Schemas with Tree-Aware Contracts

**Files:**
- Modify: `backend/app/repositories/rag_space_repo.py`
- Modify: `backend/app/schemas/rag_space.py`
- Test: `backend/tests/test_rag_space_service.py`

- [ ] **Step 1: Write failing tests for folder/file tree operations**

```python
async def test_create_folder_under_parent_returns_folder_node():
    result = await service.create_node(rag_space_id="space-1", parent_id="folder-root", node_type="folder", name="模具标准")
    assert result.node_type == "folder"
    assert result.parent_id == "folder-root"
```

- [ ] **Step 2: Run the specific failing test**

Run: `pytest backend/tests/test_rag_space_service.py::test_create_folder_under_parent_returns_folder_node -q`
Expected: FAIL because `create_node` and new response schemas do not exist yet.

- [ ] **Step 3: Refactor repositories into space/node/document responsibilities**

```python
class RagNodeRepository:
    async def create_folder(self, *, org_id: str, rag_space_id: str, parent_id: str | None, name: str, created_by: str | None): ...
    async def list_tree(self, *, org_id: str, rag_space_id: str): ...
    async def soft_delete_subtree(self, *, org_id: str, rag_space_id: str, node_ids: list[str]): ...

class RagDocumentRepository:
    async def create(self, *, org_id: str, rag_space_id: str, node_id: str, file_name: str, object_key: str, ...): ...
```

- [ ] **Step 4: Replace flat response schemas with tree-aware Pydantic models**

```python
class RagDocumentResponse(BaseModel):
    id: str
    node_id: str
    file_name: str
    parse_status: str
    index_status: str

class RagTreeNodeResponse(BaseModel):
    id: str
    parent_id: str | None = None
    node_type: str
    name: str
    children_count: int = 0
    document: RagDocumentResponse | None = None
    children: list["RagTreeNodeResponse"] = Field(default_factory=list)
```

- [ ] **Step 5: Re-run the targeted repository/service test**

Run: `pytest backend/tests/test_rag_space_service.py::test_create_folder_under_parent_returns_folder_node -q`
Expected: Still failing in service logic, but repository/schema symbols now exist.


### Task 3: Implement Tree Service Logic with Folder Create, Tree Read, Upload, and Recursive Delete

**Files:**
- Modify: `backend/app/services/rag_space_service.py`
- Modify: `backend/app/services/file_storage_service.py`
- Modify: `backend/agent/rag/knowledge_indexer.py`
- Test: `backend/tests/test_rag_space_service.py`

- [ ] **Step 1: Write failing service tests for the new behavior set**

```python
async def test_upload_file_creates_file_node_and_document_metadata(): ...
async def test_delete_folder_removes_descendant_file_nodes(): ...
async def test_list_tree_returns_nested_children(): ...
```

- [ ] **Step 2: Run only the new RAG tree service tests**

Run: `pytest backend/tests/test_rag_space_service.py -q`
Expected: FAIL on missing `list_tree`, `create_node`, folder upload targeting, and recursive delete behavior.

- [ ] **Step 3: Implement service entry points around the new repositories**

```python
async def list_tree(self, *, rag_space_id: str) -> list[RagTreeNodeResponse]: ...
async def create_node(self, *, rag_space_id: str, parent_id: str | None, node_type: str, name: str) -> RagTreeNodeResponse: ...
async def upload_documents(self, *, rag_space_id: str, parent_node_id: str, files: list[UploadFile]) -> list[RagTreeNodeResponse]: ...
async def delete_node(self, *, rag_space_id: str, node_id: str) -> None: ...
```

- [ ] **Step 4: Update file storage/indexer helpers so deletes can target new metadata**

```python
payload = {
    "rag_space_id": rag_space_id,
    "node_id": file_node_id,
    "document_id": document_id,
    "file_name": file_name,
}
await self._indexer.delete_by_filter({"rag_space_id": rag_space_id, "document_id": document_id})
```

- [ ] **Step 5: Run the full backend RAG service test file**

Run: `pytest backend/tests/test_rag_space_service.py -q`
Expected: PASS


### Task 4: Expose Tree APIs and Preserve Space Selection Compatibility

**Files:**
- Modify: `backend/app/api/v1/rag_spaces.py`
- Modify: `backend/app/schemas/rag_space.py`
- Test: `backend/tests/test_chat_flow.py`
- Test: `backend/tests/test_rag_space_service.py`

- [ ] **Step 1: Write failing API-level tests or assertions for new routes**

```python
def test_rag_tree_routes_exist():
    paths = {route.path for route in app.routes}
    assert "/api/v1/rag-spaces/{rag_space_id}/tree" in paths
```

- [ ] **Step 2: Run the relevant tests**

Run: `pytest backend/tests/test_rag_space_service.py backend/tests/test_chat_flow.py -q`
Expected: FAIL because the new routes and schema payloads are not wired yet.

- [ ] **Step 3: Replace flat document endpoints with tree-aware endpoints**

```python
@router.get("/{rag_space_id}/tree", response_model=ResponseEnvelope[list[RagTreeNodeResponse]])
@router.post("/{rag_space_id}/nodes", response_model=ResponseEnvelope[RagTreeNodeResponse])
@router.post("/{rag_space_id}/nodes/{node_id}/documents", response_model=ResponseEnvelope[list[RagTreeNodeResponse]])
@router.delete("/{rag_space_id}/nodes/{node_id}", response_model=ResponseEnvelope[dict])
```

- [ ] **Step 4: Keep `GET /v1/rag-spaces` stable for chat-side space selection**

```python
return ResponseEnvelope(data=await service.list_spaces(limit=limit))
```

- [ ] **Step 5: Re-run backend tests covering RAG APIs and chat compatibility**

Run: `pytest backend/tests/test_rag_space_service.py backend/tests/test_chat_flow.py -q`
Expected: PASS


### Task 5: Add Frontend Tree Types, API Client, and Store

**Files:**
- Modify: `frontend/src/types/rag-space.types.ts`
- Modify: `frontend/src/api/rag-space.api.ts`
- Create: `frontend/src/stores/rag-space.store.ts`
- Test: `frontend/tests/chat.store.spec.ts`

- [ ] **Step 1: Write failing frontend expectations for tree payload handling**

```ts
it("normalizes a nested RAG tree response", () => {
  const node = { id: "n1", node_type: "folder", children: [{ id: "n2", node_type: "file" }] };
  expect(node.children[0].node_type).toBe("file");
});
```

- [ ] **Step 2: Run the frontend unit test baseline**

Run: `npm --prefix frontend test -- chat.store.spec.ts`
Expected: Existing store tests pass before new RAG tree store work starts.

- [ ] **Step 3: Add tree types and API methods**

```ts
export interface RagTreeNode { id: string; parent_id: string | null; node_type: "folder" | "file"; children?: RagTreeNode[]; }
listTree(ragSpaceId: string) { return http.get<RagTreeNode[]>(`/v1/rag-spaces/${ragSpaceId}/tree`); }
createNode(ragSpaceId: string, payload: RagNodeCreateRequest) { ... }
uploadDocuments(ragSpaceId: string, nodeId: string, files: File[]) { ... }
deleteNode(ragSpaceId: string, nodeId: string) { ... }
```

- [ ] **Step 4: Create a dedicated RAG tree store**

```ts
export const useRagSpaceStore = defineStore("ragSpace", () => {
  const tree = ref<RagTreeNode[]>([]);
  const selectedNodeId = ref("");
  async function fetchTree(ragSpaceId: string) { ... }
  async function createFolder(...) { ... }
  async function uploadToNode(...) { ... }
  async function deleteNode(...) { ... }
  return { tree, selectedNodeId, fetchTree, createFolder, uploadToNode, deleteNode };
});
```

- [ ] **Step 5: Run the frontend test command again**

Run: `npm --prefix frontend test -- chat.store.spec.ts`
Expected: PASS


### Task 6: Rebuild the RAG Space Page into a Tree Manager

**Files:**
- Modify: `frontend/src/views/RagSpaceView.vue`
- Create: `frontend/src/components/rag/RagSpaceToolbar.vue`
- Create: `frontend/src/components/rag/RagTreePanel.vue`
- Create: `frontend/src/components/rag/RagTreeNodeRow.vue`
- Create: `frontend/src/components/rag/RagNodeDetailPanel.vue`
- Create: `frontend/src/components/rag/RagCreateFolderDialog.vue`
- Create: `frontend/src/components/rag/RagUploadDialog.vue`
- Create: `frontend/src/components/rag/RagDeleteConfirmDialog.vue`
- Test: `frontend/tests/quality.analysis-center.spec.ts`

- [ ] **Step 1: Write a failing UI test or interaction assertion for tree rendering**

```ts
it("renders nested folders and files in the RAG page tree", async () => {
  expect(screen.getByText("机械")).toBeInTheDocument();
  expect(screen.getByText("注塑外观标准.pdf")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend test command for the touched surface**

Run: `npm --prefix frontend test`
Expected: FAIL for the new tree view assertions because the page is still the flat list version.

- [ ] **Step 3: Build the new page shell and tree interaction**

```vue
<RagSpaceToolbar />
<section class="rag-tree-layout">
  <RagTreePanel />
  <RagNodeDetailPanel />
</section>
```

- [ ] **Step 4: Implement folder/file row actions with restrained product-console styling**

```vue
<el-button link size="small" @click="emit('create-child', node)">新建子文件夹</el-button>
<el-button link size="small" @click="emit('upload', node)">上传文件</el-button>
<el-button link type="danger" size="small" @click="emit('delete', node)">删除</el-button>
```

- [ ] **Step 5: Run the frontend test suite for the page**

Run: `npm --prefix frontend test`
Expected: PASS


### Task 7: End-to-End Verification

**Files:**
- Modify: `backend/tests/test_rag_space_service.py`
- Modify: `frontend/tests/chat.store.spec.ts`
- Modify: `frontend/tests/quality.analysis-center.spec.ts`

- [ ] **Step 1: Run backend verification**

Run: `pytest backend/tests/test_rag_space_service.py backend/tests/test_chat_flow.py -q`
Expected: PASS

- [ ] **Step 2: Run frontend verification**

Run: `npm --prefix frontend test`
Expected: PASS

- [ ] **Step 3: Run a final diff sanity check**

Run: `git diff --stat`
Expected: Shows migration, backend RAG tree files, and frontend RAG tree UI changes only.
