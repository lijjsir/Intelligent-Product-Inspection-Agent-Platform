<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useAlertStore } from "@/stores/alert.store";
import { ALERT_SEVERITY_LABELS } from "@/constants/spec";
import { useTaskStore } from "@/stores/task.store";
import { useResultStore } from "@/stores/result.store";
import type { InspectionTask } from "@/types/task.types";

const router = useRouter();
const analyticsStore = useAnalyticsStore();
const alertStore = useAlertStore();
const taskStore = useTaskStore();
const resultStore = useResultStore();
const loading = ref(false);
const pendingReviewCount = ref(0);

const overview = computed(() => analyticsStore.overview);
const alerts = computed(() => alertStore.items);
const recentTasks = computed(() => taskStore.items);
const openAlerts = computed(() => alerts.value.filter((item) => item.status === "open"));
const criticalAlerts = computed(() => openAlerts.value.filter((item) => item.severity === "critical" || item.severity === "error"));
const runningTasks = computed(() => recentTasks.value.filter((item) => ["queued", "running", "reviewing"].includes(item.status)));
const failedTasks = computed(() => recentTasks.value.filter((item) => item.status === "failed"));
const completedWithoutResult = computed(() => recentTasks.value.filter((item) => item.status === "done" && !item.has_result));
const passRate = computed(() => overview.value ? `${(overview.value.pass_rate * 100).toFixed(1)}%` : "-");
const healthTone = computed(() => {
  if (criticalAlerts.value.length || failedTasks.value.length) return "danger";
  if (completedWithoutResult.value.length || runningTasks.value.length) return "warning";
  return "success";
});
const healthLabel = computed(() => {
  if (healthTone.value === "danger") return "需要处理";
  if (healthTone.value === "warning") return "运行中";
  return "正常";
});

function statusType(status: string) {
  const map: Record<string, "info" | "primary" | "success" | "danger" | "warning"> = {
    pending: "info",
    queued: "warning",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function go(path: string) {
  router.push(path);
}

function goTask(row: InspectionTask) {
  router.push(`/ops/tasks/${row.id}`);
}

async function fetchData() {
  loading.value = true;
  try {
    await Promise.all([
      analyticsStore.fetchOverview(),
      alertStore.fetchAlerts({ page: 1, size: 20, status: "open" }),
      taskStore.fetchTasks({ page: 1, size: 8 }),
      resultStore.fetchResults({ page: 1, size: 1, verdict: "manual_required" }),
    ]);
    pendingReviewCount.value = resultStore.total;
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<template>
  <div class="ops-shell" v-loading="loading">
    <section class="ops-header">
      <div>
        <p class="eyebrow">Platform Ops</p>
        <h2>平台运维工作台</h2>
        <p class="sub">聚焦今天要处理的任务、告警和数据缺口；长期趋势留在分析中心。</p>
      </div>
      <el-tag :type="healthTone" effect="dark" size="large">{{ healthLabel }}</el-tag>
    </section>

    <section class="metric-row">
      <button class="metric-card" @click="go('/ops/tasks')">
        <span class="mc-label">可见任务总数</span>
        <strong>{{ taskStore.total.toLocaleString() }}</strong>
        <span class="mc-sub">点击查看具体任务</span>
      </button>
      <button class="metric-card" @click="go('/ops/tasks?status=running')">
        <span class="mc-label">执行中任务</span>
        <strong>{{ runningTasks.length }}</strong>
        <span class="mc-sub">queued / running / reviewing</span>
      </button>
      <button class="metric-card danger" @click="go('/ops/tasks?status=failed')">
        <span class="mc-label">失败任务</span>
        <strong>{{ failedTasks.length }}</strong>
        <span class="mc-sub">需要排查执行日志</span>
      </button>
      <button class="metric-card warning" @click="go('/ops/alerts')">
        <span class="mc-label">待处理告警</span>
        <strong>{{ openAlerts.length }}</strong>
        <span class="mc-sub">{{ criticalAlerts.length }} 条严重</span>
      </button>
      <button class="metric-card primary" @click="go('/app/results?verdict=manual_required')">
        <span class="mc-label">待人工审核</span>
        <strong>{{ pendingReviewCount }}</strong>
        <span class="mc-sub">需要专家复核</span>
      </button>
      <button class="metric-card" @click="go('/ops/analytics')">
        <span class="mc-label">分析中心通过率</span>
        <strong>{{ passRate }}</strong>
        <span class="mc-sub">趋势、分布和模型对比</span>
      </button>
    </section>

    <section class="work-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>最近质检任务</h3>
            <p>这里解释“总任务数”背后是哪几个任务。</p>
          </div>
          <el-button size="small" type="primary" plain @click="go('/ops/tasks')">全部任务</el-button>
        </div>
        <el-table :data="recentTasks" size="small" class="task-table" @row-click="goTask">
          <el-table-column prop="id" label="任务 ID" min-width="220" show-overflow-tooltip />
          <el-table-column prop="product_id" label="产品" width="120" />
          <el-table-column prop="spec_code" label="标准" min-width="160" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="source_kind" label="来源" width="120" />
          <el-table-column prop="created_at" label="创建时间" width="150">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="panel side-panel">
        <div class="panel-head compact">
          <div>
            <h3>待处理事项</h3>
            <p>工作台只放需要动作的队列。</p>
          </div>
        </div>
        <div class="queue-list">
          <button v-if="pendingReviewCount" class="queue-item primary" @click="go('/app/results?verdict=manual_required')">
            <strong>{{ pendingReviewCount }} 条结果待人工审核</strong>
            <span>需专家登录进行复核裁定</span>
          </button>
          <button v-if="failedTasks.length" class="queue-item danger" @click="go('/ops/tasks?status=failed')">
            <strong>{{ failedTasks.length }} 个任务失败</strong>
            <span>查看任务详情和执行日志</span>
          </button>
          <button v-if="completedWithoutResult.length" class="queue-item warning" @click="go('/ops/tasks?status=done')">
            <strong>{{ completedWithoutResult.length }} 个完成任务缺少结果</strong>
            <span>核对结果落库和稳定性报告</span>
          </button>
          <button v-for="alert in openAlerts.slice(0, 5)" :key="alert.id" class="queue-item" @click="go('/ops/alerts')">
            <strong>{{ alert.title }}</strong>
            <span>{{ alert.severity }} · {{ formatTime(alert.created_at) }}</span>
          </button>
          <el-empty v-if="!failedTasks.length && !completedWithoutResult.length && !openAlerts.length" description="暂无待处理事项" :image-size="56" />
        </div>
      </div>
    </section>

    <section class="quick-row">
      <el-button @click="fetchData">刷新</el-button>
      <el-button @click="go('/ops/analytics')">分析中心</el-button>
      <el-button @click="go('/ops/data-quality')">数据质量</el-button>
      <el-button @click="go('/ops/calls')">调用监控</el-button>
      <el-button @click="go('/ops/inspection-specs')">检测标准</el-button>
    </section>
  </div>
</template>

<style scoped>
.ops-shell {
  display: grid;
  gap: 16px;
  padding: 20px;
}

.ops-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 22px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.eyebrow {
  margin: 0 0 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.ops-header h2 {
  margin: 0;
  color: #0f172a;
  font-size: 24px;
}

.sub {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: grid;
  gap: 4px;
  min-height: 112px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.metric-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.metric-card strong {
  color: #0f172a;
  font-size: 30px;
  line-height: 1;
}

.metric-card.danger strong {
  color: #dc2626;
}

.metric-card.warning strong {
  color: #d97706;
}

.metric-card.primary strong {
  color: #2563eb;
}

.mc-label {
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

.mc-sub {
  color: #94a3b8;
  font-size: 12px;
}

.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
}

.panel {
  min-width: 0;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-head.compact {
  margin-bottom: 8px;
}

.panel h3 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
}

.panel p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}

.task-table {
  cursor: pointer;
}

.queue-list {
  display: grid;
  gap: 8px;
}

.queue-item {
  display: grid;
  gap: 3px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
  text-align: left;
  cursor: pointer;
}

.queue-item:hover {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.queue-item strong {
  color: #0f172a;
  font-size: 13px;
}

.queue-item span {
  color: #64748b;
  font-size: 12px;
}

.queue-item.danger {
  background: #fef2f2;
  border-color: #fecaca;
}

.queue-item.warning {
  background: #fffbeb;
  border-color: #fde68a;
}

.queue-item.primary {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.quick-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 1200px) {
  .metric-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .work-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .ops-shell {
    padding: 12px;
  }

  .ops-header {
    flex-direction: column;
  }

  .metric-row {
    grid-template-columns: 1fr;
  }
}
</style>
