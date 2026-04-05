<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { useECharts } from "@/composables/useECharts";
import type {
  RagAnalysisBreakdownItem,
  RagAnalysisItem,
  RagAnalysisResponse,
} from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const loading = computed(() => store.loading);
const ragAnalysis = computed(() => store.ragAnalysis);

const selectedSpace = ref("");
const selectedSourceGraph = ref("");
const selectedFamily = ref("");

const { chartRef: trendChartRef, setOption: setTrendOption } = useECharts();
const { chartRef: latencyChartRef, setOption: setLatencyOption } = useECharts();

const spaceOptions = computed(() => {
  const source = ragAnalysis.value?.space_breakdown || [];
  return source.map((item) => ({ label: item.label, value: item.key }));
});

const sourceGraphOptions = computed(() => {
  const source = ragAnalysis.value?.source_graph_breakdown || [];
  return source.map((item) => ({ label: item.label, value: item.key }));
});

const familyOptions = computed(() => {
  const source = ragAnalysis.value?.product_family_breakdown || [];
  return source.map((item) => ({ label: item.label, value: item.key }));
});

const filteredItems = computed(() => {
  const items = ragAnalysis.value?.recent_items || [];
  return items.filter((item) => {
    if (selectedSpace.value && (item.rag_space_id || "unknown") !== selectedSpace.value) return false;
    if (selectedSourceGraph.value && (item.source_graph || "unknown") !== selectedSourceGraph.value) return false;
    if (selectedFamily.value && (item.product_family || "unknown") !== selectedFamily.value) return false;
    return true;
  });
});

function aggregateBreakdown(
  items: RagAnalysisItem[],
  keyGetter: (item: RagAnalysisItem) => string,
  labelGetter: (item: RagAnalysisItem) => string,
): RagAnalysisBreakdownItem[] {
  const map = new Map<string, { label: string; value: number; hit: number; coverage: number }>();
  for (const item of items) {
    const key = keyGetter(item) || "unknown";
    const current = map.get(key) || { label: labelGetter(item) || key, value: 0, hit: 0, coverage: 0 };
    current.value += 1;
    current.hit += item.hit_rate;
    current.coverage += item.citation_coverage;
    map.set(key, current);
  }
  return Array.from(map.entries())
    .map(([key, value]) => ({
      key,
      label: value.label,
      value: value.value,
      avg_hit_rate: value.value > 0 ? value.hit / value.value : 0,
      avg_citation_coverage: value.value > 0 ? value.coverage / value.value : 0,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
}

const filteredSpaceBreakdown = computed(() =>
  aggregateBreakdown(filteredItems.value, (item) => item.rag_space_id || "unknown", (item) => item.rag_space_name || item.rag_space_id || "unknown"),
);

const filteredSourceGraphBreakdown = computed(() =>
  aggregateBreakdown(filteredItems.value, (item) => item.source_graph || "unknown", (item) => item.source_graph || "unknown"),
);

const filteredFamilyBreakdown = computed(() =>
  aggregateBreakdown(filteredItems.value, (item) => item.product_family || "unknown", (item) => item.product_family || "unknown"),
);

const filteredStats = computed(() => {
  const items = filteredItems.value;
  if (items.length === 0) {
    return {
      total_queries: 0,
      avg_hit_rate: 0,
      avg_citation_coverage: 0,
      empty_recall_count: 0,
      avg_latency_ms: 0,
    };
  }
  const totalQueries = items.length;
  const avgHitRate = items.reduce((sum, item) => sum + item.hit_rate, 0) / totalQueries;
  const avgCoverage = items.reduce((sum, item) => sum + item.citation_coverage, 0) / totalQueries;
  const avgLatency = items.reduce((sum, item) => sum + item.latency_ms, 0) / totalQueries;
  const emptyRecall = items.filter((item) => item.hit_count === 0).length;
  return {
    total_queries: totalQueries,
    avg_hit_rate: avgHitRate,
    avg_citation_coverage: avgCoverage,
    empty_recall_count: emptyRecall,
    avg_latency_ms: avgLatency,
  };
});

const statCards = computed(() => {
  const stats = filteredStats.value;
  return [
    { label: "总检索数", value: stats.total_queries, tone: "ocean" },
    { label: "平均命中率", value: `${(stats.avg_hit_rate * 100).toFixed(1)}%`, tone: "mint" },
    { label: "平均引用覆盖率", value: `${(stats.avg_citation_coverage * 100).toFixed(1)}%`, tone: "violet" },
    { label: "空召回次数", value: stats.empty_recall_count, tone: "amber" },
    { label: "平均延迟", value: `${stats.avg_latency_ms.toFixed(0)} ms`, tone: "coral" },
  ];
});

const recentEvidenceItems = computed(() => (ragAnalysis.value?.evidence_impact || []).slice(0, 8));
const hasData = computed(() => filteredItems.value.length > 0);

function maxBreakdownValue(items: RagAnalysisBreakdownItem[]) {
  return Math.max(1, ...items.map((item) => item.value));
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function updateCharts() {
  const items = [...filteredItems.value].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  if (items.length === 0) {
    setTrendOption({
      title: { text: "尚未产生 RAG 检索记录", left: "center", top: "middle", textStyle: { fontSize: 16, color: "#64748b" } },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    });
    setLatencyOption({
      title: { text: "等待新的检索样本", left: "center", top: "middle", textStyle: { fontSize: 16, color: "#64748b" } },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    });
    return;
  }

  const labels = items.map((item) => new Date(item.created_at).toLocaleTimeString("zh-CN", { hour12: false }));
  setTrendOption({
    color: ["#0f766e", "#2563eb"],
    tooltip: { trigger: "axis" },
    legend: { data: ["命中率", "引用覆盖率"], bottom: 0 },
    grid: { left: 44, right: 16, top: 24, bottom: 48 },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      axisLabel: { color: "#64748b" },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%`, color: "#64748b" },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.22)" } },
    },
    series: [
      {
        name: "命中率",
        type: "line",
        smooth: true,
        areaStyle: { color: "rgba(37, 99, 235, 0.12)" },
        data: items.map((item) => item.hit_rate),
      },
      {
        name: "引用覆盖率",
        type: "line",
        smooth: true,
        areaStyle: { color: "rgba(15, 118, 110, 0.12)" },
        data: items.map((item) => item.citation_coverage),
      },
    ],
  });

  setLatencyOption({
    color: ["#f97316"],
    tooltip: { trigger: "axis" },
    grid: { left: 56, right: 16, top: 24, bottom: 36 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: "#64748b" },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: "{value} ms", color: "#64748b" },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.22)" } },
    },
    series: [
      {
        type: "bar",
        barWidth: 18,
        borderRadius: [8, 8, 0, 0],
        data: items.map((item) => item.latency_ms),
      },
    ],
  });
}

watch(
  () => [ragAnalysis.value, selectedSpace.value, selectedSourceGraph.value, selectedFamily.value],
  () => updateCharts(),
  { deep: true },
);

onMounted(async () => {
  await store.fetchRagAnalysis();
  updateCharts();
});
</script>

<template>
  <div class="page-container">
    <section class="hero-card">
      <div>
        <p class="eyebrow">Knowledge Evidence Workbench</p>
        <h1>RAG 分析</h1>
        <p class="subtitle">
          观察不同 RAG 空间、不同子图、不同产品族的检索表现，并追踪证据如何影响最终质检结论。
        </p>
      </div>
      <div class="hero-tags">
        <span class="hero-chip">多产品</span>
        <span class="hero-chip">真实检索记录</span>
        <span class="hero-chip">证据影响可视化</span>
      </div>
    </section>

    <div v-loading="loading" class="workspace">
      <section class="filters-panel">
        <div class="filter-field">
          <span class="filter-label">RAG 空间</span>
          <el-select v-model="selectedSpace" clearable placeholder="全部空间">
            <el-option v-for="item in spaceOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="filter-field">
          <span class="filter-label">来源子图</span>
          <el-select v-model="selectedSourceGraph" clearable placeholder="全部子图">
            <el-option v-for="item in sourceGraphOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="filter-field">
          <span class="filter-label">产品族</span>
          <el-select v-model="selectedFamily" clearable placeholder="全部产品族">
            <el-option v-for="item in familyOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <el-button plain @click="selectedSpace = ''; selectedSourceGraph = ''; selectedFamily = ''">重置筛选</el-button>
      </section>

      <section class="stat-grid">
        <article v-for="card in statCards" :key="card.label" class="stat-card" :data-tone="card.tone">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </article>
      </section>

      <el-alert
        v-if="!hasData"
        type="info"
        :closable="false"
        show-icon
        title="尚未产生符合当前筛选条件的 RAG 检索记录。产生新会话后，这里会展示真实命中、引用覆盖率和证据影响。"
      />

      <section class="panel-grid">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">检索表现趋势</div>
                <div class="panel-subtitle">观察命中率和引用覆盖率如何随最近检索波动。</div>
              </div>
            </div>
          </template>
          <div ref="trendChartRef" class="chart-panel" />
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">证据影响面</div>
                <div class="panel-subtitle">哪些标准规则最常依赖 RAG 证据，支撑了哪些判定结果。</div>
              </div>
            </div>
          </template>
          <div v-if="recentEvidenceItems.length" class="evidence-list">
            <article v-for="item in recentEvidenceItems" :key="item.rule_key" class="evidence-card">
              <div class="evidence-top">
                <strong>{{ item.rule_key }}</strong>
                <span>{{ item.query_count }} 次命中</span>
              </div>
              <div class="evidence-meta">关联 verdict：{{ item.verdicts.join(" / ") || "未标注" }}</div>
              <div class="evidence-meta">来源 {{ item.source_count }} 个</div>
              <div class="evidence-source-list">
                <el-tag v-for="source in item.sources" :key="source" size="small" effect="plain">{{ source }}</el-tag>
              </div>
            </article>
          </div>
          <el-empty v-else description="当前还没有可展示的规则证据关联。" />
        </el-card>
      </section>

      <section class="panel-grid secondary">
        <el-card shadow="never" class="panel-card compact">
          <template #header>
            <div class="panel-title">按 RAG 空间</div>
          </template>
          <div v-if="filteredSpaceBreakdown.length" class="rank-list">
            <article v-for="item in filteredSpaceBreakdown" :key="item.key" class="rank-row">
              <div class="rank-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }} 次 · 命中率 {{ percent(item.avg_hit_rate) }}</span>
              </div>
              <div class="rank-bar">
                <div class="rank-bar-fill ocean" :style="{ width: `${(item.value / maxBreakdownValue(filteredSpaceBreakdown)) * 100}%` }" />
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无空间统计" />
        </el-card>

        <el-card shadow="never" class="panel-card compact">
          <template #header>
            <div class="panel-title">按来源子图</div>
          </template>
          <div v-if="filteredSourceGraphBreakdown.length" class="rank-list">
            <article v-for="item in filteredSourceGraphBreakdown" :key="item.key" class="rank-row">
              <div class="rank-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }} 次 · 覆盖率 {{ percent(item.avg_citation_coverage) }}</span>
              </div>
              <div class="rank-bar">
                <div class="rank-bar-fill mint" :style="{ width: `${(item.value / maxBreakdownValue(filteredSourceGraphBreakdown)) * 100}%` }" />
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无子图统计" />
        </el-card>

        <el-card shadow="never" class="panel-card compact">
          <template #header>
            <div class="panel-title">按产品族</div>
          </template>
          <div v-if="filteredFamilyBreakdown.length" class="rank-list">
            <article v-for="item in filteredFamilyBreakdown" :key="item.key" class="rank-row">
              <div class="rank-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }} 次 · 命中率 {{ percent(item.avg_hit_rate) }}</span>
              </div>
              <div class="rank-bar">
                <div class="rank-bar-fill violet" :style="{ width: `${(item.value / maxBreakdownValue(filteredFamilyBreakdown)) * 100}%` }" />
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无产品族统计" />
        </el-card>
      </section>

      <section class="panel-grid">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">检索延迟</div>
                <div class="panel-subtitle">确认近期请求是否因为 RAG 空间、文件大小或子图不同而出现延迟波动。</div>
              </div>
            </div>
          </template>
          <div ref="latencyChartRef" class="chart-panel small" />
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">最近检索轨迹</div>
                <div class="panel-subtitle">直接查看每条 query 命中了什么、服务了哪个 verdict、有没有符合样本预期。</div>
              </div>
            </div>
          </template>
          <el-table :data="filteredItems" stripe max-height="420" empty-text="暂无检索记录">
            <el-table-column prop="query" label="Query" min-width="240" show-overflow-tooltip />
            <el-table-column label="RAG 空间" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.rag_space_name || row.rag_space_id || "-" }}</template>
            </el-table-column>
            <el-table-column prop="source_graph" label="子图" width="150" />
            <el-table-column prop="product_family" label="产品族" width="120" />
            <el-table-column prop="verdict" label="Verdict" width="120">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.verdict === 'pass' ? 'success' : row.verdict === 'fail' ? 'danger' : 'warning'">
                  {{ row.verdict || "-" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="预期对照" width="120">
              <template #default="{ row }">
                <el-tag
                  v-if="row.expectation_matched !== null && row.expectation_matched !== undefined"
                  size="small"
                  effect="plain"
                  :type="row.expectation_matched ? 'success' : 'danger'"
                >
                  {{ row.expectation_matched ? "一致" : "不一致" }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="Top Sources" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.top_sources.join(" / ") || "-" }}</template>
            </el-table-column>
            <el-table-column label="时间" width="176">
              <template #default="{ row }">
                {{ new Date(row.created_at).toLocaleString("zh-CN") }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  min-height: 100%;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(251, 191, 36, 0.14), transparent 26%),
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 26%),
    linear-gradient(180deg, #fffef6 0%, #f8fafc 44%, #f4f7fb 100%);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 30px;
  border-radius: 28px;
  border: 1px solid rgba(226, 232, 240, 0.78);
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 18px 52px rgba(15, 23, 42, 0.06);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #0f766e;
}

.hero-card h1 {
  margin: 0;
  font-size: 34px;
  color: #0f172a;
}

.subtitle {
  max-width: 760px;
  margin: 10px 0 0;
  line-height: 1.8;
  color: #475569;
}

.hero-tags {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-chip {
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 13px;
  font-weight: 600;
}

.workspace {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.filters-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  gap: 16px;
  padding: 18px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.78);
}

.filter-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-label {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.04);
}

.stat-card[data-tone="ocean"] {
  background: linear-gradient(145deg, rgba(219, 234, 254, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="mint"] {
  background: linear-gradient(145deg, rgba(209, 250, 229, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="violet"] {
  background: linear-gradient(145deg, rgba(237, 233, 254, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="amber"] {
  background: linear-gradient(145deg, rgba(254, 243, 199, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="coral"] {
  background: linear-gradient(145deg, rgba(254, 215, 170, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-label {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
}

.panel-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 18px;
}

.panel-grid.secondary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.panel-card {
  border-radius: 24px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(255, 255, 255, 0.88);
}

.panel-card :deep(.el-card__header) {
  border-bottom-color: rgba(226, 232, 240, 0.72);
}

.panel-card.compact {
  min-height: 240px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.panel-subtitle {
  margin-top: 6px;
  color: #64748b;
  line-height: 1.7;
}

.chart-panel {
  height: 320px;
}

.chart-panel.small {
  height: 280px;
}

.rank-list,
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-row,
.evidence-card {
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(248, 250, 252, 0.92), rgba(255, 255, 255, 0.98));
  border: 1px solid rgba(226, 232, 240, 0.74);
}

.rank-copy {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: #475569;
  font-size: 13px;
}

.rank-copy strong {
  color: #0f172a;
}

.rank-bar {
  height: 9px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.9);
  overflow: hidden;
}

.rank-bar-fill {
  height: 100%;
  border-radius: inherit;
}

.rank-bar-fill.ocean {
  background: linear-gradient(90deg, #2563eb, #60a5fa);
}

.rank-bar-fill.mint {
  background: linear-gradient(90deg, #0f766e, #34d399);
}

.rank-bar-fill.violet {
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
}

.evidence-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #0f172a;
}

.evidence-top span,
.evidence-meta {
  font-size: 13px;
  color: #64748b;
}

.evidence-meta {
  margin-top: 8px;
}

.evidence-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

@media (max-width: 1200px) {
  .stat-grid,
  .panel-grid,
  .panel-grid.secondary,
  .filters-panel {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }
}
</style>
