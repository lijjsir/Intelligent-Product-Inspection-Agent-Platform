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

use([CanvasRenderer, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent] as any);

const overview = computed(() => analyticsStore.overview);
const openAlerts = computed(() => alertStore.items.slice(0, 5));
const recentTasks = computed(() => taskStore.items.slice(0, 10));
const selectedRange = ref<7 | 30 | 90>(30);
const isAdmin = computed(() => hasRole("admin"));
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
      color: ["#18181b"],
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%`,
      },
      grid: { left: 40, right: 24, top: 28, bottom: 32 },
      xAxis: {
        type: "category",
        data: overview.value.pass_rate_trend.map((item) => item.bucket),
        axisLabel: { color: "#71717a" },
        axisLine: { lineStyle: { color: "#e4e4e7" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: "#71717a",
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
        splitLine: { lineStyle: { color: "rgba(0,0,0,0.04)" } },
      },
      series: [
        {
          name: "通过率",
          type: "line",
          smooth: true,
          symbolSize: 6,
          data: overview.value.pass_rate_trend.map((item) => item.value),
          lineStyle: { width: 2, color: "#18181b" },
          itemStyle: { color: "#18181b" },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(24,24,27,0.08)" },
              { offset: 1, color: "rgba(24,24,27,0.01)" },
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
      legend: { bottom: 0, textStyle: { color: "#71717a" } },
      series: [
        {
          type: "pie",
          radius: ["44%", "72%"],
          center: ["50%", "42%"],
          label: { color: "#3f3f46" },
          color: ["#18181b", "#52525b", "#a1a1aa", "#d4d4d8"],
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
  <div class="flex flex-col gap-5">
    <!-- Hero -->
    <section class="px-7 py-8 rounded-2xl bg-zinc-900 text-white">
      <p class="text-2xs tracking-[0.16em] uppercase text-zinc-400 mb-2">PIAP Operations</p>
      <h2 class="text-[38px] font-bold leading-tight">数据与统计看板</h2>
      <p class="mt-3 max-w-2xl text-zinc-400 text-sm leading-relaxed">
        仪表盘统计真实物化后的任务、结果、稳定性和告警，不把聊天中间态当作统计源。
      </p>
      <div class="flex flex-wrap gap-2 mt-5">
        <el-tag type="info" effect="plain" size="small">最近 {{ selectedRange }} 日</el-tag>
        <el-tag v-if="isAdmin" effect="plain" size="small" class="!border-zinc-600 !text-zinc-300">admin 默认聚合全部组织</el-tag>
      </div>
    </section>

    <!-- Range + actions -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div class="flex gap-2">
        <el-button
          v-for="d in [7, 30, 90]"
          :key="d"
          :type="selectedRange === d ? 'primary' : 'default'"
          size="small"
          @click="setRange(d as 7 | 30 | 90)"
        >
          {{ d }} 日
        </el-button>
      </div>
      <div class="flex gap-2 flex-wrap">
        <el-button size="small" @click="router.push('/app/tasks')">查看任务</el-button>
        <el-button size="small" plain @click="router.push('/ops/analytics')">查看分析</el-button>
        <el-button size="small" plain @click="router.push('/app/stability')">稳定性工作台</el-button>
      </div>
    </div>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <!-- Metric grid -->
    <section v-if="overview" class="grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
      <div class="card-surface p-5 cursor-pointer" @click="router.push('/app/tasks')">
        <div class="text-[13px] text-zinc-500">范围内任务数</div>
        <div class="mt-2 text-[32px] font-extrabold text-zinc-900 leading-none">{{ overview.total_tasks }}</div>
        <div class="mt-2 text-[13px] text-zinc-400">已沉淀结果 {{ overview.total_results }}</div>
      </div>

      <div class="card-surface p-5">
        <div class="text-[13px] text-zinc-500">智能判定通过率</div>
        <div class="mt-2 text-[32px] font-extrabold text-zinc-900 leading-none">{{ (overview.pass_rate * 100).toFixed(1) }}%</div>
        <div class="mt-2 text-[13px] text-zinc-400">仅统计真实结果记录</div>
      </div>

      <div class="card-surface p-5 cursor-pointer" @click="router.push('/app/alerts')">
        <div class="text-[13px] text-zinc-500">高风险预警数</div>
        <div class="mt-2 text-[32px] font-extrabold text-zinc-900 leading-none">{{ highRiskAlerts }}</div>
        <div class="mt-2 text-[13px] text-zinc-400">仅显示未关闭且未关联已删除任务的告警</div>
      </div>

      <div class="card-surface p-5">
        <div class="text-[13px] text-zinc-500">平均耗时</div>
        <div class="mt-2 text-[32px] font-extrabold text-zinc-900 leading-none">{{ overview.avg_latency_ms.toFixed(0) }} ms</div>
        <div class="mt-2 text-[13px] text-zinc-400">累计成本 &yen;{{ overview.total_cost.toFixed(4) }}</div>
      </div>
    </section>

    <!-- Charts -->
    <section class="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
      <div class="card-surface p-5">
        <div class="mb-3">
          <strong class="text-lg text-zinc-900">通过率趋势</strong>
          <span class="block mt-1 text-[13px] text-zinc-400">按当前统计范围展示真实结果的通过率走势</span>
        </div>
        <div ref="trendRef" class="w-full h-80"></div>
      </div>

      <div class="card-surface p-5 cursor-pointer" @click="router.push('/app/stability')">
        <div class="mb-3">
          <strong class="text-lg text-zinc-900">风险等级分布</strong>
          <span class="block mt-1 text-[13px] text-zinc-400">点击进入稳定性工作台查看详情</span>
        </div>
        <div ref="riskRef" class="w-full h-80"></div>
      </div>
    </section>

    <!-- Tables -->
    <section class="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
      <div class="card-surface">
        <div class="px-5 py-3 border-b border-zinc-100 text-sm font-semibold text-zinc-900">最近预警</div>
        <el-table :data="openAlerts" size="small" empty-text="当前范围内暂无预警" class="dashboard-table">
          <el-table-column prop="severity" label="级别" width="110" />
          <el-table-column prop="title" label="标题" min-width="220" />
          <el-table-column prop="created_at" label="触发时间" width="180" />
        </el-table>
      </div>

      <div class="card-surface">
        <div class="px-5 py-3 border-b border-zinc-100 text-sm font-semibold text-zinc-900">最近任务</div>
        <el-table :data="recentTasks" size="small" empty-text="当前范围内暂无任务" class="dashboard-table">
          <el-table-column prop="id" label="任务 ID" min-width="240" show-overflow-tooltip />
          <el-table-column v-if="isAdmin" prop="org_slug" label="组织" width="120" />
          <el-table-column prop="product_id" label="产品编号" width="120" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="source_kind" label="来源" width="160" />
          <el-table-column prop="source_graph" label="子图" width="150" />
        </el-table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dashboard-table :deep(.el-table__header th) {
  @apply text-zinc-500 font-medium text-[13px] bg-transparent;
}
.dashboard-table :deep(.el-table__body tr:hover > td) {
  @apply bg-zinc-50;
}
.dashboard-table :deep(.el-table td) {
  @apply border-zinc-100;
}

/* Fix Element Plus tag colors in dark hero */
:deep(.el-tag--plain) {
  @apply border-zinc-600 text-zinc-300 bg-transparent;
}
</style>
