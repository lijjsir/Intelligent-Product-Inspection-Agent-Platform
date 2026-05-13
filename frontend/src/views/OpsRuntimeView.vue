<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useAgentOpsStore } from "@/stores/agent-ops.store";

const store = useAgentOpsStore();
const loading = ref(false);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

onMounted(async () => {
  await fetchRuntimeData();
  refreshInterval = setInterval(fetchRuntimeData, 10000);
});

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval);
});

async function fetchRuntimeData() {
  loading.value = true;
  try {
    await Promise.all([store.fetchRuntimeOverview(), store.fetchRuntimeAgents()]);
  } catch {
    ElMessage.error("获取运行态数据失败");
  } finally {
    loading.value = false;
  }
}

function getStatusType(status: string) {
  const map: Record<string, "success" | "warning" | "danger" | "info"> = {
    running: "success",
    stopped: "info",
    failed: "danger",
    idle: "warning",
  };
  return map[status] || "info";
}
</script>

<template>
  <div class="flex flex-col gap-5" v-loading="loading">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">Agent 运行中心</h2>
      <p class="mt-2 text-sm text-zinc-500">展示真实运行态接口返回的 Agent 概览和运行单元状态。</p>
    </div>

    <div class="grid grid-cols-5 gap-4">
      <div>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ store.runtimeOverview?.active_agents ?? 0 }}</div>
          <div class="stat-label">启用 Agent</div>
        </el-card>
      </div>
      <div>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ store.runtimeOverview?.running_agents ?? 0 }}</div>
          <div class="stat-label">运行中</div>
        </el-card>
      </div>
      <div>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ store.runtimeOverview?.stopped_agents ?? 0 }}</div>
          <div class="stat-label">已停止</div>
        </el-card>
      </div>
      <div>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ store.runtimeOverview?.completed_today ?? 0 }}</div>
          <div class="stat-label">今日完成</div>
        </el-card>
      </div>
      <div>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ store.runtimeOverview?.avg_latency_ms ?? 0 }} ms</div>
          <div class="stat-label">平均延迟</div>
        </el-card>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>运行单元</span>
          <el-button type="primary" size="small" @click="fetchRuntimeData">刷新</el-button>
        </div>
      </template>
      <el-table :data="store.runtimeAgents" stripe>
        <el-table-column prop="agent_name" label="Agent" min-width="180" />
        <el-table-column prop="runtime_key" label="Runtime Key" min-width="200" show-overflow-tooltip />
        <el-table-column prop="subgraph_key" label="子图" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="execution_count" label="执行数" width="100" />
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
        <el-table-column label="最近执行" width="180">
          <template #default="{ row }">
            {{ row.last_executed_at ? new Date(row.last_executed_at).toLocaleString() : "-" }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>





.stat-card {
  text-align: center;
  padding: 12px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1d4ed8;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
