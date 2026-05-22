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
  />
</template>
