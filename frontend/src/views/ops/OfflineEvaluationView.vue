<script setup lang="ts">
import { onMounted, reactive } from "vue";

import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import { useEvalDatasetStore } from "@/stores/evalDataset.store";
import { useExperimentStore } from "@/stores/experiment.store";
import { useFineTuneStore } from "@/stores/fineTune.store";
import { useOfflineEvaluationStore } from "@/stores/offlineEvaluation.store";
import { useTrainingJobStore } from "@/stores/trainingJob.store";

const store = useOfflineEvaluationStore();
const evalStore = useEvalDatasetStore();
const trainingStore = useTrainingJobStore();
const fineTuneStore = useFineTuneStore();
const experimentStore = useExperimentStore();
const refs = reactive({
  eval_set_id: "",
  target_type: "training_job",
  target_id: "",
  experiment_id: "",
});

function buildPayload(form: { name: string; description: string; config_json: string }) {
  if (!refs.eval_set_id || !refs.target_id) {
    throw new Error("missing-required-ref");
  }
  return {
    name: form.name,
    description: form.description,
    config_json: JSON.parse(form.config_json || "{}"),
    eval_set_id: refs.eval_set_id,
    target_type: refs.target_type,
    target_id: refs.target_id,
    experiment_id: refs.experiment_id || null,
  };
}

onMounted(async () => {
  await Promise.all([
    evalStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    trainingStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    fineTuneStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    experimentStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
  ]);
  refs.eval_set_id = evalStore.items[0]?.id || "";
  refs.target_id = trainingStore.items[0]?.id || "";
});
</script>

<template>
  <div v-if="!evalStore.items.length || (!trainingStore.items.length && !fineTuneStore.items.length)" class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <h2>离线评测</h2>
        <p>维护离线评测任务骨架，关联评测集与训练或微调目标。</p>
      </div>
    </section>
    <section class="card-surface p-8 text-center text-zinc-500">
      请先准备评测集，以及至少一个训练任务或微调任务。
    </section>
  </div>
  <AlgoResourcePage
    v-else
    title="离线评测"
    subtitle="维护离线评测任务骨架，关联评测集与训练或微调目标。"
    :store="store"
    :build-payload="buildPayload"
    :detail-description="(item) => `目标：${item?.target_type || '-'} / ${item?.target_id || '-'}`"
    show-launch
  >
    <template #form-extra>
      <el-form-item label="评测集">
        <el-select v-model="refs.eval_set_id" placeholder="选择评测集">
          <el-option v-for="item in evalStore.items" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="目标类型">
        <el-select v-model="refs.target_type">
          <el-option label="training_job" value="training_job" />
          <el-option label="fine_tune" value="fine_tune" />
        </el-select>
      </el-form-item>
      <el-form-item label="目标资源">
        <el-select v-model="refs.target_id" placeholder="选择目标">
          <el-option
            v-for="item in refs.target_type === 'training_job' ? trainingStore.items : fineTuneStore.items"
            :key="item.id"
            :label="item.name"
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
