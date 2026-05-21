<script setup lang="ts">
import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useExperimentStore } from "@/stores/experiment.store";

const store = useExperimentStore();
</script>

<template>
  <AlgoResourceDetail
    title="实验详情"
    :store="store"
    back-path="/ops/experiments"
    intro="查看实验记录的基础信息、配置和结果摘要占位。"
  />
</template>
