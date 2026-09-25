<script setup lang="ts">
import SupervisionAnalytics from "@/components/business/supervision/SupervisionAnalytics.vue";
import SupervisionAgentRail from "@/components/business/supervision/SupervisionAgentRail.vue";
import SupervisionModuleHeader from "@/components/business/supervision/SupervisionModuleHeader.vue";
</script>
<template>
  <main class="supervision-analytics-page">
    <SupervisionModuleHeader
      index="01"
      code="MKT"
      title="市场监控"
      agent-name="市场监控 Agent"
      tone="blue"
      description="持续分析企业、产品、地区、市场分布、抽查覆盖与暴露量变化，识别值得优先关注的对象。"
      principle="有分母才计算比率 · 数量变化不等于失效率"
    />
    <SupervisionAgentRail class="agent-navigation" />
    <SupervisionAnalytics />
  </main>
</template>

<style scoped>
.supervision-analytics-page {
  max-width: 1520px;
  margin: 0 auto;
  padding: 18px 18px 40px;
}

.agent-navigation {
  margin-top: 16px;
}

@media (max-width: 640px) {
  .supervision-analytics-page {
    padding: 0 0 24px;
  }
}
</style>
