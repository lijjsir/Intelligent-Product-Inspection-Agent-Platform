<script setup lang="ts">
import { computed } from "vue";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useTrainingJobStore } from "@/stores/trainingJob.store";
import { buildTrainingSummaryViewModel } from "@/utils/algoResultSummary";

const store = useTrainingJobStore();
const current = computed(() => store.current);
const summaryView = computed(() => buildTrainingSummaryViewModel(current.value));
</script>

<template>
  <AlgoResourceDetail
    title="训练任务详情"
    :store="store"
    back-path="/ops/training/jobs"
    :relation-sections="[
      { label: '来源数据集', value: (item) => item?.source_dataset_id },
      { label: '训练模型', value: (item) => item?.model_config_ref?.display_name || item?.model_config_ref?.model_key || item?.model_config_id },
      { label: '评测集', value: (item) => item?.eval_set_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看训练任务配置、执行状态、训练指标和产物日志。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  >
    <section v-if="current?.execution_mode === 'gpu_ssh'" class="card-surface p-4">
      <h3 class="mb-3">GPU 执行信息</h3>
      <p class="text-sm text-slate-600">当前任务通过 SSH 裸机 GPU 节点执行，详细节点与命令摘要见上方关键指标与结果摘要。</p>
    </section>
    <section v-if="summaryView.artifacts.length" class="card-surface p-4">
      <h3 class="mb-4">关键产物下载</h3>
      <div class="flex flex-wrap gap-3">
        <a
          v-for="artifact in summaryView.artifacts.filter((item) => item.link)"
          :key="artifact.title"
          class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-cyan-400 hover:text-cyan-700"
          :href="artifact.link || undefined"
          target="_blank"
          rel="noreferrer"
        >
          {{ artifact.title }}
        </a>
      </div>
    </section>
  </AlgoResourceDetail>
</template>
