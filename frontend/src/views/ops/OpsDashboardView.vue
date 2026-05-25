<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useAlertStore } from "@/stores/alert.store";
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
const riskSummary = computed(() => {
  if (criticalAlerts.value.length || failedTasks.value.length) return "优先处理告警和失败任务";
  if (completedWithoutResult.value.length || runningTasks.value.length) return "重点盯执行队列和结果落库";
  return "今天的队列状态稳定，可以转去分析中心看趋势";
});
const healthTone = computed(() => {
  if (criticalAlerts.value.length || failedTasks.value.length) return "danger";
  if (completedWithoutResult.value.length || runningTasks.value.length) return "warning";
  return "success";
});
const healthLabel = computed(() => {
  if (healthTone.value === "danger") return "需要处理";
  if (healthTone.value === "warning") return "运行中";
  return "稳定";
});

type DashboardAction = {
  label: string;
  path: string;
};

const dashboardActions: DashboardAction[] = [
  { label: "任务查看", path: "/ops/tasks" },
  { label: "分析中心", path: "/ops/analytics" },
  { label: "告警管理", path: "/ops/alerts" },
  { label: "模型观测", path: "/ops/calls" },
  { label: "Agent 查看", path: "/ops/agents" },
  { label: "质检门槛查看", path: "/ops/inspection-specs" },
  { label: "个人设置", path: "/app/profile" },
];

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
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function go(path: string) {
  router.push(path);
}

function goTask(row: InspectionTask) {
  router.push(`/ops/tasks/${row.id}`);
}

async function fetchData() {
  loading.value = true;
  analyticsStore.fetchOverview().catch(() => undefined);
  try {
    const [, , result] = await Promise.allSettled([
      alertStore.fetchAlerts({ page: 1, size: 20, status: "open" }),
      taskStore.fetchTasks({ page: 1, size: 8 }),
      resultStore.fetchResults({ page: 1, size: 1, verdict: "manual_required" }),
    ]);
    if (result.status === "fulfilled") {
      pendingReviewCount.value = resultStore.total;
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<template>
  <div class="ops-shell" v-loading="loading">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Platform Ops Desk</p>
        <h2>平台运营工作台</h2>
        <p class="sub">
          先在这里处理今天要动作的任务、告警和人工审核，再去分析中心看趋势、去模型观测看 Token、成本和质检模型表现。
        </p>

        <div class="hero-pill-row">
          <span class="hero-pill">总任务 {{ taskStore.total.toLocaleString() }}</span>
          <span class="hero-pill">待处理告警 {{ openAlerts.length }}</span>
          <span class="hero-pill">分析中心通过率 {{ passRate }}</span>
        </div>
      </div>

      <div class="hero-side">
        <el-tag :type="healthTone" effect="dark" size="large" class="health-tag">{{ healthLabel }}</el-tag>
        <p class="hero-note">{{ riskSummary }}</p>
        <el-button class="hero-refresh" plain :loading="loading" @click="fetchData">刷新数据</el-button>
      </div>
    </section>

    <section class="metric-row">
      <button class="metric-card" @click="go('/ops/tasks')">
        <span class="mc-label">任务总数</span>
        <strong>{{ taskStore.total.toLocaleString() }}</strong>
        <span class="mc-sub">进入任务查看做逐条排查</span>
      </button>
      <button class="metric-card" @click="go('/ops/tasks?status=running')">
        <span class="mc-label">执行中任务</span>
        <strong>{{ runningTasks.length }}</strong>
        <span class="mc-sub">queued / running / reviewing</span>
      </button>
      <button class="metric-card danger" @click="go('/ops/tasks?status=failed')">
        <span class="mc-label">失败任务</span>
        <strong>{{ failedTasks.length }}</strong>
        <span class="mc-sub">优先检查执行链路和日志</span>
      </button>
      <button class="metric-card warning" @click="go('/ops/alerts')">
        <span class="mc-label">待处理告警</span>
        <strong>{{ openAlerts.length }}</strong>
        <span class="mc-sub">{{ criticalAlerts.length }} 条高优先级</span>
      </button>
      <button class="metric-card primary" @click="go('/app/results?verdict=manual_required')">
        <span class="mc-label">待人工审核</span>
        <strong>{{ pendingReviewCount }}</strong>
        <span class="mc-sub">需要专家进入结果页复核</span>
      </button>
      <button class="metric-card" @click="go('/ops/analytics')">
        <span class="mc-label">分析中心通过率</span>
        <strong>{{ passRate }}</strong>
        <span class="mc-sub">趋势、风险和质量追踪统一查看</span>
      </button>
    </section>

    <section class="work-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>最近任务</h3>
            <p>把上面的大盘数字落到具体任务，方便直接点进详情。</p>
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
            <h3>待处理队列</h3>
            <p>这里只放需要动作的项目，不再堆趋势型信息。</p>
          </div>
        </div>

        <div class="queue-list">
          <button
            v-if="pendingReviewCount"
            class="queue-item primary"
            @click="go('/app/results?verdict=manual_required')"
          >
            <strong>{{ pendingReviewCount }} 条结果待人工审核</strong>
            <span>进入结果列表做最终复核和裁定</span>
          </button>

          <button
            v-if="failedTasks.length"
            class="queue-item danger"
            @click="go('/ops/tasks?status=failed')"
          >
            <strong>{{ failedTasks.length }} 个任务失败</strong>
            <span>建议先看任务详情，再对照告警管理排查</span>
          </button>

          <button
            v-if="completedWithoutResult.length"
            class="queue-item warning"
            @click="go('/ops/tasks?status=done')"
          >
            <strong>{{ completedWithoutResult.length }} 个任务完成但未落结果</strong>
            <span>重点核对结果入库和后续链路</span>
          </button>

          <button v-for="alert in openAlerts.slice(0, 5)" :key="alert.id" class="queue-item" @click="go('/ops/alerts')">
            <strong>{{ alert.title }}</strong>
            <span>{{ alert.severity }} · {{ formatTime(alert.created_at) }}</span>
          </button>

          <el-empty
            v-if="!pendingReviewCount && !failedTasks.length && !completedWithoutResult.length && !openAlerts.length"
            description="当前没有待处理事项"
            :image-size="56"
          />
        </div>
      </div>
    </section>

    <section class="support-row" aria-label="平台运营工作台快捷入口">
      <el-button
        v-for="item in dashboardActions"
        :key="item.label"
        plain
        @click="go(item.path)"
      >
        {{ item.label }}
      </el-button>
    </section>
  </div>
</template>

<style scoped>
.ops-shell {
  min-height: 100vh;
  display: grid;
  gap: 18px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(71, 85, 105, 0.16), transparent 24%),
    radial-gradient(circle at right top, rgba(148, 163, 184, 0.18), transparent 26%),
    linear-gradient(180deg, #f8fafc 0%, #e5e7eb 100%);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  color: #f8fafc;
  background:
    radial-gradient(circle at top right, rgba(203, 213, 225, 0.22), transparent 30%),
    linear-gradient(135deg, #111827 0%, #334155 52%, #475569 100%);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.18);
}

.hero-copy {
  max-width: 780px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.76;
}

.hero h2 {
  margin: 0;
  font-size: 40px;
}

.sub {
  margin: 12px 0 0;
  color: rgba(248, 250, 252, 0.84);
  line-height: 1.7;
}

.hero-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.hero-pill {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 13px;
  color: rgba(248, 250, 252, 0.92);
}

.hero-side {
  display: flex;
  min-width: 280px;
  flex-direction: column;
  align-items: flex-end;
  gap: 14px;
}

.health-tag {
  border-radius: 999px;
  padding-inline: 12px;
}

.hero-note {
  margin: 0;
  text-align: right;
  color: rgba(248, 250, 252, 0.82);
  font-size: 13px;
  line-height: 1.6;
}

.hero-refresh {
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  font-weight: 700;
}

.hero-refresh:hover,
.hero-refresh:focus {
  border-color: rgba(255, 255, 255, 0.44);
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: grid;
  gap: 4px;
  min-height: 120px;
  padding: 18px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.04);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.metric-card:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.24);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.08);
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
  line-height: 1.5;
}

.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
}

.panel {
  min-width: 0;
  padding: 18px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
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
  font-size: 18px;
}

.panel p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.task-table {
  cursor: pointer;
}

.queue-list {
  display: grid;
  gap: 10px;
}

.queue-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #f8fafc;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
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
  line-height: 1.5;
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

.support-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  padding: 14px 16px;
  border: 1px solid rgba(16, 36, 61, 0.08);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.92)),
    radial-gradient(circle at left center, rgba(71, 85, 105, 0.1), transparent 32%);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.05);
}

.support-row :deep(.el-button) {
  min-width: 116px;
  margin-left: 0;
  border-radius: 10px;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .metric-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .work-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .ops-shell {
    padding: 14px;
  }

  .hero {
    flex-direction: column;
  }

  .hero-side {
    min-width: 0;
    align-items: flex-start;
  }

  .hero-note {
    text-align: left;
  }

  .metric-row {
    grid-template-columns: 1fr;
  }

  .support-row :deep(.el-button) {
    flex: 1 1 132px;
  }
}
</style>
