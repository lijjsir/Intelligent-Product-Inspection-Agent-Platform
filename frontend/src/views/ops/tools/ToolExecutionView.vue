<template>
  <div class="tool-executions">
    <section class="stats-grid">
      <article class="stat-card">
        <div class="stat-label">今日调用</div>
        <div class="stat-value">{{ executionOverview?.today_calls?.toLocaleString() ?? "-" }}</div>
      </article>
      <article class="stat-card">
        <div class="stat-label">成功率</div>
        <div class="stat-value" :class="successTone">
          {{ executionOverview ? `${(executionOverview.success_rate * 100).toFixed(1)}%` : "-" }}
        </div>
      </article>
      <article class="stat-card">
        <div class="stat-label">平均延迟</div>
        <div class="stat-value">{{ executionOverview ? `${executionOverview.avg_latency_ms} ms` : "-" }}</div>
      </article>
      <article class="stat-card">
        <div class="stat-label">失败次数</div>
        <div class="stat-value bad">{{ executionOverview?.failed_count ?? "-" }}</div>
      </article>
    </section>

    <section class="charts-grid">
      <article class="panel">
        <div class="panel-header"><span class="panel-title">调用趋势</span></div>
        <div ref="callTrendRef" class="chart-box"></div>
      </article>
      <article class="panel">
        <div class="panel-header"><span class="panel-title">错误趋势</span></div>
        <div ref="errorTrendRef" class="chart-box"></div>
      </article>
      <article class="panel">
        <div class="panel-header"><span class="panel-title">延迟趋势</span></div>
        <div ref="latencyTrendRef" class="chart-box"></div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <span class="panel-title">执行日志</span>
        <div class="filters">
          <el-tag :type="sseConnected ? 'success' : 'info'" size="small" class="sse-tag">
            {{ sseConnected ? '实时' : '轮询' }}
          </el-tag>
          <el-select v-model="filterStatus" clearable placeholder="状态" class="filter" @change="loadExecutions">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="超时" value="timeout" />
          </el-select>
          <el-select v-model="filterType" clearable placeholder="类型" class="filter" @change="loadExecutions">
            <el-option label="运行时" value="runtime" />
            <el-option label="测试" value="test" />
          </el-select>
        </div>
      </div>

      <el-table :data="store.executions" stripe size="small" v-loading="store.executionsLoading">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="tool_name" label="工具" min-width="180" />
        <el-table-column prop="agent_name" label="Agent" width="160" />
        <el-table-column label="任务" width="110">
          <template #default="{ row }">{{ row.task_id || "-" }}</template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.execution_type === 'test' ? 'warning' : 'info'">
              {{ row.execution_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100" align="right">
          <template #default="{ row }">{{ row.duration_ms }} ms</template>
        </el-table-column>
        <el-table-column prop="input_summary" label="输入摘要" min-width="180" :show-overflow-tooltip="true" />
        <el-table-column prop="output_summary" label="输出摘要" min-width="180" :show-overflow-tooltip="true" />
        <el-table-column prop="error_message" label="错误信息" width="180" :show-overflow-tooltip="true" />
        <el-table-column prop="trace_id" label="Trace ID" width="170" :show-overflow-tooltip="true" />
      </el-table>
    </section>

    <section class="pager">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="store.executionsTotal"
        layout="total, prev, pager, next"
        @current-change="loadExecutions"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useECharts } from "@/composables/useECharts";
import { useToolsStore } from "@/stores/tools.store";
import { readStoredValue, TOKEN_KEY } from "@/utils/auth-session";
import type { ExecutionType, ToolExecutionStatus } from "@/types/tools.types";

const sseConnected = ref(false);
let eventSource: EventSource | null = null;

function connectSSE() {
  const baseUrl = (import.meta.env.VITE_API_BASE as string) ?? "/api";
  const token = readStoredValue(TOKEN_KEY);
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
  eventSource = new EventSource(`${baseUrl}/v1/tools/events/stream${tokenParam}`);

  eventSource.addEventListener("tool.execution.started", () => {
    loadExecutions();
    store.fetchExecutionOverview().then(() => renderCharts());
  });

  eventSource.addEventListener("tool.execution.completed", () => {
    loadExecutions();
    store.fetchExecutionOverview().then(() => renderCharts());
  });

  eventSource.addEventListener("tool.execution.failed", () => {
    loadExecutions();
    store.fetchExecutionOverview().then(() => renderCharts());
  });

  eventSource.onopen = () => {
    sseConnected.value = true;
  };

  eventSource.onerror = () => {
    sseConnected.value = false;
    eventSource?.close();
    setTimeout(connectSSE, 10000);
  };
}

const store = useToolsStore();
const executionOverview = computed(() => store.executionOverview);

const currentPage = ref(1);
const pageSize = ref(20);
const filterStatus = ref<ToolExecutionStatus>();
const filterType = ref<ExecutionType>();

const { chartRef: callTrendRef, setOption: setCallOption } = useECharts();
const { chartRef: errorTrendRef, setOption: setErrorOption } = useECharts();
const { chartRef: latencyTrendRef, setOption: setLatencyOption } = useECharts();

const successTone = computed(() => {
  const rate = executionOverview.value?.success_rate ?? 0;
  if (rate >= 0.95) return "good";
  if (rate >= 0.9) return "warn";
  return "bad";
});

function statusTag(status: ToolExecutionStatus) {
  return {
    success: "success",
    failed: "danger",
    timeout: "warning",
    running: "info",
    pending: "info",
  }[status] as "success" | "danger" | "warning" | "info";
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderCharts() {
  if (!executionOverview.value) return;

  const xAxis = executionOverview.value.call_trend.map((point) => point.time.slice(11, 16));
  const grid = { left: 16, right: 16, top: 18, bottom: 24 };
  const baseAxis = {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#94a3b8", fontSize: 11 },
  };

  const buildSeries = (data: number[], color: string) => ({
    type: "line",
    smooth: true,
    showSymbol: false,
    data,
    lineStyle: { color, width: 2 },
    areaStyle: { color: `${color}22` },
  });

  setCallOption({
    grid,
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xAxis, ...baseAxis },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [buildSeries(executionOverview.value.call_trend.map((point) => point.value), "#0f766e")],
  });

  setErrorOption({
    grid,
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xAxis, ...baseAxis },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [buildSeries(executionOverview.value.error_trend.map((point) => point.value), "#dc2626")],
  });

  setLatencyOption({
    grid,
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xAxis, ...baseAxis },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#eef2f7" } } },
    series: [buildSeries(executionOverview.value.latency_trend.map((point) => point.value), "#d97706")],
  });
}

async function loadExecutions() {
  await store.fetchExecutions({
    page: currentPage.value,
    size: pageSize.value,
    status: filterStatus.value,
    execution_type: filterType.value,
  });
}

onMounted(async () => {
  await Promise.all([store.fetchExecutionOverview(), loadExecutions()]);
  renderCharts();
  connectSSE();
});

onBeforeUnmount(() => {
  eventSource?.close();
});

watch(executionOverview, () => {
  window.setTimeout(renderCharts, 0);
});
</script>

<style scoped>
.tool-executions {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-grid,
.charts-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.charts-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.stat-value.warn {
  color: #b45309;
}

.stat-value.bad {
  color: #dc2626;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 0;
}

.panel-header-wrap {
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.chart-box {
  height: 220px;
}

.filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter {
  width: 120px;
}

.pager {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1200px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .filter {
    width: 100%;
  }
}
</style>
