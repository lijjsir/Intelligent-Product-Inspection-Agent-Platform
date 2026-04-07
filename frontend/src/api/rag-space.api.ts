import { http } from "./http";
import type { RagSpace, RagSpaceFile, RagSpaceCreateRequest } from "@/types/rag-space.types";

const RAG_SPACE_BASE_PATH = "/v1/rag-spaces";

export const ragSpaceApi = {
  list(limit = 200) {
    return http.get<RagSpace[]>(RAG_SPACE_BASE_PATH, { params: { limit } });
  },

  listDocuments(ragSpaceId: string, limit = 1000) {
    return http.get<RagSpaceFile[]>(`${RAG_SPACE_BASE_PATH}/${ragSpaceId}/documents`, { params: { limit } });
  },

  create(payload: RagSpaceCreateRequest) {
    return http.post<RagSpace>(RAG_SPACE_BASE_PATH, payload);
  },

  uploadDocuments(ragSpaceId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<RagSpaceFile[]>(`${RAG_SPACE_BASE_PATH}/${ragSpaceId}/documents`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  deleteDocument(ragSpaceId: string, fileId: string) {
    return http.delete<{ deleted: boolean }>(`${RAG_SPACE_BASE_PATH}/${ragSpaceId}/documents/${fileId}`);
  },
};
