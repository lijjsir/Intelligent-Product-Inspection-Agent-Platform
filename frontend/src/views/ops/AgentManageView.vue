<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import { useECharts } from "@/composables/useECharts";
import type { AgentRuntimeInstance, AgentLifecycleStatus, AgentRuntimeStatus, AgentGroup } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();
const loading = computed(() => store.loading);
const activeTab = ref("definitions");
const filters = reactive({ name: "", lifecycle_status: "", group_key: "" });

// ——— 定义 Tab ———
const definitionCards = computed(() => {
  const agents = store.agents;
  return [
    { label: "核心 Agent", value: agents.filter(a => a.group_key === "core").length, color: "#0d9488" },
    { label: "规划中 Agent", value: agents.filter(a => a.group_key === "planned").length, color: "#d97706" },
    { label: "可控制 Agent", value: agents.filter(a => a.supports_route_toggle).length, color: "#2563eb" },
    { label: "异常 Agent", value: agents.filter(a => a.runtime_status === "degraded").length, color: "#dc2626" },
  ];
});

function groupTagType(g: AgentGroup): string {
  const map: Record<string, string> = { core: "", memory: "warning", planned: "info", legacy: "info" };
  return map[g] || "info";
}
function groupLabel(g: AgentGroup): string {
  const map: Record<string, string> = { core: "核心", memory: "记忆治理", planned: "规划中", legacy: "历史" };
  return map[g] || g;
}
function lifecycleTagType(s: AgentLifecycleStatus): string {
  const map: Record<string, string> = { active: "success", partial: "warning", planned: "info", legacy: "info", deprecated: "danger" };
  return map[s] || "info";
}
function lifecycleLabel(s: AgentLifecycleStatus): string {
  const map: Record<string, string> = { active: "已接入", partial: "部分接入", planned: "规划中", legacy: "历史兼容", deprecated: "已废弃" };
  return map[s] || s;
}
function runtimeStatusTagType(s: AgentRuntimeStatus): string {
  const map: Record<string, string> = { running: "success", stopped: "info", degraded: "warning", maintenance: "danger", readonly: "info" };
  return map[s] || "info";
}
function eventLabel(type: string): string {
  const map: Record<string, string> = {
    pause_route: "暂停路由", resume_route: "恢复路由",
    start: "启动", stop: "停止", maintenance: "进入维护",
  };
  return map[type] || type;
}

// ——— 详情抽屉 ———
const detailDrawer = reactive({ visible: false });
async function openDetailDrawer(row: any) {
  detailDrawer.visible = true;
  await Promise.all([
    store.fetchAgentDetail(row.id),
    store.fetchRuntimeEvents(row.id),
  ]);
}

// ——— 运行态 Tab ———
const runtimeCards = computed(() => {
  const o = store.runtimeOverview;
  return [
    { label: "运行中", value: o?.running_agents ?? 0, color: "#0d9488" },
    { label: "已暂停", value: (o?.active_agents ?? 0) - (o?.running_agents ?? 0), color: "#d97706" },
    { label: "今日执行", value: o?.completed_today ?? 0, color: "#2563eb" },
    { label: "成功率", value: ((o?.success_rate ?? 0) * 100).toFixed(1) + "%", color: "#059669" },
    { label: "平均延迟", value: (o?.avg_latency_ms ?? 0) + " ms", color: "#7c3aed" },
    { label: "最近错误", value: o?.recent_errors ?? 0, color: (o?.recent_errors ?? 0) > 0 ? "#dc2626" : "#6b7280" },
  ];
});

const pauseDialog = reactive({ visible: false, agentName: "", runtimeKey: "", reason: "" });
function openPauseDialog(row: AgentRuntimeInstance) {
  pauseDialog.agentName = row.agent_name;
  pauseDialog.runtimeKey = row.runtime_key;
  pauseDialog.reason = "";
  pauseDialog.visible = true;
}
async function confirmPauseRoute() {
  try {
    await store.pauseRoute(pauseDialog.runtimeKey, pauseDialog.reason);
    ElMessage.success(`已暂停 ${pauseDialog.agentName} 的路由`);
    pauseDialog.visible = false;
    await refreshRuntime();
  } catch { ElMessage.error("暂停路由失败"); }
}

async function handleResumeRoute(row: AgentRuntimeInstance) {
  try {
    await store.resumeRoute(row.runtime_key);
    ElMessage.success(`已恢复 ${row.agent_name} 的路由`);
    await refreshRuntime();
  } catch { ElMessage.error("恢复路由失败"); }
}

async function handleRuntimeToggle(row: AgentRuntimeInstance) {
  try {
    if (row.status === "running") {
      await store.stopRuntimeAgent(row.runtime_key);
      ElMessage.success("Agent 已停止");
    } else {
      await store.startRuntimeAgent(row.runtime_key);
      ElMessage.success("Agent 已启动");
    }
    await refreshRuntime();
  } catch { ElMessage.error("运行状态切换失败"); }
}

// ——— 拓扑 Tab ———
const topologySubgraph = ref("all");
const topologyMode = ref<"design" | "runtime">("design");
const showPlannedInTopo = ref(true);
const showLegacyInTopo = ref(false);

const topologyOptions = computed(() => {
  const discovered = store.agents.map((item) => ({ label: item.name, value: item.subgraph_key }));
  return [{ label: "全部子图", value: "all" }, ...discovered];
});

const { chartRef, setOption, resize } = useECharts();

function topoNodeColor(node: any) {
  const status = node.status || node.itemStyle?.status;
  const lifecycle = node.lifecycle_status;
  if (lifecycle === "planned") return "#d1d5db";
  if (lifecycle === "legacy" || lifecycle === "deprecated") return "#f97316";
  if (status === "running") return "#0d9488";
  if (status === "degraded") return "#eab308";
  if (status === "stopped") return "#94a3b8";
  if (node.kind === "root") return "#6366f1";
  if (node.kind === "subgraph") return "#2563eb";
  return "#475569";
}

async function renderTopology() {
  const value = store.topology;
  if (!value) return;
  await nextTick();
  setOption({
    tooltip: { trigger: "item", formatter: (p: any) => `${p.name}<br/>${p.data?.kind || ""} ${p.data?.status || ""}` },
    series: [{
      type: "graph", layout: "force", roam: true, draggable: true,
      force: { repulsion: 280, edgeLength: 130, gravity: 0.08 },
      label: { show: true, fontSize: 11, color: "#334155" },
      lineStyle: { color: "#cbd5e1", width: 1.5, curveness: 0.12 },
      emphasis: { focus: "adjacency" },
      data: value.nodes.map((node: any) => ({
        id: node.id, name: node.label, value: node.kind,
        symbolSize: node.kind === "root" ? 72 : node.kind === "subgraph" ? 56 : 40,
        itemStyle: { color: topoNodeColor(node) },
        status: node.status, kind: node.kind, lifecycle_status: node.lifecycle_status,
      })),
      links: value.edges.map((edge: any) => ({ source: edge.source, target: edge.target })),
    }],
  });
  resize();
}

// ——— Data fetching ———
async function fetchAgents() {
  await store.fetchAgents({ page: page.value, size: pageSize.value, name: filters.name || undefined });
  total.value = store.agentsTotal;
}
async function refreshRuntime() {
  await Promise.all([store.fetchRuntimeOverview(), store.fetchRuntimeAgents()]);
}
async function fetchTopology() {
  await store.fetchAgentsTopology(topologySubgraph.value, topologyMode.value);
  await renderTopology();
}

watch(() => [page.value, pageSize.value], async () => { await fetchAgents(); });
watch(activeTab, async (value) => {
  if (value === "topology" && !store.topology) await fetchTopology();
  else if (value === "topology") await renderTopology();
});
onMounted(async () => {
  await Promise.all([fetchAgents(), refreshRuntime()]);
  await fetchTopology();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="page-header">
      <h1>Agent 管理</h1>
      <p class="mt-2 text-sm text-zinc-500">Agent 控制中心 — 定义、运行态、拓扑一站式管理。</p>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ===== 定义 Tab ===== -->
      <el-tab-pane label="定义" name="definitions">
        <!-- Overview cards -->
        <div class="flex gap-4 mb-4">
          <div class="flex-1" v-for="card in definitionCards" :key="card.label">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
              <div class="stat-label">{{ card.label }}</div>
            </el-card>
          </div>
        </div>

        <!-- Filters -->
        <el-card class="mb-4" shadow="never">
          <el-form :model="filters" inline>
            <el-form-item label="名称">
              <el-input v-model="filters.name" placeholder="搜索 Agent 名称" clearable />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="filters.group_key" placeholder="全部" clearable>
                <el-option label="核心" value="core" />
                <el-option label="规划中" value="planned" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="fetchAgents">查询</el-button>
              <el-button @click="filters.name = ''; filters.group_key = ''">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Agent table -->
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>Agent 列表</span>
              <el-tag type="info" size="small">系统自动注册</el-tag>
            </div>
          </template>
          <el-table :data="store.agents" v-loading="loading" stripe @row-click="openDetailDrawer" style="cursor: pointer">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                <el-tag :type="groupTagType(row.group_key)" size="small">{{ groupLabel(row.group_key) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="customer_visible_description" label="能力说明" min-width="220" show-overflow-tooltip />
            <el-table-column label="接入状态" width="90">
              <template #default="{ row }">
                <el-tag :type="lifecycleTagType(row.lifecycle_status)" size="small">{{ lifecycleLabel(row.lifecycle_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="参与路由" width="80">
              <template #default="{ row }">
                <el-tag :type="row.route_enabled ? 'success' : 'info'" size="small">{{ row.route_enabled ? '是' : '否' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="运行态" width="100">
              <template #default="{ row }">
                <el-tag :type="runtimeStatusTagType(row.runtime_status)" size="small">{{ row.runtime_status || 'unknown' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="指标" min-width="160">
              <template #default="{ row }">
                <div class="text-xs text-zinc-600">执行 {{ row.metrics_summary?.execution_count ?? 0 }} | 成功率 {{ ((row.metrics_summary?.success_rate ?? 0) * 100).toFixed(1) }}%</div>
                <div class="text-xs text-zinc-400">延迟 {{ row.metrics_summary?.avg_latency_ms ?? 0 }} ms</div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="page" v-model:page-size="pageSize" :total="total"
              :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next"
              @current-change="onPageChange" @size-change="onSizeChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ===== 运行态 Tab ===== -->
      <el-tab-pane label="运行态" name="runtime">
        <div class="flex gap-4 mb-4">
          <div class="flex-1" v-for="card in runtimeCards" :key="card.label">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
              <div class="stat-label">{{ card.label }}</div>
            </el-card>
          </div>
        </div>
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>运行单元</span>
              <el-button @click="refreshRuntime">刷新</el-button>
            </div>
          </template>
          <el-table :data="store.runtimeAgents" stripe>
            <el-table-column prop="agent_name" label="Agent" min-width="150" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="runtimeStatusTagType(row.runtime_status)" size="small">{{ row.runtime_status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="execution_count" label="执行数" width="80" />
            <el-table-column label="成功率" width="100">
              <template #default="{ row }">{{ (row.success_rate * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="平均延迟" width="100">
              <template #default="{ row }">{{ row.avg_latency_ms.toFixed(0) }} ms</template>
            </el-table-column>
            <el-table-column label="最近启动" width="160">
              <template #default="{ row }">{{ row.last_started_at ? new Date(row.last_started_at).toLocaleString() : "-" }}</template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <template v-if="row.lifecycle_status === 'planned'">
                  <span class="text-zinc-400 text-sm">仅展示</span>
                </template>
                <template v-else-if="row.lifecycle_status === 'legacy' || row.lifecycle_status === 'deprecated'">
                  <span class="text-red-400 text-sm">已废弃</span>
                </template>
                <template v-else>
                  <el-button v-if="row.supports_route_toggle" link :type="row.route_enabled ? 'warning' : 'success'" @click="row.route_enabled ? openPauseDialog(row) : handleResumeRoute(row)">
                    {{ row.route_enabled ? "暂停路由" : "恢复路由" }}
                  </el-button>
                  <el-button v-if="row.supports_start_stop" link type="primary" @click="handleRuntimeToggle(row)">
                    {{ row.status === "running" ? "停止" : "启动" }}
                  </el-button>
                </template>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ===== 拓扑 Tab ===== -->
      <el-tab-pane label="拓扑" name="topology">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>Agent 拓扑</span>
              <div class="toolbar">
                <el-radio-group v-model="topologyMode" size="small" @change="fetchTopology">
                  <el-radio-button value="design">设计拓扑</el-radio-button>
                  <el-radio-button value="runtime">运行拓扑</el-radio-button>
                </el-radio-group>
                <el-select v-model="topologySubgraph" style="width: 200px" size="small" @change="fetchTopology">
                  <el-option v-for="o in topologyOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
                <el-checkbox v-model="showPlannedInTopo" size="small" @change="fetchTopology">规划中</el-checkbox>
                <el-checkbox v-model="showLegacyInTopo" size="small" @change="fetchTopology">历史</el-checkbox>
              </div>
            </div>
          </template>
          <div class="topology-grid">
            <div class="graph-panel-wrap">
              <div ref="chartRef" class="graph-panel" />
            </div>
            <div class="topology-side">
              <div class="topology-section">
                <div class="section-title">图例</div>
                <div class="flex flex-col gap-2 text-sm">
                  <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full inline-block" style="background:#6366f1" /> 根路由</div>
                  <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full inline-block" style="background:#0d9488" /> 运行中</div>
                  <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full inline-block" style="background:#eab308" /> 降级</div>
                  <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full inline-block" style="background:#d1d5db" /> 规划中</div>
                  <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full inline-block" style="background:#f97316" /> 历史</div>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- ===== Detail Drawer ===== -->
    <el-drawer v-model="detailDrawer.visible" title="Agent 详情" size="520px">
      <template v-if="store.agentDetail">
        <div class="detail-section">
          <h4 class="text-sm font-semibold text-zinc-900 mb-2">基础信息</h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="名称">{{ store.agentDetail.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">
              <el-tag :type="groupTagType(store.agentDetail.group_key)" size="small">{{ groupLabel(store.agentDetail.group_key) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="子图 Key">{{ store.agentDetail.subgraph_key }}</el-descriptions-item>
            <el-descriptions-item label="入口图">{{ store.agentDetail.entry_graph }}</el-descriptions-item>
            <el-descriptions-item label="工作流绑定">{{ store.agentDetail.workflow_binding }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ store.agentDetail.graph_version }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="detail-section">
          <h4 class="text-sm font-semibold text-zinc-900 mb-2">能力说明</h4>
          <p class="text-sm text-zinc-600">{{ store.agentDetail.customer_visible_description || store.agentDetail.description }}</p>
        </div>

        <div class="detail-section">
          <h4 class="text-sm font-semibold text-zinc-900 mb-2">路由信息</h4>
          <div class="text-sm text-zinc-600">
            <p>参与路由：<el-tag :type="store.agentDetail.route_enabled ? 'success' : 'info'" size="small">{{ store.agentDetail.route_enabled ? '是' : '否' }}</el-tag></p>
            <p class="mt-1">绑定路由规则：{{ store.agentDetail.bound_routes?.length || 0 }} 条</p>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="text-sm font-semibold text-zinc-900 mb-2">运行指标</h4>
          <div class="text-sm text-zinc-600 space-y-1">
            <p>执行次数：{{ store.agentDetail.metrics_summary?.execution_count ?? 0 }}</p>
            <p>成功率：{{ ((store.agentDetail.metrics_summary?.success_rate ?? 0) * 100).toFixed(1) }}%</p>
            <p>平均延迟：{{ store.agentDetail.metrics_summary?.avg_latency_ms ?? 0 }} ms</p>
          </div>
        </div>

        <div class="detail-section">
          <h4 class="text-sm font-semibold text-zinc-900 mb-2">操作记录</h4>
          <el-timeline v-if="store.runtimeEvents.length">
            <el-timeline-item v-for="event in store.runtimeEvents.slice(0, 8)" :key="event.id" :timestamp="new Date(event.created_at).toLocaleString()" size="small">
              {{ eventLabel(event.event_type) }}
              <span v-if="event.reason" class="text-zinc-400 text-xs"> — {{ event.reason }}</span>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无操作记录" :image-size="40" />
        </div>
      </template>
    </el-drawer>

    <!-- ===== Pause Route Dialog ===== -->
    <el-dialog v-model="pauseDialog.visible" title="确认暂停路由" width="480px">
      <div>
        <p class="mb-3">你正在暂停 <strong>{{ pauseDialog.agentName }}</strong> 的路由。</p>
        <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
          <div class="text-sm font-semibold text-amber-800 mb-1">影响范围：</div>
          <ul class="text-sm text-amber-700 m-0 pl-4 space-y-0.5">
            <li>该 Agent 将不再接收新请求。</li>
            <li>已在执行中的请求不会被中断。</li>
          </ul>
        </div>
        <el-input v-model="pauseDialog.reason" type="textarea" :rows="2" placeholder="请输入暂停原因（必填）" />
      </div>
      <template #footer>
        <el-button @click="pauseDialog.visible = false">取消</el-button>
        <el-button type="warning" :disabled="!pauseDialog.reason.trim()" @click="confirmPauseRoute">确认暂停</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
}


.card-header,
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
}

.toolbar {
  justify-content: flex-end;
}



.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1d4ed8;
}

.stat-label {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.metric-line {
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.topology-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.topology-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(320px, 0.9fr);
  gap: 16px;
}

.graph-panel-wrap {
  min-height: 560px;
 border: 1px solid #dbe4f0;
 border-radius: 16px;
  background:
    radial-gradient(circle at top right, rgba(191, 219, 254, 0.45), transparent 28%),
    linear-gradient(180deg, #f8fbff 0%, #f1f5f9 100%);
  overflow: hidden;
}

.graph-panel {
  height: 560px;
  width: 100%;
}

.topology-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.topology-section {
 border: 1px solid #dbe4f0;
 border-radius: 16px;
  background: #fff;
  padding: 14px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 10px;
}

.legend-list,
.topology-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-item,
.topology-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: #475569;
  font-size: 13px;
}

.legend-dot {
  width: 10px;
  height: 10px;
 border-radius: 999px;
  flex: 0 0 auto;
}

.mono {
  font-family: "Consolas", "SFMono-Regular", monospace;
  color: #1e293b;
  background: #f8fafc;
 border-radius: 8px;
  padding: 2px 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edge-item {
  align-items: flex-start;
}

.arrow {
  color: #94a3b8;
  font-weight: 700;
}

.muted {
  color: #94a3b8;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-section {
  margin-bottom: 20px;
}
.detail-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #1e293b;
}

@media (max-width: 1200px) {
  .topology-grid {
    grid-template-columns: 1fr;
  }
}
</style>
