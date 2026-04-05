<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { RefreshRight } from "@element-plus/icons-vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { useECharts } from "@/composables/useECharts";
import { buildFallbackRoutingStrategy } from "@/views/ops/intent-route-fallback";
import type {
  RoutingDecisionCard,
  RoutingPriorityRule,
  RoutingSubgraphDescriptor,
  RoutingStrategyOverview,
  TopologyEdge,
  TopologyNode,
} from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const loading = computed(() => store.loading);
const fallbackStrategy = ref<RoutingStrategyOverview | null>(null);
const strategyLoadMessage = ref("");
const strategy = computed(() => store.routingStrategy ?? fallbackStrategy.value);
const selectedSubgraphKey = ref("legacy_quality");
const activeRuleKey = ref("task-intent");

const { chartRef: rootChartRef, setOption: setRootOption, resize: resizeRootChart } = useECharts();
const {
  chartRef: subgraphChartRef,
  setOption: setSubgraphOption,
  resize: resizeSubgraphChart,
} = useECharts();

const selectedSubgraph = computed<RoutingSubgraphDescriptor | null>(() => {
  return strategy.value?.subgraphs.find((item) => item.subgraph_key === selectedSubgraphKey.value) ?? null;
});

const activeRule = computed<RoutingDecisionCard | null>(() => {
  return strategy.value?.decision_cards.find((item) => item.key === activeRuleKey.value) ?? null;
});

const signalLookup = computed(() => {
  const map = new Map<string, { label: string; description: string }>();
  strategy.value?.signals.forEach((item) => {
    map.set(item.key, { label: item.label, description: item.description });
  });
  return map;
});

const modeLabel = computed(() => {
  const labels: Record<string, string> = {
    legacy_only: "Legacy Only",
    canary_non_pdf: "Canary Non PDF",
    router_enabled: "Router Enabled",
  };
  return labels[strategy.value?.route_mode ?? "router_enabled"] ?? "Router Enabled";
});

watch(
  strategy,
  (value) => {
    if (!value) return;
    if (!value.subgraphs.some((item) => item.subgraph_key === selectedSubgraphKey.value)) {
      selectedSubgraphKey.value = value.default_target;
    }
    if (!value.decision_cards.some((item) => item.key === activeRuleKey.value)) {
      activeRuleKey.value = value.decision_cards[0]?.key ?? "";
    }
    renderRootGraph();
  },
  { deep: true },
);

watch(
  selectedSubgraph,
  () => {
    renderSubgraph();
  },
  { deep: true },
);

onMounted(async () => {
  await refreshStrategy();
});

function subgraphTone(subgraphKey: string) {
  return subgraphKey === "legacy_quality" ? "success" : "warning";
}

function subgraphColor(subgraphKey: string) {
  return subgraphKey === "legacy_quality" ? "#0f766e" : "#b45309";
}

function nodeColor(kind: string, id: string, activeIds: string[]) {
  if (activeIds.includes(id)) return "#2563eb";
  if (kind === "root") return "#1d4ed8";
  if (kind === "subgraph") return id === "legacy_quality" ? "#0f766e" : "#b45309";
  if (kind === "legacy") return "#0f766e";
  if (kind === "native") return "#b45309";
  return "#475569";
}

function buildRootGraphOption(nodes: TopologyNode[], edges: TopologyEdge[]) {
  const positions: Record<string, { x: number; y: number }> = {
    request_intake: { x: 40, y: 130 },
    route_signal_builder: { x: 230, y: 130 },
    route_policy: { x: 420, y: 130 },
    subgraph_runner: { x: 610, y: 130 },
    contract_finalize: { x: 800, y: 130 },
    legacy_quality: { x: 800, y: 40 },
    llm_native_quality: { x: 800, y: 220 },
  };
  const activeIds = [
    "route_policy",
    "subgraph_runner",
    selectedSubgraphKey.value,
    activeRule.value?.target_subgraph ?? "",
  ].filter(Boolean);
  return {
    animationDuration: 300,
    tooltip: { trigger: "item" },
    series: [
      {
        type: "graph",
        layout: "none",
        left: 24,
        top: 24,
        right: 24,
        bottom: 24,
        roam: false,
        label: {
          show: true,
          position: "bottom",
          color: "#0f172a",
          fontWeight: 600,
        },
        lineStyle: {
          color: "#94a3b8",
          width: 2,
          curveness: 0.08,
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 10],
        data: nodes.map((node) => ({
          id: node.id,
          name: node.label,
          x: positions[node.id]?.x ?? 0,
          y: positions[node.id]?.y ?? 0,
          symbolSize: node.kind === "subgraph" ? 74 : 62,
          itemStyle: {
            color: nodeColor(node.kind, node.id, activeIds),
            shadowBlur: activeIds.includes(node.id) ? 18 : 0,
            shadowColor: activeIds.includes(node.id) ? "rgba(37, 99, 235, 0.3)" : "transparent",
          },
        })),
        links: edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          lineStyle: {
            color:
              activeIds.includes(edge.target) || activeIds.includes(edge.source)
                ? "#2563eb"
                : "#94a3b8",
            width:
              activeIds.includes(edge.target) || activeIds.includes(edge.source)
                ? 3
                : 2,
          },
        })),
      },
    ],
  };
}

function buildSubgraphOption(subgraph: RoutingSubgraphDescriptor) {
  const positions = new Map<string, { x: number; y: number }>();
  subgraph.nodes.forEach((node, index) => {
    positions.set(node.id, {
      x: 50 + index * 140,
      y: 130,
    });
  });
  const entryNodeIds = [subgraph.subgraph_key, subgraph.entry_node];
  return {
    animationDuration: 300,
    tooltip: { trigger: "item" },
    series: [
      {
        type: "graph",
        layout: "none",
        left: 24,
        top: 24,
        right: 24,
        bottom: 24,
        roam: true,
        draggable: false,
        label: {
          show: true,
          position: "bottom",
          color: "#0f172a",
          fontSize: 12,
          fontWeight: 600,
        },
        lineStyle: {
          color: "#cbd5e1",
          width: 2,
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 9],
        data: subgraph.nodes.map((node) => ({
          id: node.id,
          name: node.label,
          x: positions.get(node.id)?.x ?? 0,
          y: positions.get(node.id)?.y ?? 0,
          symbolSize: entryNodeIds.includes(node.id) ? 58 : 48,
          itemStyle: {
            color: nodeColor(node.kind, node.id, entryNodeIds),
            shadowBlur: entryNodeIds.includes(node.id) ? 16 : 0,
            shadowColor: entryNodeIds.includes(node.id)
              ? "rgba(37, 99, 235, 0.25)"
              : "transparent",
          },
        })),
        links: subgraph.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          lineStyle: {
            color:
              entryNodeIds.includes(edge.source) || entryNodeIds.includes(edge.target)
                ? "#2563eb"
                : "#cbd5e1",
            width:
              entryNodeIds.includes(edge.source) || entryNodeIds.includes(edge.target)
                ? 3
                : 2,
          },
        })),
      },
    ],
  };
}

function renderRootGraph() {
  if (!strategy.value?.root_graph) return;
  setRootOption(buildRootGraphOption(strategy.value.root_graph.nodes, strategy.value.root_graph.edges));
  window.requestAnimationFrame(() => resizeRootChart());
}

function renderSubgraph() {
  if (!selectedSubgraph.value) return;
  setSubgraphOption(buildSubgraphOption(selectedSubgraph.value));
  window.requestAnimationFrame(() => resizeSubgraphChart());
}

function selectSubgraph(subgraphKey: string) {
  selectedSubgraphKey.value = subgraphKey;
  const firstRule = strategy.value?.decision_cards.find((item) => item.target_subgraph === subgraphKey);
  if (firstRule) activeRuleKey.value = firstRule.key;
  renderRootGraph();
}

function focusRule(rule: RoutingDecisionCard) {
  activeRuleKey.value = rule.key;
  selectedSubgraphKey.value = rule.target_subgraph;
  renderRootGraph();
}

function ruleDetail(rule: RoutingPriorityRule) {
  return `P${rule.order} · ${rule.when}`;
}

async function refreshStrategy() {
  try {
    await store.fetchRoutingStrategy();
    fallbackStrategy.value = null;
    strategyLoadMessage.value = "";
  } catch {
    fallbackStrategy.value = buildFallbackRoutingStrategy();
    strategyLoadMessage.value = "未从后端获取到路由策略接口，当前展示的是前端内建的兜底策略。通常是后端仍在运行旧版本，或尚未重启到最新代码。";
    ElMessage.warning("路由策略接口不可用，已切换到前端内建策略展示");
  }
  renderRootGraph();
  renderSubgraph();
}
</script>

<template>
  <div class="route-workbench" v-loading="loading">
    <el-alert
      v-if="strategyLoadMessage"
      class="route-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="strategyLoadMessage"
    />

    <section class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">Routing Strategy Workbench</p>
        <h1>意图路由配置</h1>
        <p class="hero-desc">
          当前页面直接展示代码内建的主图与子图路由策略，不提供手工新增路由。你可以看到系统为什么会进入
          `legacy_quality` 或 `llm_native_quality`，以及触发判断所依赖的信号。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" :icon="RefreshRight" @click="refreshStrategy">刷新策略</el-button>
      </div>
    </section>

    <section class="overview-grid">
      <el-card shadow="hover" class="overview-card accent-blue">
        <p class="metric-label">路由模式</p>
        <p class="metric-value">{{ modeLabel }}</p>
        <p class="metric-note">根路由图当前按 {{ strategy?.route_mode || "router_enabled" }} 规则执行。</p>
      </el-card>
      <el-card shadow="hover" class="overview-card accent-green">
        <p class="metric-label">默认兜底子图</p>
        <p class="metric-value">{{ strategy?.default_target || "legacy_quality" }}</p>
        <p class="metric-note">未命中更高优先级规则时，最终回落到默认兼容链路。</p>
      </el-card>
      <el-card shadow="hover" class="overview-card accent-amber">
        <p class="metric-label">优先级规则</p>
        <p class="metric-value">{{ strategy?.priority_rules.length || 0 }}</p>
        <p class="metric-note">按 task_intent → has_image → llm_native 的顺序短路执行。</p>
      </el-card>
      <el-card shadow="hover" class="overview-card accent-slate">
        <p class="metric-label">系统内已有绑定</p>
        <p class="metric-value">{{ strategy?.registered_route_count || 0 }}</p>
        <p class="metric-note">
          {{ strategy?.registered_intents?.length ? strategy?.registered_intents.join(" / ") : "当前未配置额外数据库路由绑定，页面展示代码内建策略。" }}
        </p>
      </el-card>
    </section>

    <section class="strategy-shell">
      <el-card shadow="never" class="strategy-left">
        <template #header>
          <div class="section-header">
            <div>
              <h2>主图策略总览</h2>
              <p>根路由图负责采集信号、执行短路规则，并把请求分发到目标子图。</p>
            </div>
            <el-tag effect="dark" type="primary">QualityAgentRootGraph</el-tag>
          </div>
        </template>
        <div ref="rootChartRef" class="graph-panel root-graph" />
        <div class="signal-list">
          <div v-for="signal in strategy?.signals || []" :key="signal.key" class="signal-chip">
            <div class="signal-chip-top">
              <span class="signal-name">{{ signal.label }}</span>
              <el-tag size="small" effect="plain">{{ signal.source_stage }}</el-tag>
            </div>
            <p>{{ signal.description }}</p>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="strategy-right">
        <template #header>
          <div class="section-header">
            <div>
              <h2>为什么走这个智能体</h2>
              <p>每条规则都说明命中条件、目标子图和短路原因。</p>
            </div>
            <el-tag effect="plain" type="info">短路优先级</el-tag>
          </div>
        </template>
        <div class="decision-stack">
          <button
            v-for="rule in strategy?.decision_cards || []"
            :key="rule.key"
            type="button"
            class="decision-card"
            :class="{ active: activeRuleKey === rule.key }"
            @click="focusRule(rule)"
          >
            <div class="decision-top">
              <span class="decision-order">P{{ rule.priority_order }}</span>
              <el-tag :type="subgraphTone(rule.target_subgraph)" effect="light">
                {{ rule.target_subgraph }}
              </el-tag>
            </div>
            <h3>{{ rule.title }}</h3>
            <p class="decision-summary">{{ rule.summary }}</p>
            <p class="decision-reason">{{ rule.reason }}</p>
            <div class="decision-signals">
              <el-tag
                v-for="signalKey in rule.matched_signals"
                :key="signalKey"
                size="small"
                effect="plain"
              >
                {{ signalLookup.get(signalKey)?.label || signalKey }}
              </el-tag>
            </div>
          </button>
        </div>
        <div class="priority-rules">
          <div v-for="rule in strategy?.priority_rules || []" :key="rule.order" class="priority-line">
            <div>
              <p class="priority-title">{{ ruleDetail(rule) }}</p>
              <p class="priority-reason">{{ rule.reason }}</p>
            </div>
            <div class="priority-examples">
              <el-tag v-for="example in rule.examples" :key="example" size="small" effect="plain">
                {{ example }}
              </el-tag>
            </div>
          </div>
        </div>
      </el-card>
    </section>

    <section class="subgraph-shell">
      <div class="subgraph-column">
        <div class="subgraph-tabs">
          <button
            v-for="item in strategy?.subgraphs || []"
            :key="item.subgraph_key"
            type="button"
            class="subgraph-tab"
            :class="{ active: selectedSubgraphKey === item.subgraph_key }"
            @click="selectSubgraph(item.subgraph_key)"
          >
            <span class="subgraph-dot" :style="{ background: subgraphColor(item.subgraph_key) }" />
            <span>{{ item.label }}</span>
          </button>
        </div>

        <el-card shadow="never" class="subgraph-graph-card">
          <template #header>
            <div class="section-header">
              <div>
                <h2>主图与子图联动拓扑</h2>
                <p>左侧主图负责判断，右侧子图展示被选中的执行链路与入口节点。</p>
              </div>
              <el-tag :type="subgraphTone(selectedSubgraph?.subgraph_key || 'legacy_quality')" effect="dark">
                {{ selectedSubgraph?.subgraph_key || "legacy_quality" }}
              </el-tag>
            </div>
          </template>
          <div ref="subgraphChartRef" class="graph-panel subgraph-graph" />
        </el-card>
      </div>

      <el-card shadow="never" class="subgraph-detail-card">
        <template #header>
          <div class="section-header">
            <div>
              <h2>子图策略说明</h2>
              <p>展示当前子图的入口节点、典型场景和执行规模。</p>
            </div>
            <el-tag :type="subgraphTone(selectedSubgraph?.subgraph_key || 'legacy_quality')" effect="light">
              {{ selectedSubgraph?.label || "未选择子图" }}
            </el-tag>
          </div>
        </template>

        <div v-if="selectedSubgraph" class="detail-body">
          <div class="detail-highlight">
            <p class="detail-label">入口节点</p>
            <p class="detail-value">{{ selectedSubgraph.entry_node }}</p>
            <p class="detail-text">{{ selectedSubgraph.summary }}</p>
          </div>

          <div class="detail-metrics">
            <div class="detail-metric">
              <span>节点数</span>
              <strong>{{ selectedSubgraph.nodes.length }}</strong>
            </div>
            <div class="detail-metric">
              <span>连线数</span>
              <strong>{{ selectedSubgraph.edges.length }}</strong>
            </div>
            <div class="detail-metric">
              <span>当前关联规则</span>
              <strong>{{ activeRule?.title || "默认查看" }}</strong>
            </div>
          </div>

          <div class="scenario-section">
            <h3>典型触发场景</h3>
            <div class="scenario-list">
              <div v-for="scenario in selectedSubgraph.typical_scenarios" :key="scenario" class="scenario-item">
                {{ scenario }}
              </div>
            </div>
          </div>

          <div class="scenario-section">
            <h3>节点清单</h3>
            <div class="node-grid">
              <div v-for="node in selectedSubgraph.nodes" :key="node.id" class="node-card">
                <p class="node-label">{{ node.label }}</p>
                <p class="node-id">{{ node.id }}</p>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.route-workbench {
  min-height: 100%;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 34%),
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.1), transparent 28%),
    linear-gradient(180deg, #eff6ff 0%, #f8fafc 55%, #ffffff 100%);
}

.route-alert {
  margin-bottom: 16px;
  border-radius: 16px;
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 28px 30px;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(241, 245, 249, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
}

.eyebrow {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 700;
}

.hero-panel h1 {
  margin: 0;
  color: #0f172a;
  font-size: 38px;
  line-height: 1.1;
}

.hero-desc {
  margin: 14px 0 0;
  max-width: 860px;
  color: #475569;
  font-size: 15px;
  line-height: 1.7;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.overview-card {
  border-radius: 20px;
  border: none;
  overflow: hidden;
}

.overview-card :deep(.el-card__body) {
  padding: 22px;
}

.accent-blue {
  background: linear-gradient(145deg, #eff6ff, #dbeafe);
}

.accent-green {
  background: linear-gradient(145deg, #ecfdf5, #d1fae5);
}

.accent-amber {
  background: linear-gradient(145deg, #fffbeb, #fde68a);
}

.accent-slate {
  background: linear-gradient(145deg, #f8fafc, #e2e8f0);
}

.metric-label {
  margin: 0;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.metric-value {
  margin: 12px 0 8px;
  color: #0f172a;
  font-size: 28px;
  font-weight: 800;
}

.metric-note {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.strategy-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(360px, 0.95fr);
  gap: 18px;
  margin-top: 18px;
}

.strategy-left,
.strategy-right,
.subgraph-graph-card,
.subgraph-detail-card {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 14px 40px rgba(15, 23, 42, 0.05);
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.section-header h2 {
  margin: 0;
  color: #0f172a;
  font-size: 20px;
}

.section-header p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.graph-panel {
  width: 100%;
}

.root-graph {
  height: 320px;
}

.signal-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.signal-chip {
  padding: 14px 16px;
  border-radius: 18px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.signal-chip-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.signal-name {
  color: #0f172a;
  font-weight: 700;
}

.signal-chip p {
  margin: 10px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.decision-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.decision-card {
  width: 100%;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid #dbeafe;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  text-align: left;
  cursor: pointer;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease,
    border-color 160ms ease;
}

.decision-card:hover,
.decision-card.active {
  transform: translateY(-2px);
  border-color: #60a5fa;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.12);
}

.decision-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.decision-order {
  display: inline-flex;
  width: 36px;
  height: 36px;
  border-radius: 999px;
  align-items: center;
  justify-content: center;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 800;
}

.decision-card h3 {
  margin: 14px 0 8px;
  color: #0f172a;
  font-size: 18px;
}

.decision-summary,
.decision-reason {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.decision-reason {
  margin-top: 8px;
  color: #1e293b;
}

.decision-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.priority-rules {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #cbd5e1;
}

.priority-line {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.priority-title {
  margin: 0;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.priority-reason {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.priority-examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.subgraph-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.85fr);
  gap: 18px;
  margin-top: 18px;
}

.subgraph-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.subgraph-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.subgraph-tab {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 999px;
  border: 1px solid #dbeafe;
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  font-weight: 700;
  cursor: pointer;
  transition:
    background 160ms ease,
    border-color 160ms ease,
    transform 160ms ease;
}

.subgraph-tab:hover,
.subgraph-tab.active {
  transform: translateY(-1px);
  border-color: #60a5fa;
  background: #eff6ff;
}

.subgraph-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.subgraph-graph {
  height: 360px;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-highlight {
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(145deg, #eff6ff, #f8fafc);
}

.detail-label {
  margin: 0;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.detail-value {
  margin: 10px 0 8px;
  color: #0f172a;
  font-size: 24px;
  font-weight: 800;
}

.detail-text {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.detail-metric {
  padding: 16px;
  border-radius: 18px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.detail-metric span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.detail-metric strong {
  display: block;
  margin-top: 10px;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.5;
}

.scenario-section h3 {
  margin: 0 0 12px;
  color: #0f172a;
  font-size: 16px;
}

.scenario-list,
.node-grid {
  display: grid;
  gap: 10px;
}

.scenario-item,
.node-card {
  padding: 14px 16px;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  line-height: 1.6;
}

.node-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.node-label {
  margin: 0;
  color: #0f172a;
  font-weight: 700;
}

.node-id {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 12px;
  word-break: break-all;
}

@media (max-width: 1400px) {
  .overview-grid,
  .detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .strategy-shell,
  .subgraph-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .route-workbench {
    padding: 16px;
  }

  .hero-panel {
    flex-direction: column;
  }

  .overview-grid,
  .signal-list,
  .detail-metrics,
  .node-grid {
    grid-template-columns: 1fr;
  }

  .priority-line {
    flex-direction: column;
  }

  .priority-examples {
    justify-content: flex-start;
  }
}
</style>
