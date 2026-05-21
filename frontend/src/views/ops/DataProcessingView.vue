<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

onMounted(() => {
  const datasetId = String(route.query.datasetId || route.query.id || "");
  if (datasetId) {
    router.replace({ path: `/ops/data/import/${datasetId}`, query: { tab: String(route.query.tab || "overview") } });
    return;
  }
  router.replace({ path: "/ops/data/import", query: { tab: "eval-sets" } });
});
</script>

<template>
  <div class="p-6 text-zinc-500">正在跳转...</div>
</template>
