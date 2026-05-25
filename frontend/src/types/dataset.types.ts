import type { PageParams, PagedResponse } from "./common.types";

export type DatasetModality = string;
export type DatasetStatus = "active" | "archived";
export type DatasetSampleType = "image" | "text" | "video";

export interface AsyncJob {
  id: string;
  org_id: string;
  dataset_id: string;
  created_by?: string | null;
  job_type: string;
  status: string;
  payload_json?: Record<string, unknown> | null;
  result_summary?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Dataset {
  id: string;
  org_id: string;
  created_by?: string | null;
  name: string;
  description?: string | null;
  modality: DatasetModality;
  tags: string[];
  status: string;
  sample_count: number;
  image_sample_count: number;
  video_sample_count: number;
  text_sample_count: number;
  uploaded_bytes: number;
  knowledge_graph_status: string;
  alignment_status: string;
  augmentation_status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DatasetNameOption {
  name: string;
}

export interface DatasetDetail extends Dataset {
  recent_jobs: AsyncJob[];
  supported_export_formats: string[];
}

export interface DatasetSample {
  id: string;
  org_id: string;
  dataset_id: string;
  created_by?: string | null;
  sample_type: DatasetSampleType;
  sample_name?: string | null;
  text_content?: string | null;
  content_type?: string | null;
  size_bytes: number;
  checksum_sha256: string;
  storage_backend?: string | null;
  bucket?: string | null;
  object_key?: string | null;
  file_url?: string | null;
  annotation_data?: Record<string, unknown> | unknown[] | null;
  quality_score?: number | null;
  related_entities?: unknown[] | null;
  source_metadata?: Record<string, unknown> | null;
  preview_text?: string | null;
  download_url?: string | null;
  is_augmented?: boolean;
  augmentation_source_id?: string | null;
  augmentation_method?: string | null;
  augmentation_params?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DatasetUploadInitRequest {
  file_name: string;
  content_type?: string;
  file_size: number;
  chunk_size: number;
  total_chunks: number;
}

export interface DatasetUploadInitResponse {
  session_id: string;
  bucket: string;
  object_key: string;
  chunk_size: number;
  total_chunks: number;
  expires_at?: string | null;
}

export interface DatasetUploadPartResponse {
  session_id: string;
  part_number: number;
  uploaded_parts: number[];
  uploaded_count: number;
}

export interface DatasetUploadCompleteRequest {
  session_id: string;
  uploaded_parts: number[];
}

export interface DatasetUploadCompleteResponse {
  session_id: string;
  job: AsyncJob;
  dataset: DatasetDetail;
}

export interface DatasetCreateRequest {
  name: string;
  description?: string;
  modality: DatasetModality;
  tags: string[];
}

export interface DatasetUpdateRequest {
  name?: string;
  description?: string | null;
  modality?: DatasetModality;
  tags?: string[];
  status?: DatasetStatus;
}

export interface DatasetSampleCreateRequest {
  sample_name?: string;
  text_content: string;
  annotation_data?: Record<string, unknown> | unknown[] | null;
  quality_score?: number | null;
  related_entities?: string[] | null;
  source_metadata?: Record<string, unknown> | null;
}

export interface DatasetListQuery extends PageParams {
  keyword?: string;
  modality?: DatasetModality | "";
  status?: DatasetStatus | "";
}

export interface DatasetSampleListQuery extends PageParams {
  sample_type?: DatasetSampleType | "";
}

export type DatasetListResponse = PagedResponse<Dataset>;
export type DatasetSampleListResponse = PagedResponse<DatasetSample>;
