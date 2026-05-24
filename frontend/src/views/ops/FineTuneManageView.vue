<script setup lang="ts">
import { onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import { useDatasetStore } from "@/stores/dataset.store";
import { useEvalDatasetStore } from "@/stores/evalDataset.store";
import { useExperimentStore } from "@/stores/experiment.store";
import { useFineTuneStore } from "@/stores/fineTune.store";
import { useModelConfigStore } from "@/stores/model_config.store";

const store = useFineTuneStore();
const datasetStore = useDatasetStore();
const evalStore = useEvalDatasetStore();
const experimentStore = useExperimentStore();
const modelConfigStore = useModelConfigStore();
const refs = reactive({
  source_dataset_id: "",
  eval_set_id: "",
  model_config_id: "",
  experiment_id: "",
  lora_rank: 16,
  lora_alpha: 32,
  lora_dropout: 0.05,
  target_modules_text: "q_proj,v_proj",
});

function parseTargetModules() {
  return refs.target_modules_text.split(",").map((item) => item.trim()).filter(Boolean);
}

function buildPayload(form: { name: string; description: string; config_json: string }) {
  if (!refs.source_dataset_id || !refs.model_config_id) {
    throw new Error("missing-required-ref");
  }
  const configJson = JSON.parse(form.config_json || "{}");
  configJson.lora = {
    rank: refs.lora_rank,
    alpha: refs.lora_alpha,
    dropout: refs.lora_dropout,
    target_modules: parseTargetModules(),
  };
  return {
    name: form.name,
    description: form.description,
    config_json: configJson,
    source_dataset_id: refs.source_dataset_id,
    eval_set_id: refs.eval_set_id || null,
    model_config_id: refs.model_config_id,
    experiment_id: refs.experiment_id || null,
  };
}

onMounted(async () => {
  await Promise.all([
    datasetStore.fetchDatasets({ page: 1, size: 100, keyword: "", modality: "", status: "" }),
    evalStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    experimentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    modelConfigStore.fetchAll(),
  ]);
  refs.source_dataset_id = datasetStore.items.find((item: any) => item.status === "active")?.id || "";
  refs.eval_set_id = evalStore.items[0]?.id || "";
  refs.model_config_id = modelConfigStore.items.find((item) => item.is_active && ["chat", "multimodal"].includes(item.model_type))?.id || "";
});

function populateForm(item: {
  source_dataset_id?: string;
  eval_set_id?: string | null;
  model_config_id?: string;
  experiment_id?: string | null;
  config_json?: Record<string, any> | null;
}) {
  refs.source_dataset_id = item.source_dataset_id || datasetStore.items.find((row: any) => row.status === "active")?.id || "";
  refs.eval_set_id = item.eval_set_id || "";
  refs.model_config_id = item.model_config_id || modelConfigStore.items.find((row) => row.is_active && ["chat", "multimodal"].includes(row.model_type))?.id || "";
  refs.experiment_id = item.experiment_id || "";
  const lora = item.config_json?.lora || {};
  refs.lora_rank = Number(lora.rank || 16);
  refs.lora_alpha = Number(lora.alpha || 32);
  refs.lora_dropout = Number(lora.dropout || 0.05);
  refs.target_modules_text = Array.isArray(lora.target_modules) ? lora.target_modules.join(",") : "q_proj,v_proj";
}
</script>

<template>
  <div v-if="!datasetStore.items.length" class="flex flex-col gap-5">
    <AlgoWorkspaceHero title="微调管理" description="管理 LoRA 微调任务，直接绑定源数据集与 Base Model。" />
    <section class="card-surface p-8 text-center text-zinc-500">
      暂无可用数据集，请先到“数据接入”准备训练数据。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="微调管理"
    subtitle="管理 LoRA 微调任务，直接绑定源数据集与 Base Model。"
    :store="store"
    :build-payload="buildPayload"
    :populate-form="populateForm"
    :detail-description="(item) => `数据集：${item?.source_dataset_id || '-'}；基础模型：${item?.model_config_ref?.display_name || item?.model_config_ref?.model_key || item?.model_config_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="源数据集">
        <el-select v-model="refs.source_dataset_id" placeholder="选择数据集">
          <el-option v-for="item in datasetStore.items.filter((row: any) => row.status === 'active')" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="验证评测集">
        <el-select v-model="refs.eval_set_id" clearable placeholder="可选">
          <el-option v-for="item in evalStore.items" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="基础模型">
        <el-select v-model="refs.model_config_id" placeholder="选择模型配置">
          <el-option
            v-for="item in modelConfigStore.items.filter((config) => config.is_active && ['chat', 'multimodal'].includes(config.model_type))"
            :key="item.id"
            :label="`${item.display_name} (${item.source_type}:${item.source_uri})`"
            :value="item.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="LoRA Rank">
        <el-input-number v-model="refs.lora_rank" :min="1" :max="512" />
      </el-form-item>
      <el-form-item label="LoRA Alpha">
        <el-input-number v-model="refs.lora_alpha" :min="1" :max="1024" />
      </el-form-item>
      <el-form-item label="LoRA Dropout">
        <el-input-number v-model="refs.lora_dropout" :min="0" :max="1" :step="0.01" />
      </el-form-item>
      <el-form-item label="Target Modules">
        <el-input v-model="refs.target_modules_text" placeholder="q_proj,v_proj" />
      </el-form-item>
      <el-form-item label="实验">
        <el-select v-model="refs.experiment_id" clearable placeholder="选择实验">
          <el-option v-for="item in experimentStore.items" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
    </template>
  </AlgoResourcePage>
</template>
