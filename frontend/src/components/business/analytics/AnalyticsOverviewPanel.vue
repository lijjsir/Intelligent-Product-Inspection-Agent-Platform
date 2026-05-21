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

interface Props {
  dateRange: [Date, Date] | null;
}

const emit = defineEmits<{ loaded: [] }>();
const props = defineProps<Props>();
const router = useRouter();
const analyticsStore = useAnalyticsStore();

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
  if (!selectedProductLines.value.length) return allSeries;
  return allSeries.filter((item) => selectedProductLines.value.includes(item.name));
});
const productLinesParam = computed(() => {
  if (!selectedProductLines.value.length) return undefined;
  return selectedProductLines.value.join(",");
});

async function fetchOverview() {
  const params = props.dateRange
    ? { start_date: formatDate(props.dateRange[0]), end_date: formatDate(props.dateRange[1]) }
    : undefined;
  const pl = productLinesParam.value;
  await analyticsStore.fetchOverview({ ...params, ...(pl ? { product_lines: pl } : {}) });
}

watch(productLinesParam, () => fetchOverview());
watch(() => props.dateRange, () => fetchOverview());
onMounted(async () => { await fetchOverview(); emit("loaded"); });

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function openProductLineDrilldown(name: string) {
  drawerPayload.value = { title: `产品线详情 · ${name}`, lines: [] };
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
  drawerPayload.value = { title: `模型详情 · ${row.model_key}`, lines: [] };
  drawerVisible.value = true;
  fetchModelDrilldown(row.model_key);
}

function openTaskDrilldown(taskId: string) {
  productLineDrilldown.value = null;
  modelDrilldown.value = null;
  taskDrilldown.value = null;
  drawerPayload.value = { title: `任务详情 · ${taskId}`, lines: [] };
  drawerVisible.value = true;
  fetchTaskDrilldown(taskId);
}

async function fetchProductLineDrilldown(name: string) {
  drawerLoading.value = true;
  try {
    const params = props.dateRange
      ? { start_date: formatDate(props.dateRange[0]), end_date: formatDate(props.dateRange[1]) }
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
    const params = props.dateRange
      ? { start_date: formatDate(props.dateRange[0]), end_date: formatDate(props.dateRange[1]) }
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
  router.push({ path: "/app/tasks", query: { product_id: productLineDrilldown.value.product_line } });
}

function goToProductLineResults() {
  if (!productLineDrilldown.value) return;
  router.push({ path: "/app/results", query: { product_id: productLineDrilldown.value.product_line } });
}

function goToModelResults() {
  if (!modelDrilldown.value) return;
  router.push({ path: "/app/results", query: { model_key: modelDrilldown.value.model_key } });
}

function goToTaskDetail(taskId: string) {
  router.push(`/app/tasks/${taskId}`);
}

function goToResultDetail(taskId: string) {
  router.push(`/app/results/${taskId}`);
}

function goToTaskResultList(taskId: string) {
  router.push({ path: "/app/results", query: { task_id: taskId } });
}

function goToTaskStabilityDetail(taskId: string) {
  router.push(`/app/stability/${taskId}`);
}

function goToRelatedTaskList(taskIds: string[]) {
  if (!taskIds.length) return;
  router.push({ path: "/app/tasks", query: { ids: taskIds.join(",") } });
}

function goToProductLineTaskList(productLine: string) {
  router.push({ path: "/app/tasks", query: { product_id: productLine } });
}
</script>

<template>
  <div class="overview-panel">
    <el-alert v-if="analyticsStore.error" :title="analyticsStore.error" type="warning" :closable="false" />

    <div class="filter-stack">
      <div class="filter-title">产品线叠加</div>
      <el-checkbox-group v-model="selectedProductLines">
        <el-checkbox v-for="item in productLineOptions" :key="item.name" :label="item.name" :value="item.name">
          {{ item.name }}
        </el-checkbox>
      </el-checkbox-group>
    </div>

    <OverviewMetricGrid v-if="overview" :overview="overview" :red-rate="redRate" />

    <section class="chart-grid">
      <el-card shadow="never" class="chart-card wide">
        <template #header>
          <div class="card-head">
            <div>
              <strong>通过率趋势</strong>
              <span>统一时间窗口下的主稳定性指标</span>
            </div>
          </div>
        </template>
        <PassRateTrendChart v-if="overview" :points="overview.pass_rate_trend" />
      </el-card>

      <el-card shadow="never" class="chart-card wide">
        <template #header>
          <div class="card-head">
            <div>
              <strong>产品线任务趋势</strong>
              <span>点击折线查看产品线详情</span>
            </div>
          </div>
        </template>
        <ProductLineSeriesChart v-if="overview" :series="activeProductLineSeries" @select="openProductLineDrilldown" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div>
              <strong>幻觉率趋势</strong>
              <span>引用为空的结果会被计入幻觉率</span>
            </div>
          </div>
        </template>
        <HallucinationChart v-if="overview" :points="overview.hallucination_trend" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div>
              <strong>风险分布变化</strong>
              <span>按日期堆叠展示风险等级演化</span>
            </div>
          </div>
        </template>
        <RiskDistributionTrendChart v-if="overview" :points="overview.risk_distribution_trend" />
      </el-card>
    </section>

    <el-card v-if="overview" shadow="never" class="table-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>模型性能对比</strong>
            <span>点击某一行可查看模型详情</span>
          </div>
        </div>
      </template>
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
.overview-panel { display: grid; gap: 18px; }
.scope-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(16, 36, 61, 0.08);
}
.scope-banner span { color: #52606d; font-size: 13px; }
.filter-stack { display: flex; flex-direction: column; gap: 8px; }
.filter-title { font-size: 16px; font-weight: 700; color: #172033; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart-card.wide { grid-column: span 2; }
.chart-card, .table-card { border-radius: 20px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
@media (max-width: 960px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.wide { grid-column: span 1; }
}
</style>
