<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { graphic, init, type ECharts, use } from "echarts/core";

import { useAlertStore } from "@/stores/alert.store";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useTaskStore } from "@/stores/task.store";
import { usePermission } from "@/composables/usePermission";

const router = useRouter();
const analyticsStore = useAnalyticsStore();
const taskStore = useTaskStore();
const alertStore = useAlertStore();
const { hasRole } = usePermission();

const trendRef = ref<HTMLElement | null>(null);
const riskRef = ref<HTMLElement | null>(null);
let trendChart: ECharts | null = null;
let riskChart: ECharts | null = null;

use([CanvasRenderer, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent]);

const overview = computed(() => analyticsStore.overview);
const openAlerts = computed(() => alertStore.items.slice(0, 5));
const recentTasks = computed(() => taskStore.items.slice(0, 10));
const selectedRange = ref<7 | 30 | 90>(30);
const isAdmin = computed(() => hasRole("admin"));
const scopeLabel = computed(() => (overview.value?.scope_kind === "global" ? "全部组织" : "当前组织"));
const highRiskAlerts = computed(() =>
  openAlerts.value.filter((item) => ["critical", "warning", "error", "high"].includes(String(item.severity).toLowerCase())).length,
);

onMounted(async () => {
  await fetchDashboard();
  await nextTick();
  renderCharts();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  trendChart?.dispose();
  riskChart?.dispose();
  window.removeEventListener("resize", handleResize);
});

watch(overview, async () => {
  await nextTick();
  renderCharts();
});

async function setRange(days: 7 | 30 | 90) {
  selectedRange.value = days;
  await fetchDashboard();
}

async function fetchDashboard() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (selectedRange.value - 1));
  await Promise.all([
    analyticsStore.fetchOverview({
      start_date: formatDate(start),
      end_date: formatDate(end),
    }),
    taskStore.fetchTasks({ page: 1, size: 10 }),
    alertStore.fetchAlerts({ page: 1, size: 5, status: "open" }),
  ]);
}

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function handleResize() {
  trendChart?.resize();
  riskChart?.resize();
}

function renderCharts() {
  if (!overview.value) return;

  if (trendRef.value) {
    trendChart ??= init(trendRef.value);
    trendChart.setOption({
      animationDuration: 500,
      color: ["#0f766e"],
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%`,
      },
      grid: { left: 40, right: 24, top: 28, bottom: 32 },
      xAxis: {
        type: "category",
        data: overview.value.pass_rate_trend.map((item) => item.bucket),
        axisLabel: { color: "#52606d" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: "#52606d",
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
        splitLine: { lineStyle: { color: "rgba(40,56,78,0.08)" } },
      },
      series: [
        {
          name: "通过率",
          type: "line",
          smooth: true,
          symbolSize: 8,
          data: overview.value.pass_rate_trend.map((item) => item.value),
          lineStyle: { width: 3, color: "#0f766e" },
          itemStyle: { color: "#0f766e" },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(15,118,110,0.24)" },
              { offset: 1, color: "rgba(15,118,110,0.02)" },
            ]),
          },
        },
      ],
    });
  }

  if (riskRef.value) {
    riskChart ??= init(riskRef.value);
    riskChart.setOption({
      animationDuration: 500,
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#52606d" } },
      series: [
        {
          type: "pie",
          radius: ["44%", "72%"],
          center: ["50%", "42%"],
          label: { color: "#1f2937" },
          color: ["#0f766e", "#f59e0b", "#ef4444", "#7c3aed"],
          data: overview.value.risk_distribution.map((item) => ({
            name: item.name,
            value: item.value,
          })),
        },
      ],
    });
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">PIAP Operations</p>
        <h2>数据与统计看板</h2>
        <p class="subtitle">
          仪表盘现在只统计真实物化后的任务、结果、稳定性和告警，不再把聊天中间态当作统计源。
        </p>
        <div class="scope-strip">
          <el-tag type="success" effect="dark">{{ scopeLabel }}</el-tag>
          <el-tag type="info" effect="plain">最近 {{ selectedRange }} 日</el-tag>
          <el-tag v-if="isAdmin" type="warning" effect="plain">admin 默认聚合全部组织</el-tag>
        </div>
      </div>

      <div class="hero-actions">
        <div class="range-switch">
          <el-button :type="selectedRange === 7 ? 'primary' : 'default'" @click="setRange(7)">7 日</el-button>
          <el-button :type="selectedRange === 30 ? 'primary' : 'default'" @click="setRange(30)">30 日</el-button>
          <el-button :type="selectedRange === 90 ? 'primary' : 'default'" @click="setRange(90)">90 日</el-button>
        </div>
        <div class="button-group">
          <el-button type="primary" @click="router.push('/app/tasks')">查看任务</el-button>
          <el-button plain @click="router.push('/ops/analytics')">查看分析</el-button>
          <el-button plain @click="router.push('/app/stability')">稳定性工作台</el-button>
        </div>
      </div>
    </section>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <section v-if="overview" class="metric-grid">
      <el-card shadow="never" class="metric-card cyan" @click="router.push('/app/tasks')">
        <div class="label">范围内任务数</div>
        <div class="value">{{ overview.total_tasks }}</div>
        <div class="meta">已沉淀结果 {{ overview.total_results }}</div>
      </el-card>

      <el-card shadow="never" class="metric-card green">
        <div class="label">智能判定通过率</div>
        <div class="value">{{ (overview.pass_rate * 100).toFixed(1) }}%</div>
        <div class="meta">仅统计真实结果记录</div>
      </el-card>

      <el-card shadow="never" class="metric-card amber" @click="router.push('/app/alerts')">
        <div class="label">高风险预警数</div>
        <div class="value">{{ highRiskAlerts }}</div>
        <div class="meta">仅显示未关闭且未关联已删除任务的告警</div>
      </el-card>

      <el-card shadow="never" class="metric-card rose">
        <div class="label">平均耗时</div>
        <div class="value">{{ overview.avg_latency_ms.toFixed(0) }} ms</div>
        <div class="meta">累计成本 ¥{{ overview.total_cost.toFixed(4) }}</div>
      </el-card>
    </section>

    <section class="chart-grid">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div>
              <strong>通过率趋势</strong>
              <span>按当前统计范围展示真实结果的通过率走势</span>
            </div>
          </div>
        </template>
        <div ref="trendRef" class="chart-host"></div>
      </el-card>

      <el-card shadow="never" class="chart-card" @click="router.push('/app/stability')">
        <template #header>
          <div class="card-head">
            <div>
              <strong>风险等级分布</strong>
              <span>点击进入稳定性工作台查看详情</span>
            </div>
          </div>
        </template>
        <div ref="riskRef" class="chart-host"></div>
      </el-card>
    </section>

    <section class="table-grid">
      <el-card shadow="never">
        <template #header>最近预警</template>
        <el-table :data="openAlerts" size="small" empty-text="当前范围内暂无预警">
          <el-table-column prop="severity" label="级别" width="110" />
          <el-table-column prop="title" label="标题" min-width="220" />
          <el-table-column prop="created_at" label="触发时间" width="180" />
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>最近任务</template>
        <el-table :data="recentTasks" size="small" empty-text="当前范围内暂无任务">
          <el-table-column prop="id" label="任务 ID" min-width="240" show-overflow-tooltip />
          <el-table-column v-if="isAdmin" prop="org_slug" label="组织" width="120" />
          <el-table-column prop="product_id" label="产品编号" width="120" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="source_kind" label="来源" width="160" />
          <el-table-column prop="source_graph" label="子图" width="150" />
        </el-table>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.dashboard-shell {
  --line: rgba(16, 36, 61, 0.1);
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 30%),
    radial-gradient(circle at top right, rgba(190, 24, 93, 0.08), transparent 24%),
    linear-gradient(180deg, #f7f3ea 0%, #eef2f6 100%);
  display: grid;
  gap: 18px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(16, 36, 61, 0.98), rgba(17, 94, 89, 0.9));
  color: #f8fafc;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.78;
}

.hero h2 {
  margin: 0;
  font-size: 42px;
  line-height: 1.05;
}

.subtitle {
  max-width: 760px;
  margin: 12px 0 0;
  color: rgba(248, 250, 252, 0.82);
}

.scope-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.hero-actions {
  display: grid;
  gap: 12px;
  justify-items: end;
}

.range-switch,
.button-group {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card,
.chart-card,
.table-grid :deep(.el-card) {
  border-radius: 20px;
  border: 1px solid var(--line);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
}

.metric-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.metric-card.cyan .value { color: #0f766e; }
.metric-card.green .value { color: #2f855a; }
.metric-card.amber .value { color: #d97706; }
.metric-card.rose .value { color: #be123c; }

.label {
  color: #52606d;
  font-size: 13px;
}

.value {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
}

.meta {
  color: #64748b;
  font-size: 13px;
}

.chart-grid,
.table-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.card-head strong {
  display: block;
  color: #172033;
  font-size: 18px;
}

.card-head span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.chart-host {
  width: 100%;
  height: 320px;
}

@media (max-width: 1100px) {
  .metric-grid,
  .chart-grid,
  .table-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .hero {
    flex-direction: column;
  }

  .hero-actions {
    justify-items: stretch;
  }

  .range-switch,
  .button-group {
    justify-content: flex-start;
  }
}
</style>
