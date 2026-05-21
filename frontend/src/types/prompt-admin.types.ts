export type PromptSyncStatus =
  | "synced"
  | "code_changed"
  | "db_override"
  | "conflict"
  | "missing_in_code";

export type PromptCurrentSource = "code_default" | "database";
export type PromptVersionStatus = "draft" | "review" | "approved" | "deprecated";

export interface PromptDefinitionSummary {
  id: string;
  prompt_key: string;
  display_name: string;
  usage_location?: string;
  agent_name?: string;
  stage_name?: string;
  source_file?: string;
  sync_status: PromptSyncStatus;
  current_source: PromptCurrentSource;
  active_version?: number;
  updated_at?: string;
}

export interface PromptVersionItem {
  id: string;
  version: number;
  content: string;
  content_hash: string;
  status: PromptVersionStatus;
  change_summary?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptDefinitionDetail {
  id: string;
  prompt_key: string;
  display_name: string;
  description?: string;
  agent_key?: string;
  agent_name?: string;
  stage_key?: string;
  stage_name?: string;
  usage_location?: string;
  source_file?: string;
  source_symbol?: string;
  start_line?: number;
  end_line?: number;
  current_source: PromptCurrentSource;
  sync_status: PromptSyncStatus;
  code_default_content: string;
  active_content: string;
  active_version?: number;
  active_content_hash: string;
  versions: PromptVersionItem[];
}

export interface PromptOverview {
  total: number;
  db_override: number;
  code_changed: number;
  conflict: number;
  missing_in_code: number;
}

export interface CreateVersionRequest {
  content: string;
  change_summary?: string;
  base_hash?: string;
}

export interface DiffResponse {
  left_label: string;
  right_label: string;
  left_content: string;
  right_content: string;
}

export interface SyncScanResponse {
  scanned: number;
  created: number;
  updated: number;
  missing: number;
}
