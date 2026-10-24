<script setup lang="ts">
import { ref } from "vue";
import SupervisionAnalytics from "@/components/business/supervision/SupervisionAnalytics.vue";
import MarketMonitoring from "@/components/business/supervision/MarketMonitoring.vue";
import { useAuthStore } from "@/stores/auth.store";
const auth = useAuthStore();
const analyticsOpened = ref(false);
</script>
<template>
  <main class="supervision-analytics-page">
    <MarketMonitoring v-if="auth.hasPermission('quality_material_read_business')" />
    <el-alert
      v-else
      title="原始资料监测目前向管理员和研判专家开放，请使用对应账号进入。"
      type="info"
      :closable="false"
    />
    <details class="legacy-stats" @toggle="analyticsOpened ||= ($event.target as HTMLDetailsElement).open">
      <summary>已确认风险与抽查统计</summary>
      <SupervisionAnalytics v-if="analyticsOpened" />
    </details>
  </main>
</template>

<style scoped>
.supervision-analytics-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px;
}

.legacy-stats {
  margin-top: 24px;
  border-top: 1px solid var(--el-border-color-light);
}
.legacy-stats summary {
  padding: 16px 0;
  cursor: pointer;
  font-size: 13px;
}

@media (max-width: 640px) {
  .supervision-analytics-page {
    padding: 0 0 24px;
  }
}
</style>
