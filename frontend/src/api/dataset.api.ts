import { http } from "./http";
import type {
  DatasetCreateRequest,
  DatasetDetail,
  DatasetListQuery,
  DatasetListResponse,
  DatasetUploadCompleteRequest,
  DatasetUploadCompleteResponse,
  DatasetUploadInitRequest,
  DatasetUploadInitResponse,
  DatasetUploadPartResponse,
  DatasetSample,
  DatasetSampleCreateRequest,
  DatasetSampleListQuery,
  DatasetSampleListResponse,
  DatasetUpdateRequest,
  AsyncJob,
} from "@/types/dataset.types";

export const datasetApi = {
  list(query: DatasetListQuery) {
    return http.get<DatasetListResponse>("/v1/datasets", { params: query });
  },

  get(id: string) {
    return http.get<DatasetDetail>(`/v1/datasets/${id}`);
  },

  create(payload: DatasetCreateRequest) {
    return http.post<DatasetDetail>("/v1/datasets", payload);
  },

  update(id: string, payload: DatasetUpdateRequest) {
    return http.patch<DatasetDetail>(`/v1/datasets/${id}`, payload);
  },

  remove(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${id}`);
  },

  listSamples(datasetId: string, query: DatasetSampleListQuery) {
    return http.get<DatasetSampleListResponse>(`/v1/datasets/${datasetId}/samples`, { params: query });
  },

  createTextSample(datasetId: string, payload: DatasetSampleCreateRequest) {
    return http.post<DatasetSample>(`/v1/datasets/${datasetId}/samples/text`, payload);
  },

  uploadImageSamples(datasetId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<DatasetSample[]>(`/v1/datasets/${datasetId}/samples/images`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  uploadVideoSamples(datasetId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<DatasetSample[]>(`/v1/datasets/${datasetId}/samples/videos`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  initUploadSession(datasetId: string, payload: DatasetUploadInitRequest) {
    return http.post<DatasetUploadInitResponse>(`/v1/datasets/${datasetId}/upload/init`, payload);
  },

  uploadPart(datasetId: string, sessionId: string, partNumber: number, chunk: Blob) {
    const form = new FormData();
    form.append("chunk", chunk);
    return http.put<DatasetUploadPartResponse>(`/v1/datasets/${datasetId}/upload/${sessionId}/parts/${partNumber}`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  completeUploadSession(datasetId: string, payload: DatasetUploadCompleteRequest) {
    return http.post<DatasetUploadCompleteResponse>(`/v1/datasets/${datasetId}/upload/complete`, payload);
  },

  getJob(datasetId: string, jobId: string) {
    return http.get<AsyncJob>(`/v1/datasets/${datasetId}/jobs/${jobId}`);
  },

  removeSample(datasetId: string, sampleId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${datasetId}/samples/${sampleId}`);
  },
};
