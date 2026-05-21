import { http } from "./http";
import type {
  PromptDefinitionSummary,
  PromptDefinitionDetail,
  PromptOverview,
  DiffResponse,
  SyncScanResponse,
} from "@/types/prompt-admin.types";

export const promptAdminApi = {
  getOverview() {
    return http.get<PromptOverview>("/v1/prompt-admin/overview");
  },

  listDefinitions(params?: {
    agent_key?: string;
    stage_key?: string;
    keyword?: string;
    sync_status?: string;
  }) {
    return http.get<PromptDefinitionSummary[]>("/v1/prompt-admin/definitions", { params });
  },

  getDefinition(promptKey: string) {
    return http.get<PromptDefinitionDetail>(`/v1/prompt-admin/definitions/${encodeURIComponent(promptKey)}`);
  },

  createVersion(promptKey: string, payload: { content: string; change_summary?: string; base_hash?: string }) {
    return http.post<{ version_id: string; version: number; status: string }>(
      `/v1/prompt-admin/definitions/${encodeURIComponent(promptKey)}/versions`,
      payload,
    );
  },

  publishVersion(versionId: string) {
    return http.post<{ version_id: string; version: number; status: string }>(
      `/v1/prompt-admin/versions/${versionId}/publish`,
    );
  },

  rollbackDefinition(promptKey: string, targetVersionId: string) {
    return http.post<{ version_id: string; version: number; status: string }>(
      `/v1/prompt-admin/definitions/${encodeURIComponent(promptKey)}/rollback`,
      { target_version_id: targetVersionId },
    );
  },

  getDiff(promptKey: string, left: string = "code_default", right: string = "active") {
    return http.get<DiffResponse>(`/v1/prompt-admin/definitions/${encodeURIComponent(promptKey)}/diff`, {
      params: { left, right },
    });
  },

  scanCodePrompts() {
    return http.post<SyncScanResponse>("/v1/prompt-admin/sync/scan");
  },
};
