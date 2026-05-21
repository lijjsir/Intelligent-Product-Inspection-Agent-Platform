<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";
import { useAnalyticsStore } from "@/stores/analytics.store";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent]);

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const overview = computed(() => analyticsStore.overview);
const riskDistribution = computed(() => overview.value?.risk_distribution ?? []);
const alertDistribution = computed(() => overview.value?.alert_distribution ?? []);
const modelMetrics = computed(() => overview.value?.model_metrics ?? []);
const passRateTrend = computed(() => overview.value?.pass_rate_trend ?? []);
const hallucinationTrend = computed(() => overview.value?.hallucination_trend ?? []);

const totalTasks = computed(() => overview.value?.total_tasks ?? 0);
const totalAlerts = computed(() => overview.value?.total_alerts ?? 0);
const passRate = computed(() => overview.value?.pass_rate ?? 0);
const hallucinationRate = computed(() => overview.value?.hallucination_rate ?? 0);
const avgRiskScore = computed(() => overview.value?.avg_risk_score ?? 0);
const avgLatencyMs = computed(() => overview.value?.avg_latency_ms ?? 0);
const totalCost = computed(() => overview.value?.total_cost ?? 0);

const totalRisks = computed(() => riskDistribution.value.reduce((sum, r) => sum + r.value, 0));
const totalAlertCount = computed(() => alertDistribution.value.reduce((sum, a) => sum + a.value, 0));

const riskLabel: Record<string, string> = {
  critical: "严重", high: "高风险", medium: "中风险", low: "低风险",
};
const riskBarClass: Record<string, string> = {
  critical: "bar-critical", high: "bar-high", medium: "bar-medium", low: "bar-low",
};
const alertLabel: Record<string, string> = {
  critical: "严重", error: "错误", warning: "警告", info: "提示",
};
const alertBarClass: Record<string, string> = {
  critical: "bar-critical", error: "bar-high", warning: "bar-medium", info: "bar-low",
};

const modelTypeLabels: Record<string, string> = { chat: "对话", embedding: "嵌入", multimodal: "多模态", vision: "视觉", llm: "LLM", vlm: "VLM" };

async function fetchData() {
  loading.value = true;
  try {
    await analyticsStore.fetchOverview();
  } finally {
    loading.value = false;
  }
}

function pct(part: number, whole: number) {
  if (!whole) return "0%";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

function formatCost(value: number) {
  if (value >= 1) return `¥${value.toFixed(2)}`;
  if (value >= 0.01) return `¥${value.toFixed(4)}`;
  return `¥${value.toFixed(6)}`;
}

function formatRate(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function statusColor(passRate: number) {
  if (passRate >= 0.85) return "#16a34a";
  if (passRate >= 0.7) return "#d97706";
  return "#dc2626";
}

// ---- Mini trend charts ----
const passTrendRef = ref<HTMLElement | null>(null);
let passChart: ECharts | null = null;
const halluTrendRef = ref<HTMLElement | null>(null);
let halluChart: ECharts | null = null;

function renderMiniCharts() {
  // Pass rate trend
  if (passTrendRef.value && passRateTrend.value.length) {
    passChart ??= init(passTrendRef.value);
    passChart.setOption({
      animationDuration: 400,
      grid: { left: 40, right: 8, top: 8, bottom: 24 },
      xAxis: { type: "category", data: passRateTrend.value.map((p: any) => p.date ?? ""), show: false },
      yAxis: { type: "value", min: 0, max: 1, show: false },
      series: [{
        type: "line",
        data: passRateTrend.value.map((p: any) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#22c55e", width: 2 },
        areaStyle: { color: "rgba(34,197,94,0.12)" },
      }],
    });
  }

  // Hallucination trend
  if (halluTrendRef.value && hallucinationTrend.value.length) {
    halluChart ??= init(halluTrendRef.value);
    halluChart.setOption({
      animationDuration: 400,
      grid: { left: 40, right: 8, top: 8, bottom: 24 },
      xAxis: { type: "category", data: hallucinationTrend.value.map((p: any) => p.date ?? ""), show: false },
      yAxis: { type: "value", min: 0, max: 1, show: false },
      series: [{
        type: "line",
        data: hallucinationTrend.value.map((p: any) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#f59e0b", width: 2 },
        areaStyle: { color: "rgba(245,158,11,0.12)" },
      }],
    });
  }
}

onMounted(async () => {
  await fetchData();
  setTimeout(renderMiniCharts, 200);
});
</script>

<template>
  <div class="dq-shell">
    <section class="hero">
      <p class="eyebrow">Data Quality</p>
      <h2>数据质量</h2>
      <p class="sub">监控检测质量与告警态势，识别风险模式和异常波动。</p>
    </section>

    <!-- Summary cards (6) -->
    <section class="summary-row">
      <div class="summary-card">
        <span class="sl">总任务数</span>
        <span class="sv">{{ totalTasks.toLocaleString() }}</span>
      </div>
      <div class="summary-card">
        <span class="sl">通过率</span>
        <span class="sv" :style="{ color: totalTasks ? statusColor(passRate) : '#18181b' }">
          {{ formatRate(passRate) }}
        </span>
      </div>
      <div class="summary-card">
        <span class="sl">幻觉率</span>
        <span class="sv" :style="{ color: hallucinationRate > 0.1 ? '#dc2626' : '#18181b' }">
          {{ formatRate(hallucinationRate) }}
        </span>
      </div>
      <div class="summary-card">
        <span class="sl">告警总数</span>
        <span class="sv" :style="{ color: totalAlerts > 0 ? '#dc2626' : '#18181b' }">
          {{ totalAlerts.toLocaleString() }}
        </span>
      </div>
      <div class="summary-card">
        <span class="sl">平均风险分</span>
        <span class="sv">{{ avgRiskScore.toFixed(1) }}</span>
      </div>
      <div class="summary-card">
        <span class="sl">平均耗时 / 总成本</span>
        <span class="sv">{{ avgLatencyMs.toFixed(0) }}<span class="sv-unit">ms</span></span>
        <span class="sl-sub">{{ formatCost(totalCost) }}</span>
      </div>
    </section>

    <!-- Distribution row: Risk + Alert side by side -->
    <section class="distro-row-grid">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <strong>风险分布</strong>
          <span class="card-sub">检测结果的风险等级分布</span>
        </template>
        <div v-if="riskDistribution.length" class="distro-list">
          <div v-for="r in riskDistribution" :key="r.name" class="distro-row">
            <span class="distro-name">{{ riskLabel[r.name.toLowerCase()] || r.name }}</span>
            <span class="distro-tag" :class="riskBarClass[r.name.toLowerCase()] || 'bar-low'">
              {{ r.value }}
            </span>
            <div class="distro-bar-bg">
              <div :class="['distro-bar', riskBarClass[r.name.toLowerCase()] || 'bar-low']" :style="{ width: pct(r.value, totalRisks) }" />
            </div>
            <span class="distro-pct">{{ pct(r.value, totalRisks) }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无风险数据" :image-size="60" />
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <strong>告警分布</strong>
          <span class="card-sub">按严重度统计告警触发数量</span>
        </template>
        <div v-if="alertDistribution.length" class="distro-list">
          <div v-for="a in alertDistribution" :key="a.name" class="distro-row">
            <span class="distro-name">{{ alertLabel[a.name.toLowerCase()] || a.name }}</span>
            <span class="distro-tag" :class="alertBarClass[a.name.toLowerCase()] || 'bar-low'">
              {{ a.value }}
            </span>
            <div class="distro-bar-bg">
              <div :class="['distro-bar', alertBarClass[a.name.toLowerCase()] || 'bar-low']" :style="{ width: pct(a.value, totalAlertCount) }" />
            </div>
            <span class="distro-pct">{{ pct(a.value, totalAlertCount) }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无告警数据" :image-size="60" />
      </el-card>
    </section>

    <!-- Trend charts row -->
    <section class="trend-row">
      <el-card v-if="passRateTrend.length" shadow="never" class="panel-card">
        <template #header>
          <strong>通过率趋势</strong>
          <span class="card-sub">近 7 天质检通过率变化</span>
        </template>
        <div ref="passTrendRef" class="mini-chart" />
      </el-card>
      <el-card v-if="hallucinationTrend.length" shadow="never" class="panel-card">
        <template #header>
          <strong>幻觉率趋势</strong>
          <span class="card-sub">近 7 天幻觉率变化</span>
        </template>
        <div ref="halluTrendRef" class="mini-chart" />
      </el-card>
    </section>

    <!-- Model metrics comparison -->
    <el-card v-if="modelMetrics.length" shadow="never" class="table-card">
      <template #header>
        <div class="card-head">
          <strong>模型指标对比</strong>
          <span>各模型调用次数、通过率、幻觉率、Token 及成本</span>
        </div>
      </template>
      <el-table :data="modelMetrics" size="small" empty-text="暂无模型数据">
        <el-table-column prop="model_key" label="模型 Key" min-width="160" show-overflow-tooltip />
        <el-table-column label="调用次数" width="100">
          <template #default="{ row }">{{ (row.result_count ?? 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="通过率" width="90">
          <template #default="{ row }">
            <span v-if="row.result_count" :style="{ color: statusColor(row.pass_rate) }" class="font-semibold">
              {{ formatRate(row.pass_rate) }}
            </span>
            <span v-else class="text-zinc-400">-</span>
          </template>
        </el-table-column>
        <el-table-column label="幻觉率" width="90">
          <template #default="{ row }">
            <span :style="{ color: row.hallucination_rate > 0.1 ? '#dc2626' : '#18181b' }" class="font-semibold">
              {{ formatRate(row.hallucination_rate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="平均 Token" width="110">
          <template #default="{ row }">
            {{ row.avg_tokens != null && row.avg_tokens > 0 ? (row.avg_tokens >= 1000 ? (row.avg_tokens / 1000).toFixed(1) + 'k' : row.avg_tokens.toFixed(0)) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="平均延迟" width="100">
          <template #default="{ row }">
            {{ row.avg_latency_ms != null && row.avg_latency_ms > 0 ? row.avg_latency_ms.toFixed(0) + 'ms' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="130">
          <template #default="{ row }">
            <span :style="{ color: row.total_cost > 0 ? '#52525b' : '#a1a1aa' }">
              {{ row.total_cost > 0 ? formatCost(row.total_cost) : '-' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="refresh-row">
      <el-button :loading="loading" @click="fetchData">刷新数据</el-button>
    </div>
  </div>
</template>

<style scoped>
.dq-shell { display: grid; gap: 18px; padding: 24px; }

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 52%, #0891b2 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.summary-card {
  padding: 18px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.sl { display: block; font-size: 12px; color: #a1a1aa; }
.sv { display: block; margin-top: 6px; font-size: 24px; font-weight: 800; color: #18181b; }
.sv-unit { font-size: 14px; font-weight: 500; color: #a1a1aa; }
.sl-sub { display: block; margin-top: 2px; font-size: 12px; color: #71717a; font-weight: 600; }

.distro-row-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.panel-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
}
.panel-card strong { display: block; font-size: 18px; color: #172033; }
.card-sub { display: block; margin-top: 4px; font-size: 13px; color: #64748b; }

.distro-list { display: flex; flex-direction: column; gap: 10px; }
.distro-row { display: flex; align-items: center; gap: 10px; }
.distro-name { width: 70px; font-size: 13px; color: #52525b; text-align: right; flex-shrink: 0; font-weight: 600; }
.distro-tag {
  width: 44px; text-align: center; font-size: 13px; font-weight: 700; color: #fff;
  padding: 2px 0; border-radius: 4px; flex-shrink: 0;
}
.bar-critical { background: #dc2626; }
.bar-high { background: #f59e0b; }
.bar-medium { background: #3b82f6; }
.bar-low { background: #22c55e; }
.distro-bar-bg { flex: 1; height: 18px; border-radius: 5px; background: #f4f4f5; overflow: hidden; }
.distro-bar { height: 100%; border-radius: 5px; transition: width .3s ease; }
.distro-pct { width: 44px; font-size: 12px; font-weight: 600; color: #71717a; }

.trend-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.mini-chart { width: 100%; height: 160px; }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}
.card-head strong { display: block; font-size: 18px; color: #172033; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }

.refresh-row { display: flex; align-items: center; gap: 16px; }

@media (max-width: 1100px) {
  .summary-row { grid-template-columns: repeat(3, 1fr); }
  .distro-row-grid, .trend-row { grid-template-columns: 1fr; }
}
</style>
