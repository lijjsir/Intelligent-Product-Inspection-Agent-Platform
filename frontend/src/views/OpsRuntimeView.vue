<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import { ElMessage } from "element-plus";

const auth = useAuthStore();
const loading = ref(false);

const runtimeStats = ref({
  activeAgents: 0,
  queuedTasks: 0,
  completedToday: 0,
  avgLatency: 0,
  gpuUtilization: 0,
  memoryUsage: 0,
});

const agentList = ref([
  { id: "1", name: "vision-inspector", status: "running", tasks: 5, latency: 1.2 },
  { id: "2", name: "knowledge-retriever", status: "idle", tasks: 0, latency: 0.8 },
  { id: "3", name: "reasoning-engine", status: "running", tasks: 3, latency: 2.1 },
]);

const queueItems = ref([
  { id: "1", taskId: "task-001", priority: "high", status: "pending", createdAt: new Date().toISOString() },
  { id: "2", taskId: "task-002", priority: "normal", status: "processing", createdAt: new Date().toISOString() },
  { id: "3", taskId: "task-003", priority: "low", status: "pending", createdAt: new Date().toISOString() },
]);

let refreshInterval: ReturnType<typeof setInterval> | null = null;

onMounted(async () => {
  await fetchRuntimeData();
  refreshInterval = setInterval(fetchRuntimeData, 5000);
});

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval);
  }
});

async function fetchRuntimeData() {
  loading.value = true;
  try {
    runtimeStats.value = {
      activeAgents: 3,
      queuedTasks: 12,
      completedToday: 156,
      avgLatency: 1.45,
      gpuUtilization: 78,
      memoryUsage: 62,
    };
  } catch (e) {
    ElMessage.error("获取运行数据失败");
  } finally {
    loading.value = false;
  }
}

function getStatusType(status: string) {
  const map: Record<string, "success" | "warning" | "danger" | "info"> = {
    running: "success",
    idle: "info",
    error: "danger",
    pending: "warning",
    processing: "primary",
  };
  return map[status] || "info";
}

function getPriorityType(priority: string) {
  const map: Record<string, "danger" | "warning" | "info"> = {
    high: "danger",
    normal: "warning",
    low: "info",
  };
  return map[priority] || "info";
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <h2 class="title">Agent 运行中心</h2>
      <p class="subtitle">实时监控 Agent 运行状态与任务队列</p>
    </div>

    <el-row :gutter="20" class="mb-4">
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ runtimeStats.activeAgents }}</div>
          <div class="stat-label">活跃 Agent</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value text-warning">{{ runtimeStats.queuedTasks }}</div>
          <div class="stat-label">队列任务</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value text-success">{{ runtimeStats.completedToday }}</div>
          <div class="stat-label">今日完成</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ runtimeStats.avgLatency.toFixed(2) }}s</div>
          <div class="stat-label">平均延迟</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value" :class="runtimeStats.gpuUtilization > 80 ? 'text-danger' : 'text-success'">
            {{ runtimeStats.gpuUtilization }}%
          </div>
          <div class="stat-label">GPU 利用率</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value" :class="runtimeStats.memoryUsage > 80 ? 'text-danger' : 'text-success'">
            {{ runtimeStats.memoryUsage }}%
          </div>
          <div class="stat-label">内存使用</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never" class="mb-4">
          <template #header>
            <div class="card-header">
              <span>Agent 实例状态</span>
              <el-button type="primary" size="small" @click="fetchRuntimeData">刷新</el-button>
            </div>
          </template>
          <el-table :data="agentList" stripe>
            <el-table-column prop="name" label="Agent 名称" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" size="small">
                  {{ row.status.toUpperCase() }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="tasks" label="当前任务数" width="100" />
            <el-table-column prop="latency" label="平均延迟 (s)" width="120">
              <template #default="{ row }">
                {{ row.latency.toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>任务队列</span>
              <el-tag type="info" size="small">{{ queueItems.length }} 项</el-tag>
            </div>
          </template>
          <el-table :data="queueItems" stripe>
            <el-table-column prop="taskId" label="任务 ID" />
            <el-table-column prop="priority" label="优先级" width="80">
              <template #default="{ row }">
                <el-tag :type="getPriorityType(row.priority)" size="small">
                  {{ row.priority.toUpperCase() }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" size="small">
                  {{ row.status.toUpperCase() }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="创建时间" width="180">
              <template #default="{ row }">
                {{ new Date(row.createdAt).toLocaleString() }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background: #f3f4f6;
  min-height: 100%;
}

.header {
  margin-bottom: 24px;
}

.title {
  margin: 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 14px;
}

.mb-4 {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 12px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1b3a5c;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.text-success {
  color: #16a34a;
}

.text-warning {
  color: #d97706;
}

.text-danger {
  color: #dc2626;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
