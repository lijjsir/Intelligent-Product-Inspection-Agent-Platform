<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { useECharts } from "@/composables/useECharts";

const store = useAgentOpsStore();
const loading = computed(() => store.loading);
const ragAnalysis = computed(() => store.ragAnalysis);

const { chartRef: hitRateChartRef, setOption: setHitRateOption } = useECharts();
const { chartRef: latencyChartRef, setOption: setLatencyOption } = useECharts();

onMounted(async () => {
  await store.fetchRagAnalysis();
  if (ragAnalysis.value) {
    updateCharts();
  }
});

function updateCharts() {
  if (!ragAnalysis.value) return;

  setHitRateOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["命中率", "引用覆盖率"], bottom: 0 },
    xAxis: {
      type: "category",
      data: ragAnalysis.value.recent_items.map((item) =>
        new Date(item.created_at).toLocaleTimeString()
      ),
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: { formatter: "{value}" },
    },
    series: [
      {
        name: "命中率",
        type: "line",
        data: ragAnalysis.value.recent_items.map((item) => item.hit_rate),
        smooth: true,
        lineStyle: { color: "#2563A8", width: 2 },
        itemStyle: { color: "#2563A8" },
      },
      {
        name: "引用覆盖率",
        type: "line",
        data: ragAnalysis.value.recent_items.map((item) => item.citation_coverage),
        smooth: true,
        lineStyle: { color: "#16A34A", width: 2 },
        itemStyle: { color: "#16A34A" },
      },
    ],
    grid: { left: 50, right: 20, top: 20, bottom: 60 },
  });

  setLatencyOption({
    tooltip: { trigger: "axis", formatter: "{b}: {c} ms" },
    xAxis: {
      type: "category",
      data: ragAnalysis.value.recent_items.map((item) =>
        new Date(item.created_at).toLocaleTimeString()
      ),
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: "{value} ms" },
    },
    series: [
      {
        name: "延迟",
        type: "bar",
        data: ragAnalysis.value.recent_items.map((item) => item.latency_ms),
        itemStyle: { color: "#D97706" },
      },
    ],
    grid: { left: 60, right: 20, top: 20, bottom: 60 },
  });
}

const statCards = computed(() => {
  if (!ragAnalysis.value) return [];
  const stats = ragAnalysis.value.stats;
  return [
    { label: "总查询数", value: stats.total_queries, icon: "📊", color: "#3B82F6" },
    { label: "平均命中率", value: `${(stats.avg_hit_rate * 100).toFixed(1)}%`, icon: "🎯", color: "#16A34A" },
    { label: "平均引用覆盖率", value: `${(stats.avg_citation_coverage * 100).toFixed(1)}%`, icon: "📝", color: "#2563A8" },
    { label: "空召回次数", value: stats.empty_recall_count, icon: "⚠️", color: "#D97706" },
    { label: "平均延迟", value: `${stats.avg_latency_ms.toFixed(0)} ms`, icon: "⏱️", color: "#8B5CF6" },
  ];
});
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>RAG 召回分析</h1>
      <p class="subtitle">监控和分析 RAG 检索效果，优化召回质量</p>
    </div>

    <div v-loading="loading">
      <div class="stat-cards">
        <div v-for="card in statCards" :key="card.label" class="stat-card">
          <div class="stat-icon" :style="{ background: card.color + '20', color: card.color }">
            {{ card.icon }}
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <el-row :gutter="16" class="chart-row">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>
              <span>命中率 & 引用覆盖率趋势</span>
            </template>
            <div ref="hitRateChartRef" style="height: 300px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>
              <span>查询延迟分布</span>
            </template>
            <div ref="latencyChartRef" style="height: 300px" />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt-4">
        <template #header>
          <span>最近查询记录</span>
        </template>
        <el-table :data="ragAnalysis?.recent_items || []" stripe max-height="400">
          <el-table-column prop="task_id" label="任务 ID" width="200" show-overflow-tooltip />
          <el-table-column prop="query" label="查询内容" min-width="250" show-overflow-tooltip />
          <el-table-column label="命中率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.hit_rate * 100" :stroke-width="8" :show-text="false" />
              <span class="text-xs">{{ (row.hit_rate * 100).toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column label="引用覆盖率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.citation_coverage * 100" :stroke-width="8" :show-text="false" color="#16A34A" />
              <span class="text-xs">{{ (row.citation_coverage * 100).toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="latency_ms" label="延迟(ms)" width="100" sortable />
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="{ row }">
              {{ new Date(row.created_at).toLocaleString() }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100%;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
}
.subtitle {
  color: #909399;
  margin: 0;
}
.stat-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}
.stat-content {
  flex: 1;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
}
.stat-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
.chart-row {
  margin-bottom: 16px;
}
.mt-4 {
  margin-top: 16px;
}
.text-xs {
  font-size: 12px;
  color: #6b7280;
}
</style>
