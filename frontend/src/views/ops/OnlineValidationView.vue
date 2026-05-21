<script setup lang="ts">
import { onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import { useDeploymentStore } from "@/stores/deployment.store";
import { useExperimentStore } from "@/stores/experiment.store";
import { useOnlineValidationStore } from "@/stores/onlineValidation.store";

const store = useOnlineValidationStore();
const deploymentStore = useDeploymentStore();
const experimentStore = useExperimentStore();
const refs = reactive({
  deployment_id: "",
  experiment_id: "",
});

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
  refs.deployment_id = deploymentStore.items[0]?.id || "";
});
</script>

<template>
  <div v-if="!deploymentStore.items.length" class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <h2>在线验证</h2>
        <p>围绕部署记录创建在线验证任务骨架，跟踪状态与结果占位。</p>
      </div>
    </section>
    <section class="card-surface p-8 text-center text-zinc-500">
      暂无可用部署记录，请先到“部署记录”创建上游资源。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="在线验证"
    subtitle="围绕部署记录创建在线验证任务骨架，跟踪状态与结果占位。"
    :store="store"
    :build-payload="buildPayload"
    :detail-description="(item) => `部署：${item?.deployment_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="部署记录">
        <el-select v-model="refs.deployment_id" placeholder="选择部署">
          <el-option v-for="item in deploymentStore.items" :key="item.id" :label="item.name" :value="item.id" />
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
