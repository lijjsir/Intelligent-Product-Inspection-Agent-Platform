# RAG Space Tree Design

## Background

The current RAG space implementation is still a flat `space + documents` model:

- The frontend [RagSpaceView.vue](/C:/download/code/hy-teacher/new/Intelligent-Product-Inspection-Agent-Platform/frontend/src/views/RagSpaceView.vue) renders a space list plus a document list.
- The backend only stores `rag_spaces` and `rag_space_files`.
- Each RAG space currently only allows one uploaded document.
- There is no real tree structure for folders and files.

The target is to redesign the RAG space page into a tree-based knowledge browser, following the direction of [rag_space_tree_minio_qdrant_design.md](/C:/download/code/hy-teacher/new/Intelligent-Product-Inspection-Agent-Platform/docs/rag_space_tree_minio_qdrant_design.md), but with one important simplification:

- Node types are only `folder` and `file`
- There is no separate `category` node type

Top-level entries such as “机械”, “食品”, and “电子产品” are root-level `folder` nodes.

## Goal

Build a real folder/file tree for each RAG space so users can:

- Create root folders
- Create nested subfolders at any depth
- Upload files into the root or any folder
- Delete folders recursively
- Delete individual files
- Browse the full tree inside one page with clear hierarchy
- View folder or file details in the same page

The solution must include both frontend and backend changes, not just a visual mockup.

## Non-Goals

This design does not include:

- A separate `category` node model
- Drag-and-drop reordering or moving nodes
- Inline rename
- Multi-select bulk operations
- Version history for files
- Fine-grained node permissions beyond the current space ownership boundary

These can be added later without changing the core tree model.

## Recommended Approach

Use a three-layer structure:

1. `rag_spaces`
   Each RAG space remains the top-level logical container.

2. `rag_nodes`
   A new tree table that stores all visible nodes in the page.
   Each node is either:
   - `folder`
   - `file`

3. `rag_documents`
   A new document metadata table attached one-to-one to `file` nodes.
   It stores MinIO object metadata, parsing status, indexing status, and chunk counters.

This approach is preferred over path-only reconstruction because:

- Empty folders become first-class data
- Recursive deletion is reliable
- Frontend tree rendering becomes straightforward
- Future features like lazy-loading, node move, or rename fit naturally

## Data Model

### 1. `rag_spaces`

Keep the existing `rag_spaces` table and extend it with summary fields used directly by the page header:

- `folder_count`
- `file_count`
- `chunk_count`
- `index_status`

Suggested meaning:

- `folder_count`: total active folder nodes in the space
- `file_count`: total active file nodes in the space
- `chunk_count`: total indexed chunks across all files in the space
- `index_status`: summary state such as `ready`, `indexing`, `partial_failed`

### 2. `rag_nodes`

Introduce a new tree table.

Suggested fields:

- `id`
- `org_id`
- `rag_space_id`
- `parent_id`
- `node_type`
- `name`
- `full_path`
- `depth`
- `sort_order`
- `status`
- `children_count`
- `created_by`
- `created_at`
- `updated_at`
- `deleted_at`

Rules:

- `node_type` only allows `folder` or `file`
- `folder` can have children
- `file` cannot have children
- Sibling names must be unique under the same parent
- Root-level nodes use `parent_id = NULL`
- Root-level nodes may contain both folders and files, though the primary flow is folder-first

Recommended statuses:

- `ready`
- `indexing`
- `failed`
- `deleting`

### 3. `rag_documents`

Introduce a separate file metadata table linked to `rag_nodes.id` where `node_type = file`.

Suggested fields:

- `id`
- `org_id`
- `rag_space_id`
- `node_id`
- `file_name`
- `content_type`
- `size_bytes`
- `storage_backend`
- `bucket`
- `object_key`
- `checksum_sha256`
- `parse_status`
- `index_status`
- `chunk_count`
- `error_message`
- `created_at`
- `updated_at`
- `deleted_at`

Recommended parsing and indexing states:

- `parse_status`: `pending`, `parsing`, `parsed`, `failed`
- `index_status`: `pending`, `indexing`, `ready`, `failed`

## Storage and Retrieval Responsibilities

Responsibilities should be separated clearly:

- MySQL stores the source of truth for spaces, folders, files, and document metadata
- MinIO stores the original uploaded file bytes
- Qdrant stores parsed chunks and vectors for retrieval

This means:

- The tree UI reads from MySQL
- File upload writes to MinIO, then creates metadata rows in MySQL
- Parsing and indexing write chunk/vector data to Qdrant
- Deleting a file removes MySQL metadata, MinIO object, and Qdrant indexed chunks
- Deleting a folder recursively removes the full subtree and all downstream data

## Backend API Design

### Existing APIs to Keep

Retain the space-level API prefix:

- `GET /v1/rag-spaces`
- `POST /v1/rag-spaces`
- `DELETE /v1/rag-spaces/{space_id}`

### New Tree APIs

#### Get full tree

`GET /v1/rag-spaces/{space_id}/tree`

Purpose:

- Load the full tree for the current page
- Suitable for the first implementation

Response shape:

- Returns nested folder/file nodes
- Each `file` node may include an embedded `document` object

#### Create folder node

`POST /v1/rag-spaces/{space_id}/nodes`

Request:

```json
{
  "parent_id": null,
  "node_type": "folder",
  "name": "机械"
}
```

For nested folders:

```json
{
  "parent_id": "folder-node-id",
  "node_type": "folder",
  "name": "模具标准"
}
```

Notes:

- Only `folder` creation is allowed through this endpoint
- `file` nodes are created indirectly through upload

#### Delete node

`DELETE /v1/rag-spaces/{space_id}/nodes/{node_id}`

Behavior:

- If node is `folder`, recursively delete the subtree
- If node is `file`, delete the file node and linked document

### New Document APIs

#### Upload into a folder

`POST /v1/rag-spaces/{space_id}/nodes/{node_id}/documents`

Behavior:

- `node_id` must point to a `folder`
- Upload one or more files
- For each uploaded file:
  - save bytes to MinIO
  - create a `file` node under the folder
  - create a linked `rag_documents` row
  - enqueue parse/index work

This endpoint should also support a reserved root-upload path by allowing a root folder selection through the UI rather than inventing a second upload API.

#### Delete document

`DELETE /v1/rag-spaces/{space_id}/documents/{document_id}`

Behavior:

- Remove linked file node
- Remove MinIO object
- Remove Qdrant chunks

This remains useful even if node deletion is the main UI action.

## Tree Response Contract

The frontend should consume a tree-oriented payload like:

```ts
type RagTreeNode = {
  id: string;
  rag_space_id: string;
  parent_id: string | null;
  node_type: "folder" | "file";
  name: string;
  full_path: string;
  depth: number;
  status: string;
  children_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  document?: {
    id: string;
    file_name: string;
    content_type?: string | null;
    size_bytes: number;
    parse_status: string;
    index_status: string;
    chunk_count: number;
    error_message?: string | null;
  } | null;
  children?: RagTreeNode[];
};
```

This contract should be used by:

- the tree component
- the folder/file detail panel
- delete confirmation logic

## Delete Behavior

### Delete file

When deleting a file:

- soft-delete the `file` node
- soft-delete the linked `rag_documents` row
- delete MinIO object
- delete Qdrant data for the file
- refresh parent counters and space counters

### Delete folder

When deleting a folder:

- recursively collect all descendant nodes
- soft-delete all descendant `file` nodes and `folder` nodes
- soft-delete all linked `rag_documents`
- delete all MinIO objects for descendant files
- delete all related Qdrant vectors/chunks
- refresh affected counters

The confirmation text in the UI must explicitly state that deleting a folder deletes all nested subfolders and files.

## Frontend Page Design

### Page Layout

Use a single page with three main regions.

#### 1. Top toolbar

Contains:

- current space selector
- summary metrics such as total folders and total files
- action buttons:
  - `新建文件夹`
  - `上传文件`
  - `刷新`

#### 2. Left main tree panel

This is the primary surface.

Each node row shows:

- icon
- node name
- status tag when useful
- right-side actions

Folder row actions:

- `新建子文件夹`
- `上传文件`
- `删除`

File row actions:

- `删除`

Hierarchy is shown through indentation and expand/collapse, not through nested cards.

#### 3. Right detail panel

When a folder is selected:

- show path
- show child count
- show file count
- expose shortcuts for `新建子文件夹` and `上传文件`

When a file is selected:

- show file name
- size
- content type
- parse status
- index status
- updated time

## Frontend Component Split

The current monolithic [RagSpaceView.vue](/C:/download/code/hy-teacher/new/Intelligent-Product-Inspection-Agent-Platform/frontend/src/views/RagSpaceView.vue) should be split into focused components:

- `frontend/src/views/RagSpaceView.vue`
- `frontend/src/components/rag/RagSpaceToolbar.vue`
- `frontend/src/components/rag/RagTreePanel.vue`
- `frontend/src/components/rag/RagTreeNodeRow.vue`
- `frontend/src/components/rag/RagNodeDetailPanel.vue`
- `frontend/src/components/rag/RagCreateFolderDialog.vue`
- `frontend/src/components/rag/RagUploadDialog.vue`
- `frontend/src/components/rag/RagDeleteConfirmDialog.vue`

Supporting files:

- `frontend/src/api/rag-space.api.ts`
- `frontend/src/types/rag-space.types.ts`
- `frontend/src/stores/rag-space.store.ts`

## UX Rules

- Node types are only folder and file, so the UI should never mention “类别”
- Root folders such as “机械” and “食品” should visually read as first-level folders
- The page must support empty folders
- All key actions must stay in the same page
- Folder creation should require only a name
- Upload target must always be clear in the dialog
- Duplicate sibling names should return a direct validation error
- Destructive actions must require confirmation

## Migration Strategy

Recommended migration sequence:

1. Add new tables:
   - `rag_nodes`
   - `rag_documents`

2. Extend `rag_spaces` summary fields

3. Backfill existing flat `rag_space_files` into the new model:
   - create one root-level `file` node per old file
   - create one `rag_documents` row per old file

4. Switch service reads/writes to the new tables

5. Keep old tables temporarily if needed for rollback

6. Remove old `rag_space_files` usage after verification

## Error Handling

Backend must explicitly handle:

- invalid parent node
- uploading to a `file` node
- duplicate sibling names
- deleting already-deleted nodes
- MinIO deletion failure
- Qdrant deletion failure
- indexing failures after upload

Frontend must show:

- clear upload target
- clear delete consequences
- status badges for indexing failures
- graceful empty states for empty spaces and empty folders

## Testing Strategy

### Backend

Add tests for:

- creating root folder
- creating nested folder
- uploading file into root folder
- uploading file into nested folder
- rejecting uploads into a file node
- rejecting duplicate names under same parent
- deleting file node
- recursively deleting folder subtree
- syncing MinIO/Qdrant cleanup

### Frontend

Add tests for:

- rendering nested tree correctly
- expanding and collapsing folders
- creating folder under root
- creating subfolder under folder
- uploading file to selected folder
- deleting file
- deleting folder recursively
- switching detail panel by selected node type

## Implementation Notes

- The first version should use `GET /tree` to fetch the full tree, rather than premature lazy-loading
- The UI should optimize for clarity and hierarchy, not high-density admin complexity
- The design should feel like a clean document manager, matching the reference screenshot while preserving the project’s current UI language

## Recommendation Summary

Proceed with the real tree model:

- `rag_spaces` as container
- `rag_nodes` as folder/file hierarchy
- `rag_documents` as file metadata

This is the cleanest foundation for the requested page and the safest base for future RAG management features.
