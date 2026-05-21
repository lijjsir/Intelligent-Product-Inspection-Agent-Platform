import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { OnlineValidation, OnlineValidationCreateRequest } from "@/types/algo-workspace.types";

export const useOnlineValidationStore = defineStore("onlineValidation", () =>
  createAlgoResourceStore<OnlineValidation, OnlineValidationCreateRequest, Record<string, unknown>>({
    list: algoWorkspaceApi.listOnlineValidations,
    get: algoWorkspaceApi.getOnlineValidation,
    create: algoWorkspaceApi.createOnlineValidation,
    update: algoWorkspaceApi.updateOnlineValidation,
    remove: algoWorkspaceApi.removeOnlineValidation,
    launch: algoWorkspaceApi.launchOnlineValidation,
    cancel: algoWorkspaceApi.cancelOnlineValidation,
    detailPath: (id) => `/ops/eval/online/${id}`,
  }));
