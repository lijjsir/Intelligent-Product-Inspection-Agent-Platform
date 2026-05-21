<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";

const analyticsStore = useAnalyticsStore();
const loading = ref(false);
const quickDays = ref(7);

const overview = computed(() => analyticsStore.overview);
const modelMetrics = computed(() => overview.value?.model_metrics ?? []);
const passRate = computed(() => (overview.value?.pass_rate ?? 0) * 100);
const hallucinationRate = computed(() => (overview.value?.hallucination_rate ?? 0) * 100);
const totalTasks = computed(() => overview.value?.total_tasks ?? 0);
const totalResults = computed(() => overview.value?.total_results ?? 0);
const totalCost = computed(() => overview.value?.total_cost ?? 0);

const reportDate = computed(() => {
  const now = new Date();
  const start = new Date();
  start.setDate(now.getDate() - quickDays.value + 1);
  return `${start.toISOString().slice(0, 10)} 至 ${now.toISOString().slice(0, 10)}`;
});

async function fetchData() {
  loading.value = true;
  try {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (quickDays.value - 1));
    await analyticsStore.fetchOverview({
      start_date: start.toISOString().slice(0, 10),
      end_date: end.toISOString().slice(0, 10),
    });
  } finally {
    loading.value = false;
  }
}

function setRange(days: number) {
  quickDays.value = days;
  fetchData();
}

function formatCost(v: number) {
  if (v >= 1) return `¥${v.toFixed(2)}`;
  if (v >= 0.01) return `¥${v.toFixed(4)}`;
  return `¥${v.toFixed(6)}`;
}

const topModel = computed(() => {
  if (!modelMetrics.value.length) return null;
  return [...modelMetrics.value].sort((a, b) => b.result_count - a.result_count)[0];
});

const costlyModel = computed(() => {
  if (!modelMetrics.value.length) return null;
  return [...modelMetrics.value].sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0))[0];
});

onMounted(fetchData);
</script>

<template>
  <div class="report-shell">
    <section class="hero">
      <p class="eyebrow">Business Reports</p>
      <h2>业务报表</h2>
      <p class="sub">定期生成运营报告，汇总关键指标和趋势。</p>
    </section>

    <div class="toolbar">
      <div class="range-btns">
        <el-button v-for="d in [7, 30, 90]" :key="d" :type="quickDays === d ? 'primary' : 'default'" size="small" @click="setRange(d)">{{ d }} 日报表</el-button>
      </div>
      <el-button :loading="loading" @click="fetchData">刷新</el-button>
    </div>

    <el-alert v-if="analyticsStore.error" :title="analyticsStore.error" type="warning" :closable="false" />

    <div class="report-meta">
      <h3>{{ quickDays }} 日运营报表</h3>
      <p class="meta-sub">统计周期：{{ reportDate }}</p>
    </div>

    <section class="summary-row">
      <div class="sc"><span class="sl">任务数</span><span class="sv">{{ totalTasks.toLocaleString() }}</span></div>
      <div class="sc"><span class="sl">结果数</span><span class="sv">{{ totalResults.toLocaleString() }}</span></div>
      <div class="sc"><span class="sl">通过率</span><span class="sv" :class="passRate >= 85 ? 'text-green-600' : 'text-red-600'">{{ passRate.toFixed(1) }}%</span></div>
      <div class="sc"><span class="sl">总成本</span><span class="sv">{{ formatCost(totalCost) }}</span></div>
    </section>

    <section class="insights-grid">
      <el-card shadow="never" class="insight-card">
        <template #header><strong>Top 模型（调用量）</strong></template>
        <div v-if="topModel" class="insight-body">
          <span class="insight-name">{{ topModel.model_key }}</span>
          <span class="insight-stat">{{ topModel.result_count }} 次调用</span>
          <span class="insight-sub">通过率 {{ (topModel.pass_rate * 100).toFixed(1) }}%</span>
        </div>
        <el-empty v-else description="无数据" />
      </el-card>

      <el-card shadow="never" class="insight-card">
        <template #header><strong>最高成本模型</strong></template>
        <div v-if="costlyModel" class="insight-body">
          <span class="insight-name">{{ costlyModel.model_key }}</span>
          <span class="insight-stat">{{ formatCost(costlyModel.total_cost || 0) }}</span>
          <span class="insight-sub">占比 {{ totalCost ? ((costlyModel.total_cost / totalCost) * 100).toFixed(1) : 0 }}%</span>
        </div>
        <el-empty v-else description="无数据" />
      </el-card>

      <el-card shadow="never" class="insight-card">
        <template #header><strong>幻觉率</strong></template>
        <div class="insight-body">
          <span class="insight-stat" :class="hallucinationRate <= 5 ? 'text-green-600' : 'text-red-600'">{{ hallucinationRate.toFixed(1) }}%</span>
          <span class="insight-sub">{{ hallucinationRate <= 5 ? '正常范围' : '超出阈值，建议排查 RAG 召回' }}</span>
        </div>
      </el-card>

      <el-card shadow="never" class="insight-card">
        <template #header><strong>活跃模型数</strong></template>
        <div class="insight-body">
          <span class="insight-stat">{{ modelMetrics.length }}</span>
          <span class="insight-sub">个模型产生过调用</span>
        </div>
      </el-card>
    </section>

    <el-card v-if="modelMetrics.length" shadow="never" class="table-card">
      <template #header><strong>模型表现明细</strong></template>
      <el-table :data="modelMetrics" size="small">
        <el-table-column prop="model_key" label="模型" min-width="200" show-overflow-tooltip />
        <el-table-column label="调用次数" width="110">
          <template #default="{ row }">{{ row.result_count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="通过率" width="100">
          <template #default="{ row }">{{ (row.pass_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="幻觉率" width="100">
          <template #default="{ row }">{{ (row.hallucination_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="成本" width="140">
          <template #default="{ row }">{{ formatCost(row.total_cost || 0) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.report-shell { display: grid; gap: 18px; padding: 24px; }

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #0f766e 52%, #d97706 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.toolbar { display: flex; justify-content: space-between; align-items: center; }
.range-btns { display: flex; gap: 8px; }

.report-meta { padding: 20px 0 0; }
.report-meta h3 { font-size: 24px; color: #18181b; margin: 0; }
.meta-sub { margin-top: 4px; color: #71717a; font-size: 13px; }

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.sc {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.sl { display: block; font-size: 13px; color: #a1a1aa; }
.sv { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }

.insights-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.insight-card {
  border-radius: 16px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 6px 20px rgba(15,23,42,.03);
}
.insight-card strong { font-size: 16px; color: #18181b; }
.insight-body { display: flex; flex-direction: column; gap: 4px; }
.insight-name { font-size: 15px; color: #52525b; }
.insight-stat { font-size: 28px; font-weight: 800; color: #18181b; }
.insight-sub { font-size: 13px; color: #a1a1aa; }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}
.table-card strong { display: block; font-size: 18px; color: #172033; margin-bottom: 12px; }

.text-green-600 { color: #16a34a; }
.text-red-600 { color: #dc2626; }

@media (max-width: 960px) {
  .summary-row { grid-template-columns: 1fr 1fr; }
  .insights-grid { grid-template-columns: 1fr; }
}
</style>
