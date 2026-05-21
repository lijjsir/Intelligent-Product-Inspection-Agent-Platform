<script setup lang="ts">
import { onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import { useExperimentStore } from "@/stores/experiment.store";
import { useFineTuneStore } from "@/stores/fineTune.store";
import { useModelConfigStore } from "@/stores/model_config.store";
import { useTrainingJobStore } from "@/stores/trainingJob.store";

const store = useFineTuneStore();
const trainingStore = useTrainingJobStore();
const experimentStore = useExperimentStore();
const modelConfigStore = useModelConfigStore();
const refs = reactive({
  training_job_id: "",
  model_config_id: "",
  experiment_id: "",
});

function buildPayload(form: { name: string; description: string; config_json: string }) {
  if (!refs.training_job_id || !refs.model_config_id) {
    throw new Error("missing-required-ref");
  }
  return {
    name: form.name,
    description: form.description,
    config_json: JSON.parse(form.config_json || "{}"),
    training_job_id: refs.training_job_id,
    model_config_id: refs.model_config_id,
    experiment_id: refs.experiment_id || null,
  };
}

onMounted(async () => {
  await Promise.all([
    trainingStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    experimentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    modelConfigStore.fetchAll(),
  ]);
  refs.training_job_id = trainingStore.items[0]?.id || "";
  refs.model_config_id = modelConfigStore.items.find((item) => item.is_active && ["chat", "multimodal"].includes(item.model_type))?.id || "";
});

function populateForm(item: {
  training_job_id?: string;
  model_config_id?: string;
  experiment_id?: string | null;
}) {
  refs.training_job_id = item.training_job_id || trainingStore.items[0]?.id || "";
  refs.model_config_id = item.model_config_id || modelConfigStore.items.find((row) => row.is_active && ["chat", "multimodal"].includes(row.model_type))?.id || "";
  refs.experiment_id = item.experiment_id || "";
}
</script>

<template>
  <div v-if="!trainingStore.items.length" class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <h2>微调管理</h2>
        <p>管理微调运行骨架，关联训练任务和基础模型。</p>
      </div>
    </section>
    <section class="card-surface p-8 text-center text-zinc-500">
      暂无可用训练任务，请先到“训练任务”创建上游资源。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="微调管理"
    subtitle="管理微调运行骨架，关联训练任务和基础模型。"
    :store="store"
    :build-payload="buildPayload"
    :populate-form="populateForm"
    :detail-description="(item) => `训练任务：${item?.training_job_id || '-'}；基础模型：${item?.model_config_ref?.display_name || item?.model_config_ref?.model_key || item?.model_config_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="训练任务">
        <el-select v-model="refs.training_job_id" placeholder="选择训练任务">
          <el-option v-for="item in trainingStore.items" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="基础模型">
        <el-select v-model="refs.model_config_id" placeholder="选择模型配置">
          <el-option
            v-for="item in modelConfigStore.items.filter((config) => config.is_active && ['chat', 'multimodal'].includes(config.model_type))"
            :key="item.id"
            :label="`${item.display_name} (${item.model_key})`"
            :value="item.id"
          />
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
