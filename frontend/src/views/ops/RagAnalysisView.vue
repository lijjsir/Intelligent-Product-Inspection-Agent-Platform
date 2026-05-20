<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { useECharts } from "@/composables/useECharts";
import type {
  RagAnalysisBreakdownItem,
  RagAnalysisItem,
  RagTraceDetailResponse,
} from "@/types/agent-ops.types";

const AUTO_REFRESH_MS = 10_000;

const store = useAgentOpsStore();
const loading = computed(() => store.loading);
const ragAnalysis = computed(() => store.ragAnalysis);
const ragTraceDetail = computed(() => store.ragTraceDetail);
const ragTraceDetailLoading = computed(() => store.ragTraceDetailLoading);

const selectedSpace = ref("");
const selectedSourceAgent = ref("");
const detailVisible = ref(false);
const selectedRecord = ref<RagAnalysisItem | null>(null);
const detailError = ref("");

const { chartRef: trendChartRef, setOption: setTrendOption } = useECharts();
const { chartRef: latencyChartRef, setOption: setLatencyOption } = useECharts();

let refreshTimer: number | null = null;

const stats = computed(() => {
  return (
    ragAnalysis.value?.stats || {
      total_queries: 0,
      avg_hit_rate: 0,
      avg_citation_coverage: 0,
      empty_recall_count: 0,
      avg_latency_ms: 0,
    }
  );
});

const spaceOptions = computed(() => {
  const options = ragAnalysis.value?.space_options || [];
  if (options.length > 0) {
    return options;
  }
  return (ragAnalysis.value?.space_breakdown || []).map((item) => ({ key: item.key, label: item.label }));
});

const sourceAgentOptions = computed(() => {
  const options = ragAnalysis.value?.source_agent_options || [];
  if (options.length > 0) {
    return options;
  }
  return (ragAnalysis.value?.source_agent_breakdown || []).map((item) => ({
    key: item.key,
    label: item.label,
  }));
});

function displaySpace(item: { rag_space_name?: string | null; rag_space_id?: string | null }) {
  return item.rag_space_name || item.rag_space_id || "-";
}

function displayAgent(item: { source_agent?: string | null }) {
  return item.source_agent || "-";
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatLatency(value: number | null | undefined) {
  return `${Math.round(Number(value || 0))} ms`;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatExpectation(value: boolean | null | undefined) {
  if (value === null || value === undefined) return "-";
  return value ? "符合预期" : "不符合预期";
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return value.toFixed(3);
}

function stringifyValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function truncateText(value: string | null | undefined, length = 96) {
  const raw = (value || "").trim();
  if (!raw) return "-";
  return raw.length > length ? `${raw.slice(0, length)}...` : raw;
}

function summarizeChunk(chunk: Record<string, unknown>) {
  return (
    String(chunk.title || chunk.document_name || chunk.source_name || chunk.chunk_id || chunk.id || "未命名分片")
      .trim() || "未命名分片"
  );
}

function summarizeCitation(citation: Record<string, unknown>) {
  return (
    String(citation.title || citation.document_name || citation.source_name || citation.chunk_id || citation.id || "引用")
      .trim() || "引用"
  );
}

function toFallbackTraceDetail(item: RagAnalysisItem): RagTraceDetailResponse {
  return {
    trace_id: item.trace_id || `fallback:${item.created_at}:${item.query || ""}`,
    query: item.query || null,
    rag_space_id: item.rag_space_id || null,
    rag_space_name: item.rag_space_name || null,
    source_agent: item.source_agent || null,
    source_graph: item.source_graph || null,
    sub_route: item.sub_route || null,
    top_k: 0,
    hit_count: item.hit_count,
    hit_rate: item.hit_rate,
    citation_coverage: item.citation_coverage,
    latency_ms: item.latency_ms,
    top_score: item.top_score ?? null,
    product_family: null,
    expectation_matched: item.expectation_matched ?? null,
    evidence_found: item.evidence_found,
    evidence_used: item.evidence_used,
    verdict_impacted: item.verdict_impacted,
    retrieval_config: {},
    retrieved_chunks: [],
    used_citations: [],
    rule_hits: item.rule_hits,
    verdict: item.verdict || null,
    answer: null,
    result: null,
    top_sources: item.top_sources,
    created_at: item.created_at,
  };
}

const filteredItems = computed(() => {
  const items = ragAnalysis.value?.recent_items || [];
  return items.filter((item) => {
    if (selectedSpace.value && item.rag_space_id !== selectedSpace.value) return false;
    if (selectedSourceAgent.value && item.source_agent !== selectedSourceAgent.value) return false;
    return true;
  });
});

function aggregateBreakdown(
  items: RagAnalysisItem[],
  keyGetter: (item: RagAnalysisItem) => string | null | undefined,
  labelGetter: (item: RagAnalysisItem) => string | null | undefined,
): RagAnalysisBreakdownItem[] {
  const map = new Map<string, { label: string; value: number; hit: number; coverage: number }>();
  for (const item of items) {
    const key = (keyGetter(item) || "").trim();
    const label = (labelGetter(item) || "").trim();
    if (!key || !label) continue;
    const current = map.get(key) || { label, value: 0, hit: 0, coverage: 0 };
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
  aggregateBreakdown(
    filteredItems.value,
    (item) => item.rag_space_id || null,
    (item) => item.rag_space_name || item.rag_space_id || null,
  ),
);

const filteredSourceAgentBreakdown = computed(() =>
  aggregateBreakdown(filteredItems.value, (item) => item.source_agent || null, (item) => item.source_agent || null),
);

const statCards = computed(() => [
  { label: "总检索数", value: stats.value.total_queries, tone: "ocean" },
  { label: "平均命中率", value: percent(stats.value.avg_hit_rate), tone: "mint" },
  { label: "平均引用覆盖率", value: percent(stats.value.avg_citation_coverage), tone: "violet" },
  { label: "空召回次数", value: stats.value.empty_recall_count, tone: "amber" },
  { label: "平均延迟", value: formatLatency(stats.value.avg_latency_ms), tone: "coral" },
]);

const traceabilityCards = computed(() => {
  const total = Math.max(filteredItems.value.length, 1);
  const evidenceFound = filteredItems.value.filter((item) => item.evidence_found).length;
  const evidenceUsed = filteredItems.value.filter((item) => item.evidence_used).length;
  const verdictImpacted = filteredItems.value.filter((item) => item.verdict_impacted).length;
  return [
    {
      key: "found",
      title: "1. 是否搜到正确证据",
      count: evidenceFound,
      ratio: percent(evidenceFound / total),
      hint: "至少命中到有效 RAG 证据的检索次数",
      tone: "ocean",
    },
    {
      key: "used",
      title: "2. 证据是否进入最终答案",
      count: evidenceUsed,
      ratio: percent(evidenceUsed / total),
      hint: "检索到的证据被 answer / result 真正引用",
      tone: "mint",
    },
    {
      key: "impacted",
      title: "3. 证据是否影响最终判定",
      count: verdictImpacted,
      ratio: percent(verdictImpacted / total),
      hint: "命中的规则或引用内容对 verdict 产生影响",
      tone: "violet",
    },
  ];
});

const recentEvidenceItems = computed(() => (ragAnalysis.value?.evidence_impact || []).slice(0, 8));
const hasData = computed(() => filteredItems.value.length > 0);

const activeDetail = computed<RagTraceDetailResponse | null>(() => {
  if (!selectedRecord.value) return null;
  if (
    selectedRecord.value.trace_id &&
    ragTraceDetail.value &&
    ragTraceDetail.value.trace_id === selectedRecord.value.trace_id
  ) {
    return ragTraceDetail.value;
  }
  return toFallbackTraceDetail(selectedRecord.value);
});

const detailFlowCards = computed(() => {
  const detail = activeDetail.value;
  if (!detail) return [];
  return [
    {
      key: "found",
      title: "搜到证据",
      value: detail.evidence_found ? "是" : "否",
      hint: detail.evidence_found ? `${detail.hit_count} 条命中，top_k=${detail.top_k || 0}` : "本次没有有效命中",
      tone: detail.evidence_found ? "ocean" : "neutral",
    },
    {
      key: "used",
      title: "答案已使用",
      value: detail.evidence_used ? "是" : "否",
      hint: detail.evidence_used
        ? `${detail.used_citations.length} 条引用进入 answer/result`
        : "最终答案未引用检索证据",
      tone: detail.evidence_used ? "mint" : "neutral",
    },
    {
      key: "impacted",
      title: "影响判定",
      value: detail.verdict_impacted ? "是" : "否",
      hint: detail.verdict_impacted
        ? `${detail.rule_hits.length} 条规则参与 verdict`
        : "未看到证据影响最终 verdict",
      tone: detail.verdict_impacted ? "violet" : "neutral",
    },
  ];
});

const detailResultText = computed(() => {
  const detail = activeDetail.value;
  if (!detail) return "-";
  if (detail.answer) return detail.answer;
  if (detail.result !== null && detail.result !== undefined) return stringifyValue(detail.result);
  return "-";
});

function maxBreakdownValue(items: RagAnalysisBreakdownItem[]) {
  return Math.max(1, ...items.map((item) => item.value));
}

async function openRecordDetail(row: RagAnalysisItem) {
  selectedRecord.value = row;
  detailVisible.value = true;
  detailError.value = "";
  if (!row.trace_id) return;
  try {
    await store.fetchRagTraceDetail(row.trace_id);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : "检索详情加载失败";
  }
}

function rowClassName() {
  return "track-row";
}

function updateCharts() {
  const items = [...filteredItems.value].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  if (items.length === 0) {
    setTrendOption({
      title: {
        text: "当前筛选条件下暂无检索记录",
        left: "center",
        top: "middle",
        textStyle: { fontSize: 16, color: "#64748b", fontWeight: 500 },
      },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    });
    setLatencyOption({
      title: {
        text: "等待新的检索日志写入",
        left: "center",
        top: "middle",
        textStyle: { fontSize: 16, color: "#64748b", fontWeight: 500 },
      },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    });
    return;
  }

  const labels = items.map((item) =>
    new Date(item.created_at).toLocaleTimeString("zh-CN", {
      hour12: false,
    }),
  );

  setTrendOption({
    color: ["#2563eb", "#0f766e"],
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
      axisLabel: {
        formatter: (value: number) => `${Math.round(value * 100)}%`,
        color: "#64748b",
      },
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
        itemStyle: { borderRadius: [8, 8, 0, 0] },
        data: items.map((item) => item.latency_ms),
      },
    ],
  });
}

async function refreshData(options?: { silent?: boolean }) {
  await store.fetchRagAnalysis(options);
  if (detailVisible.value && selectedRecord.value?.trace_id) {
    try {
      await store.fetchRagTraceDetail(selectedRecord.value.trace_id);
      detailError.value = "";
    } catch (error) {
      detailError.value = error instanceof Error ? error.message : "检索详情加载失败";
    }
  }
}

function startAutoRefresh() {
  if (refreshTimer !== null) return;
  refreshTimer = window.setInterval(() => {
    void refreshData({ silent: true });
  }, AUTO_REFRESH_MS);
}

function stopAutoRefresh() {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

watch(
  () => [filteredItems.value, selectedSpace.value, selectedSourceAgent.value],
  () => updateCharts(),
  { deep: true },
);

watch(detailVisible, (visible) => {
  if (!visible) {
    detailError.value = "";
  }
});

onMounted(async () => {
  await refreshData();
  updateCharts();
  startAutoRefresh();
});

onBeforeUnmount(() => {
  stopAutoRefresh();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="hero-card">
      <div>
        <p class="eyebrow">Knowledge Evidence Workbench</p>
        <h1>RAG 分析</h1>
        <p class="hero-copy">
          直接观察数据库中的真实 RAG 检索日志，按空间与来源 Agent 追踪命中、引用覆盖率、延迟，以及证据是否真正进入答案并影响最终判定。
        </p>
      </div>
      <div class="hero-tags">
        <span class="hero-chip">数据库真实日志</span>
        <span class="hero-chip">按 Agent 追踪</span>
        <span class="hero-chip">10 秒自动刷新</span>
      </div>
    </section>

    <div v-loading="loading" class="workspace">
      <section class="filters-panel">
        <div class="filter-field">
          <span class="filter-label">RAG 空间</span>
          <el-select v-model="selectedSpace" clearable placeholder="全部空间">
            <el-option
              v-for="item in spaceOptions"
              :key="item.key"
              :label="item.label"
              :value="item.key"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <span class="filter-label">来源 Agent</span>
          <el-select v-model="selectedSourceAgent" clearable placeholder="全部 Agent">
            <el-option
              v-for="item in sourceAgentOptions"
              :key="item.key"
              :label="item.label"
              :value="item.key"
            />
          </el-select>
        </div>
        <div class="filters-actions">
          <span class="filters-hint">顶部指标保持数据库近 7 天总览，下方图表、分布与检索轨迹按当前筛选实时刷新。</span>
          <el-button plain @click="selectedSpace = ''; selectedSourceAgent = ''">重置筛选</el-button>
        </div>
      </section>

      <section class="stat-grid">
        <article v-for="card in statCards" :key="card.label" class="stat-card" :data-tone="card.tone">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </article>
      </section>

      <section class="traceability-grid">
        <article
          v-for="card in traceabilityCards"
          :key="card.key"
          class="traceability-card"
          :data-tone="card.tone"
        >
          <div class="traceability-title">{{ card.title }}</div>
          <div class="traceability-count">{{ card.count }}</div>
          <div class="traceability-meta">{{ card.ratio }}</div>
          <div class="traceability-hint">{{ card.hint }}</div>
        </article>
      </section>

      <el-alert
        v-if="!hasData"
        type="info"
        :closable="false"
        show-icon
        title="当前筛选条件下暂无可展示的 RAG 检索记录。"
      />

      <section class="panel-grid">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">检索表现趋势</div>
                <div class="panel-subtitle">观察最近检索中命中率和引用覆盖率如何变化。</div>
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
                <div class="panel-subtitle">哪些规则最依赖 RAG 证据，以及它们支撑了哪些判定结果。</div>
              </div>
            </div>
          </template>
          <div v-if="recentEvidenceItems.length" class="evidence-list">
            <article v-for="item in recentEvidenceItems" :key="item.rule_key" class="evidence-card">
              <div class="evidence-top">
                <strong>{{ item.rule_key }}</strong>
                <span>{{ item.query_count }} 次命中</span>
              </div>
              <div class="evidence-meta">关联 Verdict：{{ item.verdicts.join(" / ") || "未标注" }}</div>
              <div class="evidence-meta">来源 {{ item.source_count }} 个</div>
              <div class="evidence-source-list">
                <el-tag v-for="source in item.sources" :key="source" size="small" effect="plain">{{ source }}</el-tag>
              </div>
            </article>
          </div>
          <el-empty v-else description="当前还没有可展示的证据影响数据。" />
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
                <div
                  class="rank-bar-fill ocean"
                  :style="{ width: `${(item.value / maxBreakdownValue(filteredSpaceBreakdown)) * 100}%` }"
                />
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无空间统计" />
        </el-card>

        <el-card shadow="never" class="panel-card compact">
          <template #header>
            <div class="panel-title">按来源 Agent</div>
          </template>
          <div v-if="filteredSourceAgentBreakdown.length" class="rank-list">
            <article v-for="item in filteredSourceAgentBreakdown" :key="item.key" class="rank-row">
              <div class="rank-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }} 次 · 覆盖率 {{ percent(item.avg_citation_coverage) }}</span>
              </div>
              <div class="rank-bar">
                <div
                  class="rank-bar-fill mint"
                  :style="{ width: `${(item.value / maxBreakdownValue(filteredSourceAgentBreakdown)) * 100}%` }"
                />
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无 Agent 统计" />
        </el-card>
      </section>

      <section class="panel-grid">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <div class="panel-title">检索延迟</div>
                <div class="panel-subtitle">基于真实 RAG 检索日志记录的耗时，观察近期波动是否与空间或 Agent 有关。</div>
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
                <div class="panel-subtitle">点击一条记录查看完整证据链：检索配置、命中分片、已使用引用、规则与最终判定。</div>
              </div>
            </div>
          </template>
          <el-table
            :data="filteredItems"
            stripe
            max-height="420"
            empty-text="暂无检索记录"
            :row-class-name="rowClassName"
            @row-click="openRecordDetail"
          >
            <el-table-column label="Query" min-width="240">
              <template #default="{ row }">
                <div class="query-cell">{{ row.query || "-" }}</div>
              </template>
            </el-table-column>
            <el-table-column label="RAG 空间" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ displaySpace(row) }}</template>
            </el-table-column>
            <el-table-column label="来源 Agent" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ displayAgent(row) }}</template>
            </el-table-column>
            <el-table-column label="子路由" width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.sub_route || "-" }}</template>
            </el-table-column>
            <el-table-column label="证据链" width="220">
              <template #default="{ row }">
                <div class="evidence-pill-group">
                  <span class="mini-pill" :data-state="row.evidence_found ? 'ok' : 'off'">已命中</span>
                  <span class="mini-pill" :data-state="row.evidence_used ? 'ok' : 'off'">已引用</span>
                  <span class="mini-pill" :data-state="row.verdict_impacted ? 'ok' : 'off'">影响判定</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="延迟" width="100">
              <template #default="{ row }">{{ formatLatency(row.latency_ms) }}</template>
            </el-table-column>
            <el-table-column label="时间" width="176">
              <template #default="{ row }">{{ formatTimestamp(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </section>
    </div>

    <el-drawer v-model="detailVisible" size="640px" :destroy-on-close="false" title="检索轨迹详情">
      <div v-loading="ragTraceDetailLoading" class="drawer-shell">
        <template v-if="activeDetail">
          <section class="detail-section">
            <div class="detail-title">Query</div>
            <div class="detail-query">{{ activeDetail.query || "-" }}</div>
          </section>

          <section class="detail-flow-grid">
            <article
              v-for="card in detailFlowCards"
              :key="card.key"
              class="detail-flow-card"
              :data-tone="card.tone"
            >
              <span class="detail-flow-title">{{ card.title }}</span>
              <strong>{{ card.value }}</strong>
              <span class="detail-flow-hint">{{ card.hint }}</span>
            </article>
          </section>

          <el-alert
            v-if="detailError"
            type="warning"
            :closable="false"
            show-icon
            :title="detailError"
            class="detail-alert"
          />

          <section class="detail-grid">
            <article class="detail-card">
              <span class="detail-label">RAG 空间</span>
              <strong>{{ displaySpace(activeDetail) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">来源 Agent</span>
              <strong>{{ displayAgent(activeDetail) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">子路由</span>
              <strong>{{ activeDetail.sub_route || "-" }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">Verdict</span>
              <strong>{{ activeDetail.verdict || "-" }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">top_k</span>
              <strong>{{ activeDetail.top_k || 0 }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">命中数</span>
              <strong>{{ activeDetail.hit_count }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">命中率</span>
              <strong>{{ percent(activeDetail.hit_rate) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">引用覆盖率</span>
              <strong>{{ percent(activeDetail.citation_coverage) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">检索延迟</span>
              <strong>{{ formatLatency(activeDetail.latency_ms) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">最高分片分数</span>
              <strong>{{ formatScore(activeDetail.top_score) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">预期对照</span>
              <strong>{{ formatExpectation(activeDetail.expectation_matched) }}</strong>
            </article>
            <article class="detail-card">
              <span class="detail-label">时间</span>
              <strong>{{ formatTimestamp(activeDetail.created_at) }}</strong>
            </article>
            <article class="detail-card full">
              <span class="detail-label">Trace ID</span>
              <strong>{{ activeDetail.trace_id }}</strong>
            </article>
          </section>

          <section class="detail-section">
            <div class="detail-title">检索配置</div>
            <pre class="detail-pre">{{ stringifyValue(activeDetail.retrieval_config) }}</pre>
          </section>

          <section class="detail-section">
            <div class="detail-title">命中分片</div>
            <div v-if="activeDetail.retrieved_chunks.length" class="entity-list">
              <article v-for="(chunk, index) in activeDetail.retrieved_chunks" :key="index" class="entity-card">
                <div class="entity-head">
                  <strong>{{ summarizeChunk(chunk) }}</strong>
                  <span>{{ formatScore(Number(chunk.score ?? chunk.similarity_score ?? NaN)) }}</span>
                </div>
                <div class="entity-body">{{ truncateText(String(chunk.content || chunk.text || chunk.snippet || "")) }}</div>
                <div class="entity-meta">
                  {{ truncateText(String(chunk.document_name || chunk.source_name || chunk.chunk_id || "")) }}
                </div>
              </article>
            </div>
            <el-empty v-else description="暂无命中分片详情" :image-size="88" />
          </section>

          <section class="detail-section">
            <div class="detail-title">已使用引用</div>
            <div v-if="activeDetail.used_citations.length" class="entity-list">
              <article v-for="(citation, index) in activeDetail.used_citations" :key="index" class="entity-card">
                <div class="entity-head">
                  <strong>{{ summarizeCitation(citation) }}</strong>
                  <span>{{ truncateText(String(citation.kind || "rag"), 24) }}</span>
                </div>
                <div class="entity-body">{{ truncateText(String(citation.quote || citation.content || citation.text || "")) }}</div>
                <div class="entity-meta">
                  {{ truncateText(String(citation.document_name || citation.source_name || citation.chunk_id || "")) }}
                </div>
              </article>
            </div>
            <el-empty v-else description="最终答案未显式引用 RAG 证据" :image-size="88" />
          </section>

          <section class="detail-section">
            <div class="detail-title">命中规则</div>
            <div v-if="activeDetail.rule_hits.length" class="detail-tags">
              <el-tag v-for="rule in activeDetail.rule_hits" :key="rule" effect="plain" type="success">{{ rule }}</el-tag>
            </div>
            <el-empty v-else description="暂无规则命中信息" :image-size="88" />
          </section>

          <section class="detail-section">
            <div class="detail-title">来源文档</div>
            <div v-if="activeDetail.top_sources.length" class="detail-tags">
              <el-tag v-for="source in activeDetail.top_sources" :key="source" effect="plain">{{ source }}</el-tag>
            </div>
            <el-empty v-else description="暂无来源文档" :image-size="88" />
          </section>

          <section class="detail-section">
            <div class="detail-title">最终答案 / 结果</div>
            <pre class="detail-pre">{{ detailResultText }}</pre>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
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

.hero-copy {
  margin-top: 8px;
  max-width: 760px;
  line-height: 1.7;
  color: #64748b;
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
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
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

.filters-actions {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
}

.filters-hint {
  max-width: 360px;
  text-align: right;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.stat-grid,
.traceability-grid {
  display: grid;
  gap: 16px;
}

.stat-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.traceability-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stat-card,
.traceability-card {
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.04);
}

.stat-card[data-tone="ocean"],
.traceability-card[data-tone="ocean"] {
  background: linear-gradient(145deg, rgba(219, 234, 254, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="mint"],
.traceability-card[data-tone="mint"] {
  background: linear-gradient(145deg, rgba(209, 250, 229, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="violet"],
.traceability-card[data-tone="violet"] {
  background: linear-gradient(145deg, rgba(237, 233, 254, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="amber"] {
  background: linear-gradient(145deg, rgba(254, 243, 199, 0.72), rgba(255, 255, 255, 0.96));
}

.stat-card[data-tone="coral"] {
  background: linear-gradient(145deg, rgba(254, 215, 170, 0.72), rgba(255, 255, 255, 0.96));
}

.traceability-card[data-tone="neutral"],
.detail-flow-card[data-tone="neutral"] {
  background: linear-gradient(145deg, rgba(241, 245, 249, 0.78), rgba(255, 255, 255, 0.96));
}

.stat-label,
.traceability-title {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
}

.traceability-count {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
}

.traceability-meta,
.traceability-hint {
  color: #475569;
}

.traceability-meta {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 700;
}

.traceability-hint {
  margin-top: 10px;
  line-height: 1.65;
  font-size: 12px;
}

.panel-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 18px;
}

.panel-grid.secondary {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
.evidence-list,
.entity-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-row,
.evidence-card,
.entity-card {
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

.evidence-top,
.entity-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #0f172a;
}

.evidence-top span,
.evidence-meta,
.entity-head span,
.entity-meta {
  font-size: 13px;
  color: #64748b;
}

.evidence-meta,
.entity-body,
.entity-meta {
  margin-top: 8px;
}

.entity-body {
  color: #334155;
  line-height: 1.65;
}

.evidence-source-list,
.detail-tags,
.evidence-pill-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.query-cell {
  color: #0f172a;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mini-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 60px;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(226, 232, 240, 0.72);
  color: #64748b;
}

.mini-pill[data-state="ok"] {
  background: rgba(220, 252, 231, 0.96);
  color: #15803d;
}

.panel-card :deep(.track-row) {
  cursor: pointer;
}

.panel-card :deep(.track-row td) {
  transition: background-color 0.2s ease;
}

.panel-card :deep(.track-row:hover td) {
  background: rgba(239, 246, 255, 0.7);
}

.drawer-shell {
  padding-right: 6px;
}

.detail-alert {
  margin-top: 18px;
}

.detail-section + .detail-section {
  margin-top: 22px;
}

.detail-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.detail-query,
.detail-pre {
  margin-top: 10px;
  padding: 14px 16px;
  border-radius: 16px;
  line-height: 1.75;
  color: #334155;
  background: rgba(248, 250, 252, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.8);
}

.detail-pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
}

.detail-flow-grid,
.detail-grid {
  display: grid;
  gap: 12px;
  margin-top: 22px;
}

.detail-flow-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.detail-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-flow-card,
.detail-card {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.8);
}

.detail-flow-card[data-tone="ocean"] {
  background: linear-gradient(145deg, rgba(219, 234, 254, 0.74), rgba(255, 255, 255, 0.96));
}

.detail-flow-card[data-tone="mint"] {
  background: linear-gradient(145deg, rgba(209, 250, 229, 0.74), rgba(255, 255, 255, 0.96));
}

.detail-flow-card[data-tone="violet"] {
  background: linear-gradient(145deg, rgba(237, 233, 254, 0.74), rgba(255, 255, 255, 0.96));
}

.detail-flow-title,
.detail-label {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.detail-flow-card strong,
.detail-card strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  line-height: 1.55;
  word-break: break-word;
}

.detail-flow-hint {
  display: block;
  margin-top: 8px;
  color: #475569;
  line-height: 1.55;
  font-size: 12px;
}

.detail-card.full {
  grid-column: 1 / -1;
}

@media (max-width: 1200px) {
  .stat-grid,
  .traceability-grid,
  .panel-grid,
  .panel-grid.secondary,
  .filters-panel,
  .detail-grid,
  .detail-flow-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }

  .filters-actions {
    align-items: stretch;
  }

  .filters-hint {
    max-width: none;
    text-align: left;
  }
}
</style>
