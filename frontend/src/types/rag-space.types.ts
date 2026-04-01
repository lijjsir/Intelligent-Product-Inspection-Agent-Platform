export interface RagSpaceFile {
  id: string;
  rag_space_id: string;
  org_id: string;
  file_name: string;
  content_type?: string | null;
  file_url: string;
  size_bytes: number;
  status: string;
  created_at?: string | null;
}

export interface RagSpace {
  id: string;
  org_id: string;
  created_by?: string | null;
  name: string;
  description?: string | null;
  status: string;
  file_count: number;
  selected_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  files?: RagSpaceFile[];
}

export interface RagSpaceCreateRequest {
  name: string;
  description?: string;
}
