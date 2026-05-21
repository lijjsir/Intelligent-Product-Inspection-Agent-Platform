import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { Experiment, ExperimentCreateRequest } from "@/types/algo-workspace.types";

export const useExperimentStore = defineStore("experiment", () =>
  createAlgoResourceStore<Experiment, ExperimentCreateRequest, Record<string, unknown>>({
    list: algoWorkspaceApi.listExperiments,
    get: algoWorkspaceApi.getExperiment,
    create: algoWorkspaceApi.createExperiment,
    update: algoWorkspaceApi.updateExperiment,
    remove: algoWorkspaceApi.removeExperiment,
    detailPath: (id) => `/ops/experiments/${id}`,
  }));
