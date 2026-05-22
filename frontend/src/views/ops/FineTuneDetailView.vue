<script setup lang="ts">
import { computed } from "vue";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useFineTuneStore } from "@/stores/fineTune.store";
import { buildTrainingSummaryViewModel } from "@/utils/algoResultSummary";

const store = useFineTuneStore();
const current = computed(() => store.current);
const summaryView = computed(() => buildTrainingSummaryViewModel(current.value));
</script>

<template>
  <AlgoResourceDetail
    title="微调详情"
    :store="store"
    back-path="/ops/training/fine-tune"
    :relation-sections="[
      { label: '训练任务', value: (item) => item?.training_job_id },
      { label: '基础模型', value: (item) => item?.model_config_ref?.display_name || item?.model_config_ref?.model_key || item?.model_config_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看微调任务的来源训练、有效超参数、产出物和执行日志。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  />
</template>
