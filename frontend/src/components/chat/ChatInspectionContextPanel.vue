<script setup lang="ts">
import { ArrowDown, DocumentChecked, Refresh, Search } from "@element-plus/icons-vue";
import { computed, ref } from "vue";

import { taskApi } from "@/api/task.api";
import type { ChatInspectionContext, ChatInspectionTaskContext } from "@/types/chat.types";
import type { InspectionTask, TaskStatus } from "@/types/task.types";

const props = defineProps<{
  context: ChatInspectionContext;
  error?: string;
  selectedTaskIds?: string[];
}>();

const emit = defineEmits<{
  (e: "refresh"): void;
  (e: "reference", value: string): void;
  (e: "toggle-task", value: InspectionTask): void;
  (e: "clear-selected"): void;
}>();

const expanded = ref(false);
const taskDialogVisible = ref(false);
const taskLoading = ref(false);
const taskLoadError = ref("");
const taskRows = ref<InspectionTask[]>([]);
const taskTotal = ref(0);
const taskPage = ref(1);
const taskStatusFilter = ref<TaskStatus | "">("");
const productFilter = ref("");

const stats = computed(() => props.context.stats || {});
const visibleTasks = computed(() => {
  const failures = props.context.recent_failures || [];
  return failures.length ? failures.slice(0, 4) : (props.context.recent_tasks || []).slice(0, 4);
});
const hasTasks = computed(() => Boolean(props.context.summary_window || visibleTasks.value.length));
const failedCount = computed(() => {
  const value = (stats.value.verdict_fail || 0) + (stats.value.status_failed || 0);
  return value || (props.context.recent_failures || []).length;
});
const highRiskCount = computed(() => (stats.value.risk_high || 0) + (stats.value.risk_critical || 0));
const scopeLabel = computed(() => (props.context.scope === "user_recent_tasks" ? "我的任务" : "组织任务"));
const selectedIdSet = computed(() => new Set(props.selectedTaskIds || []));
const selectedCount = computed(() => selectedIdSet.value.size);

function taskTitle(task: ChatInspectionTaskContext) {
  return [task.product_id, task.spec_code].filter(Boolean).join(" / ") || task.task_id || "未命名任务";
}

function taskTone(task: ChatInspectionTaskContext) {
  const verdict = String(task.verdict || "").toLowerCase();
  const risk = String(task.risk_level || "").toLowerCase();
  const status = String(task.status || "").toLowerCase();
  if (verdict === "fail" || status === "failed" || ["high", "critical"].includes(risk)) return "danger";
  if (verdict === "manual_required") return "warning";
  return "neutral";
}

function formatDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function buildReference(task: ChatInspectionTaskContext) {
  const lines = [
    "请重点参考这个近期质检任务：",
    `- 任务 ID：${task.task_id || "未知"}`,
    `- 产品/标准：${taskTitle(task)}`,
    `- 状态：${task.status || "未知"}`,
    `- 判定：${task.verdict || "暂无"}`,
    `- 风险等级：${task.risk_level || "暂无"}`,
  ];
  if (task.failed_rules?.length) lines.push(`- 失败规则：${task.failed_rules.join("；")}`);
  if (task.root_cause) lines.push(`- 根因摘要：${task.root_cause}`);
  if (task.trace_id) lines.push(`- Trace：${task.trace_id}`);
  return lines.join("\n");
}

function plainTaskTitle(task: InspectionTask) {
  return [task.product_id, task.spec_code].filter(Boolean).join(" / ") || task.id;
}

function buildTaskReference(task: InspectionTask) {
  return [
    "请重点参考这个质检任务：",
    `- 任务 ID：${task.id}`,
    `- 产品/标准：${plainTaskTitle(task)}`,
    `- 状态：${task.status}`,
    `- 优先级：${task.priority}`,
    task.has_result ? `- 结果 ID：${task.result_id || "已生成"}` : "- 结果：暂无",
    task.has_stability ? `- 稳定性报告 ID：${task.stability_id || "已生成"}` : "- 稳定性报告：暂无",
  ].join("\n");
}

async function loadTaskOptions() {
  taskLoading.value = true;
  taskLoadError.value = "";
  try {
    const { data } = await taskApi.list(
      {
        page: taskPage.value,
        size: 10,
        status: taskStatusFilter.value || undefined,
        product_id: productFilter.value.trim() || undefined,
      },
      { suppressErrorToast: true },
    );
    taskRows.value = data.data.items;
    taskTotal.value = data.data.total;
  } catch (error) {
    taskRows.value = [];
    taskTotal.value = 0;
    taskLoadError.value = error instanceof Error ? error.message : "任务列表暂不可用";
  } finally {
    taskLoading.value = false;
  }
}

async function openTaskDialog() {
  taskDialogVisible.value = true;
  if (!taskRows.value.length) {
    await loadTaskOptions();
  }
}

async function searchTasks() {
  taskPage.value = 1;
  await loadTaskOptions();
}

function toggleTask(task: InspectionTask) {
  emit("toggle-task", task);
}
</script>

<template>
  <section class="inspection-context-panel" :class="{ expanded }">
    <div class="context-main">
      <div class="context-icon">
        <el-icon><DocumentChecked /></el-icon>
      </div>
      <div class="context-copy">
        <div class="context-title">
          <span>质检上下文</span>
          <el-tag size="small" effect="plain">{{ scopeLabel }}</el-tag>
          <el-tag
            v-if="selectedCount"
            size="small"
            effect="dark"
            closable
            @close="emit('clear-selected')"
          >
            已选择 {{ selectedCount }}
          </el-tag>
        </div>
        <div v-if="error" class="context-sub danger-text">{{ error }}</div>
        <div v-else-if="hasTasks" class="context-sub">
          AI 已参考近 {{ context.summary_window }} 条可见任务，失败 {{ failedCount }} 条，高风险 {{ highRiskCount }} 条。
        </div>
        <div v-else class="context-sub">暂无可见的近期质检任务，AI 会只按当前会话和你提供的信息回答。</div>
      </div>
      <div class="context-actions">
        <el-button size="small" text :icon="Refresh" @click="emit('refresh')" />
        <el-button size="small" text :icon="Search" @click="openTaskDialog">选择任务</el-button>
        <el-button size="small" text :disabled="!visibleTasks.length" @click="expanded = !expanded">
          {{ expanded ? "收起" : "展开" }}
          <el-icon class="arrow" :class="{ up: expanded }"><ArrowDown /></el-icon>
        </el-button>
      </div>
    </div>

    <div v-if="expanded && visibleTasks.length" class="context-task-list">
      <div
        v-for="task in visibleTasks"
        :key="task.task_id || `${task.product_id}-${task.created_at}`"
        class="context-task"
        :class="taskTone(task)"
      >
        <div class="task-copy">
          <div class="task-title">{{ taskTitle(task) }}</div>
          <div class="task-meta">
            <span>{{ task.status || "unknown" }}</span>
            <span v-if="task.verdict">判定 {{ task.verdict }}</span>
            <span v-if="task.risk_level">风险 {{ task.risk_level }}</span>
            <span v-if="task.created_at">{{ formatDate(task.created_at) }}</span>
          </div>
        </div>
        <el-button size="small" link type="primary" @click="emit('reference', buildReference(task))">引用</el-button>
      </div>
    </div>

    <el-dialog v-model="taskDialogVisible" title="选择质检任务作为 AI 上下文" width="820px" destroy-on-close>
      <div class="task-picker">
        <div class="task-picker-toolbar">
          <el-input
            v-model="productFilter"
            clearable
            placeholder="按产品编号筛选"
            class="task-filter-input"
            @keyup.enter="searchTasks"
          />
          <el-select v-model="taskStatusFilter" clearable placeholder="任务状态" class="task-filter-status">
            <el-option label="pending" value="pending" />
            <el-option label="queued" value="queued" />
            <el-option label="running" value="running" />
            <el-option label="done" value="done" />
            <el-option label="failed" value="failed" />
            <el-option label="reviewing" value="reviewing" />
          </el-select>
          <el-button type="primary" :icon="Search" :loading="taskLoading" @click="searchTasks">搜索</el-button>
        </div>

        <el-alert
          v-if="taskLoadError"
          type="warning"
          :closable="false"
          show-icon
          :title="taskLoadError"
        />

        <div v-loading="taskLoading" class="task-picker-list">
          <div v-if="!taskRows.length && !taskLoading" class="task-picker-empty">
            当前条件下没有可选质检任务。
          </div>
          <div
            v-for="task in taskRows"
            :key="task.id"
            class="picker-task"
            :class="{ selected: selectedIdSet.has(task.id) }"
          >
            <div class="picker-task-main">
              <div class="picker-task-title">{{ plainTaskTitle(task) }}</div>
              <div class="picker-task-meta">
                <span>{{ task.status }}</span>
                <span>P{{ task.priority }}</span>
                <span v-if="task.has_result">有结果</span>
                <span v-if="task.has_stability">有稳定性报告</span>
                <span v-if="task.created_at">{{ formatDate(task.created_at) }}</span>
              </div>
            </div>
            <div class="picker-task-actions">
              <el-button
                size="small"
                :type="selectedIdSet.has(task.id) ? 'success' : 'default'"
                @click="toggleTask(task)"
              >
                {{ selectedIdSet.has(task.id) ? "已纳入" : "纳入上下文" }}
              </el-button>
              <el-button size="small" link type="primary" @click="emit('reference', buildTaskReference(task))">
                引用
              </el-button>
            </div>
          </div>
        </div>

        <div class="task-picker-footer">
          <span>共 {{ taskTotal }} 条</span>
          <el-pagination
            v-model:current-page="taskPage"
            small
            layout="prev, pager, next"
            :page-size="10"
            :total="taskTotal"
            @current-change="loadTaskOptions"
          />
        </div>
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
.inspection-context-panel {
  border: 1px solid #d9e2d3;
  border-radius: 14px;
  background:
    radial-gradient(circle at 12px 12px, rgba(49, 120, 84, 0.12), transparent 24px),
    linear-gradient(135deg, #fbf8ef 0%, #f7fbf5 52%, #eef7f1 100%);
  box-shadow: 0 10px 28px rgba(35, 63, 45, 0.08);
  overflow: hidden;
}

.context-main {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
}

.context-icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 12px;
  background: #1f5d3c;
  color: #fff;
}

.context-copy {
  min-width: 0;
  flex: 1;
}

.context-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #183326;
  font-size: 13px;
  font-weight: 800;
}

.context-sub {
  margin-top: 2px;
  color: #587061;
  font-size: 12px;
  line-height: 1.45;
}

.danger-text {
  color: #b45309;
}

.context-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.arrow {
  margin-left: 2px;
  transition: transform 0.18s ease;
}

.arrow.up {
  transform: rotate(180deg);
}

.context-task-list {
  display: grid;
  gap: 8px;
  padding: 0 12px 12px;
}

.context-task {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid rgba(31, 93, 60, 0.12);
  border-radius: 12px;
  padding: 9px 10px;
  background: rgba(255, 255, 255, 0.76);
}

.context-task.danger {
  border-color: rgba(185, 28, 28, 0.18);
  background: rgba(255, 247, 237, 0.84);
}

.context-task.warning {
  border-color: rgba(217, 119, 6, 0.18);
}

.task-copy {
  min-width: 0;
}

.task-title {
  overflow: hidden;
  color: #203428;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 2px;
  color: #66796d;
  font-size: 12px;
}

.task-picker {
  display: grid;
  gap: 12px;
}

.task-picker-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.task-filter-input {
  width: 220px;
}

.task-filter-status {
  width: 160px;
}

.task-picker-list {
  display: grid;
  min-height: 220px;
  gap: 8px;
}

.task-picker-empty {
  display: grid;
  min-height: 180px;
  place-items: center;
  color: #8a958f;
  font-size: 13px;
}

.picker-task {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  border: 1px solid #e4eadf;
  border-radius: 14px;
  padding: 10px 12px;
  background: #fbfcf8;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.picker-task:hover {
  transform: translateY(-1px);
  border-color: rgba(31, 93, 60, 0.28);
}

.picker-task.selected {
  border-color: rgba(31, 93, 60, 0.42);
  background: linear-gradient(135deg, #f1f9ef, #fffaf0);
}

.picker-task-main {
  min-width: 0;
}

.picker-task-title {
  overflow: hidden;
  color: #1f3327;
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 3px;
  color: #66796d;
  font-size: 12px;
}

.picker-task-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.task-picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #718074;
  font-size: 12px;
}

@media (max-width: 640px) {
  .context-main {
    align-items: flex-start;
  }

  .context-actions {
    flex-direction: column;
    align-items: flex-end;
  }

  .picker-task {
    align-items: flex-start;
    flex-direction: column;
  }

  .picker-task-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
