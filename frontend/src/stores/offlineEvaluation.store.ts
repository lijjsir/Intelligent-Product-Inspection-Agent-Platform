import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { OfflineEvaluation, OfflineEvaluationCreateRequest, OfflineEvaluationUpdateRequest } from "@/types/algo-workspace.types";

export const useOfflineEvaluationStore = defineStore("offlineEvaluation", () =>
  createAlgoResourceStore<OfflineEvaluation, OfflineEvaluationCreateRequest, OfflineEvaluationUpdateRequest>({
    list: algoWorkspaceApi.listOfflineEvaluations,
    get: algoWorkspaceApi.getOfflineEvaluation,
    create: algoWorkspaceApi.createOfflineEvaluation,
    update: algoWorkspaceApi.updateOfflineEvaluation,
    remove: algoWorkspaceApi.removeOfflineEvaluation,
    launch: algoWorkspaceApi.launchOfflineEvaluation,
    cancel: algoWorkspaceApi.cancelOfflineEvaluation,
    detailPath: (id) => `/ops/eval/offline/${id}`,
  }));
