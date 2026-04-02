<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import RiskDistributionTrendChart from "@/components/business/analytics/RiskDistributionTrendChart.vue";
import StabilityAlertTab from "@/components/business/stability/StabilityAlertTab.vue";
import { useAnalyticsStore } from "@/stores/analytics.store";

type TabKey = "overview" | "alerts";
type RangeOption = 7 | 30 | 90;
type RiskLevel = "low" | "medium" | "high" | "critical";

const route = useRoute();
const router = useRouter();
const analyticsStore = useAnalyticsStore();

const activeTab = ref<TabKey>((route.query.tab as TabKey) || "overview");
const selectedRange = ref<RangeOption>(30);
const loaded = ref<Record<TabKey, boolean>>({ overview: true, alerts: false });

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
    return { ...item, value, percent: (value / total) * 100 };
  });
});

onMounted(async () => {
  await fetchOverview();
  if (activeTab.value === "alerts") loaded.value.alerts = true;
});

function handleTabChange(tab: TabKey) {
  activeTab.value = tab;
  if (!loaded.value[tab]) loaded.value[tab] = true;
  router.replace({ query: { ...route.query, tab: tab } });
}

// URL query 同步
watch(() => route.query.tab, (val) => {
  const t = (val as TabKey) || "overview";
  if (t !== activeTab.value) {
    activeTab.value = t;
    if (!loaded.value[t]) loaded.value[t] = true;
  }
});

async function setRange(days: RangeOption) {
  if (selectedRange.value === days && overview.value) return;
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
        <h2>稳定性工作台</h2>
        <p class="subtitle">风险总览与预警处置一体化流程，支持 ACK / 压制 / 解决告警闭环。</p>
      </div>
      <div class="hero-actions">
        <div class="range-switch" :style="{ visibility: activeTab === 'overview' ? 'visible' : 'hidden' }">
          <el-button :type="selectedRange === 7 ? 'primary' : 'default'" @click="setRange(7)">7 日</el-button>
          <el-button :type="selectedRange === 30 ? 'primary' : 'default'" @click="setRange(30)">30 日</el-button>
          <el-button :type="selectedRange === 90 ? 'primary' : 'default'" @click="setRange(90)">90 日</el-button>
        </div>
        <div class="action-group">
          <el-button type="primary" @click="router.push('/ops/analytics')">进入分析中心</el-button>
          <el-button plain @click="router.push('/app/tasks')">从任务查看详情</el-button>
        </div>
      </div>
    </section>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button :class="['tab-btn', { active: activeTab === 'overview' }]" @click="handleTabChange('overview')">稳定性总览</button>
      <button :class="['tab-btn', { active: activeTab === 'alerts' }]" @click="handleTabChange('alerts')">预警处置</button>
    </div>

    <!-- 总览 Tab -->
    <div v-show="activeTab === 'overview'" class="overview-panel">
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
                <strong>风险分布变化</strong>
                <span>按日期堆叠展示风险等级演化</span>
              </div>
            </div>
          </template>
          <RiskDistributionTrendChart v-if="overview" :points="overview.risk_distribution_trend" />
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

    <!-- 预警 Tab -->
    <div v-if="loaded.alerts" v-show="activeTab === 'alerts'" class="alert-tab-wrapper">
      <StabilityAlertTab />
    </div>
  </div>
</template>

<style scoped>
.stability-shell {
  min-height: 100vh;
  display: grid;
  align-content: start;
  gap: 18px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(15,118,110,0.14), transparent 24%),
    radial-gradient(circle at right top, rgba(217,119,6,0.12), transparent 24%),
    linear-gradient(180deg, #f6f2ea 0%, #edf2f7 100%);
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #10243d 0%, #173f5f 52%, #0f766e 100%);
  color: #f8fafc;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.76;
}

.hero-panel h2 { margin: 0; font-size: 40px; }
.subtitle { margin: 12px 0 0; max-width: 780px; color: rgba(248, 250, 252, 0.82); }
.hero-actions { display: grid; gap: 14px; align-content: start; }
.range-switch, .action-group { display: flex; justify-content: flex-end; gap: 10px; }
.hero-actions :deep(.el-button--default) {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.26);
  color: #f8fafc;
}
.hero-actions :deep(.el-button--default:hover) {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.35);
  color: #ffffff;
}
.hero-actions :deep(.el-button--primary) {
  background: #f8fafc;
  border-color: #f8fafc;
  color: #10243d;
}
.hero-actions :deep(.el-button--primary:hover) {
  background: #ffffff;
  border-color: #ffffff;
  color: #0f172a;
}

.overview-panel { display: grid; gap: 18px; }

.tab-bar {
  display: flex;
  gap: 6px;
  padding: 6px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 12px;
  width: fit-content;
}
.tab-btn {
  padding: 10px 22px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn:hover { color: #10243d; }
.tab-btn.active {
  background: #fff;
  color: #0f766e;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
}

.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 20px; }
.metric-card { border-radius: 22px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.metric-card :deep(.el-card__body) { display: grid; gap: 12px; padding: 24px; }
.metric-label { font-size: 13px; color: #64748b; }
.metric-value { font-size: 36px; font-weight: 800; line-height: 1; color: #0f172a; }
.metric-meta { font-size: 13px; color: #52606d; }
.metric-card.high-risk .metric-value { color: #dc2626; }
.metric-card.score .metric-value { color: #1d4ed8; }
.metric-card.medium-risk .metric-value { color: #d97706; }

.content-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; align-items: start; }
.panel { border-radius: 24px; border: 1px solid rgba(16, 36, 61, 0.08); }
.panel :deep(.el-card__body) { padding: 24px; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; }
.panel-head strong { display: block; color: #10243d; font-size: 18px; }
.panel-head span { color: #64748b; font-size: 13px; }

.risk-list { display: grid; gap: 22px; }
.risk-row { display: grid; gap: 12px; }
.risk-meta, .risk-values { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.risk-dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; margin-right: 10px; }
.risk-dot.low { background: #0f766e; }
.risk-dot.medium { background: #f59e0b; }
.risk-dot.high { background: #ef4444; }
.risk-dot.critical { background: #7c3aed; }

.alert-tab-wrapper { overflow: hidden; min-width: 0; }

@media (max-width: 1280px) {
  .content-grid { grid-template-columns: 1fr; }
}
@media (max-width: 1180px) {
  .hero-panel { gap: 16px; padding: 24px; }
  .metric-grid { gap: 16px; }
}
@media (max-width: 860px) {
  .stability-shell { padding: 16px; gap: 14px; }
  .hero-panel { padding: 22px; display: grid; grid-template-columns: 1fr; }
  .range-switch, .action-group { flex-wrap: wrap; justify-content: flex-start; }
  .metric-grid { grid-template-columns: 1fr; gap: 14px; }
  .content-grid { gap: 14px; }
  .metric-card :deep(.el-card__body), .panel :deep(.el-card__body) { padding: 16px; }
}
</style>
