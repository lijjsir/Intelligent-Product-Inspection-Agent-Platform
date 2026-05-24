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
const chartTab = ref<"trend" | "latency">("trend");
const recordMode = ref<"task" | "chat" | "all">("all");

const { chartRef: trendChartRef, setOption: setTrendOption } = useECharts();
const { chartRef: latencyChartRef, setOption: setLatencyOption } = useECharts();

let refreshTimer: number | null = null;

const spaceOptions = computed(() => {
  const byMode = new Map<string, string>();
  for (const item of modeSourceItems.value) {
    if (item.rag_space_id) byMode.set(item.rag_space_id, item.rag_space_name || item.rag_space_id);
  }
  if (byMode.size) {
    return Array.from(byMode.entries()).map(([key, label]) => ({ key, label })).sort((a, b) => a.label.localeCompare(b.label));
  }
  return ragAnalysis.value?.space_options || ragAnalysis.value?.space_breakdown?.map(i => ({ key: i.key, label: i.label })) || [];
});
const sourceAgentOptions = computed(() => {
  const byMode = new Set(modeSourceItems.value.map(item => item.source_agent).filter(Boolean) as string[]);
  if (byMode.size) {
    return Array.from(byMode).sort().map(label => ({ key: label, label }));
  }
  return ragAnalysis.value?.source_agent_options || ragAnalysis.value?.source_agent_breakdown?.map(i => ({ key: i.key, label: i.label })) || [];
});

function percent(value: number) { return `${(value * 100).toFixed(1)}%`; }
function formatLatency(value: number | null | undefined) { return `${Math.round(Number(value || 0))} ms`; }
function formatTimestamp(value: string | null | undefined) { if (!value) return "-"; return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
function formatScore(value: number | null | undefined) { if (value === null || value === undefined) return "-"; return value.toFixed(3); }
function stringifyValue(value: unknown) { if (value === null || value === undefined || value === "") return "-"; if (typeof value === "string") return value; try { return JSON.stringify(value, null, 2); } catch { return String(value); } }
function truncateText(value: string | null | undefined, length = 96) { const raw = (value || "").trim(); if (!raw) return "-"; return raw.length > length ? `${raw.slice(0, length)}...` : raw; }
function summarizeChunk(chunk: Record<string, unknown>) { return String(chunk.title || chunk.document_name || chunk.source_name || chunk.chunk_id || chunk.id || "未命名分片").trim() || "未命名分片"; }
function summarizeCitation(citation: Record<string, unknown>) { return String(citation.title || citation.document_name || citation.source_name || citation.chunk_id || citation.id || "引用").trim() || "引用"; }

function isTaskRagRecord(item: RagAnalysisItem) {
  const graph = String(item.source_graph || "").toLowerCase();
  const agent = String(item.source_agent || "").toLowerCase();
  const route = String(item.sub_route || "").toLowerCase();
  return graph === "inspection_task" || agent.includes("inspection") || ["task_execution", "inspection_execute", "task_create", "quality_qa"].includes(route);
}

function isChatRagRecord(item: RagAnalysisItem) {
  if (isTaskRagRecord(item)) return false;
  const graph = String(item.source_graph || "").toLowerCase();
  const agent = String(item.source_agent || "").toLowerCase();
  const route = String(item.sub_route || "").toLowerCase();
  return graph === "chat" || agent.includes("chat") || ["rag_qa", "general_chat"].includes(route);
}

function recordModeLabel(item: RagAnalysisItem) {
  return isTaskRagRecord(item) ? "任务 RAG" : "聊天 RAG";
}

function toFallbackTraceDetail(item: RagAnalysisItem): RagTraceDetailResponse {
  return {
    trace_id: item.trace_id || `fallback:${item.created_at}:${item.query || ""}`,
    query: item.query || null, rag_space_id: item.rag_space_id || null, rag_space_name: item.rag_space_name || null,
    source_agent: item.source_agent || null, source_graph: item.source_graph || null, sub_route: item.sub_route || null,
    top_k: 0, hit_count: item.hit_count, hit_rate: item.hit_rate, citation_coverage: item.citation_coverage,
    latency_ms: item.latency_ms, top_score: item.top_score ?? null, product_family: null,
    expectation_matched: item.expectation_matched ?? null, evidence_found: item.evidence_found,
    evidence_used: item.evidence_used, verdict_impacted: item.verdict_impacted,
    candidate_count: item.candidate_count || item.hit_count, rejected_count: item.rejected_count || 0,
    score_threshold: item.score_threshold ?? null,
    retrieval_config: {}, retrieved_chunks: [], used_citations: [], rule_hits: item.rule_hits,
    verdict: item.verdict || null, answer: null, result: null, top_sources: item.top_sources, created_at: item.created_at,
  };
}

const allRecentItems = computed(() => ragAnalysis.value?.recent_items || []);
const taskItems = computed(() => allRecentItems.value.filter(isTaskRagRecord));
const chatItems = computed(() => allRecentItems.value.filter(isChatRagRecord));
const modeSourceItems = computed(() => {
  if (recordMode.value === "task") return taskItems.value;
  if (recordMode.value === "chat") return chatItems.value;
  return allRecentItems.value;
});

const recordModeOptions = computed(() => [
  { key: "all" as const, label: "全部", count: allRecentItems.value.length },
  { key: "task" as const, label: "任务 RAG", count: taskItems.value.length },
  { key: "chat" as const, label: "聊天 RAG", count: chatItems.value.length },
]);

const filteredItems = computed(() => {
  const items = modeSourceItems.value;
  return items.filter(item => {
    if (selectedSpace.value && item.rag_space_id !== selectedSpace.value) return false;
    if (selectedSourceAgent.value && item.source_agent !== selectedSourceAgent.value) return false;
    return true;
  });
});

const stats = computed(() => {
  const items = filteredItems.value;
  const total = items.length;
  if (!total) {
    return { total_queries: 0, avg_hit_rate: 0, avg_citation_coverage: 0, empty_recall_count: 0, avg_latency_ms: 0 };
  }
  return {
    total_queries: total,
    avg_hit_rate: items.reduce((sum, item) => sum + Number(item.hit_rate || 0), 0) / total,
    avg_citation_coverage: items.reduce((sum, item) => sum + Number(item.citation_coverage || 0), 0) / total,
    empty_recall_count: items.filter(item => !item.evidence_found || Number(item.hit_count || 0) <= 0).length,
    avg_latency_ms: items.reduce((sum, item) => sum + Number(item.latency_ms || 0), 0) / total,
  };
});

function aggregateBreakdown(items: RagAnalysisItem[], keyFn: (i: RagAnalysisItem) => string | null | undefined, labelFn: (i: RagAnalysisItem) => string | null | undefined): RagAnalysisBreakdownItem[] {
  const map = new Map<string, { label: string; value: number; hit: number; coverage: number }>();
  for (const item of items) {
    const key = (keyFn(item) || "").trim();
    const label = (labelFn(item) || "").trim();
    if (!key || !label) continue;
    const cur = map.get(key) || { label, value: 0, hit: 0, coverage: 0 };
    cur.value++; cur.hit += item.hit_rate; cur.coverage += item.citation_coverage;
    map.set(key, cur);
  }
  return Array.from(map.entries()).map(([key, v]) => ({ key, label: v.label, value: v.value, avg_hit_rate: v.value > 0 ? v.hit / v.value : 0, avg_citation_coverage: v.value > 0 ? v.coverage / v.value : 0 })).sort((a, b) => b.value - a.value).slice(0, 8);
}

const filteredSpaceBreakdown = computed(() => aggregateBreakdown(filteredItems.value, i => i.rag_space_id || null, i => i.rag_space_name || i.rag_space_id || null));
const filteredSourceAgentBreakdown = computed(() => aggregateBreakdown(filteredItems.value, i => i.source_agent || null, i => i.source_agent || null));

const statCards = computed(() => [
  { label: "总检索数", value: stats.value.total_queries, hint: "当前范围" },
  { label: "平均命中率", value: percent(stats.value.avg_hit_rate), hint: "当前范围" },
  { label: "平均引用覆盖率", value: percent(stats.value.avg_citation_coverage), hint: "当前范围" },
  { label: "空召回次数", value: stats.value.empty_recall_count, hint: "当前范围" },
  { label: "平均延迟", value: formatLatency(stats.value.avg_latency_ms), hint: "当前范围" },
]);

const traceabilityCards = computed(() => {
  const total = Math.max(filteredItems.value.length, 1);
  const found = filteredItems.value.filter(i => i.evidence_found).length;
  const used = filteredItems.value.filter(i => i.evidence_used).length;
  const impacted = filteredItems.value.filter(i => i.verdict_impacted).length;
  return [
    { key: "found", title: "搜到正确证据", count: found, ratio: percent(found / total), tone: "blue" as const },
    { key: "used", title: "证据进入答案", count: used, ratio: percent(used / total), tone: "teal" as const },
    { key: "impacted", title: "影响最终判定", count: impacted, ratio: percent(impacted / total), tone: "purple" as const },
  ];
});

const hasData = computed(() => filteredItems.value.length > 0);
const recentEvidenceItems = computed(() => {
  const map = new Map<string, { rule_key: string; verdicts: Set<string>; source_count: number; query_count: number; sources: Set<string> }>();
  for (const item of filteredItems.value) {
    for (const rule of item.rule_hits || []) {
      if (!rule) continue;
      const aggregate = map.get(rule) || { rule_key: rule, verdicts: new Set<string>(), source_count: 0, query_count: 0, sources: new Set<string>() };
      aggregate.query_count += 1;
      if (item.verdict) aggregate.verdicts.add(item.verdict);
      for (const source of item.top_sources || []) {
        if (source) aggregate.sources.add(source);
      }
      aggregate.source_count = aggregate.sources.size;
      map.set(rule, aggregate);
    }
  }
  return Array.from(map.values())
    .map(item => ({
      rule_key: item.rule_key,
      verdicts: Array.from(item.verdicts),
      source_count: item.source_count,
      query_count: item.query_count,
      sources: Array.from(item.sources).slice(0, 5),
    }))
    .sort((a, b) => b.query_count - a.query_count)
    .slice(0, 8);
});

const activeDetail = computed<RagTraceDetailResponse | null>(() => {
  if (!selectedRecord.value) return null;
  if (selectedRecord.value.trace_id && ragTraceDetail.value && ragTraceDetail.value.trace_id === selectedRecord.value.trace_id) return ragTraceDetail.value;
  return toFallbackTraceDetail(selectedRecord.value);
});

const detailFlowCards = computed(() => {
  const d = activeDetail.value;
  if (!d) return [];
  return [
    { key: "found", title: "搜到证据", value: d.evidence_found ? "是" : "否", hint: d.evidence_found ? `${d.hit_count} 条命中, top_k=${d.top_k}` : "无有效命中" },
    { key: "used", title: "答案已使用", value: d.evidence_used ? "是" : "否", hint: d.evidence_used ? `${d.used_citations.length} 条引用` : "未引用检索证据" },
    { key: "impacted", title: "影响判定", value: d.verdict_impacted ? "是" : "否", hint: d.verdict_impacted ? `${d.rule_hits.length} 条规则` : "未影响 verdict" },
  ];
});

const detailResultText = computed(() => {
  const d = activeDetail.value;
  if (!d) return "-";
  return d.answer || (d.result !== null && d.result !== undefined ? stringifyValue(d.result) : "-");
});

function maxBreakdownValue(items: RagAnalysisBreakdownItem[]) { return Math.max(1, ...items.map(i => i.value)); }

async function openRecordDetail(row: RagAnalysisItem) {
  selectedRecord.value = row; detailVisible.value = true; detailError.value = "";
  if (!row.trace_id) return;
  try { await store.fetchRagTraceDetail(row.trace_id); }
  catch (e) { detailError.value = e instanceof Error ? e.message : "检索详情加载失败"; }
}

function buildTrendOption(items: typeof filteredItems.value) {
  const sorted = [...items].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const labels = sorted.map(i => new Date(i.created_at).toLocaleTimeString("zh-CN", { hour12: false }));
  return {
    color: ["#2563eb", "#0f766e"],
    tooltip: { trigger: "axis" as const },
    legend: { data: ["命中率", "引用覆盖率"], bottom: 0 },
    grid: { left: 44, right: 16, top: 24, bottom: 48 },
    xAxis: { type: "category" as const, data: labels, boundaryGap: false, axisLabel: { color: "#64748b" } },
    yAxis: { type: "value" as const, min: 0, max: 1, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%`, color: "#64748b" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.22)" } } },
    series: [
      { name: "命中率", type: "line" as const, smooth: true, areaStyle: { color: "rgba(37,99,235,.12)" }, data: sorted.map(i => i.hit_rate) },
      { name: "引用覆盖率", type: "line" as const, smooth: true, areaStyle: { color: "rgba(15,118,110,.12)" }, data: sorted.map(i => i.citation_coverage) },
    ],
  };
}
function buildLatencyOption(items: typeof filteredItems.value) {
  const sorted = [...items].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const labels = sorted.map(i => new Date(i.created_at).toLocaleTimeString("zh-CN", { hour12: false }));
  return {
    color: ["#f97316"],
    tooltip: { trigger: "axis" as const },
    grid: { left: 56, right: 16, top: 24, bottom: 36 },
    xAxis: { type: "category" as const, data: labels, axisLabel: { color: "#64748b" } },
    yAxis: { type: "value" as const, axisLabel: { formatter: "{value} ms", color: "#64748b" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.22)" } } },
    series: [{ type: "bar" as const, barWidth: 18, itemStyle: { borderRadius: [8, 8, 0, 0] }, data: sorted.map(i => i.latency_ms) }],
  };
}
const emptyChartOption = { title: { text: "暂无检索记录", left: "center", top: "middle", textStyle: { fontSize: 16, color: "#64748b" } }, xAxis: { show: false }, yAxis: { show: false }, series: [] };

function updateCharts() {
  const items = filteredItems.value;
  if (items.length === 0) {
    setTrendOption(emptyChartOption);
    setLatencyOption(emptyChartOption);
    return;
  }
  if (chartTab.value === "trend") {
    setTrendOption(buildTrendOption(items));
  } else {
    setLatencyOption(buildLatencyOption(items));
  }
}
function updateVisibleChart() {
  const items = filteredItems.value;
  if (items.length === 0) return;
  if (chartTab.value === "trend") {
    setTrendOption(buildTrendOption(items));
  } else {
    setLatencyOption(buildLatencyOption(items));
  }
}

async function refreshData(options?: { silent?: boolean }) {
  await store.fetchRagAnalysis(options);
  if (detailVisible.value && selectedRecord.value?.trace_id) {
    try { await store.fetchRagTraceDetail(selectedRecord.value.trace_id); detailError.value = ""; }
    catch (e) { detailError.value = e instanceof Error ? e.message : "检索详情加载失败"; }
  }
}

function startAutoRefresh() { if (refreshTimer !== null) return; refreshTimer = window.setInterval(() => { void refreshData({ silent: true }); }, AUTO_REFRESH_MS); }
function stopAutoRefresh() { if (refreshTimer !== null) { window.clearInterval(refreshTimer); refreshTimer = null; } }

watch(() => [filteredItems.value, selectedSpace.value, selectedSourceAgent.value], () => updateCharts(), { deep: true });
watch(recordMode, () => { selectedSpace.value = ""; selectedSourceAgent.value = ""; });
watch(chartTab, () => { setTimeout(() => updateVisibleChart(), 50); });
watch(detailVisible, (v) => { if (!v) detailError.value = ""; });

onMounted(async () => { await refreshData(); updateCharts(); startAutoRefresh(); });
onBeforeUnmount(() => { stopAutoRefresh(); });
</script>

<template>
  <div class="flex flex-col gap-4 p-6 min-h-full" v-loading="loading">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h3 class="text-lg font-bold text-zinc-900">RAG 分析</h3>
        <p class="text-sm text-zinc-500 mt-1">基于真实 RAG 检索日志，追踪命中率、引用覆盖率、延迟与证据有效性</p>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-xs text-zinc-400">10s 自动刷新</span>
        <div class="flex gap-2">
          <el-select v-model="selectedSpace" clearable placeholder="RAG 空间" size="small" style="width:180px">
            <el-option v-for="s in spaceOptions" :key="s.key" :label="s.label" :value="s.key" />
          </el-select>
          <el-select v-model="selectedSourceAgent" clearable placeholder="来源 Agent" size="small" style="width:160px">
            <el-option v-for="a in sourceAgentOptions" :key="a.key" :label="a.label" :value="a.key" />
          </el-select>
          <el-button v-if="selectedSpace || selectedSourceAgent" size="small" @click="selectedSpace=''; selectedSourceAgent=''">重置</el-button>
        </div>
      </div>
    </div>

    <div class="bg-white border border-zinc-200 rounded-xl p-3 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <button
          v-for="option in recordModeOptions"
          :key="option.key"
          class="px-3 py-1.5 text-sm font-semibold rounded-lg border transition-colors"
          :class="recordMode === option.key ? 'bg-zinc-900 text-white border-zinc-900' : 'bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400'"
          @click="recordMode = option.key"
        >
          {{ option.label }}
          <span class="ml-1 text-xs opacity-75">{{ option.count }}</span>
        </button>
      </div>
      <div class="text-xs text-zinc-400">
        当前展示 {{ filteredItems.length }} 条记录，统计、图表和证据链均按当前范围计算
      </div>
    </div>

    <!-- Stats row -->
    <div class="grid grid-cols-5 gap-3">
      <div v-for="card in statCards" :key="card.label" class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-xs text-zinc-500 mb-1">{{ card.label }}</div>
        <div class="text-xl font-bold text-zinc-900">{{ card.value }}</div>
        <div class="text-xs text-zinc-400 mt-0.5">{{ card.hint }}</div>
      </div>
    </div>

    <!-- Traceability row -->
    <div class="grid grid-cols-3 gap-3">
      <div v-for="card in traceabilityCards" :key="card.key" class="bg-white border border-zinc-200 rounded-xl p-4 flex items-center gap-4" :class="card.tone === 'blue' ? 'border-l-4 border-l-blue-500' : card.tone === 'teal' ? 'border-l-4 border-l-teal-500' : 'border-l-4 border-l-purple-500'">
        <div class="flex-1">
          <div class="text-sm font-semibold text-zinc-900">{{ card.title }}</div>
          <div class="text-xs text-zinc-400 mt-0.5">基于 {{ filteredItems.length || 0 }} 条记录</div>
        </div>
        <div class="text-right">
          <div class="text-2xl font-bold text-zinc-900">{{ card.count }}</div>
          <div class="text-sm font-semibold" :class="card.tone === 'blue' ? 'text-blue-600' : card.tone === 'teal' ? 'text-teal-600' : 'text-purple-600'">{{ card.ratio }}</div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <el-alert
      v-if="!hasData"
      type="info" :closable="false" show-icon
      title="暂无 RAG 检索记录"
      description="数据来自 rag_query_logs 表，在质量检测或 RAG 检索发生时自动记录。如果是首次使用或清空了数据，执行一次含知识库的质量检测即可填充。"
    />

    <!-- Chart tabs + Breakdowns -->
    <div v-if="hasData" class="grid grid-cols-[1fr_340px] gap-4">
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="flex items-center gap-3 mb-3">
          <button class="text-sm font-semibold px-3 py-1 rounded-full transition-colors" :class="chartTab === 'trend' ? 'bg-blue-100 text-blue-700' : 'text-zinc-500 hover:text-zinc-700'" @click="chartTab = 'trend'">检索趋势</button>
          <button class="text-sm font-semibold px-3 py-1 rounded-full transition-colors" :class="chartTab === 'latency' ? 'bg-amber-100 text-amber-700' : 'text-zinc-500 hover:text-zinc-700'" @click="chartTab = 'latency'">延迟分布</button>
        </div>
        <div v-show="chartTab === 'trend'" ref="trendChartRef" style="height:300px" />
        <div v-show="chartTab === 'latency'" ref="latencyChartRef" style="height:300px" />
      </div>

      <div class="flex flex-col gap-3">
        <div class="bg-white border border-zinc-200 rounded-xl p-4 flex-1">
          <div class="text-sm font-semibold text-zinc-900 mb-3">按 RAG 空间</div>
          <div v-if="filteredSpaceBreakdown.length" class="space-y-2">
            <div v-for="item in filteredSpaceBreakdown" :key="item.key" class="flex items-center gap-2 text-xs">
              <span class="w-20 truncate text-zinc-700 font-medium">{{ item.label }}</span>
              <div class="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                <div class="h-full rounded-full bg-blue-500" :style="{ width: `${(item.value / maxBreakdownValue(filteredSpaceBreakdown)) * 100}%` }" />
              </div>
              <span class="w-12 text-right text-zinc-400">{{ item.value }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无" :image-size="48" />
        </div>
        <div class="bg-white border border-zinc-200 rounded-xl p-4 flex-1">
          <div class="text-sm font-semibold text-zinc-900 mb-3">按来源 Agent</div>
          <div v-if="filteredSourceAgentBreakdown.length" class="space-y-2">
            <div v-for="item in filteredSourceAgentBreakdown" :key="item.key" class="flex items-center gap-2 text-xs">
              <span class="w-20 truncate text-zinc-700 font-medium">{{ item.label }}</span>
              <div class="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                <div class="h-full rounded-full bg-teal-500" :style="{ width: `${(item.value / maxBreakdownValue(filteredSourceAgentBreakdown)) * 100}%` }" />
              </div>
              <span class="w-12 text-right text-zinc-400">{{ item.value }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无" :image-size="48" />
        </div>
      </div>
    </div>

    <!-- Evidence impact -->
    <div v-if="recentEvidenceItems.length" class="bg-white border border-zinc-200 rounded-xl p-4">
      <div class="text-sm font-semibold text-zinc-900 mb-3">证据影响面</div>
      <div class="flex flex-wrap gap-2">
        <div v-for="item in recentEvidenceItems" :key="item.rule_key" class="flex items-center gap-2 bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-2 text-xs">
          <span class="font-semibold text-zinc-800">{{ item.rule_key }}</span>
          <span class="text-zinc-400">× {{ item.query_count }}</span>
          <span class="text-zinc-300">|</span>
          <span class="text-zinc-500">{{ item.verdicts.join(" / ") || "-" }}</span>
        </div>
      </div>
    </div>

    <!-- Recent items table -->
    <div class="bg-white border border-zinc-200 rounded-xl p-4">
      <div class="text-sm font-semibold text-zinc-900 mb-3">最近检索轨迹</div>
      <el-table :data="filteredItems" stripe max-height="420" empty-text="暂无检索记录" @row-click="openRecordDetail" style="cursor:pointer">
        <el-table-column label="Query" min-width="200">
          <template #default="{ row }">
            <template v-if="isTaskRagRecord(row)">
              <span class="text-xs text-zinc-400">任务ID：</span>
              <span class="text-sm text-zinc-800">{{ row.task_id || "-" }}</span>
            </template>
            <span v-else class="text-sm text-zinc-800 line-clamp-2">{{ row.query || "-" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="记录类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="isTaskRagRecord(row) ? 'warning' : 'primary'" effect="light">
              {{ recordModeLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务/会话" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ isTaskRagRecord(row) ? row.task_id : (row.session_id || row.task_id || "-") }}</template>
        </el-table-column>
        <el-table-column label="RAG 空间" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.rag_space_name || row.rag_space_id || "-" }}</template>
        </el-table-column>
        <el-table-column label="来源" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.source_agent || "-" }}</template>
        </el-table-column>
        <el-table-column label="子路由" width="130">
          <template #default="{ row }"><code class="text-xs bg-zinc-100 px-1 rounded">{{ row.sub_route || "-" }}</code></template>
        </el-table-column>
        <el-table-column label="命中/候选" width="110">
          <template #default="{ row }">{{ row.hit_count || 0 }} / {{ row.candidate_count || row.hit_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="Top Score" width="100">
          <template #default="{ row }">{{ formatScore(row.top_score) }}</template>
        </el-table-column>
        <el-table-column label="证据链" width="200">
          <template #default="{ row }">
            <div class="flex gap-1.5">
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="row.evidence_found ? 'bg-green-100 text-green-700' : 'bg-zinc-100 text-zinc-400'">命中</span>
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="row.evidence_used ? 'bg-green-100 text-green-700' : 'bg-zinc-100 text-zinc-400'">引用</span>
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="row.verdict_impacted ? 'bg-green-100 text-green-700' : 'bg-zinc-100 text-zinc-400'">判定</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="延迟" width="90">
          <template #default="{ row }">{{ formatLatency(row.latency_ms) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTimestamp(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Trace detail drawer -->
    <el-drawer v-model="detailVisible" size="640px" :destroy-on-close="false" title="检索轨迹详情">
      <div v-loading="ragTraceDetailLoading" class="space-y-5 pr-1">
        <template v-if="activeDetail">
          <div class="p-3 bg-zinc-50 rounded-lg border border-zinc-100">
            <div class="text-xs font-semibold text-zinc-500 mb-1">Query</div>
            <div class="text-sm text-zinc-800">{{ activeDetail.query || "-" }}</div>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div v-for="card in detailFlowCards" :key="card.key" class="p-3 rounded-lg" :class="card.value === '是' ? 'bg-green-50 border border-green-200' : 'bg-zinc-50 border border-zinc-200'">
              <div class="text-xs text-zinc-500">{{ card.title }}</div>
              <div class="text-lg font-bold" :class="card.value === '是' ? 'text-green-700' : 'text-zinc-500'">{{ card.value }}</div>
              <div class="text-xs text-zinc-400 mt-0.5">{{ card.hint }}</div>
            </div>
          </div>
          <el-alert v-if="detailError" type="warning" :closable="false" show-icon :title="detailError" />
          <div class="grid grid-cols-2 gap-2">
            <div v-for="item in [
              ['RAG 空间', activeDetail.rag_space_name || activeDetail.rag_space_id || '-'],
              ['来源 Agent', activeDetail.source_agent || '-'],
              ['子路由', activeDetail.sub_route || '-'],
              ['Verdict', activeDetail.verdict || '-'],
              ['命中数 / top_k', `${activeDetail.hit_count} / ${activeDetail.top_k || 0}`],
              ['候选 / 过滤', `${activeDetail.candidate_count || activeDetail.hit_count || 0} / ${activeDetail.rejected_count || 0}`],
              ['相关阈值', activeDetail.score_threshold ?? '-'],
              ['Top Score', formatScore(activeDetail.top_score)],
              ['命中率', percent(activeDetail.hit_rate)],
              ['引用覆盖率', percent(activeDetail.citation_coverage)],
              ['延迟', formatLatency(activeDetail.latency_ms)],
            ]" :key="item[0]" class="p-2.5 bg-zinc-50 rounded-lg border border-zinc-100">
              <div class="text-xs text-zinc-400">{{ item[0] }}</div>
              <div class="text-sm font-semibold text-zinc-800">{{ item[1] }}</div>
            </div>
          </div>
          <div v-if="activeDetail.retrieved_chunks.length">
            <div class="text-sm font-semibold text-zinc-800 mb-2">命中分片 ({{ activeDetail.retrieved_chunks.length }})</div>
            <div class="space-y-2">
              <div v-for="(chunk, i) in activeDetail.retrieved_chunks.slice(0, 10)" :key="i" class="p-3 bg-zinc-50 rounded-lg border border-zinc-100 text-xs">
                <div class="flex justify-between gap-2 mb-1"><strong>{{ summarizeChunk(chunk) }}</strong><span class="text-zinc-400">{{ formatScore(Number(chunk.score || chunk.similarity_score || NaN)) }}</span></div>
                <div class="text-zinc-600 line-clamp-3">{{ truncateText(String(chunk.content || chunk.text || chunk.snippet || "")) }}</div>
              </div>
            </div>
          </div>
          <div v-if="activeDetail.used_citations.length">
            <div class="text-sm font-semibold text-zinc-800 mb-2">已使用引用 ({{ activeDetail.used_citations.length }})</div>
            <div class="flex flex-wrap gap-1.5">
              <span v-for="(c, i) in activeDetail.used_citations" :key="i" class="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-1 rounded-full">{{ truncateText(summarizeCitation(c), 40) }}</span>
            </div>
          </div>
          <div>
            <div class="text-sm font-semibold text-zinc-800 mb-2">最终答案</div>
            <pre class="text-xs bg-zinc-50 border border-zinc-200 rounded-lg p-3 whitespace-pre-wrap break-words text-zinc-700 max-h-60 overflow-y-auto">{{ detailResultText }}</pre>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>
