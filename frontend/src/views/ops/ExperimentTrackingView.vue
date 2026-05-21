<script setup lang="ts">
import AlgoResourcePage from "@/components/business/algo/AlgoResourcePage.vue";
import { useExperimentStore } from "@/stores/experiment.store";

const store = useExperimentStore();

function buildPayload(form: { name: string; description: string; config_json: string }) {
  return {
    name: form.name,
    description: form.description,
    config_json: JSON.parse(form.config_json || "{}"),
  };
}
</script>

<template>
  <AlgoResourcePage
    title="实验追踪"
    subtitle="管理算法工程师实验骨架，统一承接训练、微调、评测和部署的链路关联。"
    :store="store"
    :build-payload="buildPayload"
  />
</template>
