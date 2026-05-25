<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, reactive, ref, watch } from "vue";
import { VueFlow, useVueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import type { Edge, Node, NodeTypesObject } from "@vue-flow/core";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import type { RouteRuleDescriptor } from "@/types/agent-ops.types";
import PipelineNode from "@/components/routing/PipelineNode.vue";

import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";

const store = useAgentOpsStore();
const { fitView } = useVueFlow();

const loading = ref(false);
const simRunning = ref(false);
const selectedRule = ref<RouteRuleDescriptor | null>(null);
const selectedAgent = ref("chat");
const eventsDrawerVisible = ref(false);
const flowNodes = ref<Node[]>([]);
const flowEdges = ref<Edge[]>([]);

const simInput = reactive({
  query: "",
  has_image: false,
  has_structured_file: false,
  has_rag_space: false,
});

const nodeTypes = {
  pipeline: markRaw(PipelineNode),
} as unknown as NodeTypesObject;

const routeTree = computed(() => store.routingCurrent?.agents || []);
const rules = computed(() => store.routingCurrent?.rules || []);
const managerIntents = computed(() => store.routingCurrent?.manager_intents || []);
const events = computed(() => store.routingEvents || []);

const matchedRule = computed(() => {
  const result = store.simulateResult;
  if (!result) return selectedRule.value;
  return rules.value.find((item) => item.priority === result.matched_priority) || selectedRule.value;
});

const activeAgent = computed(() => store.simulateResult?.selected_agent || selectedAgent.value);
const activeSubRoute = computed(() => store.simulateResult?.selected_sub_route || matchedRule.value?.target_sub_route || "");

const metricCards = computed(() => {
  const m = store.routingMetrics;
  const c = store.routingCurrent;
  return [
    { label: "路由模式", value: c?.mode_label || "-", note: "ManagerPolicy -> AgentRoutePolicy", color: "#2563eb" },
    { label: "默认目标", value: c ? `${c.default_agent} / ${c.default_sub_route}` : "-", note: "未命中规则时兜底", color: "#0d9488" },
    { label: "管理意图", value: c ? `${c.manager_intents?.length || 0} 条` : "-", note: "管理 Agent 意图理解", color: "#6366f1" },
    { label: "路由规则", value: c ? `${c.rule_count} 条` : "-", note: "策略规则动态读取", color: "#7c3aed" },
    { label: "子 Agent", value: c ? `${c.active_agent_count} 个` : "-", note: "当前可路由目标", color: "#d97706" },
    { label: "24h 路由", value: m ? `${m.total_24h} 次` : "-", note: m ? `规则 ${m.rule_hit_count} | 模型兜底 ${m.model_fallback_count}` : "", color: "#059669" },
  ];
});

function shortText(value: string, fallback: string, max = 48) {
  const text = value.trim();
  if (!text) return fallback;
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function edgeStyle(active: boolean, color = "#94a3b8") {
  return {
    stroke: active ? color : "#cbd5e1",
    strokeWidth: active ? 3 : 1.4,
  };
}

function makeEdge(id: string, source: string, target: string, active: boolean, color?: string): Edge {
  return {
    id,
    source,
    target,
    type: "smoothstep",
    animated: active,
    style: edgeStyle(active, color),
  };
}

function inputItems() {
  const items: string[] = [];
  if (simInput.has_image) items.push("image");
  if (simInput.has_structured_file) items.push("structured_file");
  if (simInput.has_rag_space) items.push("rag_space");
  return items.length ? items : ["message"];
}

function policyItems(rule: RouteRuleDescriptor | null) {
  if (!rule) return [`${rules.value.length} rules`];
  return [`P${rule.priority}`, rule.target_agent, rule.target_sub_route];
}

function buildFlowElements() {
  const current = store.routingCurrent;
  if (!current) {
    flowNodes.value = [];
    flowEdges.value = [];
    return;
  }

  const hasResult = Boolean(store.simulateResult);
  const rule = matchedRule.value;
  const activeAgentKey = activeAgent.value;
  const activeSub = activeSubRoute.value;
  const selectedIntent = managerIntents.value.find((item) => item.target_agent === activeAgentKey);

  const nodes: Node[] = [
    {
      id: "user-input",
      type: "pipeline",
      position: { x: 20, y: 170 },
      data: {
        kicker: "用户输入",
        title: shortText(simInput.query, "待模拟请求"),
        subtitle: hasResult ? "模拟结果已更新" : "输入或选择规则后动态更新",
        items: inputItems(),
        tone: "blue",
        active: true,
      },
    },
    {
      id: "manager-agent",
      type: "pipeline",
      position: { x: 300, y: 170 },
      data: {
        kicker: "管理 Agent",
        title: "ManagerPolicy",
        subtitle: selectedIntent ? selectedIntent.intent : "理解请求意图并约束可用能力",
        items: selectedIntent ? selectedIntent.needs.slice(0, 3) : [`${managerIntents.value.length} intents`],
        tone: "violet",
        active: true,
      },
    },
    {
      id: "route-policy",
      type: "pipeline",
      position: { x: 580, y: 170 },
      data: {
        kicker: "路由策略",
        title: rule ? rule.name : "AgentRoutePolicy",
        subtitle: rule ? rule.condition_summary : "根据实时信号匹配优先级规则",
        items: policyItems(rule),
        tone: "amber",
        active: true,
      },
    },
  ];

  const edges: Edge[] = [
    makeEdge("user-manager", "user-input", "manager-agent", true, "#2563eb"),
    makeEdge("manager-policy", "manager-agent", "route-policy", true, "#7c3aed"),
  ];

  const agentStartY = 80;
  const agentGap = 210;
  current.agents.forEach((agent, index) => {
    const isAgentActive = agent.key === activeAgentKey;
    const agentNodeId = `agent-${agent.key}`;
    const y = agentStartY + index * agentGap;

    nodes.push({
      id: agentNodeId,
      type: "pipeline",
      position: { x: 860, y },
      data: {
        kicker: "子 Agent",
        title: agent.label,
        subtitle: agent.key,
        items: agent.sub_routes,
        tone: agent.key === "chat" ? "teal" : "amber",
        active: isAgentActive,
        dim: hasResult && !isAgentActive,
      },
    });
    edges.push(makeEdge(`policy-${agent.key}`, "route-policy", agentNodeId, isAgentActive, agent.key === "chat" ? "#0d9488" : "#d97706"));

    agent.sub_routes.forEach((subRoute, subIndex) => {
      const isSubActive = isAgentActive && subRoute === activeSub;
      const subNodeId = `subroute-${agent.key}-${subRoute}`;
      nodes.push({
        id: subNodeId,
        type: "pipeline",
        position: { x: 1140, y: y - 48 + subIndex * 74 },
        data: {
          kicker: "子路由策略",
          title: subRoute,
          subtitle: isSubActive ? "当前命中" : "可选子路由",
          items: rules.value
            .filter((item) => item.target_agent === agent.key && item.target_sub_route === subRoute)
            .map((item) => `P${item.priority}`)
            .slice(0, 4),
          tone: isSubActive ? "blue" : "slate",
          active: isSubActive,
          dim: hasResult && !isSubActive,
        },
      });
      edges.push(makeEdge(`${agent.key}-${subRoute}`, agentNodeId, subNodeId, isSubActive, "#2563eb"));
    });
  });

  flowNodes.value = nodes;
  flowEdges.value = edges;
  void nextTick(() => fitView({ padding: 0.12, duration: 250 }));
}

async function loadAll() {
  loading.value = true;
  try {
    await store.fetchRoutingCurrent();
    buildFlowElements();

    const optionalResults = await Promise.allSettled([
      store.fetchRoutingMetrics(),
      store.fetchRoutingEvents(20),
    ]);
    const rejected = optionalResults.filter((item) => item.status === "rejected");
    if (rejected.length) {
      console.warn("Optional routing stats failed to load", rejected);
    }
  } finally {
    loading.value = false;
  }
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
    const result = store.simulateResult;
    if (result) {
      selectedAgent.value = result.selected_agent;
      selectedRule.value = rules.value.find((item) => item.priority === result.matched_priority) || null;
    }
  } finally {
    simRunning.value = false;
  }
}

function focusAgent(key: string) {
  selectedAgent.value = key;
  if (matchedRule.value?.target_agent !== key) {
    selectedRule.value = rules.value.find((item) => item.target_agent === key) || null;
  }
}

function focusRule(rule: RouteRuleDescriptor) {
  selectedRule.value = rule;
  selectedAgent.value = rule.target_agent;
}

function onNodeClick({ node }: { node: Node }) {
  if (node.id.startsWith("agent-")) {
    focusAgent(node.id.replace("agent-", ""));
    return;
  }
  if (node.id.startsWith("subroute-")) {
    const [, agentKey, ...subParts] = node.id.split("-");
    const subRoute = subParts.join("-");
    const rule = rules.value.find((item) => item.target_agent === agentKey && item.target_sub_route === subRoute);
    if (rule) focusRule(rule);
  }
}

function eventAgentLabel(agent: string): string {
  return agent === "chat" ? "Quality Chat" : agent === "inspection_task" ? "Inspection Task" : agent;
}

function eventSourceLabel(source: string): string {
  const labels: Record<string, string> = { rule: "规则命中", model: "模型分类", fallback: "兜底", manager: "管理决策" };
  return labels[source] || source;
}

watch(
  [() => store.routingCurrent, () => store.simulateResult, () => selectedAgent.value, () => selectedRule.value, () => simInput.has_image, () => simInput.has_structured_file, () => simInput.has_rag_space],
  buildFlowElements,
  { deep: true },
);

watch(() => simInput.query, buildFlowElements);

onMounted(() => loadAll());
</script>

<template>
  <div class="flex flex-col gap-4 p-6 min-h-full" v-loading="loading">
    <div>
      <h3 class="text-lg font-bold text-zinc-900 mb-3">路由策略</h3>
      <div class="grid grid-cols-6 gap-3">
        <div v-for="card in metricCards" :key="card.label" class="bg-white border border-zinc-200 rounded-lg p-4">
          <div class="text-xs font-semibold text-zinc-500 mb-2">{{ card.label }}</div>
          <div class="text-xl font-bold" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="text-xs text-zinc-400 mt-1">{{ card.note }}</div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-[220px_1fr_300px] gap-4">
      <div class="bg-white border border-zinc-200 rounded-lg p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">子 Agent</div>
        <div v-for="agent in routeTree" :key="agent.key" class="mb-3">
          <button
            type="button"
            class="w-full text-left text-sm font-semibold px-2 py-1 rounded transition-colors"
            :class="activeAgent === agent.key ? 'bg-blue-100 text-blue-700' : 'text-zinc-700 hover:bg-zinc-50'"
            @click="focusAgent(agent.key)"
          >
            {{ agent.label }}
          </button>
          <div class="ml-3 border-l-2 border-zinc-200 pl-3">
            <div
              v-for="sub in agent.sub_routes"
              :key="sub"
              class="text-xs py-1 px-2 font-mono"
              :class="activeAgent === agent.key && activeSubRoute === sub ? 'text-blue-600 font-semibold' : 'text-zinc-500'"
            >
              {{ sub }}
            </div>
          </div>
        </div>
      </div>

      <div class="bg-white border border-zinc-200 rounded-lg p-4 overflow-hidden">
        <div class="flex items-center justify-between mb-3">
          <div>
            <div class="text-sm font-semibold text-zinc-900">路由决策图</div>
            <div class="text-xs text-zinc-400 mt-1">用户输入 -> 管理 Agent -> 路由策略 -> 子 Agent -> 子路由策略</div>
          </div>
          <el-button size="small" @click="buildFlowElements">刷新</el-button>
        </div>
        <div class="routing-flow">
          <VueFlow
            v-model:nodes="flowNodes"
            v-model:edges="flowEdges"
            :node-types="nodeTypes"
            :min-zoom="0.45"
            :max-zoom="1.6"
            :nodes-draggable="true"
            fit-view-on-init
            @node-click="onNodeClick"
          >
            <Background :gap="20" :size="1" />
            <Controls position="bottom-right" />
          </VueFlow>
        </div>
        <div class="flex gap-4 mt-3 text-xs text-zinc-500">
          <span><span class="inline-block w-3 h-3 rounded-sm mr-1 bg-blue-600" /> 当前链路</span>
          <span><span class="inline-block w-3 h-3 rounded-sm mr-1 bg-zinc-300" /> 可选链路</span>
          <span>模拟结果会自动高亮命中的 Agent 与子路由</span>
        </div>
      </div>

      <div class="flex flex-col gap-4">
        <div class="bg-white border border-zinc-200 rounded-lg p-4">
          <template v-if="matchedRule">
            <div class="text-sm font-semibold text-zinc-900 mb-3">当前规则</div>
            <div class="space-y-3 text-sm">
              <div><span class="text-zinc-500">名称：</span><span class="font-semibold">{{ matchedRule.name }}</span></div>
              <div><span class="text-zinc-500">优先级：</span><span class="font-bold text-blue-600">P{{ matchedRule.priority }}</span></div>
              <div><span class="text-zinc-500">目标：</span>{{ matchedRule.target_agent }} / <code class="text-xs bg-zinc-100 px-1 rounded">{{ matchedRule.target_sub_route }}</code></div>
              <div><span class="text-zinc-500">条件：</span>{{ matchedRule.condition_summary }}</div>
            </div>
          </template>
          <template v-else>
            <div class="text-sm text-zinc-400 text-center py-12">选择规则或运行模拟</div>
          </template>
        </div>

        <div
          class="bg-white border border-zinc-200 rounded-lg p-4 flex-1 min-h-0 cursor-pointer hover:border-blue-300 hover:shadow-sm transition-all"
          @click="eventsDrawerVisible = true"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="text-sm font-semibold text-zinc-900">最近路由事件</div>
            <div class="text-xs text-zinc-400">查看全部</div>
          </div>
          <div class="overflow-y-auto" style="max-height: 330px">
            <div v-if="events.length === 0" class="text-xs text-zinc-400 text-center py-8">暂无路由事件</div>
            <div v-for="evt in events.slice(0, 8)" :key="evt.id" class="flex items-center gap-2 py-1.5 border-b border-zinc-50 last:border-0 text-xs">
              <span class="text-zinc-400 w-14 shrink-0">{{ evt.created_at ? new Date(evt.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "-" }}</span>
              <span class="shrink-0 w-16 text-center px-1.5 py-0.5 rounded font-medium" :class="evt.route_source === 'rule' ? 'bg-blue-50 text-blue-600' : 'bg-amber-50 text-amber-600'">{{ eventSourceLabel(evt.route_source) }}</span>
              <span class="truncate flex-1 text-zinc-600 min-w-0">{{ evt.request_summary || evt.intent_name || evt.reason || "-" }}</span>
            </div>
          </div>
        </div>

        <el-drawer v-model="eventsDrawerVisible" title="路由事件日志" direction="rtl" size="720px">
          <el-table :data="events" size="small" max-height="calc(100vh - 160px)">
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "-" }}</template>
            </el-table-column>
            <el-table-column label="来源" width="90">
              <template #default="{ row }">{{ eventSourceLabel(row.route_source) }}</template>
            </el-table-column>
            <el-table-column label="目标 Agent" width="140">
              <template #default="{ row }">{{ eventAgentLabel(row.selected_agent) }}</template>
            </el-table-column>
            <el-table-column label="子路由" width="150">
              <template #default="{ row }"><code class="text-xs bg-zinc-100 px-1 rounded">{{ row.sub_route || "-" }}</code></template>
            </el-table-column>
            <el-table-column label="原因" min-width="180">
              <template #default="{ row }"><span class="text-xs text-zinc-500">{{ row.reason || row.intent_name || "-" }}</span></template>
            </el-table-column>
            <el-table-column label="延迟" width="80" align="right">
              <template #default="{ row }">{{ row.latency_ms }}ms</template>
            </el-table-column>
          </el-table>
        </el-drawer>
      </div>
    </div>

    <div class="grid grid-cols-[1fr_380px] gap-4">
      <div class="bg-white border border-zinc-200 rounded-lg p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">路由规则表</div>
        <el-table :data="rules" size="small" max-height="360" @row-click="focusRule" highlight-current-row>
          <el-table-column label="优先级" width="80">
            <template #default="{ row }"><span class="font-bold text-blue-600">P{{ row.priority }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="规则名称" min-width="160" />
          <el-table-column prop="condition_summary" label="触发条件" min-width="220">
            <template #default="{ row }"><span class="text-xs text-zinc-500">{{ row.condition_summary }}</span></template>
          </el-table-column>
          <el-table-column label="目标 Agent" width="140">
            <template #default="{ row }">{{ row.target_agent === "chat" ? "Quality Chat" : "Inspection Task" }}</template>
          </el-table-column>
          <el-table-column label="子路由" width="150">
            <template #default="{ row }"><code class="text-xs">{{ row.target_sub_route }}</code></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="bg-white border border-zinc-200 rounded-lg p-4">
        <div class="text-sm font-semibold text-zinc-900 mb-3">路由模拟器</div>
        <div class="space-y-3">
          <el-input v-model="simInput.query" placeholder="输入用户消息..." size="small" />
          <div class="flex items-center gap-3 text-sm">
            <label class="flex items-center gap-1"><input type="checkbox" v-model="simInput.has_image" /> 图片</label>
            <label class="flex items-center gap-1"><input type="checkbox" v-model="simInput.has_structured_file" /> 结构化文件</label>
            <label class="flex items-center gap-1"><input type="checkbox" v-model="simInput.has_rag_space" /> RAG 空间</label>
          </div>
          <el-button type="primary" size="small" @click="runSimulate" :loading="simRunning">模拟路由</el-button>
        </div>
        <div v-if="store.simulateResult" class="mt-4 p-3 bg-zinc-50 rounded-lg text-sm space-y-1">
          <div><span class="text-zinc-500">命中规则：</span><span class="font-semibold">{{ store.simulateResult.matched_rule_name }}</span></div>
          <div><span class="text-zinc-500">目标：</span><span class="font-bold">{{ eventAgentLabel(store.simulateResult.selected_agent) }}</span></div>
          <div><span class="text-zinc-500">子路由：</span><code class="text-xs bg-white px-1 rounded">{{ store.simulateResult.selected_sub_route }}</code></div>
          <div><span class="text-zinc-500">原因：</span>{{ store.simulateResult.reason }}</div>
          <div class="flex flex-wrap gap-1 mt-2">
            <span
              v-for="(val, key) in store.simulateResult.signals"
              :key="key"
              class="text-xs px-2 py-0.5 rounded"
              :class="val ? 'bg-green-100 text-green-700' : 'bg-zinc-100 text-zinc-400'"
            >
              {{ key }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.routing-flow {
  height: 560px;
}
@media (max-width: 1400px) {
  .grid.grid-cols-6 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .grid.grid-cols-\[220px_1fr_300px\],
  .grid.grid-cols-\[1fr_380px\] {
    grid-template-columns: 1fr;
  }
}
</style>
