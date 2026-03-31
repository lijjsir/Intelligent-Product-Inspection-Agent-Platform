<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import RiskDistributionTrendChart from "@/components/business/analytics/RiskDistributionTrendChart.vue";
import { useAnalyticsStore } from "@/stores/analytics.store";

type RangeOption = 7 | 30 | 90;
type RiskLevel = "low" | "medium" | "high" | "critical";

const router = useRouter();
const analyticsStore = useAnalyticsStore();
const selectedRange = ref<RangeOption>(30);

const overview = computed(() => analyticsStore.overview);
const totalReports = computed(() => {
  return (overview.value?.risk_distribution ?? []).reduce((sum, item) => sum + item.value, 0);
});
const highRiskReports = computed(() => {
  return (overview.value?.risk_distribution ?? [])
    .filter((item) => ["high", "critical"].includes(item.name.toLowerCase()))
    .reduce((sum, item) => sum + item.value, 0);
});
const mediumRiskRate = computed(() => (overview.value?.risk_yellow_rate ?? 0) * 100);
const riskItems = computed(() => {
  const current = new Map((overview.value?.risk_distribution ?? []).map((item) => [item.name.toLowerCase(), item.value]));
  const total = totalReports.value || 1;
  const order: Array<{ key: RiskLevel; label: string; tone: string }> = [
    { key: "low", label: "低风险", tone: "low" },
    { key: "medium", label: "中风险", tone: "medium" },
    { key: "high", label: "高风险", tone: "high" },
    { key: "critical", label: "严重风险", tone: "critical" },
  ];
  return order.map((item) => {
    const value = current.get(item.key) ?? 0;
    return {
      ...item,
      value,
      percent: (value / total) * 100,
    };
  });
});

onMounted(async () => {
  await fetchOverview();
});

async function setRange(days: RangeOption) {
  if (selectedRange.value === days && overview.value) {
    return;
  }
  selectedRange.value = days;
  await fetchOverview();
}

async function fetchOverview() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (selectedRange.value - 1));
  await analyticsStore.fetchOverview({
    start_date: formatDate(start),
    end_date: formatDate(end),
  });
}

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}
</script>

<template>
  <div class="stability-shell">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">PIAP Stability Desk</p>
        <h2>稳定性总览</h2>
        <p class="subtitle">这里承接首页“风险等级分布”入口，展示近一段时间的风险结构与变化趋势。任务级稳定性报告仍从任务详情或分析中心钻取进入。</p>
      </div>
      <div class="hero-actions">
        <div class="range-switch">
          <el-button :type="selectedRange === 7 ? 'primary' : 'default'" @click="setRange(7)">7 日</el-button>
          <el-button :type="selectedRange === 30 ? 'primary' : 'default'" @click="setRange(30)">30 日</el-button>
          <el-button :type="selectedRange === 90 ? 'primary' : 'default'" @click="setRange(90)">90 日</el-button>
        </div>
        <div class="action-group">
          <el-button type="primary" @click="router.push('/app/analytics')">进入分析中心</el-button>
          <el-button plain @click="router.push('/app/tasks')">从任务查看详情</el-button>
        </div>
      </div>
    </section>

    <el-alert
      title="当前前端已实现任务级稳定性详情页（/app/stability/:id），本页提供聚合总览，避免首页入口落到空白路径。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-alert
      v-if="analyticsStore.error"
      :title="analyticsStore.error"
      type="warning"
      :closable="false"
    />

    <section v-if="overview" class="metric-grid">
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">稳定性报告数</div>
        <div class="metric-value">{{ totalReports }}</div>
        <div class="metric-meta">最近 {{ selectedRange }} 日内有稳定性评估的任务总量</div>
      </el-card>
      <el-card shadow="never" class="metric-card high-risk">
        <div class="metric-label">高风险任务数</div>
        <div class="metric-value">{{ highRiskReports }}</div>
        <div class="metric-meta">统计 high + critical 两档风险</div>
      </el-card>
      <el-card shadow="never" class="metric-card score">
        <div class="metric-label">平均风险指数</div>
        <div class="metric-value">{{ (overview.avg_risk_score * 10).toFixed(1) }}</div>
        <div class="metric-meta">以 10 分制展示聚合风险分</div>
      </el-card>
      <el-card shadow="never" class="metric-card medium-risk">
        <div class="metric-label">中风险占比</div>
        <div class="metric-value">{{ mediumRiskRate.toFixed(1) }}%</div>
        <div class="metric-meta">对应后端聚合字段 risk_yellow_rate</div>
      </el-card>
    </section>

    <section class="content-grid">
      <el-card shadow="never" class="panel">
        <template #header>
          <div class="panel-head">
            <div>
              <strong>风险趋势演化</strong>
              <span>按日观察 low / medium / high / critical 数量变化</span>
            </div>
          </div>
        </template>
        <RiskDistributionTrendChart :points="overview?.risk_distribution_trend ?? []" />
      </el-card>

      <el-card shadow="never" class="panel">
        <template #header>
          <div class="panel-head">
            <div>
              <strong>当前风险结构</strong>
              <span>基于聚合统计展示当前各等级占比</span>
            </div>
          </div>
        </template>

        <div class="risk-list">
          <div v-for="item in riskItems" :key="item.key" class="risk-row">
            <div class="risk-meta">
              <span class="risk-dot" :class="item.tone"></span>
              <strong>{{ item.label }}</strong>
            </div>
            <div class="risk-values">
              <span>{{ item.value }}</span>
              <span>{{ item.percent.toFixed(1) }}%</span>
            </div>
            <el-progress
              :percentage="Number(item.percent.toFixed(1))"
              :show-text="false"
              :color="{ low: '#0f766e', medium: '#f59e0b', high: '#ef4444', critical: '#7c3aed' }[item.tone]"
            />
          </div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.stability-shell {
  min-height: 100vh;
  display: grid;
  gap: 18px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(124, 58, 237, 0.1), transparent 24%),
    linear-gradient(180deg, #f5f3ef 0%, #eef3f8 100%);
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 28px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f766e;
}

.hero-panel h2 {
  margin: 0;
  font-size: 32px;
  color: #10243d;
}

.subtitle {
  max-width: 760px;
  margin: 12px 0 0;
  color: #52606d;
  line-height: 1.7;
}

.hero-actions {
  display: grid;
  gap: 12px;
  align-content: start;
}

.range-switch,
.action-group {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  border-radius: 22px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
}

.metric-card :deep(.el-card__body) {
  display: grid;
  gap: 10px;
}

.metric-label {
  font-size: 13px;
  color: #64748b;
}

.metric-value {
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  color: #0f172a;
}

.metric-meta {
  font-size: 13px;
  color: #52606d;
}

.metric-card.high-risk .metric-value {
  color: #dc2626;
}

.metric-card.score .metric-value {
  color: #1d4ed8;
}

.metric-card.medium-risk .metric-value {
  color: #d97706;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.9fr);
  gap: 16px;
}

.panel {
  border-radius: 24px;
  border: 1px solid rgba(16, 36, 61, 0.08);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.panel-head strong {
  display: block;
  color: #10243d;
}

.panel-head span {
  color: #64748b;
  font-size: 13px;
}

.risk-list {
  display: grid;
  gap: 18px;
}

.risk-row {
  display: grid;
  gap: 10px;
}

.risk-meta,
.risk-values {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.risk-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
  margin-right: 10px;
}

.risk-dot.low {
  background: #0f766e;
}

.risk-dot.medium {
  background: #f59e0b;
}

.risk-dot.high {
  background: #ef4444;
}

.risk-dot.critical {
  background: #7c3aed;
}

@media (max-width: 1180px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .stability-shell {
    padding: 16px;
  }

  .hero-panel {
    padding: 22px;
    display: grid;
    grid-template-columns: 1fr;
  }

  .range-switch,
  .action-group {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
