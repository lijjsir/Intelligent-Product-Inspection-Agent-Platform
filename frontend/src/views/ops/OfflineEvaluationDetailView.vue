<script setup lang="ts">
import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useOfflineEvaluationStore } from "@/stores/offlineEvaluation.store";

const store = useOfflineEvaluationStore();
</script>

<template>
  <AlgoResourceDetail
    title="离线评测详情"
    :store="store"
    back-path="/ops/eval/offline"
    :relation-sections="[
      { label: '评测集', value: (item) => item?.eval_set_id },
      { label: '目标类型', value: (item) => item?.target_type },
      { label: '目标资源', value: (item) => item?.target_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看离线评测任务的评测集引用、目标资源、执行状态和结果摘要。"
  />
</template>
