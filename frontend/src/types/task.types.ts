import type { PageParams } from "./common.types";

export type TaskStatus = "pending" | "running" | "done" | "failed" | "reviewing";

export interface InspectionTask {
  id: string;
  org_id: string;
  org_slug?: string | null;
  product_id: string;
  spec_code: string;
  status: TaskStatus;
  priority: number;
  image_urls?: string[];
  source_kind?: string | null;
  source_graph?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface TaskCreate {
  product_id: string;
  spec_code: string;
  image_urls: string[];
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
}

export interface TaskStreamEvent {
  type: string;
  stage?: string;
  message?: string;
  status?: TaskStatus;
  ts?: string;
  [k: string]: unknown;
}
