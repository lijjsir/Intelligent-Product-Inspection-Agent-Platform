export interface RagDocument {
  id: string;
  org_id: string;
  rag_space_id: string;
  node_id: string;
  file_name: string;
  content_type?: string | null;
  file_url: string;
  size_bytes: number;
  checksum_sha256: string;
  storage_backend: string;
  object_key: string;
  parse_status: string;
  index_status: string;
  chunk_count: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RagNode {
  id: string;
  org_id: string;
  rag_space_id: string;
  parent_id?: string | null;
  created_by?: string | null;
  node_type: "folder" | "file";
  name: string;
  full_path: string;
  depth: number;
  sort_order: number;
  status: string;
  children_count: number;
  document?: RagDocument | null;
  children: RagNode[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RagSpaceDocumentListItem {
  id: string;
  rag_space_id: string;
  org_id: string;
  node_id: string;
  file_name: string;
  content_type?: string | null;
  file_url: string;
  size_bytes: number;
  status: string;
  created_at?: string | null;
}

export type RagSpaceFile = RagSpaceDocumentListItem;

export interface RagSpace {
  id: string;
  org_id: string;
  created_by?: string | null;
  name: string;
  description?: string | null;
  status: string;
  file_count: number;
  folder_count: number;
  chunk_count: number;
  index_status: string;
  selected_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RagSpaceCreateRequest {
  name: string;
  description?: string;
}

export interface RagSpaceUpdateRequest {
  name: string;
  description?: string;
}

export interface RagNodeCreateRequest {
  parent_id?: string | null;
  node_type: "folder";
  name: string;
}

export interface RagNodeUpdateRequest {
  parent_id?: string | null;
  name: string;
}
