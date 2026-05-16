<script setup lang="ts">
import { ref, watch, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import AnalyticsOverviewPanel from "@/components/business/analytics/AnalyticsOverviewPanel.vue";
import AnalyticsTabNav from "@/components/business/analytics/AnalyticsTabNav.vue";
import QualityReportPanel from "@/components/business/analytics/QualityReportPanel.vue";
import QualityTracingPanel from "@/components/business/analytics/QualityTracingPanel.vue";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useQualityStore } from "@/stores/quality.store";

const route = useRoute();
const router = useRouter();
const analyticsStore = useAnalyticsStore();
const qualityStore = useQualityStore();

type TabName = "overview" | "quality" | "tracing";
const activeTab = ref<TabName>((route.query.tab as TabName) || "overview");
const dateRange = ref<[Date, Date] | null>(null);
const loaded = ref<Record<TabName, boolean>>({ overview: false, quality: false, tracing: false });
const scopeLabel = computed(() => (analyticsStore.overview?.scope_kind === "global" ? "全部组织" : "当前组织"));

watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab } });
});

watch(
  () => route.query.tab,
  (tab) => {
    if (tab && (tab === "overview" || tab === "quality" || tab === "tracing")) {
      activeTab.value = tab;
    }
  },
);

watch(activeTab, (tab) => {
  if (tab === "tracing" && !loaded.value.tracing) {
    loaded.value.tracing = true;
  }
});

onMounted(() => {
  fetchAll();
  if (activeTab.value === "tracing") {
    loaded.value.tracing = true;
  }
});

async function fetchAll() {
  const params = dateRange.value
    ? { start_date: formatDate(dateRange.value[0]), end_date: formatDate(dateRange.value[1]) }
    : undefined;
  await Promise.all([
    analyticsStore.fetchOverview(params).then(() => { loaded.value.overview = true; }),
    qualityStore.fetchReport(params).then(() => { loaded.value.quality = true; }),
    qualityStore.fetchTraces({ source: "all", limit: 100 }).then(() => { loaded.value.tracing = true; }),
  ]);
}

async function applyDateFilter() {
  await fetchAll();
}

async function clearDateFilter() {
  dateRange.value = null;
  await fetchAll();
}

async function quickRange(days: 7 | 30 | 90) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  dateRange.value = [start, end];
  await fetchAll();
}

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function handleTabChange(tab: TabName) {
  activeTab.value = tab;
}
</script>

<template>
  <div class="analytics-shell">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">PIAP Intelligence Desk</p>
        <h2>分析中心</h2>
        <p class="subtitle">这里统一查看通过率、幻觉率、风险演化、模型成本和质量追踪，统计口径与任务和稳定性页完全一致。</p>
        <div class="scope-row">
          <el-tag type="success" effect="dark">{{ scopeLabel }}</el-tag>
          <el-tag v-if="dateRange" type="info" effect="plain">
            {{ formatDate(dateRange[0]) }} 至 {{ formatDate(dateRange[1]) }}
          </el-tag>
        </div>
      </div>
      <div class="hero-actions">
        <el-button @click="quickRange(7)">7 日</el-button>
        <el-button @click="quickRange(30)">30 日</el-button>
        <el-button @click="quickRange(90)">90 日</el-button>
      </div>
    </section>

    <AnalyticsTabNav :active-tab="activeTab" @change="handleTabChange" />

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <div>
          <div class="filter-title">时间范围</div>
          <div class="filter-meta">所有图表跟随同一时间窗口，不再和任务页使用不同口径。</div>
        </div>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          unlink-panels
        />
        <el-button type="primary" @click="applyDateFilter">应用筛选</el-button>
        <el-button plain @click="clearDateFilter">重置</el-button>
      </div>
    </el-card>

    <AnalyticsOverviewPanel v-show="activeTab === 'overview'" :date-range="dateRange" />
    <QualityReportPanel v-show="activeTab === 'quality'" />
    <QualityTracingPanel v-if="loaded.tracing" v-show="activeTab === 'tracing'" />
  </div>
</template>

<style scoped>
.analytics-shell {
  min-height: 100vh;
  padding: 24px;
  display: grid;
  gap: 18px;
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

.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; opacity: 0.76; }
.hero-panel h2 { margin: 0; font-size: 40px; }
.subtitle { margin: 12px 0 0; max-width: 780px; color: rgba(248, 250, 252, 0.82); }
.scope-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }
.hero-actions { display: flex; align-items: flex-start; gap: 12px; }
.filter-card { border-radius: 20px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.filter-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.filter-title { font-size: 16px; font-weight: 700; color: #172033; }
.filter-meta { margin-top: 4px; color: #64748b; font-size: 13px; }

@media (max-width: 960px) {
  .hero-panel, .filter-row { flex-direction: column; align-items: stretch; }
}
</style>
