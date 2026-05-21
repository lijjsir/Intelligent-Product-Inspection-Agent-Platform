<script setup lang="ts">
import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useOnlineValidationStore } from "@/stores/onlineValidation.store";

const store = useOnlineValidationStore();
</script>

<template>
  <AlgoResourceDetail
    title="在线验证详情"
    :store="store"
    back-path="/ops/eval/online"
    :relation-sections="[
      { label: '部署记录', value: (item) => item?.deployment_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看在线验证任务的部署关联、执行状态和结果摘要。"
  />
</template>
