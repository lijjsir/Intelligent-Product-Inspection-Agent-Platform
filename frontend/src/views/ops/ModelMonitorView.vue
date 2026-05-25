<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { modelConfigApi } from "@/api/model_config.api";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelAnalyticsMetric } from "@/types/analytics.types";
import type { ModelConfig } from "@/types/governance.types";

use([CanvasRenderer, BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent] as any);

type ChartTab = "cost" | "share" | "tokens" | "ranking";

const analyticsStore = useAnalyticsStore();
const loading = ref(false);
const rangeDays = ref<7 | 30 | 90>(7);
const activeChart = ref<ChartTab>("cost");

const modelMetrics = computed(() => analyticsStore.overview?.model_metrics ?? []);
const qualityMetrics = computed(() => modelMetrics.value.filter((item) => (item.result_count ?? 0) > 0));
const totalCost = computed(() => analyticsStore.overview?.total_cost ?? 0);
const totalTokens = computed(() => modelMetrics.value.reduce((sum, item) => sum + (item.total_tokens ?? 0), 0));
const totalCalls = computed(() => {
  const modelCallTotal = modelMetrics.value.reduce((sum, item) => sum + metricCallCount(item), 0);
  return modelCallTotal || analyticsStore.overview?.total_results || 0;
});
const avgCostPerCall = computed(() => (totalCalls.value ? totalCost.value / totalCalls.value : 0));
const averageTokensPerCall = computed(() => (totalCalls.value ? totalTokens.value / totalCalls.value : 0));
const overallPassRate = computed(() => analyticsStore.overview?.pass_rate ?? 0);
const hasUnpricedUsage = computed(() =>
  modelMetrics.value.some((item) => (item.total_tokens ?? 0) > 0 && Number(item.total_cost || 0) === 0),
);

const models = ref<ModelConfig[]>([]);
const modelsLoading = ref(false);
const modelsError = ref("");

const chartTabs: { key: ChartTab; label: string; desc: string }[] = [
  { key: "cost", label: "消耗分布", desc: "按模型看成本消耗，沿用配置中的输入/输出单价折算。" },
  { key: "share", label: "调用占比", desc: "看调用次数在各模型之间的分布，不额外引入没有的数据。" },
  { key: "tokens", label: "Token 对比", desc: "观察平均单次 Token 使用量，辅助发现高消耗模型。" },
  { key: "ranking", label: "调用排行", desc: "按调用量快速定位主力模型和尾部模型。" },
];

const modelTypeLabels: Record<string, string> = {
  chat: "对话",
  embedding: "向量",
  multimodal: "多模态",
  vision: "视觉",
  llm: "LLM",
  vlm: "VLM",
};

const healthLabels: Record<string, { label: string; tag: string }> = {
  healthy: { label: "健康", tag: "success" },
  degraded: { label: "降级", tag: "warning" },
  unhealthy: { label: "异常", tag: "danger" },
  unknown: { label: "未知", tag: "info" },
};

const healthStatusMap = computed(() => {
  const map: Record<string, string> = {};
  for (const model of models.value) {
    map[model.model_key] = model.health_status || "unknown";
  }
  return map;
});

const spotlightModels = computed(() =>
  [...modelMetrics.value]
    .sort((a, b) => metricCallCount(b) - metricCallCount(a))
    .slice(0, 3),
);

const summaryCards = computed(() => [
  {
    label: "总成本",
    value: formatCost(totalCost.value),
    sub: `近 ${rangeDays.value} 天累计成本`,
    tone: "cost",
  },
  {
    label: "请求次数",
    value: totalCalls.value.toLocaleString(),
    sub: `活跃模型 ${modelMetrics.value.length} 个`,
    tone: "calls",
  },
  {
    label: "统计 Tokens",
    value: formatTokens(totalTokens.value),
    sub: `平均单次 ${formatTokens(averageTokensPerCall.value)}`,
    tone: "tokens",
  },
  {
    label: "质检通过率",
    value: formatRate(overallPassRate.value),
    sub: hasUnpricedUsage.value ? "存在待补价格模型" : `生成模型质检样本 ${qualityMetrics.value.reduce((sum, item) => sum + item.result_count, 0)} 条`,
    tone: "quality",
  },
]);

const usageRows = computed(() => {
  const usageMap = new Map(modelMetrics.value.map((item) => [item.model_key, item]));
  const configuredRows = models.value.map((model) => ({
    id: model.model_key,
    display_name: model.display_name || model.model_key,
    model_key: model.model_key,
    provider: model.provider,
    model_type: model.model_type,
    health_status: model.health_status || "unknown",
    is_active: model.is_active,
    has_api_key: model.has_api_key,
    input_price_per_million: model.input_price_per_million,
    output_price_per_million: model.output_price_per_million,
    priority: model.priority,
    rpm_limit: model.rpm_limit,
    usage: usageMap.get(model.model_key) || null,
  }));

  const configuredKeys = new Set(configuredRows.map((item) => item.model_key));
  const unconfiguredRows = modelMetrics.value
    .filter((item) => !configuredKeys.has(item.model_key))
    .map((item) => ({
      id: item.model_key,
      display_name: item.model_key,
      model_key: item.model_key,
      provider: "-",
      model_type: "unknown",
      health_status: "unknown",
      is_active: false,
      has_api_key: false,
      input_price_per_million: null,
      output_price_per_million: null,
      priority: 0,
      rpm_limit: null,
      usage: item,
    }));

  return [...configuredRows, ...unconfiguredRows].sort((a, b) => {
    const callDelta = metricCallCount(b.usage) - metricCallCount(a.usage);
    if (callDelta !== 0) return callDelta;
    return a.display_name.localeCompare(b.display_name, "zh-CN");
  });
});

function dateParams(days: 7 | 30 | 90) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  return {
    start_date: start.toISOString().slice(0, 10),
    end_date: end.toISOString().slice(0, 10),
  };
}

async function fetchData() {
  loading.value = true;
  try {
    await analyticsStore.fetchOverview(dateParams(rangeDays.value));
  } finally {
    loading.value = false;
  }
}

async function fetchModels() {
  modelsLoading.value = true;
  modelsError.value = "";
  try {
    const { data } = await modelConfigApi.list();
    models.value = data.data ?? [];
  } catch (error: any) {
    modelsError.value = error?.response?.data?.message || "获取模型配置失败";
  } finally {
    modelsLoading.value = false;
  }
}

function setRange(days: number) {
  if (days !== 7 && days !== 30 && days !== 90) return;
  if (rangeDays.value === days && analyticsStore.overview) return;
  rangeDays.value = days;
  fetchData();
}

function metricCallCount(metric?: Pick<ModelAnalyticsMetric, "call_count" | "result_count"> | null) {
  if (!metric) return 0;
  return metric.call_count ?? metric.result_count ?? 0;
}

function hasQualityMetric(metric?: Pick<ModelAnalyticsMetric, "result_count"> | null) {
  return Boolean((metric?.result_count ?? 0) > 0);
}

function qualityRateText(metric: ModelAnalyticsMetric | null | undefined, key: "pass_rate" | "hallucination_rate") {
  return hasQualityMetric(metric) ? formatRate(metric?.[key] ?? 0) : "不适用";
}

function formatRate(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatTokens(value: number | null | undefined) {
  const safe = Number(value || 0);
  if (!safe) return "0";
  if (safe >= 1000000) return `${(safe / 1000000).toFixed(1)}M`;
  if (safe >= 1000) return `${(safe / 1000).toFixed(1)}k`;
  return `${safe.toFixed(0)}`;
}

function formatCost(value: number | null | undefined) {
  const safe = Number(value || 0);
  if (safe >= 1) return `¥${safe.toFixed(2)}`;
  if (safe >= 0.01) return `¥${safe.toFixed(4)}`;
  return `¥${safe.toFixed(6)}`;
}

function formatPrice(value: number | null | undefined) {
  if (value == null) return "-";
  return `¥${Number(value).toFixed(2)}/M`;
}

function formatUsageCost(metric?: { total_cost?: number; total_tokens?: number } | null) {
  if (!metric) return "-";
  if ((metric.total_tokens ?? 0) > 0 && Number(metric.total_cost || 0) === 0) return "待补价格";
  return formatCost(metric.total_cost);
}

function formatAvgCost(metric?: { call_count?: number; result_count?: number; total_cost?: number; total_tokens?: number } | null) {
  if (!metric) return "-";
  if ((metric.total_tokens ?? 0) > 0 && Number(metric.total_cost || 0) === 0) return "待补价格";
  const calls = metricCallCount(metric);
  return formatCost(calls ? Number(metric.total_cost || 0) / calls : 0);
}

function usageShare(metric: ModelAnalyticsMetric) {
  return totalCalls.value ? ((metricCallCount(metric) / totalCalls.value) * 100).toFixed(1) : "0.0";
}

function healthTagType(status: string) {
  return healthLabels[status]?.tag || "info";
}

function healthLabel(status: string) {
  return healthLabels[status]?.label || "未知";
}

function pricingStatus(row: { usage: ModelAnalyticsMetric | null; input_price_per_million: number | null; output_price_per_million: number | null }) {
  const hasUsage = (row.usage?.total_tokens ?? 0) > 0;
  const hasPrice = row.input_price_per_million != null || row.output_price_per_million != null;
  if (hasUsage && !hasPrice) return { label: "待补价格", type: "warning" as const };
  if (hasPrice) return { label: "已配置", type: "success" as const };
  return { label: "未启用", type: "info" as const };
}

const chartRef = ref<HTMLElement | null>(null);
let mainChart: ECharts | null = null;

function renderChart() {
  if (!chartRef.value) return;
  if (!modelMetrics.value.length) {
    mainChart?.clear();
    return;
  }

  const metrics = [...modelMetrics.value].sort((a, b) => metricCallCount(b) - metricCallCount(a));
  mainChart ??= init(chartRef.value);

  if (activeChart.value === "share") {
    mainChart.setOption({
      animationDuration: 420,
      tooltip: {
        trigger: "item",
        formatter: (params: any) => `${params.name}<br/>调用 ${params.value} 次 · ${params.percent}%`,
      },
      legend: {
        bottom: 0,
        icon: "circle",
        textStyle: { color: "#475569", fontSize: 12 },
      },
      series: [
        {
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "44%"],
          itemStyle: { borderRadius: 10, borderColor: "#fff", borderWidth: 4 },
          label: { color: "#334155", formatter: "{b}" },
          data: metrics.map((item, index) => ({
            name: item.model_key,
            value: metricCallCount(item),
            itemStyle: { color: pieColors[index % pieColors.length] },
          })),
        },
      ],
    });
    return;
  }

  if (activeChart.value === "tokens") {
    const items = [...metrics].sort((a, b) => (b.avg_tokens || 0) - (a.avg_tokens || 0));
    mainChart.setOption({
      animationDuration: 420,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: any) => {
          const point = params[0];
          return `${point.name}<br/>平均 Token ${formatTokens(Number(point.value))}`;
        },
      },
      grid: { left: 140, right: 28, top: 18, bottom: 36 },
      xAxis: {
        type: "value",
        axisLabel: { color: "#64748b", formatter: (value: number) => formatTokens(value) },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
      },
      yAxis: {
        type: "category",
        data: items.map((item) => item.model_key),
        axisLabel: { color: "#0f172a", fontWeight: 600 },
      },
      series: [
        {
          type: "bar",
          barWidth: 16,
          data: items.map((item) => item.avg_tokens || 0),
          itemStyle: {
            borderRadius: [0, 8, 8, 0],
            color: "#38bdf8",
          },
          label: {
            show: true,
            position: "right",
            color: "#0369a1",
            formatter: (params: any) => formatTokens(Number(params.value)),
          },
        },
      ],
    });
    return;
  }

  if (activeChart.value === "ranking") {
    mainChart.setOption({
      animationDuration: 420,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: any) => {
          const point = params[0];
          return `${point.name}<br/>调用 ${Number(point.value).toLocaleString()} 次`;
        },
      },
      grid: { left: 54, right: 24, top: 22, bottom: 46 },
      xAxis: {
        type: "category",
        data: metrics.map((item) => item.model_key),
        axisLabel: { color: "#475569", interval: 0, rotate: 16 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#64748b" },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 42,
          data: metrics.map((item) => metricCallCount(item)),
          itemStyle: {
            borderRadius: [10, 10, 0, 0],
            color: "#334155",
          },
        },
      ],
    });
    return;
  }

  const costMetrics = [...metrics].sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0));
  mainChart.setOption({
    animationDuration: 420,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: any) => {
        const point = params[0];
        return `${point.name}<br/>成本 ${formatCost(Number(point.value))}`;
      },
    },
    grid: { left: 54, right: 24, top: 22, bottom: 46 },
    xAxis: {
      type: "category",
      data: costMetrics.map((item) => item.model_key),
      axisLabel: { color: "#475569", interval: 0, rotate: 16 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#64748b", formatter: (value: number) => formatCost(value) },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 42,
        data: costMetrics.map((item) => Number(item.total_cost || 0)),
        itemStyle: {
          borderRadius: [10, 10, 0, 0],
          color: "#f59e0b",
        },
      },
    ],
  });
}

function handleResize() {
  mainChart?.resize();
}

watch(
  [modelMetrics, activeChart],
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true },
);

onMounted(() => {
  fetchData();
  fetchModels();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  mainChart?.dispose();
  window.removeEventListener("resize", handleResize);
});

const pieColors = ["#334155", "#fbbf24", "#38bdf8", "#22c55e", "#f97316", "#a855f7"];
</script>

<template>
  <div class="usage-shell">
    <section class="console-head">
      <div>
        <p class="eyebrow">Model Console</p>
        <h2>模型观测</h2>
        <p class="sub">统一查看请求量、Token、成本、模型健康与质检模型表现；embedding 参与用量和成本，质检通过率/幻觉率只统计产生质检结果的生成模型。</p>
      </div>

      <div class="range-switch">
        <button
          v-for="days in [7, 30, 90]"
          :key="days"
          :class="['range-btn', { active: rangeDays === days }]"
          @click="setRange(days)"
        >
          {{ days }} 日
        </button>
      </div>
    </section>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
      show-icon
    />

    <el-alert
      title="模型成本按模型配置中的输入/输出单价折算；没有单价的模型不会被补算虚构价格。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      title="口径说明：本页的质检通过率和质检幻觉率来自检测任务结果，不等同于分析中心质量报告里的聊天幻觉率；embedding 模型没有质检结果归属时不会展示质量率。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-alert
      v-if="hasUnpricedUsage"
      title="发现有模型已经产生 Token，但模型配置里仍缺少输入或输出价格，请补全后再看完整成本。"
      type="warning"
      :closable="false"
      show-icon
    />

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.label" :class="['summary-card', card.tone]">
        <span class="summary-label">{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <span class="summary-sub">{{ card.sub }}</span>
      </article>
    </section>

    <section class="analysis-layout">
      <el-card shadow="never" class="analysis-card">
        <template #header>
          <div class="analysis-head">
            <div>
              <strong>模型用量分析</strong>
              <span>{{ chartTabs.find((item) => item.key === activeChart)?.desc }}</span>
            </div>

            <nav class="chart-tabs">
              <button
                v-for="item in chartTabs"
                :key="item.key"
                :class="['chart-tab', { active: activeChart === item.key }]"
                @click="activeChart = item.key"
              >
                {{ item.label }}
              </button>
            </nav>
          </div>
        </template>

        <div v-if="modelMetrics.length" ref="chartRef" class="analysis-chart" />
        <el-empty v-else description="最近没有模型调用数据" :image-size="64" />
      </el-card>

      <div class="spotlight-column">
        <el-card v-for="metric in spotlightModels" :key="metric.model_key" shadow="never" class="spotlight-card">
          <div class="spotlight-top">
            <div>
              <strong>{{ metric.model_key }}</strong>
              <p>{{ metricCallCount(metric).toLocaleString() }} 次调用 · 占比 {{ usageShare(metric) }}%</p>
            </div>
            <el-tag
              :type="healthTagType(healthStatusMap[metric.model_key] || 'unknown')"
              size="small"
              effect="dark"
            >
              {{ healthLabel(healthStatusMap[metric.model_key] || "unknown") }}
            </el-tag>
          </div>

          <div class="spotlight-grid">
            <div>
              <span>总成本</span>
              <strong>{{ formatUsageCost(metric) }}</strong>
            </div>
            <div>
              <span>平均 Token</span>
              <strong>{{ formatTokens(metric.avg_tokens) }}</strong>
            </div>
            <div>
              <span>质检通过率</span>
              <strong>{{ qualityRateText(metric, "pass_rate") }}</strong>
            </div>
            <div>
              <span>质检幻觉率</span>
              <strong>{{ qualityRateText(metric, "hallucination_rate") }}</strong>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="spotlight-card note-card">
          <strong>页面口径说明</strong>
          <p>这里负责模型观测：调用、Token、成本、健康和质检模型表现统一看；分析中心保留质量趋势与质检/聊天质量口径，告警分布留在告警管理。</p>
        </el-card>
      </div>
    </section>

    <section class="table-section">
      <div class="section-title">
        <h3>模型计费、用量与质检表现</h3>
        <span>同一张表里对齐配置状态、真实用量和质检结果表现；embedding 有用量就会展示 Token/成本，但质量率显示为不适用。</span>
      </div>

      <el-alert v-if="modelsError" :title="modelsError" type="warning" :closable="false" show-icon />

      <el-card shadow="never" class="table-card">
        <el-table :data="usageRows" :loading="loading || modelsLoading" size="small" empty-text="暂无模型配置">
          <el-table-column prop="display_name" label="名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="model_key" label="Key" min-width="180" show-overflow-tooltip />
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              {{ modelTypeLabels[row.model_type] || row.model_type || "-" }}
            </template>
          </el-table-column>
          <el-table-column prop="provider" label="供应商" width="100" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="healthTagType(row.health_status || 'unknown')" size="small" effect="dark">
                {{ healthLabel(row.health_status || "unknown") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="70">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
                {{ row.is_active ? "是" : "否" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="输入价" width="110">
            <template #default="{ row }">{{ formatPrice(row.input_price_per_million) }}</template>
          </el-table-column>
          <el-table-column label="输出价" width="110">
            <template #default="{ row }">{{ formatPrice(row.output_price_per_million) }}</template>
          </el-table-column>
          <el-table-column label="计费状态" width="100">
            <template #default="{ row }">
              <el-tag :type="pricingStatus(row).type" size="small" effect="plain">
                {{ pricingStatus(row).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="调用次数" width="100">
            <template #default="{ row }">{{ metricCallCount(row.usage) || "-" }}</template>
          </el-table-column>
          <el-table-column label="总 Tokens" width="110">
            <template #default="{ row }">{{ row.usage ? formatTokens(row.usage.total_tokens) : "-" }}</template>
          </el-table-column>
          <el-table-column label="总成本" width="120">
            <template #default="{ row }">{{ formatUsageCost(row.usage) }}</template>
          </el-table-column>
          <el-table-column label="单次均价" width="120">
            <template #default="{ row }">{{ formatAvgCost(row.usage) }}</template>
          </el-table-column>
          <el-table-column label="质检结果" width="100">
            <template #default="{ row }">{{ row.usage?.result_count || "-" }}</template>
          </el-table-column>
          <el-table-column label="质检通过率" width="120">
            <template #default="{ row }">{{ qualityRateText(row.usage, "pass_rate") }}</template>
          </el-table-column>
          <el-table-column label="质检幻觉率" width="120">
            <template #default="{ row }">{{ qualityRateText(row.usage, "hallucination_rate") }}</template>
          </el-table-column>
          <el-table-column label="RPM" width="80">
            <template #default="{ row }">{{ row.rpm_limit ?? "-" }}</template>
          </el-table-column>
          <el-table-column label="API Key" width="90">
            <template #default="{ row }">
              <el-tag :type="row.has_api_key ? 'success' : 'danger'" size="small" effect="plain">
                {{ row.has_api_key ? "已配置" : "未配置" }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.usage-shell {
  min-height: 100vh;
  display: grid;
  gap: 18px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.16), transparent 25%),
    radial-gradient(circle at right top, rgba(6, 182, 212, 0.14), transparent 26%),
    linear-gradient(180deg, #eff6ff 0%, #f8fafc 100%);
}

.console-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 86% 18%, rgba(125, 211, 252, 0.26), transparent 28%),
    linear-gradient(135deg, #0f172a 0%, #1d4ed8 50%, #0e7490 100%);
  color: #f8fafc;
  box-shadow: 0 24px 60px rgba(29, 78, 216, 0.18);
}

.eyebrow {
  margin: 0 0 8px;
  color: rgba(248, 250, 252, 0.76);
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.console-head h2 {
  margin: 0;
  color: #f8fafc;
  font-size: 36px;
  line-height: 1.1;
}

.sub {
  max-width: 760px;
  margin: 12px 0 0;
  color: rgba(248, 250, 252, 0.82);
  line-height: 1.7;
}

.range-switch {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.range-btn {
  min-width: 84px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}

.range-btn:hover {
  border-color: rgba(255, 255, 255, 0.42);
  background: rgba(255, 255, 255, 0.16);
}

.range-btn.active {
  border-color: rgba(255, 255, 255, 0.9);
  background: #f8fafc;
  color: #1e3a8a;
  box-shadow: 0 10px 24px rgba(29, 78, 216, 0.24);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  display: grid;
  gap: 8px;
  padding: 20px;
  border-radius: 22px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.05);
}

.summary-label {
  color: #64748b;
  font-size: 13px;
}

.summary-card strong {
  color: #0f172a;
  font-size: 34px;
  line-height: 1;
}

.summary-sub {
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.6;
}

.summary-card.cost strong {
  color: #b45309;
}

.summary-card.calls strong {
  color: #1d4ed8;
}

.summary-card.tokens strong {
  color: #0284c7;
}

.summary-card.quality strong {
  color: #0f766e;
}

.analysis-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}

.analysis-card,
.spotlight-card,
.table-card {
  border-radius: 24px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
}

.analysis-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.analysis-head strong {
  display: block;
  color: #0f172a;
  font-size: 20px;
}

.analysis-head span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.chart-tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.chart-tab {
  padding: 8px 12px;
  border: none;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}

.chart-tab:hover {
  color: #0f172a;
}

.chart-tab.active {
  background: #0f172a;
  color: #fff;
}

.analysis-chart {
  width: 100%;
  height: 420px;
}

.spotlight-column {
  display: grid;
  gap: 14px;
}

.spotlight-card {
  padding: 18px;
}

.spotlight-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.spotlight-top strong {
  color: #0f172a;
  font-size: 16px;
}

.spotlight-top p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.spotlight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.spotlight-grid span {
  display: block;
  color: #94a3b8;
  font-size: 12px;
}

.spotlight-grid strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 18px;
}

.note-card strong {
  display: block;
  color: #0f172a;
  font-size: 16px;
}

.note-card p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.table-section {
  display: grid;
  gap: 12px;
}

.section-title h3 {
  margin: 0;
  color: #0f172a;
  font-size: 20px;
}

.section-title span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analysis-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 840px) {
  .usage-shell {
    padding: 14px;
  }

  .console-head {
    flex-direction: column;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .analysis-head {
    flex-direction: column;
  }

  .chart-tabs {
    justify-content: flex-start;
  }

  .spotlight-grid {
    grid-template-columns: 1fr;
  }
}
</style>
