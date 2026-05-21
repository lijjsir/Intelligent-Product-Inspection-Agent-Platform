import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { Deployment, ModelDeploymentCreateRequest } from "@/types/algo-workspace.types";

export const useDeploymentStore = defineStore("deployment", () =>
  createAlgoResourceStore<Deployment, ModelDeploymentCreateRequest, Record<string, unknown>>({
    list: algoWorkspaceApi.listDeployments,
    get: algoWorkspaceApi.getDeployment,
    create: algoWorkspaceApi.createDeployment,
    update: algoWorkspaceApi.updateDeployment,
    remove: algoWorkspaceApi.removeDeployment,
    launch: algoWorkspaceApi.launchDeployment,
    cancel: algoWorkspaceApi.cancelDeployment,
    detailPath: (id) => `/ops/deployments/${id}`,
  }));
