<script setup lang="ts">
import { computed, onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import { useDeploymentStore } from "@/stores/deployment.store";
import { useExperimentStore } from "@/stores/experiment.store";
import { useOnlineValidationStore } from "@/stores/onlineValidation.store";

const store = useOnlineValidationStore();
const deploymentStore = useDeploymentStore();
const experimentStore = useExperimentStore();
const completedDeployments = computed(() => deploymentStore.items.filter((item) => item.status === "completed"));
const refs = reactive({
  deployment_id: "",
  experiment_id: "",
});

function isCompleted(item: { status?: string }) {
  return item.status === "completed";
}

function buildPayload(form: { name: string; description: string; config_json: string }) {
  if (!refs.deployment_id) {
    throw new Error("missing-required-ref");
  }
  return {
    name: form.name,
    description: form.description,
    config_json: JSON.parse(form.config_json || "{}"),
    deployment_id: refs.deployment_id,
    experiment_id: refs.experiment_id || null,
  };
}

onMounted(async () => {
  await Promise.all([
    deploymentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    experimentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
  ]);
  refs.deployment_id = completedDeployments.value[0]?.id || "";
});
</script>

<template>
  <div v-if="!completedDeployments.length" class="flex flex-col gap-5">
    <AlgoWorkspaceHero title="在线验证" description="围绕部署记录创建在线验证任务骨架，跟踪状态与结果占位。" />
    <section class="card-surface p-8 text-center text-zinc-500">
      暂无可用部署记录，请先到“部署记录”创建上游资源。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="在线验证"
    subtitle="围绕已完成部署创建在线验证任务，展示影子回放汇总与执行日志。"
    :store="store"
    :build-payload="buildPayload"
    :detail-description="(item) => `部署：${item?.deployment_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="部署记录">
        <el-select v-model="refs.deployment_id" placeholder="选择已完成部署">
          <el-option v-for="item in completedDeployments" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="实验">
        <el-select v-model="refs.experiment_id" clearable placeholder="选择实验">
          <el-option v-for="item in experimentStore.items" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
    </template>
  </AlgoResourcePage>
</template>
