import { http, type ApiRequestConfig } from "./http";
import type {
  RagNode,
  RagNodeCreateRequest,
  RagNodeUpdateRequest,
  RagSpace,
  RagSpaceCreateRequest,
  RagSpaceDocumentListItem,
  RagSpaceUpdateRequest,
} from "@/types/rag-space.types";

export const ragSpaceApi = {
  list(limit = 200, config?: ApiRequestConfig) {
    return http.get<RagSpace[]>("/v1/rag-spaces", { ...config, params: { ...config?.params, limit } });
  },

  getTree(ragSpaceId: string) {
    return http.get<RagNode[]>(`/v1/rag-spaces/${ragSpaceId}/tree`);
  },

  listDocuments(ragSpaceId: string, limit = 1000) {
    return http.get<RagSpaceDocumentListItem[]>(`/v1/rag-spaces/${ragSpaceId}/documents`, { params: { limit } });
  },

  create(payload: RagSpaceCreateRequest) {
    return http.post<RagSpace>("/v1/rag-spaces", payload);
  },

  updateSpace(ragSpaceId: string, payload: RagSpaceUpdateRequest) {
    return http.patch<RagSpace>(`/v1/rag-spaces/${ragSpaceId}`, payload);
  },

  createNode(ragSpaceId: string, payload: RagNodeCreateRequest) {
    return http.post<RagNode>(`/v1/rag-spaces/${ragSpaceId}/nodes`, payload);
  },

  updateNode(ragSpaceId: string, nodeId: string, payload: RagNodeUpdateRequest) {
    return http.patch<RagNode>(`/v1/rag-spaces/${ragSpaceId}/nodes/${nodeId}`, payload);
  },

  uploadDocuments(ragSpaceId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<RagNode[]>(`/v1/rag-spaces/${ragSpaceId}/documents`, form);
  },

  uploadDocumentsToNode(ragSpaceId: string, nodeId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<RagNode[]>(`/v1/rag-spaces/${ragSpaceId}/nodes/${nodeId}/documents`, form);
  },

  deleteNode(ragSpaceId: string, nodeId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/rag-spaces/${ragSpaceId}/nodes/${nodeId}`);
  },

  deleteSpace(ragSpaceId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/rag-spaces/${ragSpaceId}`);
  },

  deleteDocument(ragSpaceId: string, fileId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/rag-spaces/${ragSpaceId}/documents/${fileId}`);
  },
};
