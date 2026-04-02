import { http } from "./http";
import type { RagSpace, RagSpaceFile, RagSpaceCreateRequest } from "@/types/rag-space.types";

export const ragSpaceApi = {
  list(limit = 200) {
    return http.get<RagSpace[]>("/v1/rag-spaces", { params: { limit } });
  },

  listDocuments(ragSpaceId: string, limit = 1000) {
    return http.get<RagSpaceFile[]>(`/v1/rag-spaces/${ragSpaceId}/documents`, { params: { limit } });
  },

  create(payload: RagSpaceCreateRequest) {
    return http.post<RagSpace>("/v1/rag-spaces", payload);
  },

  uploadDocuments(ragSpaceId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<RagSpaceFile[]>(`/v1/rag-spaces/${ragSpaceId}/documents`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  deleteDocument(ragSpaceId: string, fileId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/rag-spaces/${ragSpaceId}/documents/${fileId}`);
  },
};
