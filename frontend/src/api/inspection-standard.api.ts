import { http } from "./http";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  InspectionStandardQuery,
  PaginatedDocuments,
  PaginatedInspectionStandards,
  StandardDocumentChunkItem,
  StandardDocumentItem,
  StandardDocumentPayload,
  StandardLibraryIndexResult,
  StandardLibraryScanResult,
  StandardRetrievePayload,
  StandardRetrieveResult,
} from "@/types/governance.types";

export const inspectionStandardApi = {
  list(params?: InspectionStandardQuery) {
    return http.get<PaginatedInspectionStandards>("/v1/standard-libraries", { params });
  },
  get(id: string) {
    return http.get<InspectionStandardLibraryItem>(`/v1/standard-libraries/${id}`);
  },
  create(payload: InspectionStandardPayload) {
    return http.post<InspectionStandardLibraryItem>("/v1/standard-libraries", payload);
  },
  update(id: string, payload: Partial<InspectionStandardPayload>) {
    return http.patch<InspectionStandardLibraryItem>(`/v1/standard-libraries/${id}`, payload);
  },
  remove(id: string) {
    return http.delete<{ success: boolean }>(`/v1/standard-libraries/${id}`);
  },
  scan(id: string) {
    return http.post<StandardLibraryScanResult>(`/v1/standard-libraries/${id}/scan`);
  },
  index(id: string) {
    return http.post<StandardLibraryIndexResult>(`/v1/standard-libraries/${id}/index`);
  },
  reindex(id: string) {
    return http.post<StandardLibraryIndexResult>(`/v1/standard-libraries/${id}/reindex`);
  },
  listDocuments(id: string, params?: { page?: number; size?: number }) {
    return http.get<PaginatedDocuments>(`/v1/standard-libraries/${id}/documents`, { params });
  },
  updateDocument(documentId: string, payload: StandardDocumentPayload) {
    return http.patch<StandardDocumentItem>(`/v1/standard-documents/${documentId}`, payload);
  },
  deleteDocument(documentId: string) {
    return http.delete<{ success: boolean }>(`/v1/standard-documents/${documentId}`);
  },
  listChunks(documentId: string) {
    return http.get<StandardDocumentChunkItem[]>(`/v1/standard-documents/${documentId}/chunks`);
  },
  retrieve(payload: StandardRetrievePayload) {
    return http.post<StandardRetrieveResult>("/v1/standards/retrieve", payload);
  },
};
