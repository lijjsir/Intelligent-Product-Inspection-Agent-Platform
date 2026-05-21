<template>
  <div class="tools-overview">
    <section class="hero-card">
      <div>
        <h1 class="hero-title">工具中心</h1>
        <p class="hero-subtitle">统一查看工具可用性、调用表现和风险状态。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="$router.push('/ops/tools/catalog')">查看工具库</el-button>
        <el-button @click="$router.push('/ops/tools/import')">导入与同步</el-button>
      </div>
    </section>

    <section class="stats-grid" v-loading="store.overviewLoading">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <div class="stat-label">{{ item.label }}</div>
        <div class="stat-value" :class="item.tone">{{ item.value }}</div>
      </article>
    </section>

    <section class="charts-grid">
      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">24 小时调用趋势</span>
        </div>
        <div ref="callTrendRef" class="chart-box"></div>
      </article>
      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">24 小时错误趋势</span>
        </div>
        <div ref="errorTrendRef" class="chart-box"></div>
      </article>
      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">工具健康分布</span>
        </div>
        <div ref="healthRef" class="chart-box"></div>
      </article>
    </section>

    <section class="lists-grid">
      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">最近失败最多</span>
        </div>
        <div v-if="overview?.top_failing.length" class="list">
          <div v-for="item in overview.top_failing" :key="item.tool_id" class="list-row">
            <div>
              <div class="list-main">{{ item.tool_name }}</div>
              <div class="list-sub">失败 {{ item.failure_count }} 次</div>
            </div>
            <el-tag type="danger" effect="plain">{{ (item.failure_rate * 100).toFixed(1) }}%</el-tag>
          </div>
        </div>
        <div v-else class="empty-text">暂无失败热点</div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">高延迟工具</span>
        </div>
        <div v-if="overview?.high_latency.length" class="list">
          <div v-for="item in overview.high_latency" :key="item.tool_id" class="list-row">
            <div class="list-main">{{ item.tool_name }}</div>
            <strong class="list-number">{{ item.avg_latency_ms }} ms</strong>
          </div>
        </div>
        <div v-else class="empty-text">暂无高延迟工具</div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">待关注风险</span>
        </div>
        <div v-if="overview?.pending_risk_tools.length" class="list">
          <div v-for="item in overview.pending_risk_tools" :key="item.tool_id" class="list-row">
            <div class="list-main">{{ item.tool_name }}</div>
            <el-tag type="danger" effect="plain">{{ item.risk_level }}</el-tag>
          </div>
        </div>
        <div v-else class="empty-text">当前没有待处理高风险工具</div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <span class="panel-title">关键依赖</span>
        </div>
        <div v-if="overview?.critical_dependencies.length" class="list">
          <div v-for="item in overview.critical_dependencies" :key="item.tool_id" class="list-row">
            <div class="list-main">{{ item.tool_name }}</div>
            <span class="list-sub">{{ item.dependent_agents }} 个 Agent 依赖</span>
          </div>
        </div>
        <div v-else class="empty-text">第 1 阶段暂未发现关键依赖数据</div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useECharts } from "@/composables/useECharts";
import { useToolsStore } from "@/stores/tools.store";

const store = useToolsStore();
const overview = computed(() => store.overview);

const { chartRef: callTrendRef, setOption: setCallTrendOption } = useECharts();
const { chartRef: errorTrendRef, setOption: setErrorTrendOption } = useECharts();
const { chartRef: healthRef, setOption: setHealthOption } = useECharts();

const statCards = computed(() => {
  const data = overview.value;
  if (!data) {
    return [];
  }
  return [
    { label: "工具总数", value: data.total_tools, tone: "" },
    { label: "启用工具", value: data.active_tools, tone: "good" },
    { label: "异常工具", value: data.error_tools, tone: "bad" },
    { label: "今日调用", value: data.today_calls.toLocaleString(), tone: "" },
    { label: "平均延迟", value: `${data.avg_latency_ms} ms`, tone: "" },
    { label: "高风险工具", value: data.high_risk_tools, tone: "warn" },
  ];
});

function renderCharts() {
  if (!overview.value) return;

  const baseAxis = {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#94a3b8", fontSize: 11 },
  };
  const grid = { left: 16, right: 16, top: 18, bottom: 24 };

  setCallTrendOption({
    grid,
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: overview.value.call_trend.map((point) => point.time.slice(11, 16)),
      ...baseAxis,
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#eef2f7" } },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
    },
    series: [
      {
        type: "line",
        smooth: true,
        showSymbol: false,
        data: overview.value.call_trend.map((point) => point.value),
        lineStyle: { color: "#0f766e", width: 2 },
        areaStyle: { color: "rgba(15, 118, 110, 0.12)" },
      },
    ],
  });

  setErrorTrendOption({
    grid,
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: overview.value.error_trend.map((point) => point.time.slice(11, 16)),
      ...baseAxis,
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#eef2f7" } },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
    },
    series: [
      {
        type: "line",
        smooth: true,
        showSymbol: false,
        data: overview.value.error_trend.map((point) => point.value),
        lineStyle: { color: "#dc2626", width: 2 },
        areaStyle: { color: "rgba(220, 38, 38, 0.10)" },
      },
    ],
  });

  setHealthOption({
    tooltip: { trigger: "item" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["54%", "76%"],
        label: { show: false },
        data: [
          { value: overview.value.health_distribution.healthy, name: "健康", itemStyle: { color: "#10b981" } },
          { value: overview.value.health_distribution.degraded, name: "降级", itemStyle: { color: "#f59e0b" } },
          { value: overview.value.health_distribution.unhealthy, name: "异常", itemStyle: { color: "#ef4444" } },
          { value: overview.value.health_distribution.unknown, name: "未知", itemStyle: { color: "#94a3b8" } },
        ],
      },
    ],
  });
}

onMounted(async () => {
  await store.fetchOverview();
  renderCharts();
});

watch(overview, () => {
  window.setTimeout(renderCharts, 0);
});
</script>

<style scoped>
.tools-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px;
  border: 1px solid #dbeafe;
  border-radius: 18px;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.15), transparent 32%),
    linear-gradient(135deg, #f8fafc 0%, #f0fdf4 55%, #ecfeff 100%);
}

.hero-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.hero-subtitle {
  margin: 8px 0 0;
  color: #64748b;
}

.hero-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.stat-card,
.panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.stat-card {
  padding: 16px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.stat-value.good {
  color: #047857;
}

.stat-value.bad {
  color: #dc2626;
}

.stat-value.warn {
  color: #b45309;
}

.charts-grid,
.lists-grid {
  display: grid;
  gap: 16px;
}

.charts-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.lists-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.chart-box {
  height: 240px;
}

.list {
  padding: 8px 0 12px;
}

.list-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
}

.list-row + .list-row {
  border-top: 1px solid #f1f5f9;
}

.list-main {
  font-size: 14px;
  color: #0f172a;
}

.list-sub {
  font-size: 12px;
  color: #64748b;
}

.list-number {
  color: #b45309;
}

.empty-text {
  padding: 28px 18px;
  color: #94a3b8;
  font-size: 13px;
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .charts-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .hero-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .stats-grid,
  .lists-grid {
    grid-template-columns: 1fr;
  }
}
</style>
