<script setup lang="ts">
import type { OverviewStats } from "@/types/analytics.types";

interface Props {
  overview: OverviewStats;
  redRate: number;
}

defineProps<Props>();
</script>

<template>
  <section class="metric-grid">
    <el-card shadow="never" class="metric-card">
      <div class="metric-label">总任务</div>
      <div class="metric-value">{{ overview.total_tasks }}</div>
    </el-card>
    <el-card shadow="never" class="metric-card success">
      <div class="metric-label">通过率</div>
      <div class="metric-value">{{ (overview.pass_rate * 100).toFixed(1) }}%</div>
    </el-card>
    <el-card shadow="never" class="metric-card warning">
      <div class="metric-label">幻觉率</div>
      <div class="metric-value">{{ (overview.hallucination_rate * 100).toFixed(1) }}%</div>
    </el-card>
    <el-card shadow="never" class="metric-card amber">
      <div class="metric-label">平均风险分</div>
      <div class="metric-value">{{ overview.avg_risk_score.toFixed(1) }}</div>
    </el-card>
    <el-card shadow="never" class="metric-card danger">
      <div class="metric-label">RED 占比</div>
      <div class="metric-value">{{ (redRate * 100).toFixed(1) }}%</div>
    </el-card>
    <el-card shadow="never" class="metric-card slate">
      <div class="metric-label">平均耗时</div>
      <div class="metric-value">{{ overview.avg_latency_ms.toFixed(0) }} ms</div>
    </el-card>
  </section>
</template>

<style scoped>
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; }
.metric-card { border-radius: 20px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.metric-card :deep(.el-card__body) { display: grid; gap: 10px; }
.metric-label { color: #5b6472; font-size: 13px; }
.metric-value { color: #0f172a; font-size: 34px; font-weight: 800; line-height: 1; }
.metric-card.success .metric-value { color: #15803d; }
.metric-card.warning .metric-value { color: #d97706; }
.metric-card.amber .metric-value { color: #b45309; }
.metric-card.danger .metric-value { color: #dc2626; }
.metric-card.slate .metric-value { color: #1d4ed8; }
@media (max-width: 1400px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 960px) { .metric-grid { grid-template-columns: 1fr; } }
</style>
