<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { useECharts } from "@/composables/useECharts";
import type { RouteRuleDescriptor } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const loading = ref(false);

// ── Simulator state ──
const simInput = reactive({ query: "", has_image: false, has_structured_file: false, has_rag_space: false });
const simRunning = ref(false);

// ── Selected state ──
const selectedRule = ref<RouteRuleDescriptor | null>(null);
const selectedAgent = ref<string>("chat");

// ── Metrics ──
const metricCards = computed(() => {
  const m = store.routingMetrics;
  const c = store.routingCurrent;
  return [
    { label: "路由模式", value: c?.mode_label || "—", note: "规则优先，模型兜底", color: "#2563eb" },
    { label: "默认目标", value: c ? `${c.default_agent} / ${c.default_sub_route}` : "—", note: "未命中规则时兜底", color: "#0d9488" },
    { label: "内置规则", value: c ? `${c.rule_count} 条` : "—", note: "系统硬编码规则", color: "#7c3aed" },
    { label: "参与Agent", value: c ? `${c.active_agent_count} 个` : "—", note: "chat + inspection_task", color: "#d97706" },
    { label: "24h 路由", value: m ? `${m.total_24h} 次` : "—", note: m ? `规则命中 ${m.rule_hit_count} | 模型兜底 ${m.model_fallback_count}` : "", color: "#059669" },
    { label: "异常路由", value: m ? `${m.blocked_count} 次` : "—", note: m?.blocked_count ? "存在被阻止的路由" : "运行正常", color: (m?.blocked_count ?? 0) > 0 ? "#dc2626" : "#6b7280" },
  ];
});

// ── Agent route tree ──
const routeTree = computed(() => store.routingCurrent?.agents || []);

// ── Rule table ──
const rules = computed(() => store.routingCurrent?.rules || []);

// ── Events ──
const events = computed(() => store.routingEvents || []);

// ── ECharts decision flow graph ──
const { chartRef, setOption, resize } = useECharts();

function buildFlowGraph(ruleList: RouteRuleDescriptor[], highlightAgent: string) {
  const nodes: any[] = [];
  const edges: any[] = [];
  const layerX = [60, 200, 340, 480, 620, 760]; // 6 layers

  // Layer 1: User Request
  nodes.push({ id: "user_request", name: "用户请求", x: layerX[0], y: 260, symbolSize: 56, itemStyle: { color: "#6366f1" }, kind: "entry" });

  // Layer 2: Agent Manager
  nodes.push({ id: "agent_manager", name: "Agent Manager", x: layerX[1], y: 260, symbolSize: 62, itemStyle: { color: "#2563eb" }, kind: "manager" });
  edges.push({ source: "user_request", target: "agent_manager" });

  // Layer 3: Signals
  const signalNames = ["任务意图", "图片附件", "结构化文件", "质检语义", "RAG空间", "模糊输入"];
  signalNames.forEach((name, i) => {
    const id = `signal_${i}`;
    nodes.push({ id, name, x: layerX[2], y: 80 + i * 72, symbolSize: 36, itemStyle: { color: "#94a3b8" }, kind: "signal" });
    edges.push({ source: "agent_manager", target: id, lineStyle: { type: "dashed" as const, color: "#cbd5e1" } });
  });

  // Layer 4: Rules (show top rules)
  ruleList.slice(0, 7).forEach((rule, i) => {
    const id = `rule_${rule.priority}`;
    nodes.push({
      id, name: `P${rule.priority}: ${rule.name}`,
      x: layerX[3], y: 50 + i * 68,
      symbolSize: 34,
      itemStyle: { color: rule.target_agent === "inspection_task" ? "#d97706" : "#0d9488" },
      kind: "rule",
    });
    // Connect from relevant signal
    const signalIdx = Math.min(i, 5);
    edges.push({ source: `signal_${signalIdx}`, target: id, lineStyle: { color: "#94a3b8" } });
  });

  // Layer 5: Target Agents
  nodes.push({ id: "agent_chat", name: "Quality Chat", x: layerX[4], y: 180, symbolSize: 64, itemStyle: { color: highlightAgent === "chat" ? "#0d9488" : "#94a3b8" }, kind: "agent" });
  nodes.push({ id: "agent_inspection", name: "Inspection Task", x: layerX[4], y: 320, symbolSize: 64, itemStyle: { color: highlightAgent === "inspection_task" ? "#d97706" : "#94a3b8" }, kind: "agent" });
  // Connect rules to agents
  ruleList.forEach((rule) => {
    const targetId = rule.target_agent === "chat" ? "agent_chat" : "agent_inspection";
    edges.push({ source: `rule_${rule.priority}`, target: targetId, lineStyle: { color: rule.target_agent === "chat" ? "#0d9488" : "#d97706" } });
  });

  // Layer 6: Sub-routes
  const subRoutes = [
    { id: "sub_general_chat", name: "general_chat", parent: "agent_chat", y: 120 },
    { id: "sub_rag_qa", name: "rag_qa", parent: "agent_chat", y: 180 },
    { id: "sub_task_create", name: "task_create", parent: "agent_inspection", y: 240 },
    { id: "sub_inspection_execute", name: "inspection_execute", parent: "agent_inspection", y: 320 },
    { id: "sub_quality_qa", name: "quality_qa", parent: "agent_inspection", y: 400 },
  ];
  subRoutes.forEach((sr) => {
    nodes.push({ id: sr.id, name: sr.name, x: layerX[5], y: sr.y, symbolSize: 30, itemStyle: { color: "#cbd5e1" }, kind: "subroute" });
    edges.push({ source: sr.parent, target: sr.id, lineStyle: { color: "#cbd5e1" } });
  });

  return { nodes, edges };
}

function renderFlowGraph() {
  const ruleList = store.routingCurrent?.rules || [];
  const { nodes, edges } = buildFlowGraph(ruleList, selectedAgent.value);
  setOption({
    animationDuration: 400,
    tooltip: { trigger: "item", formatter: (p: any) => `${p.name}` },
    series: [{
      type: "graph", layout: "none", left: 10, top: 10, right: 10, bottom: 10, roam: true,
      label: { show: true, position: "right", fontSize: 11, color: "#334155" },
      edgeSymbol: ["none", "arrow"], edgeSymbolSize: [0, 8],
      data: nodes,
      links: edges,
    }],
  });
  nextTick(() => resize());
}

// ── Actions ──
async function loadAll() {
  loading.value = true;
  try {
    await Promise.all([
      store.fetchRoutingCurrent(),
      store.fetchRoutingMetrics(),
      store.fetchRoutingEvents(20),
    ]);
    renderFlowGraph();
  } finally { loading.value = false; }
}

async function runSimulate() {
  simRunning.value = true;
  try {
    await store.simulateRoute({
      query: simInput.query,
      has_image: simInput.has_image,
      has_structured_file: simInput.has_structured_file,
      has_rag_space: simInput.has_rag_space,
    });
  } finally { simRunning.value = false; }
}

function focusAgent(key: string) {
  selectedAgent.value = key;
  renderFlowGraph();
}

function focusRule(rule: RouteRuleDescriptor) {
  selectedRule.value = rule;
  selectedAgent.value = rule.target_agent;
  renderFlowGraph();
}

function eventAgentLabel(agent: string): string {
  return agent === "chat" ? "Quality Chat" : agent === "inspection_task" ? "Inspection Task" : agent;
}
function eventSourceLabel(s: string): string {
  const m: Record<string, string> = { rule: "规则命中", manual: "手动指定", model: "模型分类", fallback: "兜底" };
  return m[s] || s;
}
function eventStatusIcon(blocked: boolean, latency: number): string {
  if (blocked) return "⊘";
  if (latency > 500) return "⚠";
  return "✓";
}

onMounted(async () => { await loadAll(); });
watch(() => store.simulateResult, () => { if (store.simulateResult) renderFlowGraph(); });
</script>

<template>
  <div class="flex flex-col gap-4 p-6 min-h-full" v-loading="loading">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-zinc-900 m-0">路由策略</h1>
      <p class="text-sm text-zinc-500 mt-1">查看当前系统真实路由逻辑、模拟路由结果、观测最近路由事件。</p>
    </div>

    <!-- Metrics Cards -->
    <div class="grid grid-cols-6 gap-3">
      <div v-for="card in metricCards" :key="card.label" class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-xs font-semibold text-zinc-500 mb-2">{{ card.label }}</div>
        <div class="text-xl font-bold" :style="{ color: card.color }">{{ card.value }}</div>
        <div class="text-xs text-zinc-400 mt-1">{{ card.note }}</div>
      </div>
    </div>

    <!-- Main 3-column area -->
    <div class="grid grid-cols-[220px_1fr_280px] gap-4">
      <!-- LEFT: Agent Route Tree -->
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">Agent 路由树</div>
        <div v-for="agent in routeTree" :key="agent.key" class="mb-3">
          <button
            type="button"
            class="w-full text-left px-3 py-2 rounded-lg text-sm font-semibold transition-colors"
            :class="selectedAgent === agent.key ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-50'"
            @click="focusAgent(agent.key)"
          >
            {{ agent.label }}
          </button>
          <div class="ml-3 border-l-2 border-zinc-200 pl-3">
            <div v-for="sub in agent.sub_routes" :key="sub" class="text-xs text-zinc-500 py-1 px-2">{{ sub }}</div>
          </div>
        </div>
      </div>

      <!-- CENTER: Decision Flow Graph -->
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-2">路由决策流</div>
        <div class="text-xs text-zinc-400 mb-3">用户请求 → Agent Manager → 信号识别 → 规则匹配 → 目标Agent → 子路由</div>
        <div ref="chartRef" class="w-full" style="height: 500px" />
        <!-- Legend -->
        <div class="flex gap-4 mt-2 text-xs text-zinc-500">
          <span><span class="inline-block w-3 h-3 rounded-full mr-1" style="background:#6366f1" />请求入口</span>
          <span><span class="inline-block w-3 h-3 rounded-full mr-1" style="background:#0d9488" />聊天Agent</span>
          <span><span class="inline-block w-3 h-3 rounded-full mr-1" style="background:#d97706" />检测Agent</span>
          <span><span class="inline-block w-3 h-3 rounded-full mr-1" style="background:#94a3b8" />信号/子路由</span>
        </div>
      </div>

      <!-- RIGHT: Rule Detail Panel -->
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <template v-if="selectedRule">
          <div class="text-sm font-semibold text-zinc-900 mb-3">规则详情</div>
          <div class="space-y-3 text-sm">
            <div><span class="text-zinc-500">名称：</span><span class="font-semibold">{{ selectedRule.name }}</span></div>
            <div><span class="text-zinc-500">优先级：</span><span class="font-bold text-blue-600">P{{ selectedRule.priority }}</span></div>
            <div><span class="text-zinc-500">目标Agent：</span>{{ selectedRule.target_agent === "chat" ? "Quality Chat" : "Inspection Task Agent" }}</div>
            <div><span class="text-zinc-500">子路由：</span><code class="text-xs bg-zinc-100 px-1 rounded">{{ selectedRule.target_sub_route }}</code></div>
            <div><span class="text-zinc-500">触发条件：</span>{{ selectedRule.condition_summary }}</div>
            <div v-if="selectedRule.examples.length">
              <span class="text-zinc-500">示例：</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <el-tag v-for="ex in selectedRule.examples.slice(0, 3)" :key="ex" size="small" effect="plain">{{ ex }}</el-tag>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="text-sm text-zinc-400 text-center pt-12">点击左侧规则行<br/>查看详情</div>
        </template>
      </div>
    </div>

    <!-- Rule Table + Simulator -->
    <div class="grid grid-cols-[1fr_380px] gap-4">
      <!-- LEFT: Rule Table -->
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">当前内置规则表（只读）</div>
        <el-table :data="rules" size="small" stripe max-height="360" @row-click="focusRule" highlight-current-row>
          <el-table-column label="优先级" width="70">
            <template #default="{ row }"><span class="font-bold text-blue-600">P{{ row.priority }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="规则名称" min-width="140" />
          <el-table-column prop="condition_summary" label="触发条件" min-width="180" show-overflow-tooltip />
          <el-table-column label="目标Agent" width="140">
            <template #default="{ row }">
              <el-tag :type="row.target_agent === 'chat' ? 'success' : 'warning'" size="small">
                {{ row.target_agent === "chat" ? "Quality Chat" : "Inspection Task" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="子路由" width="140">
            <template #default="{ row }"><code class="text-xs">{{ row.target_sub_route }}</code></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- RIGHT: Simulator -->
      <div class="bg-white border border-zinc-200 rounded-xl p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">路由模拟器</div>
        <div class="space-y-3">
          <el-input v-model="simInput.query" placeholder="输入文本，如：帮我检测图片是否合格" size="small" />
          <div class="flex items-center gap-3 text-sm">
            <el-checkbox v-model="simInput.has_image" size="small">含图片</el-checkbox>
            <el-checkbox v-model="simInput.has_structured_file" size="small">含文件</el-checkbox>
            <el-checkbox v-model="simInput.has_rag_space" size="small">RAG空间</el-checkbox>
          </div>
          <el-button type="primary" size="small" @click="runSimulate" :loading="simRunning" class="w-full">模拟路由</el-button>
        </div>
        <!-- Sim result -->
        <div v-if="store.simulateResult" class="mt-4 p-3 bg-zinc-50 rounded-lg text-sm space-y-1">
          <div><span class="text-zinc-500">命中规则：</span><span class="font-semibold">{{ store.simulateResult.matched_rule_name }}</span></div>
          <div><span class="text-zinc-500">目标Agent：</span><span class="font-bold">{{ store.simulateResult.selected_agent === "chat" ? "Quality Chat" : "Inspection Task Agent" }}</span></div>
          <div><span class="text-zinc-500">子路由：</span><code class="text-xs bg-white px-1 rounded">{{ store.simulateResult.selected_sub_route }}</code></div>
          <div><span class="text-zinc-500">原因：</span>{{ store.simulateResult.reason }}</div>
          <div v-if="store.simulateResult.is_fallback" class="text-amber-600 text-xs mt-1">⚠ 触发了模型分类兜底</div>
          <!-- Signal badges -->
          <div class="flex flex-wrap gap-1 mt-2">
            <el-tag v-for="(val, key) in store.simulateResult.signals" :key="key" :type="val ? 'success' : 'info'" size="small" effect="plain">
              {{ key }}: {{ val ? "✓" : "✗" }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Events -->
    <div class="bg-white border border-zinc-200 rounded-xl p-4">
      <div class="text-sm font-semibold text-zinc-900 mb-3">最近路由事件</div>
      <el-table :data="events" size="small" stripe max-height="300">
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : "-" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="60">
          <template #default="{ row }">
            <span :class="row.blocked ? 'text-red-500' : row.latency_ms > 500 ? 'text-amber-500' : 'text-green-500'">
              {{ eventStatusIcon(row.blocked, row.latency_ms) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="目标Agent" width="140">
          <template #default="{ row }">{{ eventAgentLabel(row.selected_agent) }}</template>
        </el-table-column>
        <el-table-column label="子路由" width="140">
          <template #default="{ row }"><code class="text-xs">{{ row.sub_route || "-" }}</code></template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">
            <el-tag :type="row.route_source === 'rule' ? 'success' : row.route_source === 'manual' ? 'warning' : 'info'" size="small" effect="plain">
              {{ eventSourceLabel(row.route_source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
        <el-table-column label="延迟" width="70">
          <template #default="{ row }">{{ row.latency_ms }}ms</template>
        </el-table-column>
        <el-table-column label="信息" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.request_summary || row.intent_name || "-" }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
/* Route strategy viewer — restrained zinc neutral design */

/* Loading state overlay */
:deep(.el-loading-mask) {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(2px);
}

/* Table row click affordance */
:deep(.el-table__row) {
  cursor: pointer;
}

/* Metric card hover subtle lift */
.grid > .bg-white {
  transition: box-shadow 160ms ease, border-color 160ms ease;
}
.grid > .bg-white:hover {
  border-color: #cbd5e1;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

/* Simulator result transition */
.sim-result-enter-active {
  transition: opacity 200ms ease;
}
.sim-result-enter-from {
  opacity: 0;
}

/* Responsive: stack on narrow screens */
@media (max-width: 1400px) {
  .grid.grid-cols-6 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .grid.grid-cols-\[220px_1fr_280px\] {
    grid-template-columns: 1fr;
  }
  .grid.grid-cols-\[1fr_380px\] {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .grid.grid-cols-6 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
