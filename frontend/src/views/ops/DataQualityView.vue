<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { useAnalyticsStore } from "@/stores/analytics.store";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent] as any);

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const overview = computed(() => analyticsStore.overview);
const alertDistribution = computed(() => overview.value?.alert_distribution ?? []);
const passRateTrend = computed(() => overview.value?.pass_rate_trend ?? []);
const hallucinationTrend = computed(() => overview.value?.hallucination_trend ?? []);

const totalResults = computed(() => overview.value?.total_results ?? 0);
const totalAlerts = computed(() => overview.value?.total_alerts ?? 0);
const passRate = computed(() => overview.value?.pass_rate ?? 0);
const hallucinationRate = computed(() => overview.value?.hallucination_rate ?? 0);
const avgRiskScore = computed(() => overview.value?.avg_risk_score ?? 0);
const avgLatencyMs = computed(() => overview.value?.avg_latency_ms ?? 0);

const totalAlertCount = computed(() => alertDistribution.value.reduce((sum, a) => sum + a.value, 0));

const alertLabel: Record<string, string> = {
  critical: "严重",
  error: "错误",
  warning: "警告",
  info: "提示",
};

const alertBarClass: Record<string, string> = {
  critical: "bar-critical",
  error: "bar-high",
  warning: "bar-medium",
  info: "bar-low",
};

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

function formatRate(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function statusColor(value: number) {
  if (value >= 0.85) return "#16a34a";
  if (value >= 0.7) return "#d97706";
  return "#dc2626";
}

const passTrendRef = ref<HTMLElement | null>(null);
let passChart: ECharts | null = null;
const halluTrendRef = ref<HTMLElement | null>(null);
let halluChart: ECharts | null = null;

function renderMiniCharts() {
  if (passTrendRef.value && passRateTrend.value.length) {
    passChart ??= init(passTrendRef.value);
    passChart.setOption({
      animationDuration: 400,
      tooltip: { trigger: "axis", valueFormatter: (value: number) => formatRate(value) },
      grid: { left: 46, right: 18, top: 24, bottom: 34 },
      xAxis: {
        type: "category",
        data: passRateTrend.value.map((p: any) => p.date ?? p.bucket ?? ""),
        axisLabel: { color: "#64748b" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: { color: "#64748b", formatter: (value: number) => `${Math.round(value * 100)}%` },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: [{
        name: "通过率",
        type: "line",
        data: passRateTrend.value.map((p: any) => p.value),
        smooth: true,
        symbolSize: 6,
        lineStyle: { color: "#22c55e", width: 2 },
        areaStyle: { color: "rgba(34,197,94,0.12)" },
      }],
    });
  }

  if (halluTrendRef.value && hallucinationTrend.value.length) {
    halluChart ??= init(halluTrendRef.value);
    halluChart.setOption({
      animationDuration: 400,
      tooltip: { trigger: "axis", valueFormatter: (value: number) => formatRate(value) },
      grid: { left: 46, right: 18, top: 24, bottom: 34 },
      xAxis: {
        type: "category",
        data: hallucinationTrend.value.map((p: any) => p.date ?? p.bucket ?? ""),
        axisLabel: { color: "#64748b" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: { color: "#64748b", formatter: (value: number) => `${Math.round(value * 100)}%` },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.08)" } },
      },
      series: [{
        name: "幻觉率",
        type: "line",
        data: hallucinationTrend.value.map((p: any) => p.value),
        smooth: true,
        symbolSize: 6,
        lineStyle: { color: "#f59e0b", width: 2 },
        areaStyle: { color: "rgba(245,158,11,0.12)" },
      }],
    });
  }
}

function handleResize() {
  passChart?.resize();
  halluChart?.resize();
}

watch([passRateTrend, hallucinationTrend], async () => {
  await nextTick();
  renderMiniCharts();
}, { deep: true });

onMounted(async () => {
  await fetchData();
  await nextTick();
  renderMiniCharts();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  passChart?.dispose();
  halluChart?.dispose();
  window.removeEventListener("resize", handleResize);
});
</script>

<template>
  <div class="dq-shell">
    <section class="hero">
      <p class="eyebrow">Data Quality</p>
      <h2>数据质量</h2>
      <p class="sub">聚焦结果质量、告警和质量趋势；模型维度的 Token、成本和质量对比统一进入模型观测。</p>
    </section>

    <el-alert
      title="风险趋势统一放在分析中心；模型 Token、成本和模型质量对比统一放在模型观测。"
      type="info"
      :closable="false"
    />

    <section class="summary-row">
      <div class="summary-card">
        <span class="sl">结果数</span>
        <span class="sv">{{ totalResults.toLocaleString() }}</span>
      </div>
      <div class="summary-card">
        <span class="sl">通过率</span>
        <span class="sv" :style="{ color: totalResults ? statusColor(passRate) : '#18181b' }">
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
        <span class="sl">平均耗时</span>
        <span class="sv">{{ avgLatencyMs.toFixed(0) }}<span class="sv-unit">ms</span></span>
      </div>
    </section>

    <section class="distro-row">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <strong>告警分布</strong>
          <span class="card-sub">按严重程度查看当前结果中触发的告警数量</span>
        </template>
        <div v-if="alertDistribution.length" class="distro-list">
          <div v-for="a in alertDistribution" :key="a.name" class="distro-row-item">
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

    <section class="trend-row">
      <el-card v-if="passRateTrend.length" shadow="never" class="panel-card">
        <template #header>
          <strong>通过率趋势</strong>
          <span class="card-sub">观察结果通过率的按日变化</span>
        </template>
        <div ref="passTrendRef" class="mini-chart" />
      </el-card>
      <el-card v-if="hallucinationTrend.length" shadow="never" class="panel-card">
        <template #header>
          <strong>幻觉率趋势</strong>
          <span class="card-sub">观察结果幻觉率的按日变化</span>
        </template>
        <div ref="halluTrendRef" class="mini-chart" />
      </el-card>
    </section>

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

.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; opacity: 0.76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248, 250, 252, 0.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

.summary-card {
  padding: 18px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
}

.sl { display: block; font-size: 12px; color: #a1a1aa; }
.sv { display: block; margin-top: 6px; font-size: 24px; font-weight: 800; color: #18181b; }
.sv-unit { font-size: 14px; font-weight: 500; color: #a1a1aa; }

.distro-row {
  display: grid;
  grid-template-columns: 1fr;
}

.panel-card {
  border-radius: 20px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.panel-card strong { display: block; font-size: 18px; color: #172033; }
.card-sub { display: block; margin-top: 4px; font-size: 13px; color: #64748b; }

.distro-list { display: flex; flex-direction: column; gap: 10px; }
.distro-row-item { display: flex; align-items: center; gap: 10px; }
.distro-name { width: 70px; font-size: 13px; color: #52525b; text-align: right; flex-shrink: 0; font-weight: 600; }
.distro-tag {
  width: 44px;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  padding: 2px 0;
  border-radius: 4px;
  flex-shrink: 0;
}

.bar-critical { background: #dc2626; }
.bar-high { background: #f59e0b; }
.bar-medium { background: #3b82f6; }
.bar-low { background: #22c55e; }

.distro-bar-bg { flex: 1; height: 18px; border-radius: 5px; background: #f4f4f5; overflow: hidden; }
.distro-bar { height: 100%; border-radius: 5px; transition: width 0.3s ease; }
.distro-pct { width: 52px; font-size: 12px; font-weight: 600; color: #71717a; text-align: right; }

.trend-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.mini-chart { width: 100%; height: 260px; }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
}

.card-head strong { display: block; font-size: 18px; color: #172033; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }

.refresh-row { display: flex; align-items: center; gap: 16px; }

@media (max-width: 1100px) {
  .summary-row { grid-template-columns: repeat(3, 1fr); }
  .trend-row { grid-template-columns: 1fr; }
}
</style>
