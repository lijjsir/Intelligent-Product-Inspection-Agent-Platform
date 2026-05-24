<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { useTaskStore } from "@/stores/task.store";
import type { TaskStreamEvent } from "@/types/task.types";

const route = useRoute();
const router = useRouter();
const taskStore = useTaskStore();

const loading = ref(true);
const running = ref(false);
const deleting = ref(false);
const deleteDialogVisible = ref(false);
const taskId = computed(() => String(route.params.id || ""));
const currentTask = computed(() => taskStore.current?.id === taskId.value ? taskStore.current : null);
const timeline = ref<TaskStreamEvent[]>([]);
const seenEventIds = new Set<string>();
const seenEventFingerprints = new Set<string>();
let unsubscribe: (() => void) | null = null;

function getStatusType(status: string) {
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

function eventKey(event: TaskStreamEvent) {
  return String(
    event.id
      || `${event.type}|${event.stage || ""}|${event.status || ""}|${event.message || ""}|${event.ts || ""}`,
  );
}

function eventFingerprint(event: TaskStreamEvent) {
  return `${event.type}|${event.stage || ""}|${event.status || ""}|${event.message || ""}`;
}

function eventTime(event: TaskStreamEvent) {
  const raw = String(event.ts || "");
  const normalized = raw && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? `${raw}Z` : raw;
  const value = Date.parse(normalized);
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

function rememberEvent(event: TaskStreamEvent) {
  const id = event.id ? String(event.id) : "";
  if (id) {
    if (seenEventIds.has(id)) {
      return false;
    }
    seenEventIds.add(id);
    return true;
  }
  const fingerprint = eventFingerprint(event);
  if (seenEventFingerprints.has(fingerprint)) {
    return false;
  }
  seenEventFingerprints.add(fingerprint);
  return true;
}

function sortTimeline() {
  timeline.value = [...timeline.value].sort((a, b) => eventTime(a) - eventTime(b));
}

function pushEvent(event: TaskStreamEvent) {
  if (event.type === "ready" || event.message === "stream_connected") {
    return;
  }
  if (!rememberEvent(event)) {
    return;
  }
  timeline.value = [...timeline.value, event];
  sortTimeline();
  if (timeline.value.length > 100) {
    timeline.value = timeline.value.slice(-100);
  }
  if (event.status && taskStore.current?.id === taskId.value) {
    taskStore.current = { ...taskStore.current, status: event.status };
  }
  if (event.status === "queued" || event.status === "running") {
    running.value = true;
  }
  if (event.status === "done" || event.status === "failed" || event.status === "reviewing") {
    running.value = false;
    taskStore.fetchTask(taskId.value).catch((err) => {
      console.error("Failed to refresh task after completion:", err);
      // Retry once after 2s in case of transient failure
      setTimeout(() => taskStore.fetchTask(taskId.value).catch(() => {}), 2000);
    });
  }
}

async function startPipeline() {
  try {
    running.value = true;
    const result = await taskStore.runTask(taskId.value);
    if (taskStore.current) {
      taskStore.current.status = result.status || "queued";
    }
    pushEvent({
      type: "run",
      message: `任务已提交执行（${result.mode}）`,
      status: result.status || "queued",
      ts: new Date().toISOString(),
    });
    await taskStore.fetchTask(taskId.value);
  } catch (error: any) {
    running.value = false;
    ElMessage.error(error?.response?.data?.message || "启动任务失败");
  }
}

function goBack() {
  router.back();
}

async function deleteTask() {
  deleteDialogVisible.value = true;
}

async function confirmDeleteTask() {
  deleting.value = true;
  try {
    await taskStore.deleteTask(taskId.value);
    ElMessage.success("任务已删除");
    deleteDialogVisible.value = false;
    router.push("/app/tasks");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "删除任务失败");
  } finally {
    deleting.value = false;
  }
}

async function loadTaskDetail(id: string) {
  unsubscribe?.();
  unsubscribe = null;
  if (taskStore.current?.id !== id) taskStore.current = null;
  timeline.value = [];
  seenEventIds.clear();
  seenEventFingerprints.clear();
  loading.value = true;
  try {
    await taskStore.fetchTask(id);
    const events = await taskStore.fetchTaskEvents(id);
    timeline.value = [];
    for (const event of events) {
      if (rememberEvent(event)) {
        timeline.value.push(event);
      }
    }
    sortTimeline();
    running.value = taskStore.current?.status === "queued" || taskStore.current?.status === "running";
    unsubscribe = taskStore.subscribeTaskStream(id, pushEvent);
  } catch (error) {
    console.error(error);
    ElMessage.error("获取任务详情失败");
  } finally {
    loading.value = false;
  }
}

watch(taskId, (id) => {
  if (id) void loadTaskDetail(id);
}, { immediate: true });

onUnmounted(() => {
  unsubscribe?.();
  unsubscribe = null;
});
</script>

<template>
  <div class="flex flex-col gap-5" v-loading="loading">
    <div>
      <el-button @click="goBack" class="back-button">&larr; 返回列表</el-button>
      <div v-if="currentTask" class="title-area">
        <h2 class="text-2xl font-bold text-zinc-900">任务：{{ taskStore.current.id }}</h2>
        <el-tag :type="getStatusType(taskStore.current.status)" size="large">
          {{ taskStore.current.status.toUpperCase() }}
        </el-tag>
        <el-button
          v-if="['pending', 'failed'].includes(taskStore.current.status)"
          type="primary"
          :loading="running"
          @click="startPipeline"
        >
          启动 AI 推演
        </el-button>
        <el-button
          v-if="taskStore.current.has_result"
          type="success"
          plain
          @click="router.push(`/app/results/${taskStore.current.id}`)"
        >
          查看分析结果
        </el-button>
        <el-button
          v-if="taskStore.current.has_stability"
          type="warning"
          plain
          @click="router.push(`/app/stability/${taskStore.current.id}`)"
        >
          查看稳定性评估
        </el-button>
        <el-button
          v-if="taskStore.current.status !== 'running'"
          type="danger"
          plain
          :loading="deleting"
          @click="deleteTask"
        >
          删除任务
        </el-button>
      </div>
    </div>

    <div v-if="currentTask" class="content">
      <el-card shadow="never">
        <template #header>基本信息</template>
        <el-descriptions :column="2">
          <el-descriptions-item label="任务 ID">{{ taskStore.current.id }}</el-descriptions-item>
          <el-descriptions-item label="组织 ID">{{ taskStore.current.org_id }}</el-descriptions-item>
          <el-descriptions-item label="产品编号">{{ taskStore.current.product_id }}</el-descriptions-item>
          <el-descriptions-item label="检测标准">{{ taskStore.current.spec_code }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ taskStore.current.priority }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ taskStore.current.created_at ? new Date(taskStore.current.created_at).toLocaleString("zh-CN", { hour12: false }) : "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="执行模式">{{ taskStore.current.execution?.mode || "-" }}</el-descriptions-item>
          <el-descriptions-item label="执行 Job">{{ taskStore.current.execution?.job_id || "-" }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="taskStore.current.status === 'done' && !taskStore.current.has_result"
          class="missing-result-alert"
          type="warning"
          :closable="false"
          show-icon
          title="任务已完成，但结果记录缺失，请查看执行日志或重新生成报告。"
        />
      </el-card>

      <el-card shadow="never" class="timeline-card">
        <template #header>AI 检测 Agent 实时流</template>
        <el-empty v-if="timeline.length === 0" description="等待执行阶段事件..." />
        <el-timeline v-else>
          <el-timeline-item v-for="item in timeline" :key="eventKey(item)" :timestamp="item.ts || ''" placement="top">
            <div class="event-line">
              <strong>{{ item.type }}</strong>
              <span v-if="item.stage"> / {{ item.stage }}</span>
              <span v-if="item.message"> - {{ item.message }}</span>
              <span v-if="item.status">（{{ item.status }}）</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>

    <el-dialog
      v-model="deleteDialogVisible"
      title="删除任务"
      width="420px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <div class="delete-dialog-copy">删除后该任务将不再出现在任务列表中，是否继续？</div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="deleteDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="deleting" @click="confirmDeleteTask">删除</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>


.back-button {
  margin-bottom: 16px;
}

.title-area {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}


.content {
  display: grid;
  gap: 20px;
}

.timeline-card {
  margin-top: 0;
}

.missing-result-alert {
  margin-top: 14px;
}

.event-line {
  color: #111827;
  line-height: 1.7;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.delete-dialog-copy {
  line-height: 1.8;
  color: #374151;
}
</style>
