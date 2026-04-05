<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useAgentOpsStore } from "@/stores/agent-ops.store";
import { usePagination } from "@/composables/usePagination";
import { useECharts } from "@/composables/useECharts";
import type { AgentRuntimeInstance } from "@/types/agent-ops.types";

const store = useAgentOpsStore();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();
const loading = computed(() => store.loading);
const activeTab = ref("definitions");
const filters = ref({ name: "", is_active: "" });
const topologySubgraph = ref("all");

const topologyLegend = [
  { label: "Root Route", kind: "root", color: "#0f766e" },
  { label: "Subgraph Entry", kind: "subgraph", color: "#2563eb" },
  { label: "Processing Node", kind: "node", color: "#475569" },
  { label: "Decision Node", kind: "decision", color: "#d97706" },
];

const topologyOptions = computed(() => {
  const discovered = store.agents.map((item) => ({
    label: item.name,
    value: item.subgraph_key,
  }));
  return [{ label: "全部子图", value: "all" }, ...discovered];
});

const topologyStats = computed(() => ({
  nodeCount: store.topology?.nodes.length ?? 0,
  edgeCount: store.topology?.edges.length ?? 0,
  selectedSubgraph: store.topology?.selected_subgraph || topologySubgraph.value,
}));

const visibleTopologyNodes = computed(() => (store.topology?.nodes ?? []).slice(0, 12));
const visibleTopologyEdges = computed(() => (store.topology?.edges ?? []).slice(0, 10));

const { chartRef, setOption, resize } = useECharts();

function nodeColor(kind: string) {
  if (kind === "root") return "#0f766e";
  if (kind === "subgraph") return "#2563eb";
  if (kind === "decision") return "#d97706";
  return "#475569";
}

async function renderTopology() {
  const value = store.topology;
  if (!value) return;
  await nextTick();
  setOption({
    tooltip: { trigger: "item" },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        force: { repulsion: 280, edgeLength: 130, gravity: 0.08 },
        label: { show: true, fontSize: 12, color: "#0f172a" },
        lineStyle: { color: "#94a3b8", width: 2, curveness: 0.12, opacity: 0.9 },
        emphasis: { focus: "adjacency" },
        data: value.nodes.map((node) => ({
          id: node.id,
          name: node.label,
          value: node.kind,
          symbolSize: node.kind === "root" ? 78 : node.kind === "subgraph" ? 64 : 46,
          itemStyle: {
            color: nodeColor(node.kind),
            shadowBlur: 12,
            shadowColor: "rgba(15, 23, 42, 0.16)",
          },
        })),
        links: value.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
        })),
      },
    ],
  });
  resize();
}

watch(
  () => store.topology,
  async () => {
    await renderTopology();
  },
  { deep: true },
);

watch(
  () => [page.value, pageSize.value],
  async () => {
    await fetchAgents();
  },
);

watch(activeTab, async (value) => {
  if (value !== "topology") return;
  if (!store.topology) {
    await fetchTopology();
  } else {
    await renderTopology();
  }
});

onMounted(async () => {
  await Promise.all([fetchAgents(), refreshRuntime()]);
  await fetchTopology();
});

async function fetchAgents() {
  await store.fetchAgents({
    page: page.value,
    size: pageSize.value,
    name: filters.value.name || undefined,
    is_active: filters.value.is_active === "" ? undefined : filters.value.is_active === "true",
  });
  total.value = store.agentsTotal;
}

async function refreshRuntime() {
  await Promise.all([store.fetchRuntimeOverview(), store.fetchRuntimeAgents()]);
}

async function fetchTopology() {
  await store.fetchAgentsTopology(topologySubgraph.value);
  await renderTopology();
}

async function handleRuntimeToggle(row: AgentRuntimeInstance) {
  try {
    if (row.status === "running") {
      await store.stopRuntimeAgent(row.runtime_key);
      ElMessage.success("智能体已停止");
    } else {
      await store.startRuntimeAgent(row.runtime_key);
      ElMessage.success("智能体已启动");
    }
    await refreshRuntime();
  } catch {
    ElMessage.error("运行状态切换失败");
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Agent 管理</h1>
      <p class="subtitle">自动发现当前 LangGraph 子图，查看运行状态，并管理可启停的智能体运行单元。</p>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="定义" name="definitions">
        <el-card class="mb-4" shadow="never">
          <el-form :model="filters" inline>
            <el-form-item label="名称">
              <el-input v-model="filters.name" placeholder="搜索 Agent 名称" clearable />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="filters.is_active" placeholder="全部" clearable>
                <el-option label="启用" value="true" />
                <el-option label="停用" value="false" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="fetchAgents">查询</el-button>
              <el-button @click="filters = { name: '', is_active: '' }">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>已发现的智能体子图</span>
              <el-tag type="info">系统自动注册</el-tag>
            </div>
          </template>

          <el-table :data="store.agents" v-loading="loading" stripe>
            <el-table-column prop="name" label="名称" min-width="180" />
            <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
            <el-table-column prop="subgraph_key" label="子图" width="170" />
            <el-table-column prop="entry_graph" label="入口图" width="180" />
            <el-table-column prop="workflow_binding" label="工作流绑定" width="180" />
            <el-table-column prop="graph_version" label="版本" width="90" />
            <el-table-column label="运行态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.runtime_status === 'running' ? 'success' : 'info'">
                  {{ row.runtime_status || "unknown" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="启停控制" width="110">
              <template #default="{ row }">
                <el-tag :type="row.supports_start_stop ? 'warning' : 'info'">
                  {{ row.supports_start_stop ? "可控制" : "只读" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="指标" min-width="180">
              <template #default="{ row }">
                <div class="metric-line">执行 {{ row.metrics_summary?.execution_count ?? 0 }}</div>
                <div class="metric-line">延迟 {{ row.metrics_summary?.avg_latency_ms ?? 0 }} ms</div>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
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
        <el-row :gutter="16" class="mb-4">
          <el-col :span="4">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value">{{ store.runtimeOverview?.active_agents ?? 0 }}</div>
              <div class="stat-label">启用 Agent</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value">{{ store.runtimeOverview?.running_agents ?? 0 }}</div>
              <div class="stat-label">运行中</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value">{{ store.runtimeOverview?.stopped_agents ?? 0 }}</div>
              <div class="stat-label">已停止</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value">{{ store.runtimeOverview?.total_executions ?? 0 }}</div>
              <div class="stat-label">累计执行</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="stat-card">
              <div class="stat-value">{{ store.runtimeOverview?.avg_latency_ms ?? 0 }} ms</div>
              <div class="stat-label">平均延迟</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>运行单元</span>
              <el-button @click="refreshRuntime">刷新</el-button>
            </div>
          </template>
          <el-table :data="store.runtimeAgents" stripe>
            <el-table-column prop="agent_name" label="Agent" min-width="180" />
            <el-table-column prop="subgraph_key" label="子图" width="170" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : 'info'">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="execution_count" label="执行数" width="90" />
            <el-table-column label="成功率" width="110">
              <template #default="{ row }">
                {{ (row.success_rate * 100).toFixed(1) }}%
              </template>
            </el-table-column>
            <el-table-column label="平均延迟" width="120">
              <template #default="{ row }">
                {{ row.avg_latency_ms.toFixed(0) }} ms
              </template>
            </el-table-column>
            <el-table-column label="最近启动" width="180">
              <template #default="{ row }">
                {{ row.last_started_at ? new Date(row.last_started_at).toLocaleString() : "-" }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.supports_start_stop"
                  link
                  type="primary"
                  @click="handleRuntimeToggle(row)"
                >
                  {{ row.status === "running" ? "停止" : "启动" }}
                </el-button>
                <span v-else class="muted">仅展示</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="拓扑" name="topology">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>质量智能体拓扑</span>
              <div class="toolbar">
                <el-select v-model="topologySubgraph" style="width: 240px" @change="fetchTopology">
                  <el-option
                    v-for="option in topologyOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
                <el-button @click="fetchTopology">刷新图谱</el-button>
              </div>
            </div>
          </template>

          <div class="topology-meta">
            <el-tag type="success">根路由图</el-tag>
            <el-tag type="primary">{{ topologyStats.selectedSubgraph }}</el-tag>
            <el-tag type="info">节点 {{ topologyStats.nodeCount }}</el-tag>
            <el-tag type="warning">连线 {{ topologyStats.edgeCount }}</el-tag>
          </div>

          <div class="topology-grid">
            <div class="graph-panel-wrap">
              <div ref="chartRef" class="graph-panel" />
            </div>

            <div class="topology-side">
              <div class="topology-section">
                <div class="section-title">图例</div>
                <div class="legend-list">
                  <div v-for="item in topologyLegend" :key="item.kind" class="legend-item">
                    <span class="legend-dot" :style="{ backgroundColor: item.color }" />
                    <span>{{ item.label }}</span>
                  </div>
                </div>
              </div>

              <div class="topology-section">
                <div class="section-title">节点列表</div>
                <div v-if="store.topology?.nodes?.length" class="topology-list">
                  <div v-for="node in visibleTopologyNodes" :key="node.id" class="topology-list-item">
                    <el-tag size="small" effect="plain">{{ node.kind }}</el-tag>
                    <span class="mono">{{ node.id }}</span>
                    <span>{{ node.label }}</span>
                  </div>
                </div>
                <el-empty v-else description="暂无节点数据" :image-size="72" />
              </div>

              <div class="topology-section">
                <div class="section-title">连线关系</div>
                <div v-if="store.topology?.edges?.length" class="topology-list">
                  <div
                    v-for="edge in visibleTopologyEdges"
                    :key="`${edge.source}-${edge.target}`"
                    class="topology-list-item edge-item"
                  >
                    <span class="mono">{{ edge.source }}</span>
                    <span class="arrow">→</span>
                    <span class="mono">{{ edge.target }}</span>
                  </div>
                </div>
                <el-empty v-else description="暂无连线数据" :image-size="72" />
              </div>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  min-height: 100%;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
}

.subtitle {
  margin: 0;
  color: #64748b;
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

.mb-4 {
  margin-bottom: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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

@media (max-width: 1200px) {
  .topology-grid {
    grid-template-columns: 1fr;
  }
}
</style>
