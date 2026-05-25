<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { usePermission } from "@/composables/usePermission";
import {
  ROLE_ADMIN,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_EXPERT,
  ROLE_PLATFORM_OPERATOR,
  ROLE_USER,
} from "@/constants/roles";
import { useChatStore } from "@/stores/chat.store";
import { useDatasetStore } from "@/stores/dataset.store";
import { useTaskStore } from "@/stores/task.store";
import type { TaskResultIngestResponse, TaskResultIngestTarget, TaskStreamEvent } from "@/types/task.types";

const route = useRoute();
const router = useRouter();
const taskStore = useTaskStore();
const chatStore = useChatStore();
const datasetStore = useDatasetStore();
const { hasRole } = usePermission();

const loading = ref(true);
const running = ref(false);
const deleting = ref(false);
const deleteDialogVisible = ref(false);
const ingestDialogVisible = ref(false);
const ingestSubmitting = ref(false);
const loadingIngestOptions = ref(false);
const ingestResult = ref<TaskResultIngestResponse | null>(null);
const taskId = computed(() => String(route.params.id || ""));
const currentTask = computed(() => taskStore.current?.id === taskId.value ? taskStore.current : null);
const isOpsView = computed(() => route.path.startsWith("/ops/"));
const listBasePath = computed(() => (isOpsView.value ? "/ops/tasks" : "/app/tasks"));
const timeline = ref<TaskStreamEvent[]>([]);
const seenEventIds = new Set<string>();
const seenEventFingerprints = new Set<string>();
const ingestForm = ref({
  target: "rag" as TaskResultIngestTarget,
  rag_space_id: "",
  rag_space_id_manual: "",
  dataset_name: "",
  mode: "candidate" as const,
});
let unsubscribe: (() => void) | null = null;

const canIngestTaskResult = computed(() =>
  hasRole([ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER]),
);
const canBrowseRagSpaces = computed(() => hasRole([ROLE_ADMIN, ROLE_USER, ROLE_EXPERT]));
const canBrowseDatasets = computed(() => hasRole(ROLE_ALGORITHM_ENGINEER));
const canIngestDataset = computed(() => canBrowseDatasets.value);
const requiresRagSpace = computed(() => ingestForm.value.target === "rag" || ingestForm.value.target === "both");
const requiresDataset = computed(() => ingestForm.value.target === "dataset" || ingestForm.value.target === "both");
const resolvedRagSpaceId = computed(() => ingestForm.value.rag_space_id_manual.trim() || ingestForm.value.rag_space_id.trim());
const datasetNameOptions = computed(() => datasetStore.nameOptions);
const resolvedDatasetName = computed(() => ingestForm.value.dataset_name.trim());
const canOpenIngest = computed(() => currentTask.value?.status === "done" && currentTask.value?.has_result);
const ingestStatusText = computed(() => {
  if (!currentTask.value) return "";
  if (currentTask.value.status !== "done") return "任务完成后才可手动导入。";
  if (!currentTask.value.has_result) return "当前任务还没有可沉淀的检测结果。";
  return "会基于任务结构化结果做沉淀，不会直接把 PDF 报告整份塞进 RAG 或训练集。";
});

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
    router.push(listBasePath.value);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "删除任务失败");
  } finally {
    deleting.value = false;
  }
}

async function ensureIngestOptionsLoaded() {
  if (loadingIngestOptions.value) return;
  loadingIngestOptions.value = true;
  try {
    const jobs: Promise<unknown>[] = [];
    if (canBrowseRagSpaces.value) {
      jobs.push(chatStore.fetchRagSpaces().catch(() => undefined));
    }
    if (canBrowseDatasets.value && datasetStore.nameOptions.length === 0) {
      jobs.push(
        datasetStore.fetchDatasetNames({ keyword: "", modality: "image", status: "active", limit: 100 }).catch(() => undefined),
      );
    }
    await Promise.all(jobs);
  } finally {
    loadingIngestOptions.value = false;
  }
}

async function openIngestDialog(defaultTarget: TaskResultIngestTarget) {
  if (!canOpenIngest.value) return;
  const safeTarget = (defaultTarget !== "rag" && !canIngestDataset.value) ? "rag" : defaultTarget;
  ingestForm.value = {
    target: safeTarget,
    rag_space_id: chatStore.selectedRagSpaceId || "",
    rag_space_id_manual: "",
    dataset_name: datasetNameOptions.value[0]?.name || "",
    mode: "candidate",
  };
  ingestResult.value = null;
  ingestDialogVisible.value = true;
  await ensureIngestOptionsLoaded();
  if (canBrowseRagSpaces.value && !ingestForm.value.rag_space_id && chatStore.ragSpaces.length > 0) {
    ingestForm.value.rag_space_id = chatStore.selectedRagSpaceId || chatStore.ragSpaces[0].id;
  }
  if (canBrowseDatasets.value && !ingestForm.value.dataset_name && datasetNameOptions.value.length > 0) {
    ingestForm.value.dataset_name = datasetNameOptions.value[0].name;
  }
}

async function submitIngest() {
  if (!currentTask.value) return;
  if (requiresRagSpace.value && !resolvedRagSpaceId.value) {
    ElMessage.warning("请选择或填写 RAG 空间 ID");
    return;
  }
  if (requiresDataset.value && !resolvedDatasetName.value) {
    ElMessage.warning("请选择数据集名称");
    return;
  }

  ingestSubmitting.value = true;
  try {
    const result = await taskStore.ingestTaskResult(currentTask.value.id, {
      target: ingestForm.value.target,
      rag_space_id: requiresRagSpace.value ? resolvedRagSpaceId.value : undefined,
      dataset_name: requiresDataset.value ? resolvedDatasetName.value : undefined,
      mode: ingestForm.value.mode,
    });
    ingestResult.value = result;
    const parts = [
      result.created_document_count ? `RAG 文档 ${result.created_document_count} 条` : "",
      result.created_sample_count ? `候选样本 ${result.created_sample_count} 条` : "",
      result.skipped_count ? `跳过 ${result.skipped_count} 条` : "",
    ].filter(Boolean);
    ElMessage.success(parts.length ? `导入完成：${parts.join("，")}` : "导入完成");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "导入失败");
  } finally {
    ingestSubmitting.value = false;
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
          v-if="canIngestTaskResult"
          type="primary"
          plain
          :disabled="!canOpenIngest"
          @click="openIngestDialog('rag')"
        >
          导入检测结果
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

      <el-card v-if="canIngestTaskResult" shadow="never" class="ingest-card">
        <template #header>结果沉淀</template>
        <div class="ingest-panel">
          <div class="ingest-copy-block">
            <p class="ingest-title">把当前检测结果手动导入到知识库或训练候选池</p>
            <p class="ingest-copy">{{ ingestStatusText }}</p>
          </div>
          <div class="ingest-actions">
            <el-button type="primary" :disabled="!canOpenIngest" @click="openIngestDialog('rag')">导入到 RAG</el-button>
            <el-button type="success" plain :disabled="!canOpenIngest || !canIngestDataset" @click="openIngestDialog('dataset')">导入到数据集</el-button>
            <el-button type="warning" plain :disabled="!canOpenIngest || !canIngestDataset" @click="openIngestDialog('both')">同时导入</el-button>
          </div>
        </div>
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

    <el-dialog
      v-model="ingestDialogVisible"
      title="导入检测结果"
      width="620px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form label-width="108px" class="ingest-form" v-loading="loadingIngestOptions">
        <el-form-item label="导入目标">
          <el-radio-group v-model="ingestForm.target">
            <el-radio-button label="rag">RAG</el-radio-button>
            <el-radio-button label="dataset" :disabled="!canIngestDataset">数据集</el-radio-button>
            <el-radio-button label="both" :disabled="!canIngestDataset">同时导入</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="requiresRagSpace" label="RAG 空间">
          <div class="ingest-field">
            <el-select
              v-if="canBrowseRagSpaces"
              v-model="ingestForm.rag_space_id"
              filterable
              clearable
              placeholder="选择 RAG 空间"
              class="!w-full"
            >
              <el-option
                v-for="space in chatStore.ragSpaces"
                :key="space.id"
                :label="space.name"
                :value="space.id"
              />
            </el-select>
            <el-input
              v-model="ingestForm.rag_space_id_manual"
              placeholder="也可直接填写 RAG 空间 ID"
              clearable
            />
            <p class="ingest-hint">
              {{ canBrowseRagSpaces ? "可下拉选择，也可以直接粘贴空间 ID。" : "当前角色无法浏览 RAG 空间列表，请直接填写空间 ID。" }}
            </p>
          </div>
        </el-form-item>

        <el-form-item v-if="requiresDataset" label="候选数据集">
          <div class="ingest-field">
            <el-select
              v-model="ingestForm.dataset_name"
              filterable
              clearable
              placeholder="选择图片类激活数据集名称"
              class="!w-full"
              :disabled="!canIngestDataset"
            >
              <el-option
                v-for="dataset in datasetNameOptions"
                :key="dataset.name"
                :label="dataset.name"
                :value="dataset.name"
              />
            </el-select>
            <p class="ingest-hint">
              {{ canBrowseDatasets ? "只展示支持图片样本的激活数据集名称，提交时后端会按名称解析数据集。" : "当前角色无法浏览数据集列表。" }}
            </p>
          </div>
        </el-form-item>

        <el-form-item label="导入模式">
          <el-tag type="info">candidate</el-tag>
          <span class="mode-copy">首版只进入候选池，不会直接写入正式训练集。</span>
        </el-form-item>

        <el-alert
          v-if="ingestResult"
          type="success"
          :closable="false"
          show-icon
          class="ingest-result"
        >
          <template #title>
            已完成导入：RAG 文档 {{ ingestResult.created_document_count }} 条，候选样本 {{ ingestResult.created_sample_count }} 条，跳过 {{ ingestResult.skipped_count }} 条
          </template>
          <template #default>
            <ul v-if="ingestResult.warnings.length" class="warning-list">
              <li v-for="warning in ingestResult.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="ingestDialogVisible = false">关闭</el-button>
          <el-button type="primary" :loading="ingestSubmitting" @click="submitIngest">确认导入</el-button>
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

.ingest-card {
  border: 1px solid rgba(217, 119, 6, 0.18);
}

.ingest-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.ingest-copy-block {
  flex: 1 1 320px;
}

.ingest-title {
  margin: 0;
  color: #111827;
  font-size: 16px;
  font-weight: 700;
}

.ingest-copy {
  margin: 8px 0 0;
  color: #6b7280;
  line-height: 1.7;
}

.ingest-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.ingest-form {
  display: grid;
}

.ingest-field {
  width: 100%;
  display: grid;
  gap: 10px;
}

.ingest-hint {
  margin: 0;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.6;
}

.mode-copy {
  margin-left: 10px;
  color: #6b7280;
  font-size: 13px;
}

.ingest-result {
  margin-top: 8px;
}

.warning-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #92400e;
  line-height: 1.6;
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

@media (max-width: 780px) {
  .ingest-panel {
    align-items: stretch;
  }

  .ingest-actions {
    width: 100%;
  }
}
</style>
