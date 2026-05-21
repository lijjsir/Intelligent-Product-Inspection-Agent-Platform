import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { FineTuneRun, FineTuneRunCreateRequest, FineTuneRunUpdateRequest } from "@/types/algo-workspace.types";

export const useFineTuneStore = defineStore("fineTune", () =>
  createAlgoResourceStore<FineTuneRun, FineTuneRunCreateRequest, FineTuneRunUpdateRequest>({
    list: algoWorkspaceApi.listFineTunes,
    get: algoWorkspaceApi.getFineTune,
    create: algoWorkspaceApi.createFineTune,
    update: algoWorkspaceApi.updateFineTune,
    remove: algoWorkspaceApi.removeFineTune,
    launch: algoWorkspaceApi.launchFineTune,
    cancel: algoWorkspaceApi.cancelFineTune,
    detailPath: (id) => `/ops/training/fine-tune/${id}`,
  }));
