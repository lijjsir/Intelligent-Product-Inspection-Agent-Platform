<script setup lang="ts">
import { ArrowDown, DocumentChecked, Refresh } from "@element-plus/icons-vue";
import { computed, ref } from "vue";

import type { ChatInspectionContext, ChatInspectionTaskContext } from "@/types/chat.types";

const props = defineProps<{
  context: ChatInspectionContext;
  error?: string;
}>();

const emit = defineEmits<{
  (e: "refresh"): void;
  (e: "reference", value: string): void;
}>();

const expanded = ref(false);

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
        </div>
        <div v-if="error" class="context-sub danger-text">{{ error }}</div>
        <div v-else-if="hasTasks" class="context-sub">
          AI 已参考近 {{ context.summary_window }} 条可见任务，失败 {{ failedCount }} 条，高风险 {{ highRiskCount }} 条。
        </div>
        <div v-else class="context-sub">暂无可见的近期质检任务，AI 会只按当前会话和你提供的信息回答。</div>
      </div>
      <div class="context-actions">
        <el-button size="small" text :icon="Refresh" @click="emit('refresh')" />
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

@media (max-width: 640px) {
  .context-main {
    align-items: flex-start;
  }

  .context-actions {
    flex-direction: column;
    align-items: flex-end;
  }
}
</style>
