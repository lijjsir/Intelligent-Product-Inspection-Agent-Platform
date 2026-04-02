<script setup lang="ts">
// 已合并至 AnalyticsView.vue 的 tracing tab
// 本文件保留用于兼容期，第二阶段可删除
import { onMounted } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();

onMounted(() => {
  router.replace({ name: "ops-analytics", query: { tab: "tracing" } });
});
</script>

<template>
  <div />
</template>
