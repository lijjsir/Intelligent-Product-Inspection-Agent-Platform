<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useTaskStore } from "@/stores/task.store";
import { useAlertStore } from "@/stores/alert.store";
import { useRouter } from "vue-router";

const store = useAnalyticsStore();
const taskStore = useTaskStore();
const alertStore = useAlertStore();
const router = useRouter();

const todayTaskCount = computed(() => {
  const now = new Date();
  return taskStore.items.filter((task) => {
    if (!task.created_at) return false;
    const created = new Date(task.created_at);
    return (
      created.getFullYear() === now.getFullYear() &&
      created.getMonth() === now.getMonth() &&
      created.getDate() === now.getDate()
    );
  }).length;
});

const highRiskAlertCount = computed(() => {
  return alertStore.items.filter((alert) => {
    const severity = String(alert.severity || "").toLowerCase();
    return severity === "critical" || severity === "error";
  }).length;
});

onMounted(async () => {
  await Promise.all([
    store.fetchOverview(),
    taskStore.fetchTasks({ page: 1, page_size: 10 }),
    alertStore.fetchAlerts({ page: 1, page_size: 5, status: "open" }),
  ]);
});
</script>

<template>
  <div class="page-container">
    <div class="header">
      <h2 class="title">仪表盘</h2>
      <p class="subtitle">日常运营总览与快速入口</p>
    </div>

    <el-alert
      v-if="store.error"
      :title="store.error"
      type="warning"
      :closable="false"
      class="mb-4"
    />

    <!-- 数据核心卡片群 -->
    <el-row :gutter="20" v-if="store.overview" class="mb-4">
      <el-col :span="6">
        <el-card shadow="never" class="metric-card cursor-pointer" @click="router.push('/tasks')">
          <div class="metric-title">今日任务数</div>
          <div class="metric-value">{{ todayTaskCount }}</div>
          <div class="metric-footer">按任务创建时间统计</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">通过率</div>
          <div class="metric-value text-success">
            {{ (store.overview.pass_rate * 100).toFixed(1) }}%
          </div>
          <div class="metric-footer">当前组织历史通过占比</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card cursor-pointer" @click="router.push('/alerts')">
          <div class="metric-title">高风险预警数</div>
          <div class="metric-value text-danger">
            {{ highRiskAlertCount }}
          </div>
          <div class="metric-footer">OPEN 且级别为 CRITICAL/ERROR</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">平均耗时</div>
          <div class="metric-value text-warning">--</div>
          <div class="metric-footer">当前版本暂未聚合该指标</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mb-4">
      <template #header>快捷操作</template>
      <div class="quick-actions">
        <el-button type="primary" @click="router.push('/tasks')">新建任务</el-button>
        <el-button @click="router.push('/alerts')">进入预警中心</el-button>
        <el-button @click="router.push('/analytics')">查看分析中心</el-button>
      </div>
    </el-card>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never" class="table-card">
          <template #header>待处理预警（前5条）</template>
          <el-table :data="alertStore.items" size="small" empty-text="暂无待处理预警">
            <el-table-column prop="severity" label="级别" width="120" />
            <el-table-column prop="title" label="标题" min-width="220" />
            <el-table-column prop="created_at" label="触发时间" width="180" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="table-card">
          <template #header>最近任务（前10条）</template>
          <el-table :data="taskStore.items" size="small" empty-text="暂无任务数据">
            <el-table-column prop="id" label="任务编号" min-width="220" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column prop="product_id" label="产品编号" width="140" />
            <el-table-column prop="created_at" label="提交时间" width="180" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
  margin-bottom: 24px;
}

.title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.mb-4 {
  margin-bottom: 16px;
}

.metric-card {
  text-align: center;
  transition: all 0.2s ease;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
}

.cursor-pointer {
  cursor: pointer;
}

.metric-title {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 32px;
  font-weight: bold;
  color: #111827;
  margin-bottom: 8px;
}

.metric-footer {
  font-size: 12px;
  color: #9ca3af;
}

.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }

.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.table-card {
  height: 100%;
}
</style>
