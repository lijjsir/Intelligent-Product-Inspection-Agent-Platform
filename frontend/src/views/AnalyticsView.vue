<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, MarkPointComponent } from "echarts/components";
import { graphic, init, type ECharts, use } from "echarts/core";

import { analyticsApi } from "@/api/analytics.api";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelAnalyticsMetric, ModelDrilldown, ProductLineDrilldown } from "@/types/analytics.types";

const router = useRouter();
const analyticsStore = useAnalyticsStore();
const dateRange = ref<[Date, Date] | null>(null);
const selectedProductLines = ref<string[]>([]);
const drawerVisible = ref(false);
const drawerPayload = ref<{ title: string; lines: string[] }>({ title: "", lines: [] });
const productLineDrilldown = ref<ProductLineDrilldown | null>(null);
const modelDrilldown = ref<ModelDrilldown | null>(null);
const drawerLoading = ref(false);

const passTrendRef = ref<HTMLElement | null>(null);
const hallucinationTrendRef = ref<HTMLElement | null>(null);
const riskTrendRef = ref<HTMLElement | null>(null);
const productLineRef = ref<HTMLElement | null>(null);
let passTrendChart: ECharts | null = null;
let hallucinationTrendChart: ECharts | null = null;
let riskTrendChart: ECharts | null = null;
let productLineChart: ECharts | null = null;

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent, MarkPointComponent]);

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
  await nextTick();
  renderCharts();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  passTrendChart?.dispose();
  hallucinationTrendChart?.dispose();
  riskTrendChart?.dispose();
  productLineChart?.dispose();
  window.removeEventListener("resize", handleResize);
});

watch(overview, async (value) => {
  if (value && !selectedProductLines.value.length) {
    selectedProductLines.value = value.product_line_series.slice(0, 3).map((item) => item.name);
  }
  await nextTick();
  renderCharts();
});

watch(selectedProductLines, async () => {
  await nextTick();
  renderCharts();
});

function handleResize() {
  passTrendChart?.resize();
  hallucinationTrendChart?.resize();
  riskTrendChart?.resize();
  productLineChart?.resize();
}

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
  drawerVisible.value = true;
  fetchProductLineDrilldown(name);
}

function openModelDrilldown(row: ModelAnalyticsMetric) {
  productLineDrilldown.value = null;
  modelDrilldown.value = null;
  drawerPayload.value = {
    title: `模型钻取 · ${row.model_key}`,
    lines: [],
  };
  drawerVisible.value = true;
  fetchModelDrilldown(row.model_key);
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

function renderCharts() {
  if (!overview.value) {
    return;
  }

  if (passTrendRef.value) {
    passTrendChart ??= init(passTrendRef.value);
    passTrendChart.setOption({
      animationDuration: 500,
      color: ["#0f766e"],
      tooltip: { trigger: "axis", valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%` },
      grid: { left: 40, right: 24, top: 32, bottom: 28 },
      xAxis: {
        type: "category",
        data: overview.value.pass_rate_trend.map((item) => item.bucket),
        axisLabel: { color: "#5b6472" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: "#5b6472",
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: [
        {
          name: "通过率",
          type: "line",
          smooth: true,
          symbolSize: 7,
          data: overview.value.pass_rate_trend.map((item) => item.value),
          lineStyle: { width: 3 },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(15,118,110,0.28)" },
              { offset: 1, color: "rgba(15,118,110,0.02)" },
            ]),
          },
        },
      ],
    });
  }

  if (hallucinationTrendRef.value) {
    hallucinationTrendChart ??= init(hallucinationTrendRef.value);
    hallucinationTrendChart.setOption({
      animationDuration: 500,
      color: ["#d97706"],
      tooltip: { trigger: "axis", valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%` },
      grid: { left: 40, right: 24, top: 32, bottom: 28 },
      xAxis: {
        type: "category",
        data: overview.value.hallucination_trend.map((item) => item.bucket),
        axisLabel: { color: "#5b6472" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: "#5b6472",
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: [
        {
          name: "幻觉率",
          type: "line",
          smooth: true,
          symbolSize: 7,
          data: overview.value.hallucination_trend.map((item) => item.value),
          markPoint: {
            symbolSize: 48,
            itemStyle: { color: "#dc2626" },
            data: overview.value.hallucination_trend.length ? [{ type: "max", name: "异常峰值" }] : [],
          },
          lineStyle: { width: 3 },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(217,119,6,0.24)" },
              { offset: 1, color: "rgba(217,119,6,0.03)" },
            ]),
          },
        },
      ],
    });
  }

  if (riskTrendRef.value) {
    riskTrendChart ??= init(riskTrendRef.value);
    riskTrendChart.setOption({
      animationDuration: 500,
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { top: 0, textStyle: { color: "#5b6472" } },
      grid: { left: 40, right: 24, top: 48, bottom: 28 },
      xAxis: {
        type: "category",
        data: overview.value.risk_distribution_trend.map((item) => item.bucket),
        axisLabel: { color: "#5b6472" },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#5b6472" },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: [
        { name: "低风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: overview.value.risk_distribution_trend.map((item) => item.low), color: "#0f766e" },
        { name: "中风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: overview.value.risk_distribution_trend.map((item) => item.medium), color: "#f59e0b" },
        { name: "高风险", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: overview.value.risk_distribution_trend.map((item) => item.high), color: "#ef4444" },
        { name: "严重", type: "line", stack: "risk", smooth: true, areaStyle: {}, data: overview.value.risk_distribution_trend.map((item) => item.critical), color: "#7c3aed" },
      ],
    });
  }

  if (productLineRef.value) {
    productLineChart ??= init(productLineRef.value);
    const series = activeProductLineSeries.value;
    const xAxisData = series[0]?.points.map((item) => item.bucket) ?? [];
    productLineChart.setOption({
      animationDuration: 500,
      tooltip: { trigger: "axis" },
      legend: { top: 0, textStyle: { color: "#5b6472" } },
      grid: { left: 40, right: 24, top: 48, bottom: 28 },
      xAxis: {
        type: "category",
        data: xAxisData,
        axisLabel: { color: "#5b6472" },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#5b6472" },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: series.map((item) => ({
        name: item.name,
        type: "line",
        smooth: true,
        symbolSize: 6,
        data: item.points.map((point) => point.value),
      })),
    });
    productLineChart.off("click");
    productLineChart.on("click", (params) => {
      if (typeof params.seriesName === "string") {
        openProductLineDrilldown(params.seriesName);
      }
    });
  }
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

    <section v-if="overview" class="metric-grid">
      <el-card shadow="never" class="metric-card"><div class="metric-label">总任务</div><div class="metric-value">{{ overview.total_tasks }}</div></el-card>
      <el-card shadow="never" class="metric-card success"><div class="metric-label">通过率</div><div class="metric-value">{{ (overview.pass_rate * 100).toFixed(1) }}%</div></el-card>
      <el-card shadow="never" class="metric-card warning"><div class="metric-label">幻觉率</div><div class="metric-value">{{ (overview.hallucination_rate * 100).toFixed(1) }}%</div></el-card>
      <el-card shadow="never" class="metric-card amber"><div class="metric-label">平均风险分</div><div class="metric-value">{{ overview.avg_risk_score.toFixed(1) }}</div></el-card>
      <el-card shadow="never" class="metric-card danger"><div class="metric-label">RED 级率</div><div class="metric-value">{{ (redRate * 100).toFixed(1) }}%</div></el-card>
      <el-card shadow="never" class="metric-card slate"><div class="metric-label">平均耗时</div><div class="metric-value">{{ overview.avg_latency_ms.toFixed(0) }} ms</div></el-card>
    </section>

    <section class="chart-grid">
      <el-card shadow="never" class="chart-card wide">
        <template #header><div class="card-head"><div><strong>通过率趋势</strong><span>统一时间窗口下的主稳定性指标</span></div></div></template>
        <div ref="passTrendRef" class="chart-host"></div>
      </el-card>

      <el-card shadow="never" class="chart-card wide">
        <template #header><div class="card-head"><div><strong>产品线叠加趋势</strong><span>点击折线可打开产品线钻取面板</span></div></div></template>
        <div ref="productLineRef" class="chart-host"></div>
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header><div class="card-head"><div><strong>幻觉率趋势</strong><span>峰值点自动高亮</span></div></div></template>
        <div ref="hallucinationTrendRef" class="chart-host"></div>
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header><div class="card-head"><div><strong>风险分布变化</strong><span>按日期堆叠展示风险等级演化</span></div></div></template>
        <div ref="riskTrendRef" class="chart-host"></div>
      </el-card>
    </section>

    <el-card v-if="overview" shadow="never" class="table-card">
      <template #header><div class="card-head"><div><strong>模型性能对比</strong><span>点击某一行可查看模型钻取信息</span></div></div></template>
      <el-table :data="overview.model_metrics" size="small" empty-text="暂无模型对比数据" @row-click="openModelDrilldown">
        <el-table-column prop="model_key" label="模型" min-width="220" />
        <el-table-column prop="result_count" label="结果数" width="90" />
        <el-table-column label="通过率" width="120"><template #default="scope">{{ (scope.row.pass_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="幻觉率" width="120"><template #default="scope">{{ (scope.row.hallucination_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column prop="avg_tokens" label="平均 Tokens" width="130" />
        <el-table-column label="累计成本" width="140"><template #default="scope">￥{{ Number(scope.row.total_cost).toFixed(4) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" size="420px" :title="drawerPayload.title">
      <div class="drilldown-stack" v-loading="drawerLoading">
        <template v-if="productLineDrilldown">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="产品线">{{ productLineDrilldown.product_line }}</el-descriptions-item>
            <el-descriptions-item label="任务总量">{{ productLineDrilldown.total_tasks }}</el-descriptions-item>
            <el-descriptions-item label="结果总量">{{ productLineDrilldown.total_results }}</el-descriptions-item>
            <el-descriptions-item label="通过率">{{ (productLineDrilldown.pass_rate * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="幻觉率">{{ (productLineDrilldown.hallucination_rate * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="平均耗时">{{ productLineDrilldown.avg_latency_ms.toFixed(0) }} ms</el-descriptions-item>
            <el-descriptions-item label="累计成本">￥{{ productLineDrilldown.total_cost.toFixed(4) }}</el-descriptions-item>
          </el-descriptions>
          <div class="drawer-actions">
            <el-button type="primary" @click="goToProductLineTasks">查看任务列表</el-button>
            <el-button plain @click="goToProductLineResults">查看结果列表</el-button>
          </div>
          <el-card shadow="never">
            <template #header>结论分布</template>
            <div v-for="item in productLineDrilldown.verdict_distribution" :key="item.name" class="drawer-line">
              <span>{{ item.name }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </el-card>
          <el-card shadow="never">
            <template #header>最近任务</template>
            <el-table :data="productLineDrilldown.recent_tasks" size="small" empty-text="暂无任务">
              <el-table-column prop="task_id" label="任务" min-width="180" />
              <el-table-column prop="status" label="状态" width="90" />
              <el-table-column prop="spec_id" label="规格" width="120" />
              <el-table-column label="操作" width="90">
                <template #default="scope">
                  <el-button link type="primary" @click="goToTaskDetail(scope.row.task_id)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </template>
        <template v-else-if="modelDrilldown">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="模型">{{ modelDrilldown.model_key }}</el-descriptions-item>
            <el-descriptions-item label="结果数">{{ modelDrilldown.result_count }}</el-descriptions-item>
            <el-descriptions-item label="通过率">{{ (modelDrilldown.pass_rate * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="幻觉率">{{ (modelDrilldown.hallucination_rate * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="平均 Tokens">{{ modelDrilldown.avg_tokens.toFixed(1) }}</el-descriptions-item>
            <el-descriptions-item label="平均耗时">{{ modelDrilldown.avg_latency_ms.toFixed(0) }} ms</el-descriptions-item>
            <el-descriptions-item label="累计成本">￥{{ modelDrilldown.total_cost.toFixed(4) }}</el-descriptions-item>
          </el-descriptions>
          <div class="drawer-actions">
            <el-button type="primary" @click="goToModelResults">查看结果列表</el-button>
          </div>
          <el-card shadow="never">
            <template #header>产品线分布</template>
            <div v-for="item in modelDrilldown.product_line_distribution" :key="item.name" class="drawer-line">
              <span>{{ item.name }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </el-card>
          <el-card shadow="never">
            <template #header>最近结果</template>
            <el-table :data="modelDrilldown.recent_results" size="small" empty-text="暂无结果">
              <el-table-column prop="result_id" label="结果" min-width="160" />
              <el-table-column prop="product_line" label="产品线" width="120" />
              <el-table-column prop="verdict" label="结论" width="90" />
              <el-table-column label="操作" width="90">
                <template #default="scope">
                  <el-button link type="primary" @click="goToResultDetail(scope.row.task_id)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </template>
        <template v-else>
          <el-alert title="暂无钻取数据，请调整时间范围或先产生分析结果。" type="info" :closable="false" />
        </template>
        <el-card shadow="never" v-for="(line, index) in drawerPayload.lines" :key="index">
          {{ line }}
        </el-card>
      </div>
    </el-drawer>
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
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; }
.metric-card :deep(.el-card__body) { display: grid; gap: 10px; }
.metric-label { color: #5b6472; font-size: 13px; }
.metric-value { color: #0f172a; font-size: 34px; font-weight: 800; line-height: 1; }
.metric-card.success .metric-value { color: #15803d; }
.metric-card.warning .metric-value { color: #d97706; }
.metric-card.amber .metric-value { color: #b45309; }
.metric-card.danger .metric-value { color: #dc2626; }
.metric-card.slate .metric-value { color: #1d4ed8; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart-card.wide { grid-column: span 2; }
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
.chart-host { width: 100%; height: 320px; }
.drilldown-stack { display: grid; gap: 12px; }
.drawer-actions { display: flex; gap: 12px; }
.drawer-line { display: flex; justify-content: space-between; padding: 6px 0; color: #334155; }
@media (max-width: 1400px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 960px) {
  .hero-panel, .filter-row { flex-direction: column; align-items: stretch; }
  .metric-grid, .chart-grid { grid-template-columns: 1fr; }
  .chart-card.wide { grid-column: span 1; }
  .chart-host { height: 280px; }
}
</style>
