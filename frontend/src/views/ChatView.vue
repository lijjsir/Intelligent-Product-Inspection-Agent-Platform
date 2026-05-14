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
  return date.toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") return "你";
  if (role === "assistant") return "智能体";
  return "系统";
}

function intentLabel(intent?: string) {
  switch (intent) {
    case "smalltalk": return "闲聊";
    case "general_qa": return "普通问答";
    case "quality_qa": return "质量问答";
    case "task_create": return "任务创建";
    case "task_followup": return "任务跟进";
    default: return "";
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

function trustTagType(level?: string | null) {
  if (level === "low") return "success";
  if (level === "medium") return "warning";
  return "danger";
}

function trustStatusText(status?: string | null) {
  if (status === "scored") return "已评审";
  if (status === "rule_only") return "规则评审";
  if (status === "reviewing") return "评审中";
  if (status === "failed") return "评审失败";
  return "未评审";
}

function attachmentName(url: string) {
  const last = url.split("/").pop() || url;
  return decodeURIComponent(last);
}

function buildAttachmentFromUrl(url: string): ChatAttachment {
  return { id: `task-${url}`, name: attachmentName(url), url, size_bytes: 0, kind: "image" };
}

function parseImageUrls(value: string) {
  return value.split(/\r?\n|,|;/).map((item) => item.trim()).filter(Boolean);
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
  taskForm.value.image_urls_input = Array.from(new Set([...uploaded, ...manual])).join("\n");
}

function fillTaskForm(message: ChatMessage) {
  const draft = buildTaskDraft(message);
  const uploaded = message.payload?.attachment_echo || [];
  const draftUrls = (draft?.image_urls || []).map((url) => buildAttachmentFromUrl(url));
  const attachmentMap = new Map<string, ChatAttachment>();
  for (const item of [...uploaded, ...draftUrls]) {
    if (item.url) attachmentMap.set(item.url, item);
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
  taskForm.value = { product_id: "", spec_code: "", image_urls_input: "", priority: 5 };
  taskFormAttachments.value = [];
  taskFormRef.value?.clearValidate();
}

function buildTaskPayload(message: ChatMessage, useDialogState: boolean): TaskCreate {
  if (useDialogState) {
    const imageUrls = Array.from(
      new Set([...taskFormAttachments.value.map((item) => item.url), ...parseImageUrls(taskForm.value.image_urls_input)]),
    );
    return { product_id: taskForm.value.product_id.trim(), spec_code: taskForm.value.spec_code.trim(), image_urls: imageUrls, priority: taskForm.value.priority, metadata: { source: "chat" } };
  }
  const draft = buildTaskDraft(message);
  return { product_id: String(draft?.product_id || "").trim(), spec_code: String(draft?.spec_code || "").trim(), image_urls: (draft?.image_urls || []).filter(Boolean), priority: draft?.priority ?? 5, metadata: { source: "chat" } };
}

async function createTaskFromMessage(message: ChatMessage, useDialogState: boolean) {
  const payload = buildTaskPayload(message, useDialogState);
  if (!payload.product_id || !payload.spec_code || payload.image_urls.length === 0) {
    ElMessage.warning("检测任务信息还不完整，请先补全表单。");
    return;
  }
  taskSubmitting.value = true;
  try {
    const createdMessage = await chatStore.submitTask({ source_message_id: message.id, product_id: payload.product_id, spec_code: payload.spec_code, image_urls: payload.image_urls, priority: payload.priority ?? 5, metadata: payload.metadata });
    if (createdMessage?.payload?.created_task?.id) ensureTaskStream(createdMessage.payload.created_task.id);
    ElMessage.success("检测任务已创建并开始执行。");
    if (useDialogState) resetTaskDialog();
  } catch (error) {
    ElMessage.error("任务创建失败，请稍后重试。");
    console.error(error);
  } finally { taskSubmitting.value = false; }
}

async function submitTaskDialog() {
  if (!taskSourceMessage.value) return;
  const form = taskFormRef.value;
  if (!form) return;
  try { await form.validate(); } catch { return; }
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

const triggerAttachmentSelect = () => { attachmentInputRef.value?.click(); };
const triggerTaskImageSelect = () => { taskImageInputRef.value?.click(); };

const handleAttachmentSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try { await chatStore.uploadPendingAttachments(files); } catch (error) { ElMessage.error("附件上传失败，请稍后重试。"); console.error(error); } finally { inputElement.value = ""; }
};

const handleTaskImageSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try {
    const { data } = await chatApi.uploadAttachments(files);
    const merged = new Map<string, ChatAttachment>();
    for (const item of [...taskFormAttachments.value, ...data.data.items]) { if (item.url) merged.set(item.url, item); }
    taskFormAttachments.value = Array.from(merged.values());
    syncTaskFormImageUrls();
  } catch (error) { ElMessage.error("任务图片上传失败，请稍后重试。"); console.error(error); } finally { inputElement.value = ""; }
};

function openTraceUrl(url: string) { window.open(url, "_blank", "noopener,noreferrer"); }
function removePendingAttachment(id: string) { chatStore.removePendingAttachment(id); }
function removeTaskAttachment(id: string) { taskFormAttachments.value = taskFormAttachments.value.filter((item) => item.id !== id); syncTaskFormImageUrls(); }

async function scrollToBottom() {
  await nextTick();
  const container = messageListRef.value;
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}

function taskState(taskId: string) { return taskStreamStates.value[taskId] || null; }

function disposeTaskStreams() {
  for (const dispose of taskStreamDisposers.values()) dispose();
  taskStreamDisposers.clear();
}

function ensureTaskStream(taskId: string) {
  if (!taskId || taskStreamDisposers.has(taskId)) return;
  taskStreamStates.value = { ...taskStreamStates.value, [taskId]: taskStreamStates.value[taskId] || { status: "running" } };
  const dispose = taskStore.subscribeTaskStream(taskId, async (event) => {
    taskStreamStates.value = { ...taskStreamStates.value, [taskId]: { status: String(event.status || taskStreamStates.value[taskId]?.status || "running"), stage: typeof event.stage === "string" ? event.stage : taskStreamStates.value[taskId]?.stage, message: typeof event.message === "string" ? event.message : taskStreamStates.value[taskId]?.message } };
    if (event.status === "done" || event.status === "failed") { const currentDispose = taskStreamDisposers.get(taskId); currentDispose?.(); taskStreamDisposers.delete(taskId); await chatStore.reloadCurrentSessionMessages(); }
  });
  taskStreamDisposers.set(taskId, dispose);
}

function syncTaskStreamsFromMessages() {
  const createdTaskIds = new Set(chatStore.messages.map((message) => message.payload?.created_task?.id).filter((value): value is string => Boolean(value)));
  for (const taskId of createdTaskIds) {
    const message = chatStore.messages.find((item) => item.payload?.created_task?.id === taskId);
    const status = String(message?.payload?.created_task?.status || "");
    if (status !== "done" && status !== "failed") ensureTaskStream(taskId);
  }
  for (const [taskId, dispose] of taskStreamDisposers.entries()) { if (!createdTaskIds.has(taskId)) { dispose(); taskStreamDisposers.delete(taskId); } }
}

onMounted(async () => {
  try { await chatStore.initForChatPage(); } catch (error) { ElMessage.error("聊天初始化失败，请刷新页面后重试。"); console.error(error); }
  try { if (inspectionSpecStore.items.length === 0) await inspectionSpecStore.fetchAll(); } catch { /* non-blocking */ }
  try { await billingStore.fetchMyUsage(); } catch { /* non-blocking */ }
  await scrollToBottom();
  syncTaskStreamsFromMessages();
});

onBeforeUnmount(() => { chatStore.stopStream(); disposeTaskStreams(); });

watch(() => chatStore.messages.length, async () => { await scrollToBottom(); syncTaskStreamsFromMessages(); });
watch(() => chatStore.messages.map((item) => `${item.id}:${item.content.length}`).join("|"), async () => { await scrollToBottom(); syncTaskStreamsFromMessages(); });
watch(latestTokenCountedMessageId, async (messageId) => {
  if (!messageId || messageId === syncedUsageMessageId.value) return;
  syncedUsageMessageId.value = messageId;
  try { await billingStore.fetchMyUsage(); } catch { /* non-blocking */ }
});
</script>

<template>
  <div class="chat-page">
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-select
          :model-value="chatStore.selectedRagSpaceId || undefined"
          clearable filterable placeholder="知识库 (可选)"
          size="small" class="rag-select"
          @update:model-value="(value: string) => (value ? chatStore.selectRagSpace(value) : chatStore.clearSelectedRagSpace())"
        >
          <el-option label="不使用知识库" value="" />
          <el-option v-for="space in chatStore.ragSpaces" :key="space.id" :label="`${space.name} (${space.file_count})`" :value="space.id" />
        </el-select>
        <span class="token-badge">Token: {{ totalTokenText }}</span>
        <el-tag v-if="chatStore.selectedRagSpace" size="small" effect="plain" type="success" class="rag-tag">
          {{ chatStore.selectedRagSpace.name }}
        </el-tag>
        <el-tag v-if="chatStore.pendingAttachments.length" size="small" effect="plain" type="warning">
          附件 {{ chatStore.pendingAttachments.length }}
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="chatStore.ragSpacesError"
      class="alert-bar"
      type="warning" :closable="false" show-icon
      title="知识库暂不可用" :description="chatStore.ragSpacesError"
    />

    <!-- Chat area -->
    <div class="chat-shell">
      <div ref="messageListRef" class="message-list">
        <div v-if="chatStore.messages.length === 0" class="empty-state">
          <div class="empty-icon">&#x1F4AC;</div>
          <div class="empty-title">开始对话</div>
          <div class="empty-desc">发送一条消息，智能助手将为你解答问题</div>
        </div>

        <div v-else class="message-group">
          <article
            v-for="message in chatStore.messages"
            :key="message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-meta">
              <span class="role-name">{{ roleLabel(message.role) }}</span>
              <span class="time">{{ formatTime(message.created_at) }}</span>
            </div>

            <div class="bubble" :class="message.role">
              <div class="bubble-text">
                {{ message.content }}
                <span v-if="message.message_type === 'streaming' && chatStore.loading" class="cursor-blink">&nbsp;</span>
              </div>

              <!-- Attachments -->
              <div v-if="message.payload?.attachment_echo?.length" class="bubble-attachments">
                <a v-for="att in message.payload.attachment_echo" :key="att.id" :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
              </div>

              <!-- Tags -->
              <div v-if="message.payload?.intent || message.payload?.selected_rag_space || message.payload?.citations?.length" class="bubble-tags">
                <el-tag v-if="message.payload?.intent" size="small" effect="plain" type="primary">{{ intentLabel(message.payload.intent) }}</el-tag>
                <el-tag v-if="message.payload?.selected_rag_space" size="small" effect="plain" type="success">RAG: {{ message.payload.selected_rag_space.name }}</el-tag>
                <el-tag v-if="message.payload?.citations?.length" size="small" effect="plain" type="info">引用 {{ message.payload.citations.length }}</el-tag>
                <el-tag v-if="message.payload?.trust_scoring" size="small" effect="plain" :type="trustTagType(message.payload.trust_scoring.risk_level)">
                  可信 {{ message.payload.trust_scoring.trust_score == null ? trustStatusText(message.payload.trust_scoring.status) : `${(message.payload.trust_scoring.trust_score * 100).toFixed(0)}%` }}
                </el-tag>
                <el-button
                  v-if="message.payload?.trust_scoring?.trace_url"
                  size="small" link type="primary"
                  @click="openTraceUrl(message.payload.trust_scoring.trace_url)"
                >
                  Trace
                </el-button>
              </div>

              <!-- Trust details -->
              <div v-if="message.payload?.trust_scoring && message.role === 'assistant'" class="trust-detail">
                <span>幻觉风险: {{ message.payload.trust_scoring.hallucination_risk == null ? "-" : (message.payload.trust_scoring.hallucination_risk * 100).toFixed(0) + "%" }}</span>
                <span>过度自信: {{ message.payload.trust_scoring.overconfidence == null ? "-" : (message.payload.trust_scoring.overconfidence * 100).toFixed(0) + "%" }}</span>
                <span>引用: {{ message.payload.trust_scoring.has_citation ? "有" : "无" }}</span>
              </div>

              <!-- Result card -->
              <div v-if="message.payload?.result_card" class="result-card">
                <div class="rc-header">
                  <div>
                    <div class="rc-title">{{ message.payload.result_card.product_name || message.payload.result_card.product_id }}</div>
                    <div class="rc-sub">{{ message.payload.result_card.product_family || "unknown" }} &middot; {{ message.payload.result_card.spec_code }}</div>
                  </div>
                  <div class="rc-badges">
                    <el-tag size="small" effect="dark" :type="verdictTagType(message.payload.result_card.verdict)">{{ message.payload.result_card.verdict.toUpperCase() }}</el-tag>
                    <el-tag size="small" effect="plain" :type="riskTagType(message.payload.result_card.risk_level)">风险 {{ message.payload.result_card.risk_level }}</el-tag>
                  </div>
                </div>
                <div class="rc-grid">
                  <div class="rc-item"><span>总体得分</span><strong>{{ Number(message.payload.result_card.overall_score || 0).toFixed(2) }}</strong></div>
                  <div class="rc-item"><span>RAG 空间</span><strong>{{ message.payload.rag_summary?.rag_space_name || message.payload.rag_summary?.rag_space_id || "未使用" }}</strong></div>
                  <div class="rc-item"><span>引用数量</span><strong>{{ message.payload.rag_summary?.hit_count ?? 0 }}</strong></div>
                  <div class="rc-item"><span>引用覆盖率</span><strong>{{ ((message.payload.rag_summary?.citation_coverage ?? 0) * 100).toFixed(1) }}%</strong></div>
                </div>
                <div v-if="message.payload.result_card.key_reasons?.length" class="rc-reasons">
                  <span class="rc-label">关键原因</span>
                  <div class="rc-tags">
                    <el-tag v-for="reason in message.payload.result_card.key_reasons" :key="reason" size="small" effect="plain">{{ reason }}</el-tag>
                  </div>
                </div>
                <div v-if="message.payload.result_card.failed_rules?.length" class="rc-reasons">
                  <span class="rc-label">失败规则</span>
                  <div class="rc-tags">
                    <el-tag v-for="rule in message.payload.result_card.failed_rules" :key="rule" size="small" type="danger" effect="plain">{{ rule }}</el-tag>
                  </div>
                </div>
                <div class="rc-footer">
                  <div>
                    <span class="rc-label">预期对照</span>
                    <el-tag v-if="message.payload.expectation_check" size="small" effect="plain" :type="message.payload.expectation_check.matched ? 'success' : 'danger'">{{ message.payload.expectation_check.matched ? "与样本预期一致" : "与样本预期不一致" }}</el-tag>
                    <span v-else class="text-xs text-zinc-400">未提供样本预期</span>
                  </div>
                  <div class="rc-sources">
                    <span class="rc-label">Top Sources</span>
                    <span class="text-xs text-zinc-400">{{ message.payload.rag_summary?.top_sources?.join(" / ") || "暂无引用来源" }}</span>
                  </div>
                </div>
                <div class="rc-sync">
                  <el-tag v-if="message.payload.materialization_status" size="small" effect="plain" :type="materializationTagType(message.payload.materialization_status)">{{ message.payload.materialization_status === "synced" ? "已同步" : "同步失败" }}</el-tag>
                  <el-button v-if="message.payload.materialized_task?.id" size="small" link type="primary" @click="router.push(`/app/tasks/${message.payload.materialized_task.id}`)">查看任务</el-button>
                </div>
              </div>

              <!-- Task card -->
              <div v-if="message.payload?.created_task" class="task-card">
                <div class="task-title">检测任务已创建</div>
                <div class="task-grid">
                  <span>任务 ID</span><span>{{ message.payload.created_task.id }}</span>
                  <span>产品编号</span><span>{{ message.payload.created_task.product_id }}</span>
                  <span>检测标准</span><span>{{ message.payload.created_task.spec_code }}</span>
                  <span>图片数量</span><span>{{ message.payload.created_task.image_count }}</span>
                </div>
                <div v-if="taskState(message.payload.created_task.id)" class="task-status">
                  <el-tag size="small" type="warning" effect="plain">{{ taskState(message.payload.created_task.id)?.status || "running" }}</el-tag>
                  <span>{{ taskState(message.payload.created_task.id)?.stage || taskState(message.payload.created_task.id)?.message || "执行中..." }}</span>
                </div>
                <el-button size="small" @click="router.push(`/app/tasks/${message.payload.created_task.id}`)">查看任务详情</el-button>
              </div>

              <!-- Task actions -->
              <div v-if="message.role === 'assistant' && hasTaskAction(message)" class="task-actions">
                <el-alert v-if="message.payload?.missing_slots?.length" type="info" :closable="false" show-icon title="任务信息还不完整，请补充后再提交。" />
                <div class="task-actions-btns">
                  <el-button size="small" @click="openTaskDialog(message)">{{ canConfirmTask(message) ? "编辑检测信息" : "填写检测信息" }}</el-button>
                  <el-button v-if="canConfirmTask(message)" size="small" type="primary" :loading="taskSubmitting" @click="createTaskFromMessage(message, false)">确认并提交任务</el-button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- Composer -->
      <div class="composer">
        <div v-if="chatStore.pendingAttachments.length" class="composer-attachments">
          <el-tag v-for="att in chatStore.pendingAttachments" :key="att.id" closable effect="plain" @close="removePendingAttachment(att.id)">{{ att.name }}</el-tag>
        </div>
        <div v-if="streamStatusText" class="stream-status">{{ streamStatusText }}</div>
        <div class="composer-row">
          <el-input v-model="input" type="textarea" :rows="2" resize="none" placeholder="输入消息，Enter 发送，Shift+Enter 换行" @keydown="onInputKeydown" class="composer-input" />
          <div class="composer-actions">
            <el-button size="small" :icon="Paperclip" @click="triggerAttachmentSelect" />
            <el-button size="small" :icon="CollectionTag" @click="chatStore.selectedRagSpaceId ? chatStore.clearSelectedRagSpace() : undefined" :type="chatStore.selectedRagSpaceId ? 'warning' : 'default'" />
            <el-button type="primary" :icon="Promotion" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage">发送</el-button>
          </div>
        </div>
        <input ref="attachmentInputRef" type="file" multiple hidden @change="handleAttachmentSelected" />
      </div>
    </div>

    <!-- Task dialog -->
    <el-dialog v-model="taskDialogVisible" title="填写检测任务" width="640px" @closed="resetTaskDialog">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-position="top">
        <el-form-item label="产品编号" prop="product_id">
          <el-input v-model="taskForm.product_id" placeholder="例如：P-1001" />
        </el-form-item>
        <el-form-item label="检测标准" prop="spec_code">
          <el-select v-model="taskForm.spec_code" filterable allow-create default-first-option placeholder="选择或输入检测标准" class="!w-full">
            <el-option v-for="spec in specOptions" :key="spec.id" :label="`${spec.spec_code} · ${spec.name}`" :value="spec.spec_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="检测图片" prop="image_urls_input">
          <div class="flex items-center gap-2 mb-2">
            <el-button size="small" @click="triggerTaskImageSelect">上传图片</el-button>
            <span class="text-xs text-zinc-400">也可以直接粘贴图片 URL，每行一个。</span>
          </div>
          <el-input v-model="taskForm.image_urls_input" type="textarea" :rows="5" resize="none" placeholder="https://example.com/a.jpg" />
          <div v-if="taskFormAttachments.length" class="flex flex-wrap gap-2 mt-3">
            <el-tag v-for="att in taskFormAttachments" :key="att.id" closable effect="plain" @close="removeTaskAttachment(att.id)">{{ att.name }}</el-tag>
          </div>
          <input ref="taskImageInputRef" type="file" accept="image/*" multiple hidden @change="handleTaskImageSelected" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-slider v-model="taskForm.priority" :min="1" :max="10" show-input />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetTaskDialog">取消</el-button>
        <el-button type="primary" :loading="taskSubmitting" @click="submitTaskDialog">确认并提交任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ── Page shell — Grid layout guarantees composer stays at bottom ── */
.chat-page {
  display: grid;
  grid-template-rows: auto auto 1fr;
  height: 100%;
  gap: 0;
}

/* ── Toolbar ── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.rag-select { width: 220px; }
.token-badge { font-size: 12px; color: #6b7280; white-space: nowrap; }

/* ── Alert ── */
.alert-bar { margin: 0 12px; border-radius: 10px; }

/* ── Chat shell — Grid: message list fills, composer at bottom ── */
.chat-shell {
  display: grid;
  grid-template-rows: 1fr auto;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}

/* ── Message list ── */
.message-list {
  overflow-y: auto;
  padding: 12px 20px;
  scroll-behavior: smooth;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #9ca3af;
}
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-title { font-size: 18px; font-weight: 600; color: #6b7280; margin-bottom: 8px; }
.empty-desc { font-size: 14px; }

.message-group { display: flex; flex-direction: column; gap: 12px; }

.message-row.user { display: flex; flex-direction: column; align-items: flex-end; }
.message-row.assistant { display: flex; flex-direction: column; align-items: flex-start; }

.message-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 4px;
}
.role-name { font-weight: 600; color: #374151; }
.time { font-variant-numeric: tabular-nums; }

/* ── Bubble ── */
.bubble {
  max-width: min(860px, 92%);
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
}
.bubble.user {
  background: #1f2937;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.bubble.assistant {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 4px;
}
.bubble-text { white-space: pre-wrap; }

.cursor-blink {
  display: inline-block;
  width: 6px;
  height: 14px;
  background: #6b7280;
  border-radius: 1px;
  vertical-align: middle;
  margin-left: 2px;
  animation: blink 0.8s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

.bubble-attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.att-link {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  background: #e5e7eb;
  color: #374151;
  font-size: 12px;
  text-decoration: none;
  border: none;
}
.att-link:hover { background: #d1d5db; }
.bubble.user .att-link { background: rgba(255,255,255,0.15); color: #e5e7eb; }

.bubble-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }

.trust-detail {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin-top: 8px;
  font-size: 11px;
  color: #6b7280;
}

/* ── Result card ── */
.result-card {
  margin-top: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fafafa;
}
.rc-header { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.rc-title { font-size: 15px; font-weight: 700; color: #111827; }
.rc-sub { font-size: 12px; color: #6b7280; margin-top: 2px; }
.rc-badges { display: flex; gap: 6px; }
.rc-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; }
.rc-item { padding: 10px; border-radius: 8px; background: #fff; border: 1px solid #e5e7eb; }
.rc-item span { display: block; font-size: 11px; font-weight: 600; color: #6b7280; }
.rc-item strong { display: block; margin-top: 4px; color: #111827; font-size: 14px; }
.rc-reasons { margin-top: 10px; }
.rc-label { font-size: 11px; font-weight: 600; color: #6b7280; display: block; margin-bottom: 4px; }
.rc-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.rc-footer { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.rc-sources { max-width: 50%; }
.rc-sync { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }

/* ── Task card ── */
.task-card {
  margin-top: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fafafa;
}
.task-title { font-weight: 700; color: #1f2937; margin-bottom: 8px; }
.task-grid { display: grid; grid-template-columns: 72px 1fr; gap: 4px 12px; font-size: 13px; color: #6b7280; }
.task-status { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 13px; color: #6b7280; }
.task-actions { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.task-actions-btns { display: flex; gap: 8px; flex-wrap: wrap; }

/* ── Composer ── */
.composer {
  padding: 10px 16px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}
.composer-attachments { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.stream-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
.composer-row { display: flex; align-items: flex-end; gap: 8px; }
.composer-input { flex: 1; }
.composer-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }

@media (max-width: 640px) {
  .chat-page { height: 100%; }
  .message-list { padding: 8px 10px; }
  .bubble { max-width: 96%; }
  .rc-grid { grid-template-columns: repeat(2, 1fr); }
  .composer-row { flex-wrap: wrap; }
}
</style>
