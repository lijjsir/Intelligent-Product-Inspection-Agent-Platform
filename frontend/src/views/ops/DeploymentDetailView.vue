<script setup lang="ts">
import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useDeploymentStore } from "@/stores/deployment.store";

const store = useDeploymentStore();
</script>

<template>
  <AlgoResourceDetail
    title="部署详情"
    :store="store"
    back-path="/ops/deployments"
    :relation-sections="[
      { label: '来源类型', value: (item) => item?.source_type },
      { label: '来源资源', value: (item) => item?.source_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看部署记录的来源资源、执行状态和结果摘要。"
  />
</template>
