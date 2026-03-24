<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { analyticsApi } from "@/api/analytics.api";
import AnalyticsDrilldownDrawer from "@/components/business/analytics/AnalyticsDrilldownDrawer.vue";
import HallucinationChart from "@/components/business/analytics/HallucinationChart.vue";
import ModelCompareTable from "@/components/business/analytics/ModelCompareTable.vue";
import OverviewMetricGrid from "@/components/business/analytics/OverviewMetricGrid.vue";
import PassRateTrendChart from "@/components/business/analytics/PassRateTrendChart.vue";
import ProductLineSeriesChart from "@/components/business/analytics/ProductLineSeriesChart.vue";
import RiskDistributionTrendChart from "@/components/business/analytics/RiskDistributionTrendChart.vue";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelAnalyticsMetric, ModelDrilldown, ProductLineDrilldown, TaskDrilldown } from "@/types/analytics.types";

const router = useRouter();
const analyticsStore = useAnalyticsStore();
const dateRange = ref<[Date, Date] | null>(null);
const selectedProductLines = ref<string[]>([]);
const drawerVisible = ref(false);
const drawerPayload = ref<{ title: string; lines: string[] }>({ title: "", lines: [] });
const productLineDrilldown = ref<ProductLineDrilldown | null>(null);
const modelDrilldown = ref<ModelDrilldown | null>(null);
const taskDrilldown = ref<TaskDrilldown | null>(null);
const drawerLoading = ref(false);

const overview = computed(() => analyticsStore.overview);
const redRate = computed(() => {
  const items = overview.value?.alert_distribution ?? [];
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const redValue = items
    .filter((item) => ["critical", "red"].includes(item.name.toLowerCase()))
    .reduce((sum, item) => sum + item.value, 0);
  return total ? redValue / total : 0;
});
const productLineOptions = computed(() => overview.value?.product_line_series ?? []);
const activeProductLineSeries = computed(() => {
  const allSeries = overview.value?.product_line_series ?? [];
  if (!selectedProductLines.value.length) {
    return allSeries;
  }
  return allSeries.filter((item) => selectedProductLines.value.includes(item.name));
});

onMounted(async () => {
  await applyDateFilter();
});

watch(overview, (value) => {
  if (value && !selectedProductLines.value.length) {
    selectedProductLines.value = value.product_line_series.slice(0, 3).map((item) => item.name);
  }
});

async function applyDateFilter() {
  if (!dateRange.value) {
    await analyticsStore.fetchOverview();
    return;
  }
  const [start, end] = dateRange.value;
  await analyticsStore.fetchOverview({
    start_date: formatDate(start),
    end_date: formatDate(end),
  });
}

async function quickRange(days: number) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  dateRange.value = [start, end];
  await applyDateFilter();
}

async function clearDateFilter() {
  dateRange.value = null;
  await applyDateFilter();
}

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function openProductLineDrilldown(name: string) {
  drawerPayload.value = {
    title: `产品线钻取 · ${name}`,
    lines: [],
  };
  productLineDrilldown.value = null;
  modelDrilldown.value = null;
  taskDrilldown.value = null;
  drawerVisible.value = true;
  fetchProductLineDrilldown(name);
}

function openModelDrilldown(row: ModelAnalyticsMetric) {
  productLineDrilldown.value = null;
  modelDrilldown.value = null;
  taskDrilldown.value = null;
  drawerPayload.value = {
    title: `模型钻取 · ${row.model_key}`,
    lines: [],
  };
  drawerVisible.value = true;
  fetchModelDrilldown(row.model_key);
}

function openTaskDrilldown(taskId: string) {
  productLineDrilldown.value = null;
  modelDrilldown.value = null;
  taskDrilldown.value = null;
  drawerPayload.value = {
    title: `任务钻取 · ${taskId}`,
    lines: [],
  };
  drawerVisible.value = true;
  fetchTaskDrilldown(taskId);
}

async function fetchProductLineDrilldown(name: string) {
  drawerLoading.value = true;
  try {
    const params = dateRange.value
      ? {
          start_date: formatDate(dateRange.value[0]),
          end_date: formatDate(dateRange.value[1]),
        }
      : undefined;
    const { data } = await analyticsApi.getProductLineDrilldown(name, params);
    productLineDrilldown.value = data.data;
  } finally {
    drawerLoading.value = false;
  }
}

async function fetchModelDrilldown(modelKey: string) {
  drawerLoading.value = true;
  try {
    const params = dateRange.value
      ? {
          start_date: formatDate(dateRange.value[0]),
          end_date: formatDate(dateRange.value[1]),
        }
      : undefined;
    const { data } = await analyticsApi.getModelDrilldown(modelKey, params);
    modelDrilldown.value = data.data;
  } finally {
    drawerLoading.value = false;
  }
}

async function fetchTaskDrilldown(taskId: string) {
  drawerLoading.value = true;
  try {
    const { data } = await analyticsApi.getTaskDrilldown(taskId);
    taskDrilldown.value = data.data;
  } finally {
    drawerLoading.value = false;
  }
}

function goToProductLineTasks() {
  if (!productLineDrilldown.value) return;
  router.push({ path: "/tasks", query: { product_id: productLineDrilldown.value.product_line } });
}

function goToProductLineResults() {
  if (!productLineDrilldown.value) return;
  router.push({ path: "/results", query: { product_id: productLineDrilldown.value.product_line } });
}

function goToModelResults() {
  if (!modelDrilldown.value) return;
  router.push({ path: "/results", query: { model_key: modelDrilldown.value.model_key } });
}

function goToTaskDetail(taskId: string) {
  router.push(`/tasks/${taskId}`);
}

function goToResultDetail(taskId: string) {
  router.push(`/results/${taskId}`);
}

function goToTaskResultList(taskId: string) {
  router.push({ path: "/results", query: { task_id: taskId } });
}

function goToTaskStabilityDetail(taskId: string) {
  router.push(`/stability/${taskId}`);
}

function goToRelatedTaskList(taskIds: string[]) {
  if (!taskIds.length) return;
  router.push({ path: "/tasks", query: { ids: taskIds.join(",") } });
}

function goToProductLineTaskList(productLine: string) {
  router.push({ path: "/tasks", query: { product_id: productLine } });
}
</script>

<template>
  <div class="analytics-shell">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">PIAP Intelligence Desk</p>
        <h2>分析中心</h2>
        <p class="subtitle">围绕通过率、幻觉率、风险演化和模型成本做聚合观察，支持产品线叠加和图表钻取。</p>
      </div>
      <div class="hero-actions">
        <el-button @click="quickRange(7)">7 日</el-button>
        <el-button @click="quickRange(30)">30 日</el-button>
        <el-button @click="quickRange(90)">90 日</el-button>
      </div>
    </section>

    <el-alert v-if="analyticsStore.error" :title="analyticsStore.error" type="warning" :closable="false" />

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <div>
          <div class="filter-title">时间范围</div>
          <div class="filter-meta">所有图表跟随同一时间窗口</div>
        </div>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          unlink-panels
        />
        <el-button type="primary" @click="applyDateFilter">应用筛选</el-button>
        <el-button plain @click="clearDateFilter">重置</el-button>
      </div>
      <div class="filter-stack">
        <div class="filter-title">产品线叠加</div>
        <el-checkbox-group v-model="selectedProductLines">
          <el-checkbox v-for="item in productLineOptions" :key="item.name" :label="item.name">
            {{ item.name }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
    </el-card>

    <OverviewMetricGrid v-if="overview" :overview="overview" :red-rate="redRate" />

    <section class="chart-grid">
      <el-card shadow="never" class="chart-card wide">
        <template #header><div class="card-head"><div><strong>通过率趋势</strong><span>统一时间窗口下的主稳定性指标</span></div></div></template>
        <PassRateTrendChart v-if="overview" :points="overview.pass_rate_trend" />
      </el-card>

      <el-card shadow="never" class="chart-card wide">
        <template #header><div class="card-head"><div><strong>产品线叠加趋势</strong><span>点击折线可打开产品线钻取面板</span></div></div></template>
        <ProductLineSeriesChart v-if="overview" :series="activeProductLineSeries" @select="openProductLineDrilldown" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header><div class="card-head"><div><strong>幻觉率趋势</strong><span>峰值点自动高亮</span></div></div></template>
        <HallucinationChart v-if="overview" :points="overview.hallucination_trend" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header><div class="card-head"><div><strong>风险分布变化</strong><span>按日期堆叠展示风险等级演化</span></div></div></template>
        <RiskDistributionTrendChart v-if="overview" :points="overview.risk_distribution_trend" />
      </el-card>
    </section>

    <el-card v-if="overview" shadow="never" class="table-card">
      <template #header><div class="card-head"><div><strong>模型性能对比</strong><span>点击某一行可查看模型钻取信息</span></div></div></template>
      <ModelCompareTable :items="overview.model_metrics" @select="openModelDrilldown" />
    </el-card>

    <AnalyticsDrilldownDrawer
      v-model:visible="drawerVisible"
      :title="drawerPayload.title"
      :loading="drawerLoading"
      :product-line-drilldown="productLineDrilldown"
      :model-drilldown="modelDrilldown"
      :task-drilldown="taskDrilldown"
      @product-line-tasks="goToProductLineTasks"
      @product-line-results="goToProductLineResults"
      @model-results="goToModelResults"
      @task-detail="goToTaskDetail"
      @result-detail="goToResultDetail"
      @task-drilldown="openTaskDrilldown"
      @task-related-list="goToRelatedTaskList"
      @task-product-list="goToProductLineTaskList"
      @task-result-list="goToTaskResultList"
      @task-stability-detail="goToTaskStabilityDetail"
    />
  </div>
</template>

<style scoped>
.analytics-shell {
  min-height: 100vh;
  padding: 24px;
  display: grid;
  gap: 18px;
  background:
    radial-gradient(circle at top left, rgba(15,118,110,0.14), transparent 24%),
    radial-gradient(circle at right top, rgba(217,119,6,0.12), transparent 24%),
    linear-gradient(180deg, #f6f2ea 0%, #edf2f7 100%);
}
.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #10243d 0%, #173f5f 52%, #0f766e 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; opacity: 0.76; }
.hero-panel h2 { margin: 0; font-size: 40px; }
.subtitle { margin: 12px 0 0; max-width: 780px; color: rgba(248, 250, 252, 0.82); }
.hero-actions { display: flex; align-items: flex-start; gap: 12px; }
.filter-card, .metric-card, .chart-card, .table-card { border-radius: 20px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.filter-row, .filter-stack { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.filter-stack { margin-top: 16px; align-items: flex-start; flex-direction: column; }
.filter-title { font-size: 16px; font-weight: 700; color: #172033; }
.filter-meta { margin-top: 4px; color: #64748b; font-size: 13px; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart-card.wide { grid-column: span 2; }
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
@media (max-width: 960px) {
  .hero-panel, .filter-row { flex-direction: column; align-items: stretch; }
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.wide { grid-column: span 1; }
}
</style>
