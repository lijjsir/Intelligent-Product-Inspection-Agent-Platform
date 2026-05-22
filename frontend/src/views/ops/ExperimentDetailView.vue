<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useExperimentStore } from "@/stores/experiment.store";
import { buildExperimentSummaryViewModel, summarizeMetrics } from "@/utils/algoResultSummary";
import type { ExperimentRelatedResourceSummary } from "@/types/algo-workspace.types";

const route = useRoute();
const store = useExperimentStore();
const current = computed(() => store.current);
const relatedResources = computed(() => current.value?.related_resources);
const summaryView = computed(() => buildExperimentSummaryViewModel(current.value));

function deploymentEndpoint(item: ExperimentRelatedResourceSummary) {
  const metrics = item?.metrics || {};
  return String(metrics.endpoint || metrics.endpoint_placeholder || "-");
}

function deploymentStatus(item: ExperimentRelatedResourceSummary) {
  const metrics = item?.metrics || {};
  return String(metrics.status || item?.status || "-");
}

function deploymentModel(item: ExperimentRelatedResourceSummary) {
  const metrics = item?.metrics || {};
  return String(metrics.model_key || "-");
}

function summarizeOfflineMetrics(item: Record<string, any>) {
  return summarizeMetrics(item?.metrics || {}, [
    { key: "accuracy", label: "accuracy" },
    { key: "f1", label: "f1" },
    { key: "mAP", label: "mAP" },
  ]);
}

function summarizeDeploymentMetrics(item: Record<string, any>) {
  return summarizeMetrics(item?.metrics || {}, [
    { key: "endpoint", label: "endpoint" },
    { key: "endpoint_placeholder", label: "endpoint" },
    { key: "status", label: "status" },
    { key: "model_key", label: "model" },
  ]);
}

async function load() {
  const id = String(route.params.id || "");
  if (!id) return;
  await store.fetchOne(id);
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <AlgoResourceDetail
    title="实验详情"
    :store="store"
    back-path="/ops/experiments"
    intro="查看实验下关联的训练、微调、离线评测和部署资源。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  >
    <section class="grid gap-5 md:grid-cols-2">
      <article class="card-surface p-4">
        <h3 class="mb-4">训练任务</h3>
        <el-empty v-if="!relatedResources?.training_jobs?.length" description="暂无关联训练任务" />
        <el-table v-else :data="relatedResources?.training_jobs">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="metrics.best_val_accuracy" label="最佳精度" min-width="140" />
        </el-table>
      </article>
      <article class="card-surface p-4">
        <h3 class="mb-4">微调任务</h3>
        <el-empty v-if="!relatedResources?.fine_tunes?.length" description="暂无关联微调任务" />
        <el-table v-else :data="relatedResources?.fine_tunes">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="metrics.best_val_accuracy" label="最佳精度" min-width="140" />
        </el-table>
      </article>
      <article class="card-surface p-4">
        <h3 class="mb-4">离线评测</h3>
        <el-empty v-if="!relatedResources?.offline_evaluations?.length" description="暂无关联离线评测" />
        <el-table v-else :data="relatedResources?.offline_evaluations">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="metrics.accuracy" label="Accuracy" min-width="120" />
          <el-table-column label="摘要" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ summarizeOfflineMetrics(row) || "-" }}</span>
            </template>
          </el-table-column>
        </el-table>
      </article>
      <article class="card-surface p-4">
        <h3 class="mb-4">部署记录</h3>
        <el-empty v-if="!relatedResources?.deployments?.length" description="暂无关联部署" />
        <el-table v-else :data="relatedResources?.deployments">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column label="运行状态" width="140">
            <template #default="{ row }">
              <span>{{ deploymentStatus(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="模型" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ deploymentModel(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="入口" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ deploymentEndpoint(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="运行时注册" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ summarizeDeploymentMetrics(row) || "-" }}</span>
            </template>
          </el-table-column>
        </el-table>
      </article>
    </section>
  </AlgoResourceDetail>
</template>
