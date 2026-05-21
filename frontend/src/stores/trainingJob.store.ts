import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import { createAlgoResourceStore } from "@/stores/algo-resource-factories";
import type { TrainingJob, TrainingJobCreateRequest, TrainingJobUpdateRequest } from "@/types/algo-workspace.types";

export const useTrainingJobStore = defineStore("trainingJob", () =>
  createAlgoResourceStore<TrainingJob, TrainingJobCreateRequest, TrainingJobUpdateRequest>({
    list: algoWorkspaceApi.listTrainingJobs,
    get: algoWorkspaceApi.getTrainingJob,
    create: algoWorkspaceApi.createTrainingJob,
    update: algoWorkspaceApi.updateTrainingJob,
    remove: algoWorkspaceApi.removeTrainingJob,
    launch: algoWorkspaceApi.launchTrainingJob,
    cancel: algoWorkspaceApi.cancelTrainingJob,
  }));
