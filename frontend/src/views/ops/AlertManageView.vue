<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAlertStore } from "@/stores/alert.store";
import { useAlertRuleStore } from "@/stores/alert-rule.store";
import type { AlertEvent, AlertAction } from "@/types/alert.types";
import type { AlertRule } from "@/types/alert-rule.types";

const alertStore = useAlertStore();
const alertRuleStore = useAlertRuleStore();
const route = useRoute();
const router = useRouter();

type TabName = "alerts" | "rules";
const activeTab = ref<TabName>("alerts");

// ===== Alert List State =====
const statusFilter = ref<string>("");
const severityFilter = ref<string>("");
const page = ref(1);
const size = ref(20);
const drawerVisible = ref(false);
const drawerAlert = ref<AlertEvent | null>(null);
const actionNote = ref("");
const actionLoading = ref(false);

const severityTag: Record<string, string> = {
  critical: "danger", error: "danger", warning: "warning", info: "info",
};
const severityLabel: Record<string, string> = {
  critical: "严重", error: "错误", warning: "警告", info: "提示",
};
const severityOrder = ["critical", "error", "warning", "info"];
const statusLabel: Record<string, string> = {
  open: "待响应", acknowledged: "已接收", suppressed: "已静默", resolved: "已关闭",
};
const statusTag: Record<string, string> = {
  open: "danger", acknowledged: "warning", suppressed: "info", resolved: "success",
};

const items = computed(() => alertStore.items);
const total = computed(() => alertStore.total);
const loading = computed(() => alertStore.loading);

const stats = computed(() => {
  const counts: Record<string, number> = { open: 0, acknowledged: 0, suppressed: 0, resolved: 0, critical: 0, error: 0, warning: 0, info: 0 };
  for (const a of items.value) {
    if (Object.prototype.hasOwnProperty.call(counts, a.status)) (counts as any)[a.status]++;
    if (Object.prototype.hasOwnProperty.call(counts, a.severity)) (counts as any)[a.severity]++;
  }
  return counts;
});

const severityDistribution = computed(() =>
  severityOrder
    .filter((k) => stats.value[k] > 0)
    .map((k) => ({ key: k, label: severityLabel[k] || k, count: stats.value[k] }))
);
const maxSeverityCount = computed(() => Math.max(...severityDistribution.value.map((s) => s.count), 1));

async function fetchAlerts() {
  await alertStore.fetchAlerts({ page: page.value, size: size.value, status: statusFilter.value || undefined, severity: severityFilter.value || undefined });
}

function syncFromRoute() {
  statusFilter.value = String(route.query.status || "");
  severityFilter.value = String(route.query.severity || "");
  page.value = Number(route.query.page || 1);
  size.value = Number(route.query.size || 20);
}

function pushQuery() {
  router.push({
    path: "/ops/alerts",
    query: {
      ...(statusFilter.value ? { status: statusFilter.value } : {}),
      ...(severityFilter.value ? { severity: severityFilter.value } : {}),
      ...(page.value !== 1 ? { page: String(page.value) } : {}),
      ...(size.value !== 20 ? { size: String(size.value) } : {}),
    },
  });
}

function onFilterChange() {
  page.value = 1;
  pushQuery();
}

function openDrawer(alert: AlertEvent) {
  drawerAlert.value = alert;
  actionNote.value = "";
  drawerVisible.value = true;
}

function closeDrawer() {
  drawerVisible.value = false;
  drawerAlert.value = null;
  actionNote.value = "";
}

async function handleAction(alert: AlertEvent, action: AlertAction) {
  if (action === "suppress" && !actionNote.value.trim()) {
    ElMessage.warning("静默/压制必须填写原因");
    return;
  }
  actionLoading.value = true;
  try {
    switch (action) {
      case "acknowledge": await alertStore.ackAlert(alert.id, actionNote.value || undefined); ElMessage.success("已接收告警"); break;
      case "suppress": await alertStore.suppressAlert(alert.id, actionNote.value); ElMessage.success("已静默告警"); break;
      case "resolve": await alertStore.resolveAlert(alert.id, actionNote.value || undefined); ElMessage.success("已关闭告警"); break;
    }
    actionNote.value = "";
    const updated = alertStore.items.find((a) => a.id === alert.id);
    if (updated) drawerAlert.value = updated;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "操作失败");
  } finally {
    actionLoading.value = false;
  }
}

function onPageChange(p: number) { page.value = p; pushQuery(); }
function onSizeChange(s: number) { size.value = s; page.value = 1; pushQuery(); }
function formatTime(ts?: string) {
  if (!ts) return "-";
  const dt = new Date(ts);
  if (Number.isNaN(dt.getTime())) return ts;
  return dt.toLocaleString("zh-CN", { hour12: false });
}
function severBarClass(key: string) {
  return { critical: "bar-critical", error: "bar-error", warning: "bar-warning", info: "bar-info" }[key] || "bar-info";
}

function alertTaskId(alert?: AlertEvent | null) {
  const match = alert?.title?.match(/任务\s+([0-9a-fA-F-]{8,})/);
  return match?.[1] || "";
}

function shortId(id: string) {
  return id.length > 18 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
}

function alertRuleName(alert: AlertEvent) {
  const match = alert.title.match(/[（(]规则[:：]\s*([^)）]+)[)）]/);
  return match?.[1] || "";
}

function alertRowTitle(alert: AlertEvent) {
  const ruleName = alertRuleName(alert);
  return ruleName ? `规则：${ruleName}` : alert.title;
}

function goTask(alert: AlertEvent) {
  const taskId = alertTaskId(alert);
  if (taskId) router.push(`/ops/tasks/${taskId}`);
}

function goStability(alert: AlertEvent) {
  const taskId = alertTaskId(alert);
  if (taskId) router.push(`/app/stability/${taskId}`);
}

function goManualReview(alert: AlertEvent) {
  const taskId = alertTaskId(alert);
  if (taskId) router.push(`/app/results?task_id=${taskId}&verdict=manual_required`);
}

// ===== Alert Rules State =====
const rulePage = ref(1);
const ruleSize = ref(20);
const searchEnabled = ref<string>("");

const ruleItems = computed(() => alertRuleStore.items);
const ruleTotal = computed(() => alertRuleStore.total);
const rulesLoading = computed(() => alertRuleStore.loading);

const alertTypeLabel: Record<string, string> = {
  stability_risk: "稳定性风险", quality_review: "质检审核", model_error: "模型错误",
  high_latency: "延迟过高", cost_spike: "成本激增", pass_rate_drop: "通过率下降",
  hallucination_rise: "幻觉率上升", data_quality: "数据质量", system_error: "系统异常",
  custom: "自定义",
};

async function fetchRules() {
  const params: any = { page: rulePage.value, size: ruleSize.value };
  if (searchEnabled.value !== "") params.enabled = searchEnabled.value === "true";
  await alertRuleStore.fetchRules(params);
}

function onRulePageChange(p: number) { rulePage.value = p; fetchRules(); }
function onRuleSizeChange(s: number) { ruleSize.value = s; rulePage.value = 1; fetchRules(); }

onMounted(() => {
  syncFromRoute();
  fetchAlerts();
  fetchRules();
});

watch(
  () => route.query,
  async () => {
    syncFromRoute();
    await fetchAlerts();
  },
);
</script>

<template>
  <div class="alert-shell">
    <section class="hero">
      <p class="eyebrow">Alert Intelligence</p>
      <h2>告警管理</h2>
      <p class="sub">运营侧负责告警响应和分诊；专家人工审核在检测结果页完成，规则治理归管理员维护。</p>
    </section>

    <!-- Tabs -->
    <nav class="alert-tabs">
      <button :class="['tab-btn', { active: activeTab === 'alerts' }]" @click="activeTab = 'alerts'">告警列表</button>
      <button :class="['tab-btn', { active: activeTab === 'rules' }]" @click="activeTab = 'rules'">告警规则</button>
    </nav>

    <!-- === Alerts List Tab === -->
    <template v-if="activeTab === 'alerts'">
      <section class="stat-row">
        <div class="stat-card"><span class="stat-label">总告警</span><span class="stat-value">{{ total }}</span></div>
        <div class="stat-card stat-open"><span class="stat-label">待响应</span><span class="stat-value">{{ stats.open }}</span></div>
        <div class="stat-card stat-ack"><span class="stat-label">已接收</span><span class="stat-value">{{ stats.acknowledged }}</span></div>
        <div class="stat-card stat-resolved"><span class="stat-label">已关闭</span><span class="stat-value">{{ stats.resolved }}</span></div>
      </section>

      <section class="ops-note">
        <strong>不是专家审核流程</strong>
        <span>接收、静默、关闭是三种互斥响应动作，不需要依次点击。静默表示已知重复、误报或暂不提醒；关闭表示确认根因已经恢复。</span>
      </section>

      <el-card v-if="severityDistribution.length" shadow="never" class="panel-card">
        <template #header>
          <div class="card-head"><strong>告警分布</strong><span>按当前筛选结果统计告警严重度分布</span></div>
        </template>
        <div class="distro-list">
          <div v-for="s in severityDistribution" :key="s.key" class="distro-row">
            <el-tag :type="severityTag[s.key] || 'info'" size="small" effect="dark" class="distro-tag">{{ s.label }}</el-tag>
            <div class="distro-bar-bg"><div :class="['distro-bar', severBarClass(s.key)]" :style="{ width: `${(s.count / maxSeverityCount) * 100}%` }" /></div>
            <span class="distro-count">{{ s.count }}</span>
          </div>
        </div>
      </el-card>

      <div class="filter-bar">
        <div class="filter-group">
          <label>状态</label>
          <el-select v-model="statusFilter" size="default" clearable placeholder="全部" @change="onFilterChange">
            <el-option label="待响应" value="open" />
            <el-option label="已接收" value="acknowledged" />
            <el-option label="已静默" value="suppressed" />
            <el-option label="已关闭" value="resolved" />
          </el-select>
        </div>
        <div class="filter-group">
          <label>严重度</label>
          <el-select v-model="severityFilter" size="default" clearable placeholder="全部" @change="onFilterChange">
            <el-option label="严重" value="critical" />
            <el-option label="错误" value="error" />
            <el-option label="警告" value="warning" />
            <el-option label="提示" value="info" />
          </el-select>
        </div>
        <el-button @click="fetchAlerts">刷新</el-button>
      </div>

      <el-card shadow="never" class="table-card">
        <el-table :data="items" :loading="loading" size="default" empty-text="暂无告警" highlight-current-row class="alert-table" @row-click="openDrawer">
          <el-table-column label="级别" width="84">
            <template #default="{ row }"><el-tag :type="severityTag[row.severity] || 'info'" size="small" effect="dark">{{ severityLabel[row.severity] || row.severity }}</el-tag></template>
          </el-table-column>
          <el-table-column label="任务" width="158">
            <template #default="{ row }">
              <el-button v-if="alertTaskId(row)" link type="primary" class="task-link" @click.stop="goTask(row)">
                {{ shortId(alertTaskId(row)) }}
              </el-button>
              <span v-else class="time-cell">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="规则 / 标题" min-width="320">
            <template #default="{ row }">
              <div class="title-stack">
                <span class="alert-title">{{ alertRowTitle(row) }}</span>
                <span v-if="alertRuleName(row)" class="alert-subtitle">{{ row.title }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="140">
            <template #default="{ row }">{{ alertTypeLabel[row.alert_type] || row.alert_type }}</template>
          </el-table-column>
          <el-table-column label="状态" width="94">
            <template #default="{ row }"><el-tag :type="statusTag[row.status] || 'info'" size="small">{{ statusLabel[row.status] || row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="时间" width="176">
            <template #default="{ row }"><span class="time-cell">{{ formatTime(row.created_at) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'open' || row.status === 'acknowledged'">
                <el-button size="small" type="primary" plain @click.stop="openDrawer(row)">响应</el-button>
              </template>
              <span v-else class="text-zinc-400 text-[13px]">-</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @current-change="onPageChange" @size-change="onSizeChange" />
        </div>
      </el-card>

      <!-- Detail Drawer -->
      <el-drawer v-model="drawerVisible" :title="drawerAlert?.title || '告警详情'" size="480px" direction="rtl" @close="closeDrawer">
        <template v-if="drawerAlert">
          <div class="drawer-body">
            <div class="drawer-header">
              <div class="drawer-tags">
                <el-tag :type="severityTag[drawerAlert.severity] || 'info'" size="default" effect="dark">{{ severityLabel[drawerAlert.severity] || drawerAlert.severity }}</el-tag>
                <el-tag :type="statusTag[drawerAlert.status] || 'info'" size="default">{{ statusLabel[drawerAlert.status] || drawerAlert.status }}</el-tag>
                <el-tag type="" size="default">{{ alertTypeLabel[drawerAlert.alert_type] || drawerAlert.alert_type }}</el-tag>
              </div>
              <p class="drawer-time">{{ formatTime(drawerAlert.created_at) }}</p>
            </div>
            <div class="drawer-section">
              <h4>告警详情</h4>
              <pre class="detail-pre">{{ drawerAlert.detail ? JSON.stringify(drawerAlert.detail, null, 2) : "无详情" }}</pre>
            </div>
            <div v-if="alertTaskId(drawerAlert)" class="drawer-section">
              <h4>关联入口</h4>
              <div class="relation-actions">
                <el-button plain @click="goTask(drawerAlert)">任务详情</el-button>
                <el-button plain @click="goStability(drawerAlert)">稳定性报告</el-button>
                <el-button plain @click="goManualReview(drawerAlert)">人工审核结果</el-button>
              </div>
            </div>
            <div class="drawer-section">
              <h4>操作记录</h4>
              <div class="timeline">
                <div v-if="drawerAlert.ack_at" class="tl-item"><span class="tl-dot ack" /><div class="tl-body"><span class="tl-title">已接收</span><span class="tl-time">{{ formatTime(drawerAlert.ack_at) }}</span><span v-if="drawerAlert.ack_by" class="tl-by">{{ drawerAlert.ack_by }}</span></div></div>
                <div v-if="drawerAlert.suppressed_at" class="tl-item"><span class="tl-dot suppressed" /><div class="tl-body"><span class="tl-title">已静默</span><span class="tl-time">{{ formatTime(drawerAlert.suppressed_at) }}</span><span v-if="drawerAlert.action_note" class="tl-note">{{ drawerAlert.action_note }}</span></div></div>
                <div v-if="drawerAlert.resolved_at" class="tl-item"><span class="tl-dot resolved" /><div class="tl-body"><span class="tl-title">已关闭</span><span class="tl-time">{{ formatTime(drawerAlert.resolved_at) }}</span></div></div>
                <div v-if="!drawerAlert.ack_at && !drawerAlert.suppressed_at && !drawerAlert.resolved_at" class="tl-empty">暂无操作记录</div>
              </div>
            </div>
            <div v-if="drawerAlert.status === 'open' || drawerAlert.status === 'acknowledged'" class="drawer-actions">
              <h4>响应动作</h4>
              <p class="action-help">三种动作任选其一；运营无法直接修复模型时，优先跳到任务或人工审核入口分派处理。</p>
              <el-input v-model="actionNote" type="textarea" :rows="3" placeholder="操作备注（静默/压制必须填写原因）" />
              <div class="action-btns">
                <template v-if="drawerAlert.status === 'open'">
                  <el-button type="warning" :loading="actionLoading" @click="handleAction(drawerAlert, 'acknowledge')">接收跟进</el-button>
                </template>
                <el-button type="info" :loading="actionLoading" @click="handleAction(drawerAlert, 'suppress')">静默/压制</el-button>
                <el-button type="primary" :loading="actionLoading" @click="handleAction(drawerAlert, 'resolve')">关闭告警</el-button>
              </div>
            </div>
          </div>
        </template>
      </el-drawer>
    </template>

    <!-- === Rules Tab === -->
    <template v-if="activeTab === 'rules'">
      <section class="stat-row">
        <div class="stat-card"><span class="stat-label">规则总数</span><span class="stat-value">{{ ruleTotal }}</span></div>
        <div class="stat-card stat-open"><span class="stat-label">严重级别</span><span class="stat-value">{{ ruleItems.filter((r: AlertRule) => r.severity === 'critical').length }}</span></div>
        <div class="stat-card stat-ack"><span class="stat-label">警告级别</span><span class="stat-value">{{ ruleItems.filter((r: AlertRule) => r.severity === 'warning').length }}</span></div>
        <div class="stat-card stat-resolved"><span class="stat-label">已启用</span><span class="stat-value">{{ ruleItems.filter((r: AlertRule) => r.enabled).length }}</span></div>
      </section>

      <div class="filter-bar">
        <div class="filter-group">
          <label>启用状态</label>
          <el-select v-model="searchEnabled" size="default" clearable placeholder="全部" @change="() => { rulePage = 1; fetchRules(); }">
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
        </div>
        <el-button @click="fetchRules">刷新</el-button>
      </div>

      <el-alert
        title="平台运营可查看告警规则用于排障核对；新增、编辑、启停和删除请到管理员的系统治理中处理。"
        type="info"
        :closable="false"
        show-icon
      />

      <el-card shadow="never" class="table-card">
        <el-table :data="ruleItems" :loading="rulesLoading" size="default" empty-text="暂无告警规则" class="rule-table">
          <el-table-column prop="name" label="规则名称" min-width="200">
            <template #default="{ row }"><span class="rule-name">{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column label="告警类型" width="140">
            <template #default="{ row }"><span class="type-cell">{{ alertTypeLabel[row.alert_type] || row.alert_type }}</span></template>
          </el-table-column>
          <el-table-column label="严重度" width="84">
            <template #default="{ row }"><el-tag :type="severityTag[row.severity] || 'info'" size="small" effect="dark">{{ severityLabel[row.severity] || row.severity }}</el-tag></template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'info'">
                {{ row.enabled ? "已启用" : "已停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="冷却时间" width="100">
            <template #default="{ row }"><span class="cool-cell">{{ row.cooldown_seconds }}s</span></template>
          </el-table-column>
          <el-table-column label="更新时间" width="176">
            <template #default="{ row }"><span class="time-cell">{{ formatTime(row.updated_at) }}</span></template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination v-model:current-page="rulePage" v-model:page-size="ruleSize" :total="ruleTotal" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @current-change="onRulePageChange" @size-change="onRuleSizeChange" />
        </div>
      </el-card>

    </template>
  </div>
</template>

<style scoped>
.alert-shell {
  min-height: 100vh;
  display: grid;
  gap: 18px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(220, 38, 38, 0.13), transparent 24%),
    radial-gradient(circle at right top, rgba(251, 146, 60, 0.16), transparent 25%),
    linear-gradient(180deg, #fff1f2 0%, #fff7ed 100%);
}

.hero {
  padding: 28px; border-radius: 24px;
  background:
    radial-gradient(circle at 88% 16%, rgba(253, 186, 116, 0.24), transparent 30%),
    linear-gradient(135deg, #450a0a 0%, #991b1b 52%, #ea580c 100%);
  color: #f8fafc;
  box-shadow: 0 24px 60px rgba(153, 27, 27, 0.16);
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.alert-tabs { display: flex; gap: 4px; background: rgba(255,255,255,.7); border-radius: 12px; padding: 4px; width: fit-content; }
.tab-btn {
  padding: 8px 20px; border-radius: 8px; border: none; background: transparent;
  color: #64748b; font-size: 14px; font-weight: 500; cursor: pointer; transition: all .2s;
}
.tab-btn:hover { color: #991b1b; background: rgba(255,255,255,.6); }
.tab-btn.active { background: #fff; color: #b91c1c; box-shadow: 0 2px 8px rgba(153,27,27,.1); font-weight: 600; }

.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { padding: 20px; border-radius: 16px; background: #fff; border: 1px solid rgba(16,36,61,.08); box-shadow: 0 4px 16px rgba(15,23,42,.03); }
.stat-label { display: block; font-size: 13px; color: #a1a1aa; }
.stat-value { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }
.stat-open .stat-value { color: #dc2626; }
.stat-ack .stat-value { color: #d97706; }
.stat-resolved .stat-value { color: #16a34a; }

.ops-note {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid rgba(180, 83, 9, 0.16);
  border-radius: 16px;
  background: #fff;
  color: #52525b;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
}
.ops-note strong {
  flex-shrink: 0;
  color: #9a3412;
  font-size: 14px;
}
.ops-note span {
  font-size: 13px;
  line-height: 1.6;
}

.panel-card { border-radius: 20px; border: 1px solid rgba(16,36,61,.08); box-shadow: 0 8px 24px rgba(15,23,42,.04); }
.card-head strong { display: block; font-size: 18px; color: #172033; }
.card-head span { display: block; margin-top: 4px; font-size: 13px; color: #64748b; }
.distro-list { display: flex; flex-direction: column; gap: 10px; }
.distro-row { display: flex; align-items: center; gap: 12px; }
.distro-tag { min-width: 52px; justify-content: center; }
.distro-bar-bg { flex: 1; height: 20px; border-radius: 6px; background: #f4f4f5; overflow: hidden; }
.distro-bar { height: 100%; border-radius: 6px; transition: width .4s ease; }
.bar-critical { background: #991b1b; }
.bar-error { background: #dc2626; }
.bar-warning { background: #f59e0b; }
.bar-info { background: #3b82f6; }
.distro-count { width: 36px; text-align: right; font-size: 14px; font-weight: 700; color: #18181b; }

.filter-bar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 16px; background: #fff; border-radius: 16px; border: 1px solid rgba(16,36,61,.08); }
.filter-group { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.filter-group label { font-size: 13px; font-weight: 600; color: #52525b; white-space: nowrap; }
.filter-group :deep(.el-select) { width: 140px; }

.table-card { border-radius: 20px; border: 1px solid rgba(16,36,61,.08); box-shadow: 0 18px 40px rgba(15,23,42,.05); }
.alert-table { cursor: pointer; }
.task-link {
  max-width: 132px;
  padding: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.title-stack {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.alert-title { color: #18181b; font-weight: 500; }
.alert-subtitle {
  overflow: hidden;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time-cell { font-size: 13px; color: #71717a; }
.rule-name { font-weight: 600; color: #18181b; }
.type-cell { font-size: 13px; color: #52525b; }
.cool-cell { font-size: 13px; color: #71717a; }
.alert-table :deep(.el-table__header th), .rule-table :deep(.el-table__header th) { color: #71717a; font-weight: 600; font-size: 13px; background: transparent; }
.alert-table :deep(.el-table__body tr:hover > td), .rule-table :deep(.el-table__body tr:hover > td) { background: #fff1f2; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }

.drawer-body { display: flex; flex-direction: column; gap: 8px; }
.drawer-header { margin-bottom: 4px; }
.drawer-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.drawer-time { color: #a1a1aa; font-size: 13px; margin: 0; }
.drawer-section { padding-top: 20px; border-top: 1px solid #f4f4f5; }
.drawer-section h4 { margin: 0 0 12px; font-size: 15px; color: #18181b; font-weight: 600; }
.detail-pre { margin: 0; padding: 14px 16px; background: #fafafa; border-radius: 10px; font-size: 13px; color: #52525b; white-space: pre-wrap; word-break: break-all; max-height: 280px; overflow-y: auto; }
.relation-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.relation-actions :deep(.el-button) {
  margin-left: 0;
}
.timeline { position: relative; padding-left: 20px; }
.tl-item { display: flex; gap: 12px; align-items: flex-start; padding-bottom: 16px; position: relative; }
.tl-item:not(:last-child)::after { content: ""; position: absolute; left: 4px; top: 14px; bottom: 0; width: 1.5px; background: #e4e4e7; }
.tl-dot { flex-shrink: 0; width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; }
.tl-dot.ack { background: #d97706; }
.tl-dot.suppressed { background: #71717a; }
.tl-dot.resolved { background: #16a34a; }
.tl-body { display: flex; flex-direction: column; gap: 2px; }
.tl-title { font-size: 14px; font-weight: 600; color: #18181b; }
.tl-time { font-size: 12px; color: #a1a1aa; }
.tl-by { font-size: 12px; color: #71717a; }
.tl-note { font-size: 12px; color: #52525b; font-style: italic; }
.tl-empty { font-size: 13px; color: #a1a1aa; }
.drawer-actions { padding-top: 20px; border-top: 1px solid #f4f4f5; }
.drawer-actions h4 { margin: 0 0 12px; font-size: 15px; color: #18181b; font-weight: 600; }
.action-help {
  margin: -4px 0 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}
.drawer-actions .action-btns { margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; }

@media (max-width: 960px) {
  .stat-row { grid-template-columns: 1fr 1fr; }
  .hero h2 { font-size: 28px; }
  .ops-note { align-items: flex-start; flex-direction: column; gap: 4px; }
}
</style>
