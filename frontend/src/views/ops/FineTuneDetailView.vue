<script setup lang="ts">
import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useFineTuneStore } from "@/stores/fineTune.store";

const store = useFineTuneStore();
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
    intro="查看微调任务的关联训练任务、基础模型、执行状态和结果摘要。"
  />
</template>
