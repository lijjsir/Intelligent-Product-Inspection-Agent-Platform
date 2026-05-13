<script setup lang="ts">
import { CollectionTag, Paperclip, Promotion } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { chatApi } from "@/api/chat.api";
import { useBillingStore } from "@/stores/billing.store";
import { useChatStore } from "@/stores/chat.store";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import type { ChatAttachment, ChatMessage, ChatTaskDraft } from "@/types/chat.types";
import type { TaskCreate } from "@/types/task.types";

const router = useRouter();
const billingStore = useBillingStore();
const chatStore = useChatStore();
const taskStore = useTaskStore();
const inspectionSpecStore = useInspectionSpecStore();

const input = ref("");
const messageListRef = ref<HTMLElement | null>(null);
const attachmentInputRef = ref<HTMLInputElement | null>(null);
const taskImageInputRef = ref<HTMLInputElement | null>(null);

const taskDialogVisible = ref(false);
const taskSubmitting = ref(false);
const taskFormRef = ref<FormInstance>();
const taskSourceMessage = ref<ChatMessage | null>(null);
const taskFormAttachments = ref<ChatAttachment[]>([]);
const taskStreamStates = ref<Record<string, { status: string; stage?: string; message?: string }>>({});
const taskStreamDisposers = new Map<string, () => void>();
const taskForm = ref({
  product_id: "",
  spec_code: "",
  image_urls_input: "",
  priority: 5,
});

const taskRules: FormRules = {
  product_id: [{ required: true, message: "请输入产品编号", trigger: "blur" }],
  spec_code: [{ required: true, message: "请选择或输入检测标准", trigger: "blur" }],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasText = Boolean(value?.trim());
        const hasUploads = taskFormAttachments.value.length > 0;
        if (!hasText && !hasUploads) {
          callback(new Error("请至少提供一张待检测图片"));
          return;
        }
        callback();
      },
      trigger: "change",
    },
  ],
};

const canSend = computed(() => !chatStore.loading && Boolean(input.value.trim() || chatStore.pendingAttachments.length > 0));
const streamStatusText = computed(() => {
  if (!chatStore.loading) return "";
  if (chatStore.streamPhase === "connecting") return "正在建立连接...";
  if (chatStore.streamPhase === "streaming") return "智能体处理中...";
  if (chatStore.streamPhase === "closing") return "正在整理回复...";
  return "智能体处理中...";
});
const specOptions = computed(() => inspectionSpecStore.items);
const totalTokenText = computed(() => (billingStore.myUsage?.total_tokens ?? 0).toLocaleString("zh-CN"));
const latestTokenCountedMessageId = computed(() => {
  const candidates = [...chatStore.messages].reverse();
  for (const message of candidates) {
    if (message.role !== "assistant") continue;
    if (message.message_type === "streaming") continue;
    if (!["assistant_text", "quality_answer"].includes(message.message_type)) continue;
    return message.id;
  }
  return "";
});
const syncedUsageMessageId = ref("");

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") return "你";
  if (role === "assistant") return "智能体";
  return "系统";
}

function intentLabel(intent?: string) {
  switch (intent) {
    case "smalltalk":
      return "闲聊";
    case "general_qa":
      return "普通问答";
    case "quality_qa":
      return "质量问答";
    case "task_create":
      return "任务创建";
    case "task_followup":
      return "任务跟进";
    default:
      return "";
  }
}

function verdictTagType(verdict?: string | null) {
  if (verdict === "pass") return "success";
  if (verdict === "fail") return "danger";
  return "warning";
}

function riskTagType(level?: string | null) {
  if (level === "low" || level === "green") return "success";
  if (level === "medium" || level === "yellow" || level === "orange") return "warning";
  return "danger";
}

function materializationTagType(status?: string | null) {
  if (status === "synced") return "success";
  if (status === "failed") return "danger";
  return "info";
}

function attachmentName(url: string) {
  const last = url.split("/").pop() || url;
  return decodeURIComponent(last);
}

function buildAttachmentFromUrl(url: string): ChatAttachment {
  return {
    id: `task-${url}`,
    name: attachmentName(url),
    url,
    size_bytes: 0,
    kind: "image",
  };
}

function parseImageUrls(value: string) {
  return value
    .split(/\r?\n|,|;/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildTaskDraft(message: ChatMessage): ChatTaskDraft | null {
  return message.payload?.task_form_defaults || message.payload?.task_draft || null;
}

function hasTaskAction(message: ChatMessage) {
  const state = message.payload?.action_state;
  return state === "awaiting_task_details" || state === "awaiting_task_confirmation";
}

function canConfirmTask(message: ChatMessage) {
  return message.payload?.action_state === "awaiting_task_confirmation";
}

function syncTaskFormImageUrls() {
  const uploaded = taskFormAttachments.value.map((item) => item.url).filter(Boolean);
  const manual = parseImageUrls(taskForm.value.image_urls_input);
  const merged = Array.from(new Set([...uploaded, ...manual]));
  taskForm.value.image_urls_input = merged.join("\n");
}

function fillTaskForm(message: ChatMessage) {
  const draft = buildTaskDraft(message);
  const uploaded = message.payload?.attachment_echo || [];
  const draftUrls = (draft?.image_urls || []).map((url) => buildAttachmentFromUrl(url));
  const attachmentMap = new Map<string, ChatAttachment>();
  for (const item of [...uploaded, ...draftUrls]) {
    if (item.url) {
      attachmentMap.set(item.url, item);
    }
  }
  taskForm.value = {
    product_id: draft?.product_id || "",
    spec_code: draft?.spec_code || "",
    image_urls_input: Array.from(attachmentMap.keys()).join("\n"),
    priority: draft?.priority ?? 5,
  };
  taskFormAttachments.value = Array.from(attachmentMap.values());
}

function openTaskDialog(message: ChatMessage) {
  taskSourceMessage.value = message;
  fillTaskForm(message);
  taskDialogVisible.value = true;
}

function resetTaskDialog() {
  taskDialogVisible.value = false;
  taskSourceMessage.value = null;
  taskForm.value = {
    product_id: "",
    spec_code: "",
    image_urls_input: "",
    priority: 5,
  };
  taskFormAttachments.value = [];
  taskFormRef.value?.clearValidate();
}

function buildTaskPayload(message: ChatMessage, useDialogState: boolean): TaskCreate {
  if (useDialogState) {
    const imageUrls = Array.from(
      new Set([...taskFormAttachments.value.map((item) => item.url), ...parseImageUrls(taskForm.value.image_urls_input)]),
    );
    return {
      product_id: taskForm.value.product_id.trim(),
      spec_code: taskForm.value.spec_code.trim(),
      image_urls: imageUrls,
      priority: taskForm.value.priority,
      metadata: { source: "chat" },
    };
  }

  const draft = buildTaskDraft(message);
  return {
    product_id: String(draft?.product_id || "").trim(),
    spec_code: String(draft?.spec_code || "").trim(),
    image_urls: (draft?.image_urls || []).filter(Boolean),
    priority: draft?.priority ?? 5,
    metadata: { source: "chat" },
  };
}

async function createTaskFromMessage(message: ChatMessage, useDialogState: boolean) {
  const payload = buildTaskPayload(message, useDialogState);
  if (!payload.product_id || !payload.spec_code || payload.image_urls.length === 0) {
    ElMessage.warning("检测任务信息还不完整，请先补全表单。");
    return;
  }

  taskSubmitting.value = true;
  try {
    const createdMessage = await chatStore.submitTask({
      source_message_id: message.id,
      product_id: payload.product_id,
      spec_code: payload.spec_code,
      image_urls: payload.image_urls,
      priority: payload.priority ?? 5,
      metadata: payload.metadata,
    });
    if (createdMessage?.payload?.created_task?.id) {
      ensureTaskStream(createdMessage.payload.created_task.id);
    }
    ElMessage.success("检测任务已创建并开始执行。");
    if (useDialogState) {
      resetTaskDialog();
    }
  } catch (error) {
    ElMessage.error("任务创建失败，请稍后重试。");
    console.error(error);
  } finally {
    taskSubmitting.value = false;
  }
}

async function submitTaskDialog() {
  if (!taskSourceMessage.value) return;
  const form = taskFormRef.value;
  if (!form) return;
  try {
    await form.validate();
  } catch {
    return;
  }
  await createTaskFromMessage(taskSourceMessage.value, true);
}

async function sendMessage() {
  if (!canSend.value) return;
  const message = input.value.trim();
  try {
    await chatStore.sendMessage({ message });
    input.value = "";
  } catch (error) {
    ElMessage.error("消息发送失败，请稍后重试。");
    console.error(error);
  }
}

const onInputKeydown = async (event: KeyboardEvent) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendMessage();
  }
};

const triggerAttachmentSelect = () => {
  attachmentInputRef.value?.click();
};

const triggerTaskImageSelect = () => {
  taskImageInputRef.value?.click();
};

const handleAttachmentSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try {
    await chatStore.uploadPendingAttachments(files);
  } catch (error) {
    ElMessage.error("附件上传失败，请稍后重试。");
    console.error(error);
  } finally {
    inputElement.value = "";
  }
};

const handleTaskImageSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try {
    const { data } = await chatApi.uploadAttachments(files);
    const merged = new Map<string, ChatAttachment>();
    for (const item of [...taskFormAttachments.value, ...data.data.items]) {
      if (item.url) merged.set(item.url, item);
    }
    taskFormAttachments.value = Array.from(merged.values());
    syncTaskFormImageUrls();
  } catch (error) {
    ElMessage.error("任务图片上传失败，请稍后重试。");
    console.error(error);
  } finally {
    inputElement.value = "";
  }
};

function removePendingAttachment(id: string) {
  chatStore.removePendingAttachment(id);
}

function removeTaskAttachment(id: string) {
  taskFormAttachments.value = taskFormAttachments.value.filter((item) => item.id !== id);
  syncTaskFormImageUrls();
}

async function scrollToBottom() {
  await nextTick();
  const container = messageListRef.value;
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}

function taskState(taskId: string) {
  return taskStreamStates.value[taskId] || null;
}

function disposeTaskStreams() {
  for (const dispose of taskStreamDisposers.values()) {
    dispose();
  }
  taskStreamDisposers.clear();
}

function ensureTaskStream(taskId: string) {
  if (!taskId || taskStreamDisposers.has(taskId)) return;
  taskStreamStates.value = {
    ...taskStreamStates.value,
    [taskId]: taskStreamStates.value[taskId] || { status: "running" },
  };
  const dispose = taskStore.subscribeTaskStream(taskId, async (event) => {
    taskStreamStates.value = {
      ...taskStreamStates.value,
      [taskId]: {
        status: String(event.status || taskStreamStates.value[taskId]?.status || "running"),
        stage: typeof event.stage === "string" ? event.stage : taskStreamStates.value[taskId]?.stage,
        message: typeof event.message === "string" ? event.message : taskStreamStates.value[taskId]?.message,
      },
    };
    if (event.status === "done" || event.status === "failed") {
      const currentDispose = taskStreamDisposers.get(taskId);
      currentDispose?.();
      taskStreamDisposers.delete(taskId);
      await chatStore.reloadCurrentSessionMessages();
    }
  });
  taskStreamDisposers.set(taskId, dispose);
}

function syncTaskStreamsFromMessages() {
  const createdTaskIds = new Set(
    chatStore.messages
      .map((message) => message.payload?.created_task?.id)
      .filter((value): value is string => Boolean(value)),
  );
  for (const taskId of createdTaskIds) {
    const message = chatStore.messages.find((item) => item.payload?.created_task?.id === taskId);
    const status = String(message?.payload?.created_task?.status || "");
    if (status !== "done" && status !== "failed") {
      ensureTaskStream(taskId);
    }
  }
  for (const [taskId, dispose] of taskStreamDisposers.entries()) {
    if (!createdTaskIds.has(taskId)) {
      dispose();
      taskStreamDisposers.delete(taskId);
    }
  }
}

onMounted(async () => {
  try {
    await chatStore.initForChatPage();
  } catch (error) {
    ElMessage.error("聊天初始化失败，请刷新页面后重试。");
    console.error(error);
  }

  try {
    if (inspectionSpecStore.items.length === 0) {
      await inspectionSpecStore.fetchAll();
    }
  } catch {
    // Spec loading should not block chat usage.
  }

  try {
    await billingStore.fetchMyUsage();
  } catch {
    // Token summary is informative only.
  }

  await scrollToBottom();
  syncTaskStreamsFromMessages();
});

onBeforeUnmount(() => {
  chatStore.stopStream();
  disposeTaskStreams();
});

watch(
  () => chatStore.messages.length,
  async () => {
    await scrollToBottom();
    syncTaskStreamsFromMessages();
  },
);

watch(
  () => chatStore.messages.map((item) => `${item.id}:${item.content.length}`).join("|"),
  async () => {
    await scrollToBottom();
    syncTaskStreamsFromMessages();
  },
);

watch(latestTokenCountedMessageId, async (messageId) => {
  if (!messageId || messageId === syncedUsageMessageId.value) return;
  syncedUsageMessageId.value = messageId;
  try {
    await billingStore.fetchMyUsage();
  } catch {
    // Ignore refresh failures for the lightweight token badge.
  }
});
</script>

<template>
  <div class="flex flex-col gap-4 min-h-[calc(100vh-136px)]">
    <!-- Toolbar -->
    <section class="flex items-center justify-between gap-3 px-5 py-3.5 bg-white border border-zinc-200 rounded-xl shadow-surface-sm flex-wrap">
      <div class="flex items-center gap-3 flex-wrap">
        <span class="text-[13px] font-semibold text-zinc-700">知识库</span>
        <el-select
          :model-value="chatStore.selectedRagSpaceId || undefined"
          clearable
          filterable
          placeholder="不使用文档"
          class="!w-[280px]"
          size="small"
          @update:model-value="(value) => (value ? chatStore.selectRagSpace(value) : chatStore.clearSelectedRagSpace())"
        >
          <el-option label="不使用文档" value="" />
          <el-option
            v-for="space in chatStore.ragSpaces"
            :key="space.id"
            :label="`${space.name} (${space.file_count})`"
            :value="space.id"
          />
        </el-select>
        <el-tag size="small" effect="plain" type="info">已使用 Token：{{ totalTokenText }}</el-tag>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <el-tag v-if="chatStore.selectedRagSpace" size="small" effect="plain" type="success">
          当前使用：{{ chatStore.selectedRagSpace.name }}
        </el-tag>
        <el-tag v-if="chatStore.pendingAttachments.length" size="small" effect="plain" type="warning">
          待发送附件：{{ chatStore.pendingAttachments.length }}
        </el-tag>
      </div>
    </section>

    <el-alert
      v-if="chatStore.ragSpacesError"
      class="!rounded-xl"
      type="warning"
      :closable="false"
      show-icon
      title="知识库暂不可用"
      :description="chatStore.ragSpacesError"
    />

    <!-- Chat shell -->
    <section class="flex flex-col flex-1 min-h-0 bg-white border border-zinc-200 rounded-2xl shadow-surface-sm overflow-hidden">
      <!-- Message list -->
      <div ref="messageListRef" class="flex-1 min-h-0 overflow-y-auto px-6 py-5">
        <el-empty v-if="chatStore.messages.length === 0" description="发送一条消息开始对话" />

        <div v-else class="flex flex-col gap-5">
          <article
            v-for="message in chatStore.messages"
            :key="message.id"
            class="flex flex-col gap-2"
            :class="message.role === 'user' ? 'items-end' : ''"
          >
            <div class="flex gap-2.5 text-[13px] text-zinc-500">
              <span class="font-bold text-zinc-700">{{ roleLabel(message.role) }}</span>
              <span>{{ formatTime(message.created_at) }}</span>
            </div>

            <!-- Bubble -->
            <div
              class="max-w-[min(920px,88%)] px-5 py-4 rounded-2xl border border-zinc-100 bg-white shadow-surface-sm"
              :class="message.role === 'user' ? '!bg-zinc-900 !text-white !border-zinc-900' : ''"
            >
              <div class="whitespace-pre-wrap leading-relaxed break-words">{{ message.content }}</div>

              <!-- Attachments -->
              <div v-if="message.payload?.attachment_echo?.length" class="flex flex-wrap gap-2 mt-3.5">
                <a
                  v-for="attachment in message.payload.attachment_echo"
                  :key="attachment.id"
                  :href="attachment.url"
                  target="_blank"
                  rel="noreferrer"
                  class="inline-flex items-center px-3 py-1.5 rounded-full bg-zinc-100 text-zinc-700 text-[13px] hover:bg-zinc-200 transition-colors"
                  :class="message.role === 'user' ? '!bg-zinc-800 !text-zinc-200 hover:!bg-zinc-700' : ''"
                >
                  {{ attachment.name }}
                </a>
              </div>

              <!-- Tags -->
              <div class="flex flex-wrap gap-2 mt-3.5">
                <el-tag v-if="message.payload?.intent" size="small" effect="plain" type="primary">
                  {{ intentLabel(message.payload.intent) }}
                </el-tag>
                <el-tag v-if="message.payload?.selected_rag_space" size="small" effect="plain" type="success">
                  RAG：{{ message.payload.selected_rag_space.name }}
                </el-tag>
                <el-tag v-if="message.payload?.citations?.length" size="small" effect="plain" type="info">
                  引用 {{ message.payload.citations.length }}
                </el-tag>
                <el-tag v-if="message.payload?.source_graph" size="small" effect="plain" type="warning">
                  子图：{{ message.payload.source_graph }}
                </el-tag>
              </div>

              <!-- Result card -->
              <div v-if="message.payload?.result_card" class="mt-4 p-4 rounded-xl border border-zinc-200 bg-zinc-50/50">
                <div class="flex justify-between gap-3 flex-wrap">
                  <div>
                    <div class="text-base font-bold text-zinc-900">
                      {{ message.payload.result_card.product_name || message.payload.result_card.product_id }}
                    </div>
                    <div class="text-[13px] text-zinc-500 mt-0.5">
                      {{ message.payload.result_card.product_family || "unknown" }} · {{ message.payload.result_card.spec_code }}
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <el-tag size="small" effect="dark" :type="verdictTagType(message.payload.result_card.verdict)">
                      {{ message.payload.result_card.verdict.toUpperCase() }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="riskTagType(message.payload.result_card.risk_level)">
                      风险 {{ message.payload.result_card.risk_level }}
                    </el-tag>
                  </div>
                </div>

                <div class="grid grid-cols-4 gap-3 mt-4 max-sm:grid-cols-2">
                  <div class="p-3 rounded-xl bg-white border border-zinc-100">
                    <span class="text-xs font-bold text-zinc-500">总体得分</span>
                    <strong class="block mt-1.5 text-zinc-900 text-[15px]">{{ Number(message.payload.result_card.overall_score || 0).toFixed(2) }}</strong>
                  </div>
                  <div class="p-3 rounded-xl bg-white border border-zinc-100">
                    <span class="text-xs font-bold text-zinc-500">RAG 空间</span>
                    <strong class="block mt-1.5 text-zinc-900 text-[15px]">{{ message.payload.rag_summary?.rag_space_name || message.payload.rag_summary?.rag_space_id || "未使用" }}</strong>
                  </div>
                  <div class="p-3 rounded-xl bg-white border border-zinc-100">
                    <span class="text-xs font-bold text-zinc-500">引用数量</span>
                    <strong class="block mt-1.5 text-zinc-900 text-[15px]">{{ message.payload.rag_summary?.hit_count ?? 0 }}</strong>
                  </div>
                  <div class="p-3 rounded-xl bg-white border border-zinc-100">
                    <span class="text-xs font-bold text-zinc-500">引用覆盖率</span>
                    <strong class="block mt-1.5 text-zinc-900 text-[15px]">{{ ((message.payload.rag_summary?.citation_coverage ?? 0) * 100).toFixed(1) }}%</strong>
                  </div>
                </div>

                <div v-if="message.payload.result_card.key_reasons?.length" class="mt-4">
                  <div class="text-xs font-bold text-zinc-500 mb-2">关键原因</div>
                  <div class="flex flex-wrap gap-2">
                    <el-tag
                      v-for="reason in message.payload.result_card.key_reasons"
                      :key="reason"
                      size="small"
                      effect="plain"
                    >
                      {{ reason }}
                    </el-tag>
                  </div>
                </div>

                <div v-if="message.payload.result_card.failed_rules?.length" class="mt-4">
                  <div class="text-xs font-bold text-zinc-500 mb-2">失败规则</div>
                  <div class="flex flex-wrap gap-2">
                    <el-tag
                      v-for="rule in message.payload.result_card.failed_rules"
                      :key="rule"
                      size="small"
                      type="danger"
                      effect="plain"
                    >
                      {{ rule }}
                    </el-tag>
                  </div>
                </div>

                <div class="flex justify-between gap-3 mt-4 flex-wrap">
                  <div class="flex flex-col gap-2">
                    <span class="text-xs font-bold text-zinc-500">预期对照</span>
                    <el-tag
                      v-if="message.payload.expectation_check"
                      size="small"
                      effect="plain"
                      :type="message.payload.expectation_check.matched ? 'success' : 'danger'"
                    >
                      {{ message.payload.expectation_check.matched ? "系统结果与样本预期一致" : "系统结果与样本预期不一致" }}
                    </el-tag>
                    <span v-else class="text-[13px] text-zinc-400">未提供样本预期</span>
                  </div>
                  <div class="flex flex-col gap-2 max-w-[48%]">
                    <span class="text-xs font-bold text-zinc-500">Top Sources</span>
                    <span class="text-[13px] text-zinc-400">
                      {{ message.payload.rag_summary?.top_sources?.join(" / ") || "暂无引用来源" }}
                    </span>
                  </div>
                </div>

                <div class="flex items-center gap-2.5 flex-wrap mt-4">
                  <el-tag
                    v-if="message.payload.materialization_status"
                    size="small"
                    effect="plain"
                    :type="materializationTagType(message.payload.materialization_status)"
                  >
                    {{ message.payload.materialization_status === "synced" ? "已同步到任务/分析统计" : "同步到后台统计失败" }}
                  </el-tag>
                  <el-button
                    v-if="message.payload.materialized_task?.id"
                    size="small"
                    link
                    type="primary"
                    @click="router.push(`/app/tasks/${message.payload.materialized_task.id}`)"
                  >
                    查看同步任务
                  </el-button>
                  <span v-if="message.payload.materialization_error" class="text-[13px] text-zinc-400">
                    {{ message.payload.materialization_error }}
                  </span>
                </div>
              </div>

              <!-- Task card -->
              <div v-if="message.payload?.created_task" class="mt-4 p-4 rounded-xl bg-zinc-50 border border-zinc-100">
                <div class="font-bold text-zinc-800 mb-2.5">检测任务已创建</div>
                <div class="grid grid-cols-[96px_1fr] gap-x-3 gap-y-2 text-[13px]">
                  <span class="text-zinc-500">任务 ID</span>
                  <span>{{ message.payload.created_task.id }}</span>
                  <span class="text-zinc-500">产品编号</span>
                  <span>{{ message.payload.created_task.product_id }}</span>
                  <span class="text-zinc-500">检测标准</span>
                  <span>{{ message.payload.created_task.spec_code }}</span>
                  <span class="text-zinc-500">图片数量</span>
                  <span>{{ message.payload.created_task.image_count }}</span>
                </div>
                <div v-if="taskState(message.payload.created_task.id)" class="flex items-center gap-2.5 mt-3 text-[13px] text-zinc-600">
                  <el-tag size="small" type="warning" effect="plain">
                    {{ taskState(message.payload.created_task.id)?.status || "running" }}
                  </el-tag>
                  <span>{{ taskState(message.payload.created_task.id)?.stage || taskState(message.payload.created_task.id)?.message || "智能体执行中..." }}</span>
                </div>
                <div class="flex gap-2 mt-3">
                  <el-button size="small" @click="router.push(`/app/tasks/${message.payload.created_task.id}`)">查看任务详情</el-button>
                </div>
              </div>

              <!-- Task actions -->
              <div v-if="message.role === 'assistant' && hasTaskAction(message)" class="mt-4 flex flex-col gap-2.5">
                <el-alert
                  v-if="message.payload?.missing_slots?.length"
                  type="info"
                  :closable="false"
                  show-icon
                  title="任务信息还不完整，请补充后再提交。"
                />
                <div class="flex gap-2.5 flex-wrap">
                  <el-button size="small" @click="openTaskDialog(message)">
                    {{ canConfirmTask(message) ? "编辑检测信息" : "填写检测信息" }}
                  </el-button>
                  <el-button
                    v-if="canConfirmTask(message)"
                    size="small"
                    type="primary"
                    :loading="taskSubmitting"
                    @click="createTaskFromMessage(message, false)"
                  >
                    确认并提交任务
                  </el-button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- Composer -->
      <div class="border-t border-zinc-100 px-5 py-4 bg-white">
        <div v-if="chatStore.pendingAttachments.length" class="flex items-center justify-between gap-3 mb-3">
          <span class="text-[13px] font-semibold text-zinc-700">待发送附件</span>
          <div class="flex gap-2 flex-wrap">
            <el-tag
              v-for="attachment in chatStore.pendingAttachments"
              :key="attachment.id"
              closable
              effect="plain"
              @close="removePendingAttachment(attachment.id)"
            >
              {{ attachment.name }}
            </el-tag>
          </div>
        </div>

        <div v-if="streamStatusText" class="inline-flex items-center px-3 py-1.5 rounded-full bg-zinc-100 text-zinc-700 text-[13px] font-semibold mb-3">
          {{ streamStatusText }}
        </div>

        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入消息，Enter 发送，Shift + Enter 换行"
          @keydown="onInputKeydown"
        />

        <div class="flex items-center justify-between gap-3 mt-3">
          <div class="flex gap-2 flex-wrap">
            <el-button size="small" :icon="Paperclip" @click="triggerAttachmentSelect">添加附件</el-button>
            <el-button size="small" :icon="CollectionTag" @click="chatStore.selectedRagSpaceId ? chatStore.clearSelectedRagSpace() : undefined">
              {{ chatStore.selectedRagSpaceId ? "取消知识库" : "未使用知识库" }}
            </el-button>
          </div>
          <el-button type="primary" :icon="Promotion" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage">
            发送
          </el-button>
        </div>

        <input
          ref="attachmentInputRef"
          class="hidden"
          type="file"
          multiple
          @change="handleAttachmentSelected"
        />
      </div>
    </section>

    <!-- Task dialog -->
    <el-dialog v-model="taskDialogVisible" title="填写检测任务" width="640px" @closed="resetTaskDialog">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-position="top">
        <el-form-item label="产品编号" prop="product_id">
          <el-input v-model="taskForm.product_id" placeholder="例如：P-1001" />
        </el-form-item>

        <el-form-item label="检测标准" prop="spec_code">
          <el-select
            v-model="taskForm.spec_code"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入检测标准"
            class="!w-full"
          >
            <el-option
              v-for="spec in specOptions"
              :key="spec.id"
              :label="`${spec.spec_code} · ${spec.name}`"
              :value="spec.spec_code"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="检测图片" prop="image_urls_input">
          <div class="flex items-center gap-2 mb-2">
            <el-button size="small" @click="triggerTaskImageSelect">上传图片</el-button>
            <span class="text-xs text-zinc-400">也可以直接粘贴图片 URL，每行一个。</span>
          </div>
          <el-input
            v-model="taskForm.image_urls_input"
            type="textarea"
            :rows="5"
            resize="none"
            placeholder="https://example.com/a.jpg"
          />
          <div v-if="taskFormAttachments.length" class="flex flex-wrap gap-2 mt-3">
            <el-tag
              v-for="attachment in taskFormAttachments"
              :key="attachment.id"
              closable
              effect="plain"
              @close="removeTaskAttachment(attachment.id)"
            >
              {{ attachment.name }}
            </el-tag>
          </div>
          <input
            ref="taskImageInputRef"
            class="hidden"
            type="file"
            accept="image/*"
            multiple
            @change="handleTaskImageSelected"
          />
        </el-form-item>

        <el-form-item label="优先级">
          <el-slider v-model="taskForm.priority" :min="1" :max="10" show-input />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="flex gap-2 justify-end">
          <el-button @click="resetTaskDialog">取消</el-button>
          <el-button type="primary" :loading="taskSubmitting" @click="submitTaskDialog">确认并提交任务</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
