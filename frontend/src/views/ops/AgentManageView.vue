<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Connection, RefreshRight, VideoPause, VideoPlay } from "@element-plus/icons-vue";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import { useECharts } from "@/composables/useECharts";
import { useAuthStore } from "@/stores/auth.store";
import { ROLE_PLATFORM_OPERATOR } from "@/constants/roles";
import type { AgentDefinition, AgentRuntimeInstance } from "@/types/agent-ops.types";
import {
  buildDefinitionCards,
  buildRuntimeCards,
  filterTopologyOptions,
  groupLabel,
  groupTagType,
  lifecycleLabel,
  lifecycleTagType,
  runtimeModeHint,
  runtimeStatusTagType,
  topologyHasNodes,
  topologyLegend,
  topologyNodeColor,
  visibleDefinitionAgents,
  visibleRuntimeAgents,
} from "@/views/ops/agent-manage.utils";

const store = useAgentOpsStore();
const auth = useAuthStore();
const isReadonly = computed(() => auth.primaryRole === ROLE_PLATFORM_OPERATOR);
const pageTitle = computed(() => (isReadonly.value ? "Agent 查看" : "Agent 管理"));
const pageDescription = computed(() =>
  isReadonly.value
    ? "查看 Agent 定义、运行态和拓扑状态，平台运营账号仅保留观察与排查入口。"
    : "围绕 Agent 定义、运行态和拓扑的统一运营视图。拓扑页展示的是 Agent 总体结构与当前真实状态，不再默认展开子 Agent 内部节点。",
);
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();
const loading = computed(() => store.loading);

const activeTab = ref<"definitions" | "runtime" | "topology">("definitions");
const filters = reactive({
  name: "",
  group_key: "",
});

const topologySubgraph = ref("all");
const topologyMode = ref<"design" | "runtime">("design");
const showPlannedInTopo = ref(false);
let topologyRefreshTimer: number | null = null;

const detailDrawer = reactive({ visible: false });
const pauseDialog = reactive({
  visible: false,
  runtimeKey: "",
  agentName: "",
  reason: "",
});

const definitionCards = computed(() => buildDefinitionCards(store.agents));
const runtimeCards = computed(() => buildRuntimeCards(store.runtimeOverview, store.runtimeAgents));
const topologyOptions = computed(() => filterTopologyOptions(store.agents));
const topologyLegendRows = computed(() => topologyLegend(topologyMode.value));
const hasTopologyNodes = computed(() => topologyHasNodes(store.topology));

const definitionRows = computed(() =>
  visibleDefinitionAgents(store.agents).filter((item) => {
    const nameKeyword = filters.name.trim().toLowerCase();
    if (nameKeyword && !item.name.toLowerCase().includes(nameKeyword)) return false;
    if (filters.group_key && item.group_key !== filters.group_key) return false;
    return true;
  }),
);

const runtimeRows = computed(() => visibleRuntimeAgents(store.runtimeAgents));

const { chartRef, setOption, resize } = useECharts();

function eventLabel(type: string) {
  const map: Record<string, string> = {
    pause_route: "暂停路由",
    resume_route: "恢复路由",
    start: "启动运行态",
    stop: "停止运行态",
    maintenance: "进入维护",
  };
  return map[type] || type;
}

function formatPercent(value?: number | null) {
  return `${(((value ?? 0) as number) * 100).toFixed(1)}%`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function runtimeActionSummary(row: AgentRuntimeInstance) {
  if (row.runtime_status === "running" && row.route_enabled) return "接收新请求";
  if (!row.route_enabled) return "已暂停路由，不再接收新请求";
  if (row.runtime_status === "degraded") return "运行中，处于降级状态";
  return "当前不接收请求";
}

async function fetchAgents() {
  await store.fetchAgents({
    page: page.value,
    size: pageSize.value,
    name: filters.name || undefined,
  });
  total.value = store.agentsTotal;
}

async function refreshRuntime() {
  await Promise.all([store.fetchRuntimeOverview(), store.fetchRuntimeAgents()]);
}

async function fetchTopology() {
  await store.fetchAgentsTopology(topologySubgraph.value, topologyMode.value, showPlannedInTopo.value);
  await renderTopology();
}

async function refreshTopologyLive() {
  await refreshRuntime();
  await fetchTopology();
}

async function refreshAll() {
  await Promise.all([fetchAgents(), refreshRuntime()]);
  if (activeTab.value === "topology") {
    await fetchTopology();
  }
}

async function openDetailDrawer(row: AgentDefinition) {
  detailDrawer.visible = true;
  await Promise.all([store.fetchAgentDetail(row.id), store.fetchRuntimeEvents(row.id)]);
}

function openPauseDialog(row: AgentRuntimeInstance) {
  pauseDialog.visible = true;
  pauseDialog.runtimeKey = row.runtime_key;
  pauseDialog.agentName = row.agent_name;
  pauseDialog.reason = "";
}

async function confirmPauseRoute() {
  try {
    await store.pauseRoute(pauseDialog.runtimeKey, pauseDialog.reason.trim());
    pauseDialog.visible = false;
    ElMessage.success(`已暂停 ${pauseDialog.agentName} 的路由`);
    await refreshAll();
  } catch {
    ElMessage.error("暂停路由失败");
  }
}

async function handleResumeRoute(row: AgentRuntimeInstance) {
  try {
    await store.resumeRoute(row.runtime_key);
    ElMessage.success(`已恢复 ${row.agent_name} 的路由`);
    await refreshAll();
  } catch {
    ElMessage.error("恢复路由失败");
  }
}

async function renderTopology() {
  if (!store.topology) return;
  await nextTick();
  setOption({
    tooltip: {
      trigger: "item",
      formatter: (params: { data?: { kind?: string; status?: string; lifecycle_status?: string; route_enabled?: boolean; execution_count?: number; avg_latency_ms?: number; last_started_at?: string | null }[] | any; name: string }) => {
        const data = params.data || {};
        const lines = [params.name];
        if (data.kind === "system") lines.push("类型: 系统路由骨架");
        if (data.kind === "agent") lines.push("类型: Agent");
        if (data.lifecycle_status) lines.push(`生命周期: ${lifecycleLabel(data.lifecycle_status)}`);
        if (data.status) lines.push(`运行态: ${data.status}`);
        if (typeof data.route_enabled === "boolean") lines.push(`参与路由: ${data.route_enabled ? "是" : "否"}`);
        if (typeof data.execution_count === "number") lines.push(`执行数: ${data.execution_count}`);
        if (typeof data.avg_latency_ms === "number") lines.push(`平均延迟: ${Math.round(data.avg_latency_ms)} ms`);
        if (data.last_started_at) lines.push(`最近启动: ${formatDateTime(data.last_started_at)}`);
        return lines.join("<br/>");
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        force: { repulsion: 260, edgeLength: 120, gravity: 0.06 },
        label: { show: true, fontSize: 11, color: "#334155" },
        lineStyle: { color: "#cbd5e1", width: 1.4, curveness: 0.1 },
        emphasis: { focus: "adjacency" },
        data: store.topology.nodes.map((node) => ({
          id: node.id,
          name: node.label,
          kind: node.kind,
          status: node.status,
          lifecycle_status: node.lifecycle_status,
          route_enabled: node.route_enabled,
          execution_count: node.execution_count,
          avg_latency_ms: node.avg_latency_ms,
          last_started_at: node.last_started_at,
          symbolSize: node.kind === "system" ? 62 : store.topology?.selected_subgraph === node.subgraph_key ? 56 : 46,
          itemStyle: {
            color: topologyNodeColor(node),
            borderColor: store.topology?.selected_subgraph === node.subgraph_key ? "#0f172a" : "#ffffff",
            borderWidth: store.topology?.selected_subgraph === node.subgraph_key ? 2 : 0,
          },
        })),
        links: store.topology.edges.map((edge) => ({ source: edge.source, target: edge.target })),
      },
    ],
  });
  resize();
}

function startTopologyPolling() {
  stopTopologyPolling();
  if (activeTab.value !== "topology") return;
  topologyRefreshTimer = window.setInterval(() => {
    void refreshTopologyLive();
  }, 10000);
}

function stopTopologyPolling() {
  if (topologyRefreshTimer !== null) {
    window.clearInterval(topologyRefreshTimer);
    topologyRefreshTimer = null;
  }
}

watch(() => [page.value, pageSize.value], async () => {
  await fetchAgents();
});

watch(activeTab, async (tab) => {
  if (tab === "topology") {
    await refreshTopologyLive();
    startTopologyPolling();
    return;
  }
  stopTopologyPolling();
});

onMounted(async () => {
  await Promise.all([fetchAgents(), refreshRuntime()]);
});

onUnmounted(() => {
  stopTopologyPolling();
});
</script>

<template>
  <div class="agent-manage-page">
    <section class="page-head">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageDescription }}</p>
      </div>
      <el-button :icon="RefreshRight" @click="refreshAll">刷新数据</el-button>
    </section>

    <el-tabs v-model="activeTab" class="agent-tabs">
      <el-tab-pane label="定义" name="definitions">
        <section class="metric-grid">
          <article v-for="card in definitionCards" :key="card.key" class="metric-tile">
            <div class="metric-value" :style="{ color: card.tone }">{{ card.value }}</div>
            <div class="metric-label">{{ card.label }}</div>
          </article>
        </section>

        <el-card shadow="never" class="panel-card filter-card">
          <div class="filter-row">
            <el-input v-model="filters.name" clearable placeholder="搜索 Agent 名称" class="filter-input" />
            <el-select v-model="filters.group_key" clearable placeholder="全部类型" class="filter-select">
              <el-option label="核心" value="core" />
              <el-option label="记忆治理" value="memory" />
              <el-option label="规划中" value="planned" />
              <el-option label="历史兼容" value="legacy" />
            </el-select>
            <el-button type="primary" @click="fetchAgents">查询</el-button>
            <el-button @click="filters.name = ''; filters.group_key = ''">重置</el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-head">
              <div>
                <div class="panel-title">Agent 列表</div>
                <div class="panel-note">已废弃的 Agent 已从列表移除，保留当前仍有运营意义的定义数据。</div>
              </div>
              <el-tag type="info" size="small">系统自动注册</el-tag>
            </div>
          </template>

          <el-table :data="definitionRows" stripe v-loading="loading" @row-click="openDetailDrawer" style="cursor: pointer">
            <el-table-column prop="name" label="名称" min-width="180" />
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <el-tag :type="groupTagType(row.group_key)" size="small">{{ groupLabel(row.group_key) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="接入状态" width="110">
              <template #default="{ row }">
                <el-tag :type="lifecycleTagType(row.lifecycle_status)" size="small">{{ lifecycleLabel(row.lifecycle_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="参与路由" width="100">
              <template #default="{ row }">
                <el-tag :type="row.route_enabled ? 'success' : 'info'" size="small">{{ row.route_enabled ? "是" : "否" }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="运行态" width="120">
              <template #default="{ row }">
                <el-tag :type="runtimeStatusTagType(row.runtime_status || 'stopped')" size="small">
                  {{ row.runtime_status || "stopped" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="customer_visible_description" label="能力说明" min-width="260" show-overflow-tooltip />
            <el-table-column label="指标" min-width="190">
              <template #default="{ row }">
                <div class="metric-stack">
                  <span>执行 {{ row.metrics_summary?.execution_count ?? 0 }}</span>
                  <span>成功率 {{ formatPercent(row.metrics_summary?.success_rate) }}</span>
                  <span>平均延迟 {{ Math.round(row.metrics_summary?.avg_latency_ms ?? 0) }} ms</span>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrap">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="onPageChange"
              @size-change="onSizeChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="运行态" name="runtime">
        <section class="metric-grid compact-grid">
          <article v-for="card in runtimeCards" :key="card.key" class="metric-tile">
            <div class="metric-value" :style="{ color: card.tone }">{{ card.value }}</div>
            <div class="metric-label">{{ card.label }}</div>
          </article>
        </section>

        <el-card shadow="never" class="panel-card runtime-card">
          <template #header>
            <div class="panel-head">
              <div>
                <div class="panel-title">运行态控制</div>
                <div class="panel-note">暂停路由会同时停止该 Agent 的运行态；恢复路由会同步恢复为可接收请求的状态。</div>
              </div>
              <el-tag type="warning" size="small">{{ runtimeModeHint() }}</el-tag>
            </div>
          </template>

          <el-table :data="runtimeRows" stripe>
            <el-table-column prop="agent_name" label="Agent" min-width="180" />
            <el-table-column label="运行态" width="120">
              <template #default="{ row }">
                <el-tag :type="runtimeStatusTagType(row.runtime_status)" size="small">{{ row.runtime_status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="路由状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.route_enabled ? 'success' : 'warning'" size="small">
                  {{ row.route_enabled ? "接收流量" : "已暂停路由" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="当前说明" min-width="180">
              <template #default="{ row }">
                <span class="text-zinc-600">{{ runtimeActionSummary(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="execution_count" label="执行数" width="90" />
            <el-table-column label="成功率" width="100">
              <template #default="{ row }">{{ formatPercent(row.success_rate) }}</template>
            </el-table-column>
            <el-table-column label="平均延迟" width="110">
              <template #default="{ row }">{{ Math.round(row.avg_latency_ms) }} ms</template>
            </el-table-column>
            <el-table-column label="最近启动" width="180">
              <template #default="{ row }">{{ formatDateTime(row.last_started_at) }}</template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" min-width="180" fixed="right">
              <template #default="{ row }">
                <div class="action-row">
                  <el-button
                    v-if="row.supports_route_toggle"
                    link
                    :type="row.route_enabled ? 'warning' : 'success'"
                    @click="row.route_enabled ? openPauseDialog(row) : handleResumeRoute(row)"
                  >
                    <el-icon><component :is="row.route_enabled ? VideoPause : VideoPlay" /></el-icon>
                    <span>{{ row.route_enabled ? "暂停路由" : "恢复路由" }}</span>
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="拓扑" name="topology">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-head topology-head">
              <div>
                <div class="panel-title">Agent 拓扑</div>
                <div class="panel-note">当前展示 Agent 总览拓扑：系统路由骨架 + Agent 节点。内部子节点默认隐藏，节点状态会按当前注册、路由和运行态实时刷新。</div>
              </div>
              <div class="topology-toolbar">
                <el-radio-group v-model="topologyMode" size="small" @change="fetchTopology">
                  <el-radio-button value="design">设计拓扑</el-radio-button>
                  <el-radio-button value="runtime">运行拓扑</el-radio-button>
                </el-radio-group>
                <el-select v-model="topologySubgraph" class="topology-select" size="small" @change="fetchTopology">
                  <el-option v-for="option in topologyOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
                <el-checkbox v-model="showPlannedInTopo" size="small" @change="fetchTopology">显示规划中</el-checkbox>
              </div>
            </div>
          </template>

          <div class="topology-grid">
            <div class="graph-shell">
              <div v-if="hasTopologyNodes" ref="chartRef" class="graph-panel" />
              <el-empty v-else description="当前筛选下没有可展示的拓扑节点" :image-size="90" />
            </div>

            <aside class="legend-panel">
              <div class="legend-title">
                <el-icon><Connection /></el-icon>
                <span>图例与说明</span>
              </div>
              <div class="legend-list">
                <div v-for="item in topologyLegendRows" :key="item.label" class="legend-item">
                  <span class="legend-dot" :style="{ background: item.color }" />
                  <span>{{ item.label }}</span>
                </div>
              </div>
              <p class="legend-note">绿色节点表示当前处于运行中的 Agent。切到“运行拓扑”后，只保留当前可实际接收请求的 Agent。</p>
            </aside>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailDrawer.visible" title="Agent 详情" size="520px">
      <template v-if="store.agentDetail">
        <section class="detail-block">
          <h4>基础信息</h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="名称">{{ store.agentDetail.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">
              <el-tag :type="groupTagType(store.agentDetail.group_key)" size="small">
                {{ groupLabel(store.agentDetail.group_key) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="子图 Key">{{ store.agentDetail.subgraph_key }}</el-descriptions-item>
            <el-descriptions-item label="入口图">{{ store.agentDetail.entry_graph || "-" }}</el-descriptions-item>
            <el-descriptions-item label="路由状态">
              <el-tag :type="store.agentDetail.route_enabled ? 'success' : 'info'" size="small">
                {{ store.agentDetail.route_enabled ? "参与路由" : "已暂停路由" }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="运行态">
              <el-tag :type="runtimeStatusTagType(store.agentDetail.runtime_status || 'stopped')" size="small">
                {{ store.agentDetail.runtime_status || "stopped" }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <section class="detail-block">
          <h4>能力说明</h4>
          <p class="detail-copy">{{ store.agentDetail.customer_visible_description || store.agentDetail.description || "-" }}</p>
        </section>

        <section class="detail-block">
          <h4>运行指标</h4>
          <div class="detail-metrics">
            <p>执行次数：{{ store.agentDetail.metrics_summary?.execution_count ?? 0 }}</p>
            <p>成功率：{{ formatPercent(store.agentDetail.metrics_summary?.success_rate) }}</p>
            <p>平均延迟：{{ Math.round(store.agentDetail.metrics_summary?.avg_latency_ms ?? 0) }} ms</p>
          </div>
        </section>

        <section class="detail-block">
          <h4>操作记录</h4>
          <el-timeline v-if="store.runtimeEvents.length">
            <el-timeline-item
              v-for="event in store.runtimeEvents.slice(0, 8)"
              :key="event.id"
              :timestamp="formatDateTime(event.created_at)"
              size="small"
            >
              {{ eventLabel(event.event_type) }}
              <span v-if="event.reason" class="timeline-note">{{ event.reason }}</span>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无操作记录" :image-size="48" />
        </section>
      </template>
    </el-drawer>

    <el-dialog v-model="pauseDialog.visible" title="确认暂停路由" width="460px">
      <div class="pause-copy">
        <p>暂停 <strong>{{ pauseDialog.agentName }}</strong> 的路由后，新请求将不会再分发到该 Agent，运行态也会同步停用。</p>
        <el-input
          v-model="pauseDialog.reason"
          type="textarea"
          :rows="3"
          placeholder="请输入暂停原因，用于后续审计和排查"
        />
      </div>
      <template #footer>
        <el-button @click="pauseDialog.visible = false">取消</el-button>
        <el-button type="warning" :disabled="!pauseDialog.reason.trim()" @click="confirmPauseRoute">确认暂停</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.agent-manage-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(22, 163, 74, 0.16), transparent 24%),
    radial-gradient(circle at right top, rgba(132, 204, 22, 0.14), transparent 25%),
    linear-gradient(180deg, #f0fdf4 0%, #f8fafc 100%);
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 86% 18%, rgba(190, 242, 100, 0.22), transparent 30%),
    linear-gradient(135deg, #10231c 0%, #14532d 50%, #365314 100%);
  color: #f8fafc;
  box-shadow: 0 24px 60px rgba(20, 83, 45, 0.18);
}

.page-head h1 {
  margin: 0;
  font-size: 40px;
  line-height: 1.1;
  color: #f8fafc;
}

.page-head p {
  max-width: 840px;
  margin: 12px 0 0;
  color: rgba(248, 250, 252, 0.82);
  line-height: 1.7;
}

.page-head :deep(.el-button) {
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  font-weight: 700;
}

.page-head :deep(.el-button:hover),
.page-head :deep(.el-button:focus) {
  border-color: rgba(255, 255, 255, 0.44);
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.agent-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.compact-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.metric-tile,
.panel-card,
.graph-shell,
.legend-panel {
  border: 1px solid #dbe4f0;
  border-radius: 16px;
  background: #fff;
}

.metric-tile {
  padding: 18px 20px;
}

.metric-value {
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
}

.metric-label {
  margin-top: 10px;
  color: #64748b;
  font-size: 13px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.panel-note {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.filter-card :deep(.el-card__body) {
  padding: 18px 20px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-input {
  width: 260px;
}

.filter-select {
  width: 180px;
}

.metric-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #475569;
  font-size: 12px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.runtime-card :deep(.el-card__body) {
  padding-top: 8px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topology-head {
  align-items: flex-start;
}

.topology-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.topology-select {
  width: 200px;
}

.topology-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.9fr) minmax(280px, 0.8fr);
  gap: 16px;
}

.graph-shell {
  min-height: 560px;
  background:
    radial-gradient(circle at top right, rgba(191, 219, 254, 0.36), transparent 28%),
    linear-gradient(180deg, #f8fbff 0%, #f1f5f9 100%);
  overflow: hidden;
}

.graph-shell :deep(.el-empty) {
  min-height: 560px;
}

.graph-panel {
  width: 100%;
  height: 560px;
}

.legend-panel {
  padding: 16px;
}

.legend-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.legend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: #334155;
  font-size: 14px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.legend-note {
  margin: 16px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.detail-block {
  margin-bottom: 22px;
}

.detail-block h4 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.detail-copy,
.detail-metrics {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.timeline-note {
  margin-left: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.pause-copy {
  display: grid;
  gap: 12px;
  color: #475569;
  line-height: 1.7;
}

@media (max-width: 1280px) {
  .metric-grid,
  .compact-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .topology-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .agent-manage-page {
    padding: 14px;
  }

  .page-head,
  .panel-head,
  .topology-head {
    flex-direction: column;
    align-items: stretch;
  }

  .metric-grid,
  .compact-grid {
    grid-template-columns: 1fr;
  }

  .filter-row,
  .topology-toolbar {
    align-items: stretch;
  }

  .filter-input,
  .filter-select,
  .topology-select {
    width: 100%;
  }
}
</style>
