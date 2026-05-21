<script setup lang="ts">
import { onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import { useDeploymentStore } from "@/stores/deployment.store";
import { useExperimentStore } from "@/stores/experiment.store";
import { useFineTuneStore } from "@/stores/fineTune.store";

const store = useDeploymentStore();
const fineTuneStore = useFineTuneStore();
const experimentStore = useExperimentStore();
const refs = reactive({
  source_type: "fine_tune",
  source_id: "",
  experiment_id: "",
});

function buildPayload(form: { name: string; description: string; config_json: string }) {
  if (!refs.source_id) {
    throw new Error("missing-required-ref");
  }
  return {
    name: form.name,
    description: form.description,
    config_json: JSON.parse(form.config_json || "{}"),
    source_type: refs.source_type,
    source_id: refs.source_id,
    experiment_id: refs.experiment_id || null,
  };
}

onMounted(async () => {
  await Promise.all([
    fineTuneStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    experimentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
  ]);
  refs.source_id = fineTuneStore.items[0]?.id || "";
});
</script>

<template>
  <div v-if="!fineTuneStore.items.length" class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <h2>部署记录</h2>
        <p>管理模型部署骨架，关联微调产物并承接后续在线验证。</p>
      </div>
    </section>
    <section class="card-surface p-8 text-center text-zinc-500">
      暂无可用微调任务，请先到“微调管理”创建上游资源。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="部署记录"
    subtitle="管理模型部署骨架，关联微调产物并承接后续在线验证。"
    :store="store"
    :build-payload="buildPayload"
    :detail-description="(item) => `来源：${item?.source_type || '-'} / ${item?.source_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="来源类型">
        <el-select v-model="refs.source_type">
          <el-option label="fine_tune" value="fine_tune" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源资源">
        <el-select v-model="refs.source_id" placeholder="选择微调任务">
          <el-option v-for="item in fineTuneStore.items" :key="item.id" :label="item.name" :value="item.id" />
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
