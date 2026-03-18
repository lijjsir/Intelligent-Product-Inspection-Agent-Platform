import type { PageParams } from "./common.types";

export type TaskStatus = "pending" | "running" | "done" | "failed" | "reviewing";

export interface InspectionTask {
  id: string;
  org_id: string;
  product_id: string;
  spec_id: string;
  status: TaskStatus;
  priority: number;
  created_at?: string;
}

export interface TaskCreate {
  product_id: string;
  spec_id: string;
  image_urls: string[];
  priority?: number;
  metadata?: Record<string, unknown>;
}

export interface TaskListQuery extends PageParams {
  status?: TaskStatus;
  product_id?: string;
}
