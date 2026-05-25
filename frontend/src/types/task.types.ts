import type { PageParams } from "./common.types";

export type TaskStatus = "pending" | "queued" | "running" | "done" | "failed" | "reviewing" | "archived";

export interface ImageItem {
  index: number;
  url: string;
  hash: string;
  sample_number?: number | null;
}

export interface DefectItem {
  type: string;
  confidence: number;
  bbox: [number, number, number, number];
  description: string;
  image_index?: number;
  image_hash?: string;
}

export interface InspectionTask {
  id: string;
  org_id: string;
  org_slug?: string | null;
  product_id: string;
  spec_code: string;
  status: TaskStatus;
  priority: number;
  image_urls?: string[];
  image_items?: ImageItem[] | null;
  source_kind?: string | null;
  source_graph?: string | null;
  has_result?: boolean;
  has_stability?: boolean;
  result_id?: string | null;
  stability_id?: string | null;
  execution?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface TaskCreate {
  product_id: string;
  spec_code: string;
  image_urls: string[];
  image_items?: ImageItem[];
  priority?: number;
  metadata?: Record<string, unknown>;
}

export interface TaskListQuery extends PageParams {
  status?: TaskStatus;
  product_id?: string;
  ids?: string;
}

export interface TaskRunResponse {
  mode: "celery" | "local_background";
  job_id: string | null;
  status?: TaskStatus;
}

export type TaskResultIngestTarget = "rag" | "dataset" | "both";
export type TaskResultIngestMode = "candidate";

export interface TaskResultIngestRequest {
  target: TaskResultIngestTarget;
  rag_space_id?: string | null;
  dataset_id?: string | null;
  dataset_name?: string | null;
  mode?: TaskResultIngestMode;
}

export interface TaskResultIngestResponse {
  task_id: string;
  target: TaskResultIngestTarget;
  mode: TaskResultIngestMode;
  rag_space_id?: string | null;
  dataset_id?: string | null;
  dataset_name?: string | null;
  created_document_count: number;
  created_sample_count: number;
  skipped_count: number;
  warnings: string[];
}

export interface TaskStatusResponse {
  id: string;
  status: TaskStatus;
}

export interface TaskStreamEvent {
  id?: string;
  type: string;
  stage?: string;
  message?: string;
  status?: TaskStatus;
  ts?: string;
  [k: string]: unknown;
}
