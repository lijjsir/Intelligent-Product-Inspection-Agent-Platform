<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, type ECharts, use } from "echarts/core";
import { modelConfigApi } from "@/api/model_config.api";
import { useAnalyticsStore } from "@/stores/analytics.store";
import type { ModelConfig } from "@/types/governance.types";

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent] as any);

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const modelMetrics = computed(() => analyticsStore.overview?.model_metrics ?? []);

const models = ref<ModelConfig[]>([]);
const modelsLoading = ref(false);
const modelsError = ref("");

const modelTypeLabels: Record<string, string> = {
  chat: "对话", embedding: "嵌入", multimodal: "多模态", vision: "视觉", llm: "LLM", vlm: "VLM",
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

function formatCost(value: number) {
  if (value >= 1) return `¥${value.toFixed(2)}`;
  if (value >= 0.01) return `¥${value.toFixed(4)}`;
  return `¥${value.toFixed(6)}`;
}

function formatRate(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatPrice(val: number | null | undefined) {
  if (val == null) return "-";
  return `¥${val.toFixed(2)}/M`;
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

// Token & Cost comparison chart
const tokenChartRef = ref<HTMLElement | null>(null);
let tokenChart: ECharts | null = null;

const tokenChartData = computed(() =>
  [...modelMetrics.value]
    .filter((m) => m.avg_tokens != null && m.avg_tokens > 0)
    .sort((a, b) => (b.avg_tokens || 0) - (a.avg_tokens || 0))
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
        const costItem = params.find((p: any) => p.seriesName === "总成本");
        const tokenVal = tokenItem?.value ?? 0;
        const costVal = costItem?.value ?? 0;
        return `<strong>${params[0].name}</strong><br/>
          平均 Token: ${tokenVal >= 1000 ? (tokenVal / 1000).toFixed(1) + "k" : tokenVal}<br/>
          总成本: ¥${Number(costVal).toFixed(2)}`;
      },
    },
    grid: { left: 140, right: 80, top: 30, bottom: 50 },
    xAxis: [
      {
        type: "value",
        name: "Token",
        nameLocation: "middle",
        nameGap: 30,
        position: "bottom",
        axisLabel: {
          color: "#2563eb",
          formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`,
        },
        splitLine: { lineStyle: { color: "rgba(25,42,70,0.06)" } },
      },
      {
        type: "value",
        name: "成本 ¥",
        nameLocation: "middle",
        nameGap: 30,
        position: "top",
        axisLabel: { color: "#f59e0b", formatter: (v: number) => `¥${v.toFixed(2)}` },
        splitLine: { show: false },
      },
    ],
    yAxis: {
      type: "category",
      data: items.map((m) => m.model_key),
      axisLabel: { color: "#18181b", fontSize: 12, fontWeight: 600 },
    },
    series: [
      {
        name: "平均 Token",
        type: "bar",
        xAxisIndex: 0,
        barWidth: 14,
        barGap: "30%",
        data: items.map((m) => m.avg_tokens),
        itemStyle: { borderRadius: [0, 4, 4, 0], color: "#2563eb" },
        label: {
          show: true, position: "right", color: "#2563eb", fontSize: 11,
          formatter: (p: any) => p.value >= 1000 ? `${(p.value / 1000).toFixed(1)}k` : `${p.value}`,
        },
      },
      {
        name: "总成本",
        type: "bar",
        xAxisIndex: 1,
        barWidth: 14,
        data: items.map((m) => parseFloat((m.total_cost || 0).toFixed(4))),
        itemStyle: { borderRadius: [0, 4, 4, 0], color: "#f59e0b" },
        label: {
          show: true, position: "right", color: "#f59e0b", fontSize: 11,
          formatter: (p: any) => `¥${Number(p.value).toFixed(2)}`,
        },
      },
    ],
  });
}

function handleResize() {
  tokenChart?.resize();
}

watch(tokenChartData, async () => { await nextTick(); renderTokenChart(); }, { deep: true });

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
      <p class="sub">实时监控各模型的调用量、通过率、延迟和成本，查看模型配置与运行状态详情。</p>
    </section>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <!-- Model Health Cards -->
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
              {{ m.result_count ? formatRate(m.pass_rate) : '-' }}
            </span>
          </div>
          <div class="stat">
            <span class="stat-label">幻觉率</span>
            <span class="stat-value">{{ formatRate(m.hallucination_rate) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">调用次数</span>
            <span class="stat-value">{{ m.result_count }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">总成本</span>
            <span class="stat-value">{{ m.total_cost > 0 ? formatCost(m.total_cost) : '-' }}</span>
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

    <!-- Token & Cost Comparison Chart -->
    <el-card v-if="tokenChartData.length" shadow="never" class="chart-card">
      <template #header>
        <div class="card-head">
          <strong>Token 消耗与成本对比</strong>
          <span>按平均 Token 降序排列，叠加总成本</span>
        </div>
      </template>
      <div ref="tokenChartRef" class="chart-host" />
    </el-card>

    <!-- 模型配置详情 -->
    <section class="section-header">
      <h3>模型配置详情</h3>
      <span class="section-count">共 {{ models.length }} 个模型</span>
    </section>

    <el-alert v-if="modelsError" :title="modelsError" type="warning" :closable="false" />

    <el-card shadow="never" class="table-card">
      <el-table :data="models" :loading="modelsLoading" size="small" empty-text="暂无模型配置">
        <el-table-column prop="display_name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="model_key" label="Key" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <span class="text-[13px]">{{ modelTypeLabels[row.model_type] || row.model_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" width="90" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="healthLabels[row.health_status]?.tag || 'info'" size="small" effect="dark">
              {{ healthLabels[row.health_status]?.label || row.health_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
              {{ row.is_active ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="入价" width="90">
          <template #default="{ row }">{{ formatPrice(row.input_price_per_million) }}</template>
        </el-table-column>
        <el-table-column label="出价" width="90">
          <template #default="{ row }">{{ formatPrice(row.output_price_per_million) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="65">
          <template #default="{ row }">{{ row.priority }}</template>
        </el-table-column>
        <el-table-column label="RPM" width="70">
          <template #default="{ row }">{{ row.rpm_limit ?? "-" }}</template>
        </el-table-column>
        <el-table-column label="API Key" width="80">
          <template #default="{ row }">
            <el-tag :type="row.has_api_key ? 'success' : 'danger'" size="small" effect="plain">
              {{ row.has_api_key ? '已配置' : '未配置' }}
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
  background: linear-gradient(135deg, #1e293b 0%, #334155 52%, #7c3aed 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.model-card {
  border-radius: 16px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
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
  transition: width .3s ease;
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
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}

.chart-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
}
.card-head strong { display: block; font-size: 18px; color: #172033; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
.chart-host { width: 100%; height: 320px; }

.refresh-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
</style>
