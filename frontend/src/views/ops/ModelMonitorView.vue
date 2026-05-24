<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { modelConfigApi } from "@/api/model_config.api";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelConfig } from "@/types/governance.types";

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent] as any);

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const modelMetrics = computed(() => analyticsStore.overview?.model_metrics ?? []);
const totalCost = computed(() => analyticsStore.overview?.total_cost ?? 0);
const totalCalls = computed(() => {
  const modelCallTotal = modelMetrics.value.reduce((sum, item) => sum + (item.call_count ?? item.result_count ?? 0), 0);
  return modelCallTotal || analyticsStore.overview?.total_results || 0;
});
const avgCostPerCall = computed(() => (totalCalls.value ? totalCost.value / totalCalls.value : 0));
const sortedCostMetrics = computed(() =>
  [...modelMetrics.value].sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0)),
);
const maxCost = computed(() => sortedCostMetrics.value[0]?.total_cost || 1);
const hasUnpricedUsage = computed(() =>
  modelMetrics.value.some((item) => (item.total_tokens ?? 0) > 0 && Number(item.total_cost || 0) === 0),
);

const models = ref<ModelConfig[]>([]);
const modelsLoading = ref(false);
const modelsError = ref("");

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
  for (const m of models.value) {
    map[m.model_key] = m.health_status || "unknown";
  }
  return map;
});

async function fetchData() {
  loading.value = true;
  try {
    await analyticsStore.fetchOverview();
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
  } catch (e: any) {
    modelsError.value = e?.response?.data?.message || "获取模型列表失败";
  } finally {
    modelsLoading.value = false;
  }
}

function formatRate(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatPrice(val: number | null | undefined) {
  if (val == null) return "-";
  return `￥${val.toFixed(2)}/M`;
}

function formatTokens(value: number | null | undefined) {
  if (value == null || value <= 0) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return `${value.toFixed(0)}`;
}

function formatCost(value: number | null | undefined) {
  const safe = Number(value || 0);
  if (safe >= 1) return `¥${safe.toFixed(2)}`;
  if (safe >= 0.01) return `¥${safe.toFixed(4)}`;
  return `¥${safe.toFixed(6)}`;
}

function formatModelCost(metric: { total_cost?: number; total_tokens?: number }) {
  if ((metric.total_tokens ?? 0) > 0 && Number(metric.total_cost || 0) === 0) return "未配置价格";
  return formatCost(metric.total_cost);
}

function formatSummaryCost(value: number) {
  if (hasUnpricedUsage.value && Number(value || 0) === 0) return "未配置价格";
  return formatCost(value);
}

function formatModelAvgCost(metric: { call_count?: number; result_count?: number; total_cost?: number; total_tokens?: number }) {
  if ((metric.total_tokens ?? 0) > 0 && Number(metric.total_cost || 0) === 0) return "未配置价格";
  return formatCost(avgCost(metric));
}

function formatPct(part: number, whole: number) {
  if (!whole) return "0%";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

function metricCallCount(metric: { call_count?: number; result_count?: number }) {
  return metric.call_count ?? metric.result_count ?? 0;
}

function avgCost(metric: { call_count?: number; result_count?: number; total_cost?: number }) {
  const calls = metricCallCount(metric);
  return calls ? Number(metric.total_cost || 0) / calls : 0;
}

function costBarWidth(cost: number) {
  return `${Math.max((cost / maxCost.value) * 100, 2)}%`;
}

function statusColor(passRate: number) {
  if (passRate >= 0.85) return "#16a34a";
  if (passRate >= 0.7) return "#d97706";
  return "#dc2626";
}

function healthTagType(status: string) {
  return healthLabels[status]?.tag || "info";
}

function healthLabel(status: string) {
  return healthLabels[status]?.label || status;
}

const tokenChartRef = ref<HTMLElement | null>(null);
let tokenChart: ECharts | null = null;

const tokenChartData = computed(() =>
  [...modelMetrics.value]
    .filter((m) => m.avg_tokens != null && m.avg_tokens > 0)
    .sort((a, b) => (b.avg_tokens || 0) - (a.avg_tokens || 0)),
);

function renderTokenChart() {
  if (!tokenChartRef.value || !tokenChartData.value.length) return;
  tokenChart ??= init(tokenChartRef.value);
  const items = tokenChartData.value;
  tokenChart.setOption({
    animationDuration: 500,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: any) => {
        const tokenItem = params.find((p: any) => p.seriesName === "平均 Token");
        const tokenVal = tokenItem?.value ?? 0;
        return `<strong>${params[0].name}</strong><br/>平均 Token: ${formatTokens(Number(tokenVal))}`;
      },
    },
    grid: { left: 140, right: 48, top: 24, bottom: 40 },
    xAxis: {
      type: "value",
      name: "Token",
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: {
        color: "#2563eb",
        formatter: (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`),
      },
      splitLine: { lineStyle: { color: "rgba(25,42,70,0.06)" } },
    },
    yAxis: {
      type: "category",
      data: items.map((m) => m.model_key),
      axisLabel: { color: "#18181b", fontSize: 12, fontWeight: 600 },
    },
    series: [
      {
        name: "平均 Token",
        type: "bar",
        barWidth: 16,
        data: items.map((m) => m.avg_tokens),
        itemStyle: { borderRadius: [0, 4, 4, 0], color: "#2563eb" },
        label: {
          show: true,
          position: "right",
          color: "#2563eb",
          fontSize: 11,
          formatter: (p: any) => formatTokens(Number(p.value)),
        },
      },
    ],
  });
}

function handleResize() {
  tokenChart?.resize();
}

watch(tokenChartData, async () => {
  await nextTick();
  renderTokenChart();
}, { deep: true });

onMounted(() => {
  fetchData();
  fetchModels();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  tokenChart?.dispose();
  window.removeEventListener("resize", handleResize);
});
</script>

<template>
  <div class="monitor-shell">
    <section class="hero">
      <p class="eyebrow">Model Monitor</p>
      <h2>调用监控</h2>
      <p class="sub">统一查看模型健康、调用效果、Token 消耗和成本，不再拆成重复的成本分析页。</p>
    </section>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <el-alert
      title="模型相关指标已收口在这里：通过率、幻觉率、Token、总成本和均价使用同一套本地账本口径。"
      type="info"
      :closable="false"
    />

    <el-alert
      v-if="hasUnpricedUsage"
      title="检测到有模型已产生 Token 但成本为 0，通常是模型配置未填写输入/输出单价；这里不会用假价格补算。"
      type="warning"
      :closable="false"
      show-icon
    />

    <section class="summary-row">
      <div class="summary-card">
        <span class="summary-label">总成本</span>
        <strong>{{ formatSummaryCost(totalCost) }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">总调用次数</span>
        <strong>{{ totalCalls.toLocaleString() }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">平均单次成本</span>
        <strong>{{ formatSummaryCost(avgCostPerCall) }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">有调用模型数</span>
        <strong>{{ modelMetrics.length }}</strong>
      </div>
    </section>

    <section class="metric-grid">
      <el-card v-for="m in modelMetrics" :key="m.model_key" shadow="never" class="model-card">
        <div class="model-header">
          <strong class="model-name">{{ m.model_key }}</strong>
          <el-tag
            :type="healthTagType(healthStatusMap[m.model_key] || 'unknown')"
            size="small"
            effect="dark"
            class="status-tag"
          >
            {{ healthLabel(healthStatusMap[m.model_key] || 'unknown') }}
          </el-tag>
        </div>
        <div class="model-stats">
          <div class="stat">
            <span class="stat-label">通过率</span>
            <span class="stat-value" :style="{ color: m.result_count ? statusColor(m.pass_rate) : '#a1a1aa' }">
              {{ m.result_count ? formatRate(m.pass_rate) : "-" }}
            </span>
          </div>
          <div class="stat">
            <span class="stat-label">幻觉率</span>
            <span class="stat-value">{{ formatRate(m.hallucination_rate) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">调用次数</span>
            <span class="stat-value">{{ metricCallCount(m) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">平均 Token</span>
            <span class="stat-value">{{ formatTokens(m.avg_tokens) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">总成本</span>
            <span class="stat-value">{{ formatModelCost(m) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">均价</span>
            <span class="stat-value">{{ formatModelAvgCost(m) }}</span>
          </div>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: formatRate(m.pass_rate), background: statusColor(m.pass_rate) }"
          />
        </div>
      </el-card>
    </section>

    <el-empty v-if="!loading && !modelMetrics.length" description="暂无模型调用数据" />

    <el-card v-if="tokenChartData.length" shadow="never" class="chart-card">
      <template #header>
        <div class="card-head">
          <strong>平均 Token 对比</strong>
          <span>按模型查看单次响应的平均 Token 使用量</span>
        </div>
      </template>
      <div ref="tokenChartRef" class="chart-host" />
    </el-card>

    <el-card v-if="sortedCostMetrics.length" shadow="never" class="chart-card">
      <template #header>
        <div class="card-head">
          <strong>模型成本分布</strong>
          <span>按总成本降序排列，和 Token/调用质量共用同一模型维度</span>
        </div>
      </template>
      <div class="cost-list">
        <div v-for="m in sortedCostMetrics" :key="m.model_key" class="cost-row">
          <div class="cost-bar-bg">
            <div class="cost-bar" :style="{ width: costBarWidth(m.total_cost) }" />
          </div>
          <div class="cost-info">
            <div class="cost-model">
              <span class="model-key">{{ m.model_key }}</span>
              <strong>{{ formatPct(m.total_cost, totalCost) }}</strong>
            </div>
            <div class="cost-detail">
              <span>{{ formatModelCost(m) }}</span>
              <span>{{ metricCallCount(m) }} 次调用</span>
              <span>均价 {{ formatModelAvgCost(m) }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <section class="section-header">
      <h3>模型配置详情</h3>
      <span class="section-count">共 {{ models.length }} 个模型</span>
    </section>

    <el-alert v-if="modelsError" :title="modelsError" type="warning" :closable="false" />

    <el-card shadow="never" class="table-card">
      <el-table :data="models" :loading="modelsLoading" size="small" empty-text="暂无模型配置">
        <el-table-column prop="display_name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="model_key" label="Key" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <span class="text-[13px]">{{ modelTypeLabels[row.model_type] || row.model_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" width="100" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="healthLabels[row.health_status]?.tag || 'info'" size="small" effect="dark">
              {{ healthLabels[row.health_status]?.label || row.health_status }}
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
        <el-table-column label="输入价" width="100">
          <template #default="{ row }">{{ formatPrice(row.input_price_per_million) }}</template>
        </el-table-column>
        <el-table-column label="输出价" width="100">
          <template #default="{ row }">{{ formatPrice(row.output_price_per_million) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="70">
          <template #default="{ row }">{{ row.priority }}</template>
        </el-table-column>
        <el-table-column label="RPM" width="70">
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

    <div class="refresh-row">
      <el-button :loading="loading || modelsLoading" @click="() => { fetchData(); fetchModels(); }">刷新数据</el-button>
    </div>
  </div>
</template>

<style scoped>
.monitor-shell {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 52%, #0f766e 100%);
  color: #f8fafc;
}

.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; opacity: 0.76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248, 250, 252, 0.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-card {
  padding: 18px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
}

.summary-label {
  display: block;
  color: #71717a;
  font-size: 13px;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  color: #18181b;
  font-size: 28px;
  font-weight: 800;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.model-card {
  border-radius: 16px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.model-name {
  font-size: 16px;
  color: #18181b;
  font-weight: 700;
  word-break: break-all;
}

.status-tag {
  border-radius: 6px;
  font-weight: 700;
}

.model-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.stat { display: flex; flex-direction: column; gap: 2px; }
.stat-label { font-size: 12px; color: #a1a1aa; }
.stat-value { font-size: 18px; font-weight: 700; color: #18181b; }

.progress-bar {
  height: 6px;
  border-radius: 3px;
  background: #f4f4f5;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #18181b;
}

.section-count {
  font-size: 13px;
  color: #a1a1aa;
}

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
}

.chart-card {
  border-radius: 20px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.card-head strong { display: block; font-size: 18px; color: #172033; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
.chart-host { width: 100%; height: 320px; }

.cost-list { display: flex; flex-direction: column; gap: 12px; }
.cost-row { position: relative; min-height: 76px; }
.cost-bar-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: 10px;
  overflow: hidden;
  background: #fafafa;
}
.cost-bar {
  height: 100%;
  background: rgba(15, 118, 110, 0.12);
  border-radius: 10px;
  transition: width 0.35s ease;
}
.cost-info {
  position: relative;
  z-index: 1;
  padding: 14px 16px;
}
.cost-model {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}
.model-key { font-weight: 700; color: #18181b; word-break: break-all; }
.cost-model strong { color: #0f766e; font-size: 18px; }
.cost-detail {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 6px;
  color: #71717a;
  font-size: 13px;
}

.refresh-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

@media (max-width: 960px) {
  .summary-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
