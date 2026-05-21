<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const overview = computed(() => analyticsStore.overview);
const modelMetrics = computed(() => overview.value?.model_metrics ?? []);
const totalCost = computed(() => overview.value?.total_cost ?? 0);

const sortedMetrics = computed(() =>
  [...modelMetrics.value].sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0))
);

const maxCost = computed(() => {
  if (!sortedMetrics.value.length) return 1;
  return sortedMetrics.value[0].total_cost || 1;
});

const avgCostPerResult = computed(() => {
  const total = overview.value?.total_results ?? 1;
  return total > 0 ? totalCost.value / total : 0;
});

async function fetchData() {
  loading.value = true;
  try {
    await analyticsStore.fetchOverview();
  } finally {
    loading.value = false;
  }
}

function formatCost(value: number) {
  if (value >= 1) return `¥${value.toFixed(2)}`;
  if (value >= 0.01) return `¥${value.toFixed(4)}`;
  return `¥${value.toFixed(6)}`;
}

function formatPct(part: number, whole: number) {
  if (!whole) return "0%";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

function barWidth(cost: number) {
  return `${Math.max((cost / maxCost.value) * 100, 2)}%`;
}

onMounted(fetchData);
</script>

<template>
  <div class="cost-shell">
    <section class="hero">
      <p class="eyebrow">Cost Intelligence</p>
      <h2>成本分析</h2>
      <p class="sub">按模型维度拆解 Token 消耗和费用，追踪成本趋势。</p>
    </section>

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <section class="summary-row">
      <div class="summary-card">
        <span class="sum-label">总成本</span>
        <span class="sum-value">{{ formatCost(totalCost) }}</span>
      </div>
      <div class="summary-card">
        <span class="sum-label">模型数</span>
        <span class="sum-value">{{ modelMetrics.length }}</span>
      </div>
      <div class="summary-card">
        <span class="sum-label">平均单次成本</span>
        <span class="sum-value">{{ formatCost(avgCostPerResult) }}</span>
      </div>
      <div class="summary-card">
        <span class="sum-label">总调用次数</span>
        <span class="sum-value">{{ (overview?.total_results ?? 0).toLocaleString() }}</span>
      </div>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-head">
          <strong>模型成本分布</strong>
          <span>按总成本降序排列</span>
        </div>
      </template>

      <div v-if="sortedMetrics.length" class="cost-table">
        <div v-for="m in sortedMetrics" :key="m.model_key" class="cost-row">
          <div class="cost-bar-bg">
            <div class="cost-bar" :style="{ width: barWidth(m.total_cost) }" />
          </div>
          <div class="cost-info">
            <div class="cost-model">
              <span class="model-key">{{ m.model_key }}</span>
              <span class="cost-pct">{{ formatPct(m.total_cost, totalCost) }}</span>
            </div>
            <div class="cost-detail">
              <span>{{ formatCost(m.total_cost) }}</span>
              <span class="sep">|</span>
              <span>{{ m.result_count }} 次调用</span>
              <span class="sep">|</span>
              <span>均价 {{ formatCost(m.result_count ? m.total_cost / m.result_count : 0) }}</span>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无成本数据" />
    </el-card>

    <el-card v-if="sortedMetrics.length" shadow="never" class="table-card">
      <template #header>
        <div class="card-head">
          <strong>模型成本明细</strong>
        </div>
      </template>
      <el-table :data="sortedMetrics" size="small" class="detail-table">
        <el-table-column prop="model_key" label="模型" min-width="200" show-overflow-tooltip />
        <el-table-column label="通过率" width="100">
          <template #default="{ row }">
            {{ (row.pass_rate * 100).toFixed(1) }}%
          </template>
        </el-table-column>
        <el-table-column label="调用次数" width="110">
          <template #default="{ row }">
            {{ row.result_count.toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="140">
          <template #default="{ row }">
            <strong class="text-zinc-900">{{ formatCost(row.total_cost) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="均价" width="120">
          <template #default="{ row }">
            {{ formatCost(row.result_count ? row.total_cost / row.result_count : 0) }}
          </template>
        </el-table-column>
        <el-table-column label="成本占比" width="120">
          <template #default="{ row }">
            <el-progress
              :percentage="parseFloat(formatPct(row.total_cost, totalCost))"
              :stroke-width="8"
              :show-text="false"
            />
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
.cost-shell {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #18181b 0%, #3f3f46 52%, #d97706 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.summary-card {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.sum-label { display: block; font-size: 13px; color: #a1a1aa; }
.sum-value { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }

.cost-table { display: flex; flex-direction: column; gap: 12px; }
.cost-row { position: relative; }
.cost-bar-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: 8px;
  overflow: hidden;
}
.cost-bar {
  height: 100%;
  background: rgba(217,119,6,.12);
  border-radius: 8px;
  transition: width .4s ease;
}
.cost-info {
  position: relative;
  z-index: 1;
  padding: 12px 16px;
}
.cost-model { display: flex; justify-content: space-between; align-items: center; }
.model-key { font-weight: 600; color: #18181b; }
.cost-pct { font-size: 18px; font-weight: 800; color: #d97706; }
.cost-detail { margin-top: 4px; display: flex; gap: 8px; font-size: 13px; color: #71717a; }
.sep { color: #d4d4d8; }

.detail-table :deep(.el-table__header th) {
  color: #71717a;
  font-weight: 600;
  font-size: 13px;
}

.refresh-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

@media (max-width: 960px) {
  .summary-row { grid-template-columns: 1fr 1fr; }
}
</style>
