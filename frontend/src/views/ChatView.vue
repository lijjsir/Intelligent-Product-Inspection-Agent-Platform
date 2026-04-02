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
  <div class="chat-page">
    <section class="chat-toolbar">
      <div class="toolbar-block">
        <span class="toolbar-label">知识库</span>
        <el-select
          :model-value="chatStore.selectedRagSpaceId || undefined"
          clearable
          filterable
          placeholder="不使用文档"
          class="rag-select"
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
        <el-tag type="info" effect="plain" class="token-tag">
          已使用 Token：{{ totalTokenText }}
        </el-tag>
      </div>

      <div class="toolbar-status">
        <el-tag v-if="chatStore.selectedRagSpace" type="success" effect="plain">
          当前使用：{{ chatStore.selectedRagSpace.name }}
        </el-tag>
        <el-tag v-if="chatStore.pendingAttachments.length" type="warning" effect="plain">
          待发送附件：{{ chatStore.pendingAttachments.length }}
        </el-tag>
      </div>
    </section>

    <el-alert
      v-if="chatStore.ragSpacesError"
      class="rag-warning"
      type="warning"
      :closable="false"
      show-icon
      title="知识库暂不可用"
      :description="chatStore.ragSpacesError"
    />

    <section class="chat-shell">
      <div ref="messageListRef" class="chat-body">
        <el-empty v-if="chatStore.messages.length === 0" description="发送一条消息开始对话" />

        <div v-else class="message-list">
          <article
            v-for="message in chatStore.messages"
            :key="message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-meta">
              <span class="message-role">{{ roleLabel(message.role) }}</span>
              <span class="message-time">{{ formatTime(message.created_at) }}</span>
            </div>

            <div class="message-bubble" :class="message.role">
              <div class="message-content">{{ message.content }}</div>

              <div v-if="message.payload?.attachment_echo?.length" class="attachment-list">
                <a
                  v-for="attachment in message.payload.attachment_echo"
                  :key="attachment.id"
                  :href="attachment.url"
                  target="_blank"
                  rel="noreferrer"
                  class="attachment-chip"
                >
                  {{ attachment.name }}
                </a>
              </div>

              <div class="message-tags">
                <el-tag v-if="message.payload?.intent" size="small" effect="plain" type="primary">
                  {{ intentLabel(message.payload.intent) }}
                </el-tag>
                <el-tag v-if="message.payload?.selected_rag_space" size="small" effect="plain" type="success">
                  RAG：{{ message.payload.selected_rag_space.name }}
                </el-tag>
                <el-tag v-if="message.payload?.citations?.length" size="small" effect="plain" type="info">
                  引用 {{ message.payload.citations.length }}
                </el-tag>
              </div>

              <div v-if="message.payload?.created_task" class="task-card">
                <div class="task-card-title">检测任务已创建</div>
                <div class="task-card-grid">
                  <span>任务 ID</span>
                  <span>{{ message.payload.created_task.id }}</span>
                  <span>产品编号</span>
                  <span>{{ message.payload.created_task.product_id }}</span>
                  <span>检测标准</span>
                  <span>{{ message.payload.created_task.spec_code }}</span>
                  <span>图片数量</span>
                  <span>{{ message.payload.created_task.image_count }}</span>
                </div>
                <div v-if="taskState(message.payload.created_task.id)" class="task-stream-inline">
                  <el-tag size="small" type="warning" effect="plain">
                    {{ taskState(message.payload.created_task.id)?.status || "running" }}
                  </el-tag>
                  <span class="task-stream-text">
                    {{ taskState(message.payload.created_task.id)?.stage || taskState(message.payload.created_task.id)?.message || "智能体执行中..." }}
                  </span>
                </div>
                <div class="task-action-buttons task-card-actions">
                  <el-button size="small" @click="router.push(`/app/tasks/${message.payload.created_task.id}`)">查看任务详情</el-button>
                </div>
              </div>

              <div v-if="message.role === 'assistant' && hasTaskAction(message)" class="task-actions">
                <el-alert
                  v-if="message.payload?.missing_slots?.length"
                  type="info"
                  :closable="false"
                  show-icon
                  title="任务信息还不完整，请补充后再提交。"
                />

                <div class="task-action-buttons">
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

      <div class="composer">
        <div v-if="chatStore.pendingAttachments.length" class="pending-attachments">
          <span class="pending-label">待发送附件</span>
          <div class="pending-list">
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

        <div v-if="streamStatusText" class="stream-status">
          {{ streamStatusText }}
        </div>

        <el-input
          v-model="input"
          type="textarea"
          :rows="4"
          resize="none"
          placeholder="输入消息，Enter 发送，Shift + Enter 换行"
          @keydown="onInputKeydown"
        />

        <div class="composer-actions">
          <div class="composer-left">
            <el-button :icon="Paperclip" @click="triggerAttachmentSelect">添加附件</el-button>
            <el-button :icon="CollectionTag" @click="chatStore.selectedRagSpaceId ? chatStore.clearSelectedRagSpace() : undefined">
              {{ chatStore.selectedRagSpaceId ? "取消知识库" : "未使用知识库" }}
            </el-button>
          </div>

          <el-button type="primary" :icon="Promotion" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage">
            发送
          </el-button>
        </div>

        <input
          ref="attachmentInputRef"
          class="hidden-input"
          type="file"
          multiple
          @change="handleAttachmentSelected"
        />
      </div>
    </section>

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
            style="width: 100%"
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
          <div class="dialog-upload">
            <el-button @click="triggerTaskImageSelect">上传图片</el-button>
            <span class="dialog-tip">也可以直接粘贴图片 URL，每行一个。</span>
          </div>
          <el-input
            v-model="taskForm.image_urls_input"
            type="textarea"
            :rows="5"
            resize="none"
            placeholder="https://example.com/a.jpg"
          />
          <div v-if="taskFormAttachments.length" class="pending-list dialog-list">
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
            class="hidden-input"
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
        <div class="dialog-footer">
          <el-button @click="resetTaskDialog">取消</el-button>
          <el-button type="primary" :loading="taskSubmitting" @click="submitTaskDialog">确认并提交任务</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: calc(100vh - 140px);
}
.chat-toolbar,
.chat-shell {
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 20px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(232, 250, 245, 0.92)),
    radial-gradient(circle at top right, rgba(6, 182, 212, 0.1), transparent 45%);
}

.toolbar-block,
.toolbar-status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-label,
.pending-label {
  font-size: 13px;
  font-weight: 600;
  color: #0f3d4c;
}

.token-tag {
  font-weight: 600;
}

.rag-select {
  width: 300px;
}

.rag-warning {
  border-radius: 16px;
}

.chat-shell {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(144, 238, 210, 0.18), transparent 35%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(244, 251, 249, 0.98));
  overflow: hidden;
}

.chat-body {
  flex: 1;
  min-height: 0;
  padding: 24px 24px 8px;
  overflow-y: auto;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.message-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-row.user {
  align-items: flex-end;
}

.message-meta {
  display: flex;
  gap: 10px;
  font-size: 13px;
  color: #486170;
}

.message-role {
  font-weight: 700;
}

.message-bubble {
  max-width: min(920px, 88%);
  padding: 18px 20px;
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
}

.message-bubble.user {
  background: linear-gradient(135deg, #0f766e, #115e59);
  color: #fff;
}

.message-content {
  white-space: pre-wrap;
  line-height: 1.9;
  word-break: break-word;
}

.attachment-list,
.message-tags,
.task-action-buttons,
.pending-list,
.dialog-upload,
.dialog-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.attachment-list,
.message-tags,
.task-card,
.task-actions {
  margin-top: 14px;
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  text-decoration: none;
  font-size: 13px;
}

.task-card {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(15, 118, 110, 0.06);
}

.task-card-title {
  margin-bottom: 10px;
  font-weight: 700;
  color: #0f3d4c;
}

.task-card-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 8px 12px;
  font-size: 13px;
}

.task-card-grid span:nth-child(odd) {
  color: #486170;
}

.task-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-stream-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  font-size: 13px;
  color: #475569;
}

.task-stream-text {
  line-height: 1.6;
}

.task-card-actions {
  margin-top: 12px;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px 20px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
}

.pending-attachments,
.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-left {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stream-status {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 13px;
  font-weight: 600;
}

.dialog-tip {
  font-size: 12px;
  color: #64748b;
}

.dialog-list {
  margin-top: 12px;
}

.hidden-input {
  display: none;
}

@media (max-width: 900px) {
  .chat-toolbar,
  .pending-attachments,
  .composer-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .rag-select,
  .message-bubble {
    width: 100%;
    max-width: 100%;
  }
}
</style>
