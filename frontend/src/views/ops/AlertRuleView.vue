<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAlertRuleStore } from "@/stores/alert-rule.store";
import type { AlertRule, AlertRuleCreate, AlertRuleUpdate } from "@/types/alert-rule.types";

const alertRuleStore = useAlertRuleStore();
const page = ref(1);
const size = ref(20);
const searchEnabled = ref<string>("");

const dialogVisible = ref(false);
const editingRule = ref<AlertRule | null>(null);
const formLoading = ref(false);

const defaultForm = (): AlertRuleCreate => ({
  name: "",
  description: "",
  alert_type: "model_error",
  severity: "warning",
  enabled: true,
  condition_config: {},
  notification_channels: {},
  cooldown_seconds: 300,
});

const form = ref<AlertRuleCreate>(defaultForm());
const formMode = computed(() => (editingRule.value ? "edit" : "create"));

const severityTag: Record<string, string> = {
  critical: "danger",
  error: "danger",
  warning: "warning",
  info: "info",
};

const severityLabel: Record<string, string> = {
  critical: "严重",
  error: "错误",
  warning: "警告",
  info: "提示",
};

const alertTypeLabel: Record<string, string> = {
  stability_risk: "稳定性风险", quality_review: "质检审核", model_error: "模型错误",
  high_latency: "延迟过高", cost_spike: "成本激增", pass_rate_drop: "通过率下降",
  hallucination_rise: "幻觉率上升", data_quality: "数据质量", system_error: "系统异常",
  custom: "自定义",
};

const alertTypeOptions = [
  { label: "稳定性风险", value: "stability_risk" },
  { label: "质检审核", value: "quality_review" },
  { label: "模型错误", value: "model_error" },
  { label: "延迟过高", value: "high_latency" },
  { label: "成本激增", value: "cost_spike" },
  { label: "通过率下降", value: "pass_rate_drop" },
  { label: "幻觉率上升", value: "hallucination_rise" },
  { label: "数据质量", value: "data_quality" },
  { label: "系统异常", value: "system_error" },
  { label: "自定义", value: "custom" },
];

const items = computed(() => alertRuleStore.items);
const total = computed(() => alertRuleStore.total);
const loading = computed(() => alertRuleStore.loading);

async function fetchRules() {
  const params: any = { page: page.value, size: size.value };
  if (searchEnabled.value !== "") params.enabled = searchEnabled.value === "true";
  await alertRuleStore.fetchRules(params);
}

function openCreate() {
  editingRule.value = null;
  form.value = defaultForm();
  dialogVisible.value = true;
}

function openEdit(rule: AlertRule) {
  editingRule.value = rule;
  form.value = {
    name: rule.name,
    description: rule.description || "",
    alert_type: rule.alert_type,
    severity: rule.severity,
    enabled: rule.enabled,
    condition_config: rule.condition_config ? { ...rule.condition_config } : {},
    notification_channels: rule.notification_channels ? { ...rule.notification_channels } : {},
    cooldown_seconds: rule.cooldown_seconds,
  };
  dialogVisible.value = true;
}

async function handleSubmit() {
  if (!form.value.name.trim()) {
    ElMessage.warning("请输入规则名称");
    return;
  }
  formLoading.value = true;
  try {
    if (formMode.value === "edit" && editingRule.value) {
      const payload: AlertRuleUpdate = { ...form.value };
      await alertRuleStore.updateRule(editingRule.value.id, payload);
      ElMessage.success("规则已更新");
    } else {
      await alertRuleStore.createRule(form.value);
      ElMessage.success("规则已创建");
    }
    dialogVisible.value = false;
    form.value = defaultForm();
    editingRule.value = null;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "操作失败");
  } finally {
    formLoading.value = false;
  }
}

async function handleDelete(rule: AlertRule) {
  try {
    await ElMessageBox.confirm(`确定删除规则 "${rule.name}"？`, "确认删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await alertRuleStore.deleteRule(rule.id);
    ElMessage.success("规则已删除");
  } catch {
    // cancelled
  }
}

async function handleToggle(rule: AlertRule) {
  try {
    await alertRuleStore.updateRule(rule.id, { enabled: !rule.enabled });
    ElMessage.success(rule.enabled ? "规则已停用" : "规则已启用");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "操作失败");
  }
}

function formatTime(ts?: string) {
  if (!ts) return "-";
  const dt = new Date(ts);
  if (Number.isNaN(dt.getTime())) return ts;
  return dt.toLocaleString("zh-CN", { hour12: false });
}

function onPageChange(p: number) {
  page.value = p;
  fetchRules();
}

function onSizeChange(s: number) {
  size.value = s;
  page.value = 1;
  fetchRules();
}

onMounted(() => {
  fetchRules();
});
</script>

<template>
  <div class="rule-shell">
    <section class="hero">
      <p class="eyebrow">Alert Rules</p>
      <h2>告警规则配置</h2>
      <p class="sub">定义告警触发条件、严重度、通知渠道和收敛策略。</p>
    </section>

    <!-- Summary -->
    <section class="stat-row">
      <div class="stat-card">
        <span class="stat-label">规则总数</span>
        <span class="stat-value">{{ total }}</span>
      </div>
      <div class="stat-card stat-crit">
        <span class="stat-label">严重级别</span>
        <span class="stat-value">{{ items.filter(r => r.severity === 'critical').length }}</span>
      </div>
      <div class="stat-card stat-warn">
        <span class="stat-label">警告级别</span>
        <span class="stat-value">{{ items.filter(r => r.severity === 'warning').length }}</span>
      </div>
      <div class="stat-card stat-enabled">
        <span class="stat-label">已启用</span>
        <span class="stat-value">{{ items.filter(r => r.enabled).length }}</span>
      </div>
    </section>

    <!-- Filters -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>启用状态</label>
        <el-select v-model="searchEnabled" size="default" clearable placeholder="全部" @change="() => { page = 1; fetchRules(); }">
          <el-option label="已启用" value="true" />
          <el-option label="已停用" value="false" />
        </el-select>
      </div>
      <el-button type="primary" @click="openCreate">新建规则</el-button>
      <el-button @click="fetchRules">刷新</el-button>
    </div>

    <!-- Rule List -->
    <el-card shadow="never" class="table-card">
      <el-table :data="items" :loading="loading" size="default" empty-text="暂无告警规则" class="rule-table">
        <el-table-column prop="name" label="规则名称" min-width="200">
          <template #default="{ row }">
            <span class="rule-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="告警类型" width="140">
          <template #default="{ row }">
            <span class="type-cell">{{ alertTypeLabel[row.alert_type] || row.alert_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="严重度" width="84">
          <template #default="{ row }">
            <el-tag :type="severityTag[row.severity] || 'info'" size="small" effect="dark">
              {{ severityLabel[row.severity] || row.severity }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              size="small"
              @change="handleToggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="冷却时间" width="100">
          <template #default="{ row }">
            <span class="cool-cell">{{ row.cooldown_seconds }}s</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="176">
          <template #default="{ row }">
            <span class="time-cell">{{ formatTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="formMode === 'edit' ? '编辑规则' : '新建规则'"
      width="560px"
      destroy-on-close
      @close="editingRule = null; form = defaultForm()"
    >
      <el-form :model="form" label-position="top" class="rule-form">
        <el-form-item label="规则名称" required>
          <el-input v-model="form.name" placeholder="例如：模型延迟告警" maxlength="128" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="规则的详细描述" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="告警类型" required>
              <el-select v-model="form.alert_type" placeholder="选择告警类型">
                <el-option
                  v-for="opt in alertTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="严重度">
              <el-select v-model="form.severity">
                <el-option label="严重" value="critical" />
                <el-option label="错误" value="error" />
                <el-option label="警告" value="warning" />
                <el-option label="提示" value="info" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="冷却时间（秒）">
              <el-input-number v-model="form.cooldown_seconds" :min="0" :max="86400" :step="60" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用">
              <el-switch v-model="form.enabled" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="触发条件 (JSON)">
          <el-input
            v-model="form.condition_config"
            type="textarea"
            :rows="3"
            placeholder='{"metric": "latency_ms", "operator": "gt", "threshold": 3000}'
          />
          <span class="form-hint">JSON 格式的触发条件，如阈值、比较运算符等</span>
        </el-form-item>
        <el-form-item label="通知渠道 (JSON)">
          <el-input
            v-model="form.notification_channels"
            type="textarea"
            :rows="3"
            placeholder='{"email": ["ops@example.com"], "webhook": "https://..."}'
          />
          <span class="form-hint">JSON 格式的通知渠道配置</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="formLoading" @click="handleSubmit">
          {{ formMode === "edit" ? "保存" : "创建" }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rule-shell {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 52%, #0f766e 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.stat-card {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.stat-label { display: block; font-size: 13px; color: #a1a1aa; }
.stat-value { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }
.stat-crit .stat-value { color: #dc2626; }
.stat-warn .stat-value { color: #d97706; }
.stat-enabled .stat-value { color: #16a34a; }

.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px;
  background: #fff;
  border-radius: 16px;
  border: 1px solid rgba(16,36,61,.08);
}
.filter-group { display: flex; align-items: center; gap: 8px; }
.filter-group label { font-size: 13px; font-weight: 600; color: #52525b; }

.table-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 18px 40px rgba(15,23,42,.05);
}
.rule-name { font-weight: 600; color: #18181b; }
.type-cell { font-size: 13px; color: #52525b; }
.cool-cell { font-size: 13px; color: #71717a; }
.time-cell { font-size: 13px; color: #a1a1aa; }
.rule-table :deep(.el-table__header th) {
  color: #71717a;
  font-weight: 600;
  font-size: 13px;
  background: transparent;
}
.rule-table :deep(.el-table__body tr:hover > td) {
  background: #f0fdfa;
}
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }

.rule-form .el-select { width: 100%; }
.form-hint { display: block; margin-top: 4px; font-size: 12px; color: #a1a1aa; }

@media (max-width: 960px) {
  .stat-row { grid-template-columns: 1fr 1fr; }
  .hero h2 { font-size: 28px; }
}
</style>
