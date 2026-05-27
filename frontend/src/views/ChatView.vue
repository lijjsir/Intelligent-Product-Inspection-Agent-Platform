<script setup lang="ts">
import { CircleClose, CollectionTag, Paperclip, Promotion } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { feedbackApi } from "@/api/feedback.api";
import ChatInspectionContextPanel from "@/components/chat/ChatInspectionContextPanel.vue";
import PromptTemplateTray from "@/components/chat/PromptTemplateTray.vue";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useBillingStore } from "@/stores/billing.store";
import { useChatStore } from "@/stores/chat.store";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import type { ChatAttachment, ChatMessage, ChatTaskDraft } from "@/types/chat.types";
import type { InspectionTask, TaskCreate } from "@/types/task.types";
import { writeTextToClipboard } from "@/utils/clipboard";
import { canConfirmTaskAction, hasTaskAction } from "./chat-task-actions";

const router = useRouter();
const billingStore = useBillingStore();
const chatStore = useChatStore();
const taskStore = useTaskStore();
const inspectionSpecStore = useInspectionSpecStore();

const input = ref("");
const messageListRef = ref<HTMLElement | null>(null);
const attachmentInputRef = ref<HTMLInputElement | null>(null);
const webSearchEnabled = ref(false);
const inspectionContextEnabled = false;
const selectedInspectionTasks = ref<InspectionTask[]>([]);

const taskDialogVisible = ref(false);
const taskSubmitting = ref(false);
const taskFormRef = ref<FormInstance>();
const taskSourceMessage = ref<ChatMessage | null>(null);
const taskStreamStates = ref<Record<string, { status: string; stage?: string; message?: string }>>({});
const taskStreamDisposers = new Map<string, () => void>();
const taskForm = ref({
  product_id: "",
  spec_code: "",
  image_urls_input: "",
  priority: 5,
});

const taskRules: FormRules = {
  product_id: [{ required: true, message: "请选择检测标准以自动填入产品线", trigger: "blur" }],
  spec_code: [{ required: true, message: "请选择或输入检测标准", trigger: "blur" }],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasText = Boolean(value?.trim());
        const hasUploads = chatStore.pendingAttachments.length > 0;
        if (!hasText && !hasUploads) {
          callback(new Error("请至少提供一张待检测图片"));
          return;
        }
        callback();
      },
      trigger: "blur",
    },
  ],
};

const canSend = computed(() => !chatStore.loading && Boolean(input.value.trim() || chatStore.pendingAttachments.length > 0));
const composerPlaceholder = computed(() => "输入消息，Enter 发送，Shift+Enter 换行");
const streamStatusText = computed(() => {
  if (!chatStore.loading) return "";
  if (chatStore.streamPhase === "connecting") return "正在建立连接...";
  if (chatStore.streamPhase === "streaming") return "智能体处理中...";
  if (chatStore.streamPhase === "closing") return "正在整理回复...";
  return "智能体处理中...";
});
const specOptions = computed(() => inspectionSpecStore.items);
const filteredSpecOptions = computed(() =>
  specOptions.value.filter((item) => item.is_active),
);
const selectedTaskSpec = computed(() => specOptions.value.find((item) => item.spec_code === taskForm.value.spec_code) || null);
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
const messageReactions = ref<Record<string, "up" | "down">>({});
const editingMessageId = ref("");
const editingContent = ref("");

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

function paperScoreTagType(score: number) {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "danger";
}

function downloadReport(file: { url: string; file_name: string }) {
  const a = document.createElement("a");
  a.href = file.url;
  a.download = file.file_name;
  a.target = "_blank";
  a.click();
}

function parseImageUrls(value: string) {
  return value.split(/\r?\n|,|;/).map((item) => item.trim()).filter(Boolean);
}

function buildTaskDraft(message: ChatMessage): ChatTaskDraft | null {
  return message.payload?.task_form_defaults || message.payload?.task_draft || null;
}

function canConfirmTask(message: ChatMessage) {
  return canConfirmTaskAction(message);
}

function onTaskSpecChange(specCode: string) {
  const spec = specOptions.value.find((s) => s.spec_code === specCode);
  if (spec) {
    taskForm.value.product_id = spec.product_family || spec.product_id || "";
  }
}

function fillTaskForm(message: ChatMessage) {
  const draft = buildTaskDraft(message);
  taskForm.value = {
    product_id: draft?.product_id || "",
    spec_code: draft?.spec_code || "",
    image_urls_input: (draft?.image_urls || []).join("\n"),
    priority: draft?.priority ?? 5,
  };
}

let specsLoadPromise: Promise<void> | null = null;

async function ensureInspectionSpecsLoaded(force = false) {
  if (!force && inspectionSpecStore.items.length > 0) return;
  if (!specsLoadPromise) {
    specsLoadPromise = (async () => {
      try {
        await inspectionSpecStore.fetchAll();
      } catch (error) {
        ElMessage.error("检测标准加载失败，请稍后重试。");
        console.error(error);
      } finally {
        specsLoadPromise = null;
      }
    })();
  }
  await specsLoadPromise;
}

async function openTaskDialog(message: ChatMessage) {
  await ensureInspectionSpecsLoaded(true);
  taskSourceMessage.value = message;
  fillTaskForm(message);
  taskDialogVisible.value = true;
}

async function openManualTaskDialog() {
  await ensureInspectionSpecsLoaded(true);
  taskSourceMessage.value = null;
  taskForm.value = { product_id: "", spec_code: "", image_urls_input: "", priority: 5 };
  chatStore.clearPendingAttachments();
  taskDialogVisible.value = true;
  nextTick(() => taskFormRef.value?.clearValidate());
}

async function handleTaskSpecDropdownVisible(visible: boolean) {
  if (!visible) return;
  await ensureInspectionSpecsLoaded(true);
}

function resetTaskDialog() {
  taskDialogVisible.value = false;
  taskSourceMessage.value = null;
  taskForm.value = { product_id: "", spec_code: "", image_urls_input: "", priority: 5 };
  taskFormRef.value?.clearValidate();
}

function buildTaskPayload(message: ChatMessage | null, useDialogState: boolean): TaskCreate {
  if (useDialogState) {
    const imageUrls = Array.from(
      new Set([...chatStore.pendingAttachments.map((item) => item.url), ...parseImageUrls(taskForm.value.image_urls_input)]),
    );
    return { product_id: taskForm.value.product_id.trim(), spec_code: taskForm.value.spec_code.trim(), image_urls: imageUrls, priority: taskForm.value.priority, metadata: { source: "chat" } };
  }
  const draft = message ? buildTaskDraft(message) : null;
  return { product_id: String(draft?.product_id || "").trim(), spec_code: String(draft?.spec_code || "").trim(), image_urls: (draft?.image_urls || []).filter(Boolean), priority: draft?.priority ?? 5, metadata: { source: "chat" } };
}

async function submitTaskPayload(payload: TaskCreate, sourceMessageId?: string | null) {
  if (!payload.product_id || !payload.spec_code || payload.image_urls.length === 0) {
    ElMessage.warning("\u68c0\u6d4b\u4efb\u52a1\u4fe1\u606f\u8fd8\u4e0d\u5b8c\u6574\uff0c\u8bf7\u5148\u8865\u5168\u8868\u5355\u3002");
    return;
  }
  const draft = {
    ...payload,
    priority: payload.priority ?? 5,
    metadata: { ...(payload.metadata || {}), source: "chat_draft", chat_source_message_id: sourceMessageId || undefined },
  };
  sessionStorage.setItem("piap_quality_task_draft", JSON.stringify(draft));
  ElMessage.info("\u804a\u5929\u9875\u53ea\u4fdd\u7559\u4efb\u52a1\u8349\u7a3f\uff0c\u8bf7\u5728\u8d28\u91cf\u68c0\u6d4b\u4efb\u52a1\u9875\u786e\u8ba4\u5e76\u63d0\u4ea4\u6b63\u5f0f\u68c0\u6d4b\u3002");
  await router.push({ path: "/app/tasks", query: { create: "1", source: "chat" } });
}

async function createTaskFromMessage(message: ChatMessage, useDialogState: boolean) {
  const payload = buildTaskPayload(message, useDialogState);
  await submitTaskPayload(payload, message.id);
  if (useDialogState) resetTaskDialog();
}

async function submitTaskDialog() {
  const form = taskFormRef.value;
  if (!form) return;
  try { await form.validate(); } catch { return; }
  if (taskSourceMessage.value) {
    const payload = buildTaskPayload(taskSourceMessage.value, true);
    await submitTaskPayload(payload, taskSourceMessage.value.id);
    resetTaskDialog();
    return;
  }
  const lines: string[] = [];
  const pid = taskForm.value.product_id.trim();
  const spec = taskForm.value.spec_code.trim();
  if (pid) lines.push(`\u4ea7\u54c1\u7f16\u53f7\uff1a${pid}`);
  if (spec) lines.push(`\u6807\u51c6\uff1a${spec}`);
  if (taskForm.value.image_urls_input.trim()) lines.push(`\u56fe\u7247URL\uff1a${taskForm.value.image_urls_input.trim()}`);
  const msg = `\u521b\u5efa\u8d28\u68c0\u4efb\u52a1\u3002${lines.join("\uff1b")}`;
  resetTaskDialog();
  taskSubmitting.value = true;
  try {
    await chatStore.sendMessage({
      message: msg,
      ext: {
        ui_mode: "inspection",
        product_id: pid || undefined,
        spec_code: spec || undefined,
      },
    });
  } catch (error) {
    ElMessage.error("\u4efb\u52a1\u521b\u5efa\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
    console.error(error);
  } finally { taskSubmitting.value = false; }
}

async function sendMessage() {
  if (!canSend.value) return;
  const message = input.value.trim() || "请先查看附件并说明你能识别到的信息。";
  try {
    await chatStore.sendMessage({
      message,
      metadata: undefined,
      ext: {
        ui_mode: "auto",
        force_web_search: webSearchEnabled.value || undefined,
        inspection_context_enabled: inspectionContextEnabled,
        selected_inspection_task_ids: inspectionContextEnabled ? selectedInspectionTasks.value.map((task) => task.id) : [],
      },
    });
    input.value = "";
  } catch (error) {
    ElMessage.error("消息发送失败，请稍后重试。");
    console.error(error);
  }
}

function appendInspectionContextReference(value: string) {
  const text = value.trim();
  if (!text) return;
  input.value = input.value.trim() ? `${input.value.trim()}\n\n${text}` : text;
  ElMessage.success("已把任务引用加入输入框");
}

function toggleSelectedInspectionTask(task: InspectionTask) {
  const exists = selectedInspectionTasks.value.some((item) => item.id === task.id);
  selectedInspectionTasks.value = exists
    ? selectedInspectionTasks.value.filter((item) => item.id !== task.id)
    : [...selectedInspectionTasks.value, task].slice(-8);
}

function clearSelectedInspectionTasks() {
  selectedInspectionTasks.value = [];
}

const onInputKeydown = async (event: KeyboardEvent) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendMessage();
  }
};

const triggerAttachmentSelect = () => { attachmentInputRef.value?.click(); };

function extractClipboardImageFiles(event: ClipboardEvent) {
  return Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

const handleAttachmentSelected = async (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  const files = Array.from(inputElement.files || []);
  if (files.length === 0) return;
  try { await chatStore.uploadPendingAttachments(files); } catch (error) { ElMessage.error("\u9644\u4ef6\u4e0a\u4f20\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"); console.error(error); } finally { inputElement.value = ""; }
};

const handleComposerPaste = async (event: ClipboardEvent) => {
  const files = extractClipboardImageFiles(event);
  if (files.length === 0) return;
  event.preventDefault();
  try {
    await chatStore.uploadPendingAttachments(files);
    ElMessage.success(`\u5df2\u7c98\u8d34 ${files.length} \u5f20\u56fe\u7247`);
  } catch (error) {
    ElMessage.error("\u56fe\u7247\u7c98\u8d34\u4e0a\u4f20\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
    console.error(error);
  }
};

const handleTaskDialogPaste = async (event: ClipboardEvent) => {
  const files = extractClipboardImageFiles(event);
  if (files.length === 0) return;
  event.preventDefault();
  try {
    await chatStore.uploadPendingAttachments(files);
    ElMessage.success(`\u5df2\u6dfb\u52a0 ${files.length} \u5f20\u4efb\u52a1\u56fe\u7247`);
  } catch (error) {
    ElMessage.error("\u4efb\u52a1\u56fe\u7247\u7c98\u8d34\u4e0a\u4f20\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
    console.error(error);
  }
};

function removePendingAttachment(id: string) { chatStore.removePendingAttachment(id); }

async function copyToClipboard(text: string, successText = "已复制") {
  try {
    const copied = await writeTextToClipboard(text);
    if (!copied) throw new Error("clipboard unavailable");
    ElMessage.success(successText);
  } catch {
    ElMessage.error("复制失败，请手动复制。");
  }
}

function shareChatMessage(message: ChatMessage) {
  const url = `${window.location.origin}${window.location.pathname}#chat-message-${message.id}`;
  copyToClipboard(url, "分享链接已复制");
}

function messageAttachments(message: ChatMessage): ChatAttachment[] {
  return [...(message.payload?.attachment_echo || [])];
}

// ── Typewriter effect ────────────────────────────────────────────
const typewriterPos = ref<Record<string, number>>({});
const typewriterTimers = new Map<string, ReturnType<typeof setInterval>>();

function getDisplayedContent(message: ChatMessage): string {
  if (message.role !== "assistant") return message.content;
  const pos = typewriterPos.value[message.id];
  if (pos === undefined) {
    // streaming but timer not yet started → show empty, avoid flash
    return message.message_type === "streaming" ? "" : message.content;
  }
  return message.content.slice(0, pos);
}

function ensureTypewriter(msgId: string) {
  if (typewriterTimers.has(msgId)) return;
  if (typewriterPos.value[msgId] === undefined) {
    typewriterPos.value[msgId] = 0;
  }
  const TICK_MS = 20; // ~50 chars/sec
  const timer = setInterval(() => {
    const msg = chatStore.messages.find((m) => m.id === msgId);
    if (!msg) { disposeTypewriter(msgId); return; }
    const target = msg.content.length;
    const current = typewriterPos.value[msgId] ?? 0;
    if (current >= target) {
      if (msg.message_type !== "streaming") disposeTypewriter(msgId);
      return;
    }
    typewriterPos.value[msgId] = current + 1;
  }, TICK_MS);
  typewriterTimers.set(msgId, timer);
}

function disposeTypewriter(msgId: string) {
  const timer = typewriterTimers.get(msgId);
  if (timer) { clearInterval(timer); typewriterTimers.delete(msgId); }
  delete typewriterPos.value[msgId];
}

function disposeAllTypewriters() {
  for (const timer of typewriterTimers.values()) clearInterval(timer);
  typewriterTimers.clear();
  typewriterPos.value = {};
}

// Only START typewriters — never stop them from the watch.
// The timer self-destructs when content is fully revealed AND streaming ended.
watch(
  () =>
    chatStore.messages
      .filter((m) => m.role === "assistant" && m.message_type === "streaming")
      .map((m) => m.id),
  (ids) => { for (const id of ids) ensureTypewriter(id); },
  { deep: false, immediate: true },
);

onBeforeUnmount(() => disposeAllTypewriters());

const RAG_CITE_RE = /\[RAG-(\d+)\]/g;

function renderRagCitations(content: string): Array<{ type: "text" | "cite"; value: string }> {
  const segments: Array<{ type: "text" | "cite"; value: string }> = [];
  let last = 0;
  let match: RegExpExecArray | null;
  RAG_CITE_RE.lastIndex = 0;
  while ((match = RAG_CITE_RE.exec(content)) !== null) {
    if (match.index > last) {
      segments.push({ type: "text", value: content.slice(last, match.index) });
    }
    segments.push({ type: "cite", value: match[1] });
    last = match.index + match[0].length;
  }
  if (last < content.length) {
    segments.push({ type: "text", value: content.slice(last) });
  }
  return segments.length > 0 ? segments : [{ type: "text", value: content }];
}

async function interruptCurrentResponse(silent = false) {
  try {
    await chatStore.cancelCurrentResponse();
    if (!silent) ElMessage.success("已中断本次回答");
    return true;
  } catch (error) {
    ElMessage.error("中断回答失败，请稍后重试。");
    console.error(error);
    return false;
  }
}

async function editUserMessage(message: ChatMessage) {
  if (message.role !== "user") return;
  if (editingMessageId.value === message.id) {
    cancelQuestionEdit();
    return;
  }
  if (chatStore.loading) {
    if (!chatStore.canCancelResponse) {
      ElMessage.warning("回答刚开始，请稍等片刻再编辑。");
      return;
    }
    const interrupted = await interruptCurrentResponse(true);
    if (!interrupted) return;
  }
  editingMessageId.value = message.id;
  editingContent.value = message.content;
  chatStore.replacePendingAttachments(messageAttachments(message));
}

function cancelQuestionEdit() {
  editingMessageId.value = "";
  editingContent.value = "";
  chatStore.clearPendingAttachments();
}

async function saveEditedMessage(message: ChatMessage) {
  if (!editingContent.value.trim()) return;
  try {
    await chatStore.sendMessage({
      message: editingContent.value.trim(),
      metadata: { edited_from_message_id: message.id },
      ext: { ui_mode: "auto" },
    });
    editingMessageId.value = "";
    editingContent.value = "";
    chatStore.clearPendingAttachments();
  } catch (error) {
    ElMessage.error("消息发送失败，请稍后重试。");
    console.error(error);
  }
}

function onEditKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    const msg = chatStore.messages.find((m) => m.id === editingMessageId.value);
    if (msg) saveEditedMessage(msg);
  } else if (event.key === "Escape") {
    cancelQuestionEdit();
  }
}

function resolveResultId(message: ChatMessage) {
  return (
    message.payload?.result_id ||
    message.payload?.materialized_task?.result_id ||
    message.payload?.created_task?.result_id ||
    (message.payload?.result as { id?: string } | undefined)?.id ||
    ""
  );
}

function taskCardTitle(message: ChatMessage) {
  const status = String(message.payload?.created_task?.status || "");
  if (message.payload?.result || status === "done") return "检测任务执行完成";
  if (status === "failed") return "检测任务执行失败";
  if (status === "queued" || status === "running") return "检测任务已启动";
  return "检测任务已创建";
}

function taskResult(message: ChatMessage) {
  const value = message.payload?.result;
  return value && typeof value === "object" ? value as { id?: string; verdict?: string; overall_score?: number; risk_level?: string; risk_score?: number } : null;
}

function resultVerdictType(verdict?: string) {
  if (verdict === "pass") return "success";
  if (verdict === "fail") return "danger";
  return "warning";
}

async function loadMessageReactions() {
  const ids = chatStore.messages
    .filter((message) => !message.optimistic)
    .map((message) => message.id)
    .filter(Boolean);
  if (ids.length === 0) {
    messageReactions.value = {};
    return;
  }
  try {
    const { data } = await feedbackApi.listMessages({
      target_type: "chat",
      target_ids: ids.join(","),
    });
    const next: Record<string, "up" | "down"> = {};
    for (const item of data.data) {
      next[item.target_id] = item.feedback_type;
    }
    messageReactions.value = next;
  } catch {
    // Feedback state is decorative for the chat surface; sending feedback still reports errors.
  }
}

async function submitChatFeedback(message: ChatMessage, feedbackType: "up" | "down") {
  if (message.optimistic || message.message_type === "streaming") return;
  const previous = messageReactions.value[message.id];
  messageReactions.value = { ...messageReactions.value, [message.id]: feedbackType };
  try {
    await feedbackApi.submitMessage("chat", message.id, {
      feedback_type: feedbackType,
      rating: feedbackType === "up" ? 5 : 1,
      category: (feedbackType === "up" ? "helpful" : "not_helpful") as any,
      comment: `chat_message:${message.message_type}`,
    });
    const resultId = resolveResultId(message);
    if (resultId) {
      await feedbackApi.submit(resultId, {
        feedback_type: feedbackType,
        rating: feedbackType === "up" ? 5 : 1,
        category: (feedbackType === "up" ? "chat_helpful" : "chat_not_helpful") as any,
        comment: `from_chat_message:${message.id}`,
      });
    }
    ElMessage.success(feedbackType === "up" ? "已点赞" : "已点踩");
  } catch (error) {
    if (previous) {
      messageReactions.value = { ...messageReactions.value, [message.id]: previous };
    } else {
      const next = { ...messageReactions.value };
      delete next[message.id];
      messageReactions.value = next;
    }
    ElMessage.error("反馈提交失败，请稍后重试。");
    console.error(error);
  }
}

async function retryFromAssistantMessage(message: ChatMessage) {
  if (chatStore.loading) return;
  const index = chatStore.messages.findIndex((item) => item.id === message.id);
  const source = [...chatStore.messages.slice(0, index)]
    .reverse()
    .find((item) => item.role === "user" && item.content.trim());
  if (!source) {
    ElMessage.warning("没有找到可重试的上一条用户消息。");
    return;
  }
  const sourceRag = source.payload?.selected_rag_space;
  if (sourceRag?.id) {
    chatStore.selectRagSpace(sourceRag.id);
  } else {
    chatStore.clearSelectedRagSpace();
  }
  try {
    await chatStore.sendMessage({
      message: source.content,
      ext: {
        ui_mode: "auto",
      },
    });
  } catch (error) {
    ElMessage.error("重试失败，请稍后再试。");
    console.error(error);
  }
}

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
  await ensureInspectionSpecsLoaded();
  try { await billingStore.fetchMyUsage({ suppressErrorToast: true }); } catch { /* non-blocking */ }
  await scrollToBottom();
  syncTaskStreamsFromMessages();
  await loadMessageReactions();
});

onBeforeUnmount(() => { chatStore.stopStream(); disposeTaskStreams(); });

watch(() => chatStore.messages.length, async () => { await scrollToBottom(); syncTaskStreamsFromMessages(); });
watch(() => chatStore.messages.map((item) => `${item.id}:${item.content.length}`).join("|"), async () => { await scrollToBottom(); syncTaskStreamsFromMessages(); });
watch(() => chatStore.messages.map((item) => item.id).join(","), loadMessageReactions);
watch(latestTokenCountedMessageId, async (messageId) => {
  if (!messageId || messageId === syncedUsageMessageId.value) return;
  syncedUsageMessageId.value = messageId;
  try { await billingStore.fetchMyUsage({ suppressErrorToast: true }); } catch { /* non-blocking */ }
});
</script>

<template>
  <div class="chat-page">
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="token-badge">Token: {{ totalTokenText }}</span>
        <el-select
          v-model="chatStore.selectedRagSpaceId"
          placeholder="选择知识库"
          clearable
          size="small"
          class="rag-select"
          @change="(val: string) => val ? chatStore.selectRagSpace(val) : chatStore.clearSelectedRagSpace()"
        >
          <el-option
            v-for="space in chatStore.ragSpaces"
            :key="space.id"
            :label="space.name"
            :value="space.id"
          />
        </el-select>
        <el-tooltip :content="webSearchEnabled ? '联网搜索已开启：Agent 必须使用网络检索' : '联网搜索已关闭：Agent 自行判断'" placement="bottom">
          <el-button
            size="small"
            :type="webSearchEnabled ? 'primary' : 'default'"
            :icon="Promotion"
            @click="webSearchEnabled = !webSearchEnabled"
          >
            {{ webSearchEnabled ? '联网搜索·开' : '联网搜索' }}
          </el-button>
        </el-tooltip>
        <el-tag v-if="chatStore.pendingAttachments.length" size="small" effect="plain" type="warning">
          &#x9644;&#x4EF6; {{ chatStore.pendingAttachments.length }}
        </el-tag>
</div>
    </div>

    <el-alert
      v-if="chatStore.ragSpacesError"
      class="alert-bar"
      type="warning" :closable="false" show-icon
      title="知识库暂不可用" :description="chatStore.ragSpacesError"
    />

    <ChatInspectionContextPanel
      v-if="inspectionContextEnabled"
      class="inspection-context-strip"
      :context="chatStore.inspectionContext"
      :error="chatStore.inspectionContextError"
      :selected-task-ids="selectedInspectionTasks.map((task) => task.id)"
      @refresh="chatStore.fetchInspectionContext"
      @reference="appendInspectionContextReference"
      @toggle-task="toggleSelectedInspectionTask"
      @clear-selected="clearSelectedInspectionTasks"
    />

    <!-- Chat area -->
    <div class="chat-shell">
      <div ref="messageListRef" class="message-list">
        <div v-if="chatStore.messages.length === 0" class="empty-state">
          <div class="empty-icon">&#x1F4AC;</div>
          <div class="empty-title">&#x5F00;&#x59CB;&#x5BF9;&#x8BDD;</div>
          <div class="empty-desc">&#x53D1;&#x9001;&#x4E00;&#x6761;&#x6D88;&#x606F;&#xFF0C;&#x667A;&#x80FD;&#x52A9;&#x624B;&#x5C06;&#x4E3A;&#x4F60;&#x89E3;&#x7B54;&#x95EE;&#x9898;</div>
        </div>

        <div v-else class="message-group">
          <article
            v-for="message in chatStore.messages"
            :key="message.id"
            :id="`chat-message-${message.id}`"
            class="message-row"
            :class="message.role"
          >
            <div class="message-meta">
              <span class="role-name">{{ roleLabel(message.role) }}</span>
              <span class="time">{{ formatTime(message.created_at) }}</span>
            </div>

            <div class="bubble" :class="message.role">
              <div v-if="editingMessageId === message.id" class="bubble-edit">
                <el-input
                  v-model="editingContent"
                  type="textarea"
                  :rows="3"
                  resize="vertical"
                  class="bubble-edit-input"
                  @keydown="onEditKeydown"
                />
                <div class="bubble-edit-actions">
                  <el-button size="small" @click="cancelQuestionEdit">取消</el-button>
                  <el-button size="small" type="primary" @click="saveEditedMessage(message)">保存并发送</el-button>
                </div>
              </div>
              <div v-else class="bubble-text">
                <template v-for="(seg, si) in renderRagCitations(getDisplayedContent(message))" :key="si">
                  <span v-if="seg.type === 'text'">{{ seg.value }}</span>
                  <span v-else class="rag-cite" :title="`RAG 引用 #${seg.value}`">RAG-{{ seg.value }}</span>
                </template>
                <span v-if="message.message_type === 'streaming' && chatStore.loading" class="cursor-blink">&nbsp;</span>
              </div>

              <!-- Attachments -->
              <div v-if="message.payload?.attachment_echo?.length" class="bubble-attachments">
                <a v-for="att in message.payload.attachment_echo" :key="att.id" :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
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
                  <div class="rc-item"><span>系统标准</span><strong>{{ message.payload.rag_summary?.standard_binding_name || "未命中" }}</strong></div>
                  <div class="rc-item"><span>系统标准空间</span><strong>{{ message.payload.rag_summary?.system_rag_space_names?.join(" / ") || "无" }}</strong></div>
                  <div class="rc-item"><span>合并来源数</span><strong>{{ message.payload.rag_summary?.merged_rag_source_count ?? 0 }}</strong></div>
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

              <!-- Paper review report card -->
              <div v-if="message.payload?.paper_format_report" class="paper-review-card">
                <div class="prc-header">
                  <span class="prc-title">论文查非辅助报告</span>
                  <div class="prc-header-right">
                    <el-tag v-if="message.payload.paper_format_report.model_used === false" size="small" type="warning" effect="dark">
                      模型未生效-仅规则检查
                    </el-tag>
                    <el-tag size="small" effect="dark" :type="paperScoreTagType(message.payload.paper_format_report.score)">
                      {{ message.payload.paper_format_report.score }} / 100
                    </el-tag>
                  </div>
                </div>
                <div class="prc-meta" v-if="message.payload.paper_format_report.document_type">
                  <span>文档：{{ message.payload.paper_format_report.document_type?.toUpperCase() }}</span>
                  <span v-if="message.payload.paper_format_report.template_id">模板：{{ message.payload.paper_format_report.template_id }}</span>
                </div>
                <div class="prc-grid">
                  <div class="prc-item">
                    <span>发现问题</span>
                    <strong>{{ message.payload.paper_format_report.issue_count }}</strong>
                  </div>
                  <div class="prc-item">
                    <span>高优先级</span>
                    <strong class="prc-high">{{ message.payload.paper_format_report.high_count }}</strong>
                  </div>
                  <div class="prc-item">
                    <span>中优先级</span>
                    <strong class="prc-medium">{{ message.payload.paper_format_report.medium_count }}</strong>
                  </div>
                  <div class="prc-item">
                    <span>低优先级</span>
                    <strong class="prc-low">{{ message.payload.paper_format_report.low_count }}</strong>
                  </div>
                </div>
                <div class="prc-summary" v-if="message.payload.paper_format_report.summary">
                  {{ message.payload.paper_format_report.summary }}
                </div>
                <div class="prc-template-errors" v-if="message.payload.paper_format_report.template_errors?.length">
                  <el-alert
                    v-for="(err, ei) in message.payload.paper_format_report.template_errors"
                    :key="ei"
                    :title="err"
                    type="error"
                    show-icon
                    :closable="false"
                    style="margin-bottom: 6px;"
                  />
                </div>
                <div class="prc-limitations" v-if="message.payload.paper_format_report.limitations?.length">
                  <span v-for="limit in message.payload.paper_format_report.limitations" :key="limit" class="prc-limit-tag">{{ limit }}</span>
                </div>
                <div class="prc-downloads">
                  <el-button
                    v-for="file in message.payload.paper_format_report.report_files"
                    :key="file.format"
                    size="small"
                    type="primary"
                    :plain="file.format !== 'md'"
                    @click="downloadReport(file)"
                  >
                    下载 {{ file.format.toUpperCase() }}
                  </el-button>
                  <span v-if="!message.payload.paper_format_report.report_files?.length" class="prc-no-files">
                    报告文件生成中，请稍后刷新页面下载。
                  </span>
                </div>
              </div>

              <!-- Task card -->
              <div v-if="message.payload?.created_task" class="task-card">
                <div class="task-title">{{ taskCardTitle(message) }}</div>
                <div class="task-grid">
                  <span>任务 ID</span><span>{{ message.payload.created_task.id }}</span>
                  <span>产品线</span><span>{{ message.payload.created_task.product_id }}</span>
                  <span>检测标准</span><span>{{ message.payload.created_task.spec_code }}</span>
                  <span>图片数量</span><span>{{ message.payload.created_task.image_count }}</span>
                </div>
                <div v-if="taskState(message.payload.created_task.id)" class="task-status">
                  <el-tag size="small" type="warning" effect="plain">{{ taskState(message.payload.created_task.id)?.status || "running" }}</el-tag>
                  <span>{{ taskState(message.payload.created_task.id)?.stage || taskState(message.payload.created_task.id)?.message || "执行中..." }}</span>
                </div>
                <div v-if="taskResult(message)" class="task-result-strip">
                  <el-tag size="small" effect="dark" :type="resultVerdictType(taskResult(message)?.verdict)">{{ taskResult(message)?.verdict || "uncertain" }}</el-tag>
                  <span>综合评分 {{ Number(taskResult(message)?.overall_score || 0).toFixed(3) }}</span>
                  <span>风险 {{ taskResult(message)?.risk_level || "-" }}</span>
                  <span>风险分 {{ Number(taskResult(message)?.risk_score || 0).toFixed(3) }}</span>
                </div>
                <div class="task-card-actions">
                  <el-button size="small" @click="router.push(`/app/tasks/${message.payload.created_task.id}`)">查看任务详情</el-button>
                  <el-button v-if="taskResult(message)" size="small" type="primary" plain @click="router.push(`/app/results/${message.payload.created_task.id}`)">查看质检结果</el-button>
                </div>
              </div>

              <!-- Task actions -->
              <div v-if="message.role === 'assistant' && hasTaskAction(message)" class="task-actions">
                <div class="task-action-note">
                  <strong>当前还是任务草稿</strong>
                  <span>你可以继续追问识别依据、补充检测关注点或修改字段；点确认后才会创建正式任务并进入执行队列。</span>
                </div>
                <el-alert v-if="message.payload?.missing_slots?.length" type="info" :closable="false" show-icon title="任务信息还不完整，请补充后再提交。" />
                <div class="task-actions-btns">
                  <el-button size="small" @click="openTaskDialog(message)">{{ canConfirmTask(message) ? "编辑检测信息" : "补全任务信息" }}</el-button>
                  <el-button v-if="canConfirmTask(message)" size="small" type="primary" :loading="taskSubmitting" @click="createTaskFromMessage(message, false)">前往任务页确认</el-button>
                </div>
              </div>
            </div>
            <MessageActionBar
              :reaction="messageReactions[message.id] || ''"
              :show-edit="message.role === 'user'"
              :show-feedback="message.role === 'assistant' && message.message_type !== 'streaming'"
              :show-retry="message.role === 'assistant' && message.message_type !== 'streaming'"
              :retry-disabled="chatStore.loading"
              @copy="copyToClipboard(message.content, '消息已复制')"
              @edit="editUserMessage(message)"
              @like="submitChatFeedback(message, 'up')"
              @dislike="submitChatFeedback(message, 'down')"
              @share="shareChatMessage(message)"
              @retry="retryFromAssistantMessage(message)"
            />
          </article>
        </div>
      </div>

      <!-- Composer -->
      <div class="composer">

        <div v-if="chatStore.pendingAttachments.length" class="composer-attachments">
          <el-tag v-for="att in chatStore.pendingAttachments" :key="att.id" closable effect="plain" @close="removePendingAttachment(att.id)">{{ att.name }}</el-tag>
        </div>
        <div v-if="streamStatusText" class="stream-status">
          <span>{{ streamStatusText }}</span>
          <el-button
            v-if="chatStore.canCancelResponse"
            size="small"
            type="danger"
            link
            :icon="CircleClose"
            @click="interruptCurrentResponse()"
          >
            中断回答
          </el-button>
        </div>
        <PromptTemplateTray v-model="input" class="prompt-template-entry" />
        <div class="composer-row" @paste="handleComposerPaste">
          <el-input v-model="input" type="textarea" :rows="2" resize="none" :placeholder="composerPlaceholder" @keydown="onInputKeydown" class="composer-input" />
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
    <el-dialog v-model="taskDialogVisible" :title="taskSourceMessage ? '编辑检测信息' : '整理质检任务草稿'" width="640px" destroy-on-close @closed="resetTaskDialog">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-position="top">
        <el-form-item label="检测标准" prop="spec_code">
          <el-select v-model="taskForm.spec_code" filterable allow-create default-first-option placeholder="选择或输入检测标准" class="!w-full" @change="onTaskSpecChange">
            <el-option v-for="spec in filteredSpecOptions" :key="spec.id" :label="`${spec.spec_code} · ${spec.name}`" :value="spec.spec_code" />
          </el-select>
          <div class="task-form-toolbar">
            <span class="task-form-toolbar-text">如果下拉列表没有及时更新，可以手动刷新一次。</span>
            <el-button link type="primary" :loading="inspectionSpecStore.loading" @click="ensureInspectionSpecsLoaded(true)">刷新检测标准</el-button>
          </div>
          <div class="task-form-hint">
            &#x5F53;&#x524D;&#x53EF;&#x9009; {{ filteredSpecOptions.length }} &#x4E2A;&#x68C0;&#x6D4B;&#x6807;&#x51C6;&#x3002;
          </div>
          <div v-if="selectedTaskSpec" class="task-spec-preview">
            <div class="task-spec-preview-title">
              {{ selectedTaskSpec.spec_code }} · {{ selectedTaskSpec.name }}
            </div>
            <div class="task-spec-preview-grid">
              <span>&#x4EA7;&#x54C1;&#x7EBF;</span><strong v-if="selectedTaskSpec.product_id">{{ selectedTaskSpec.product_id }}</strong><strong v-else>&#x5168;&#x5C40;</strong>
              <span>&#x9700;&#x8981;&#x56FE;&#x7247;</span><strong>{{ selectedTaskSpec.required_image_count }}</strong>
              <span>&#x81EA;&#x52A8;&#x653E;&#x884C;</span><strong v-if="selectedTaskSpec.auto_pass_enabled">&#x5F00;&#x542F;</strong><strong v-else>&#x5173;&#x95ED;</strong>
              <span>&#x7F6E;&#x4FE1;&#x5EA6;&#x95E8;&#x9650;</span><strong>{{ selectedTaskSpec.ai_gate_confidence_threshold.toFixed(2) }}</strong>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="产品线">
          <div class="task-spec-preview-grid" style="border:1px solid #e5e7eb;border-radius:6px;padding:8px 12px;background:#f9fafb">
            <span>产品线</span><strong>{{ taskForm.product_id || '选择标准后自动填入' }}</strong>
          </div>
        </el-form-item>
        <el-form-item label="检测图片" prop="image_urls_input">
          <div class="flex items-center gap-2 mb-2">
            <el-button size="small" @click="triggerAttachmentSelect">上传图片</el-button>
            <span class="text-xs text-zinc-400">也可以直接粘贴图片或 URL，每行一个。</span>
          </div>
          <el-input v-model="taskForm.image_urls_input" type="textarea" :rows="4" resize="none" placeholder="https://example.com/a.jpg" @paste="handleTaskDialogPaste" />
          <div v-if="chatStore.pendingAttachments.length" class="flex flex-wrap gap-2 mt-3">
            <el-tag v-for="att in chatStore.pendingAttachments" :key="att.id" closable effect="plain" @close="removePendingAttachment(att.id)">{{ att.name }}</el-tag>
          </div>
        </el-form-item>
        <el-form-item label="优先级">
          <el-slider v-model="taskForm.priority" :min="1" :max="10" show-input />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetTaskDialog">取消</el-button>
        <el-button type="primary" :loading="taskSubmitting" @click="submitTaskDialog">{{ taskSourceMessage ? "前往任务页确认提交" : "发送给 Agent 整理草稿" }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
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
.token-badge { font-size: 12px; color: #6b7280; white-space: nowrap; }
.rag-select { width: 180px; }

/* ── Alert ── */
.alert-bar { margin: 0 12px; border-radius: 10px; }

.inspection-context-strip {
  margin: 10px 16px 8px;
}

.chat-shell {
  display: grid;
  grid-template-rows: 1fr auto;
  flex: 1;
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
.rag-cite {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin: 0 2px;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: linear-gradient(135deg, #dbeafe, #ede9fe);
  color: #4338ca;
  border: 1px solid #c7d2fe;
  cursor: help;
  vertical-align: baseline;
  white-space: nowrap;
}
.bubble.user .rag-cite {
  background: linear-gradient(135deg, rgba(219,234,254,.25), rgba(237,233,254,.25));
  color: #c7d2fe;
  border-color: rgba(199,210,254,.3);
}

.bubble-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bubble-edit-input :deep(.el-textarea__inner) {
  min-height: 60px;
}
.bubble.user .bubble-edit-input :deep(.el-textarea__inner) {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.25);
}
.bubble.user .bubble-edit-input :deep(.el-textarea__inner):focus {
  border-color: rgba(255, 255, 255, 0.5);
}
.bubble-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

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

/* ── Paper review report card ── */
.paper-review-card {
  margin-top: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #dbeafe;
  background: #eff6ff;
}
.prc-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }
.prc-header-right { display: flex; gap: 6px; align-items: center; }
.prc-title { font-weight: 700; color: #1e40af; font-size: 14px; }
.prc-meta { display: flex; gap: 16px; font-size: 12px; color: #64748b; margin-bottom: 8px; }
.prc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; margin-bottom: 10px; }
.prc-item { display: flex; justify-content: space-between; font-size: 13px; color: #475569; }
.prc-item strong { color: #1e293b; }
.prc-high { color: #dc2626 !important; }
.prc-medium { color: #d97706 !important; }
.prc-low { color: #6b7280 !important; }
.prc-summary { font-size: 13px; color: #475569; line-height: 1.5; margin-bottom: 10px; }
.prc-downloads { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.prc-limitations { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.prc-limit-tag { font-size: 11px; color: #b45309; background: #fef3c7; padding: 2px 6px; border-radius: 4px; }
.prc-no-files { font-size: 12px; color: #94a3b8; }

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
.task-result-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f0fdfa;
  color: #115e59;
  font-size: 12px;
  font-weight: 600;
}
.task-card-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.task-actions { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.task-action-note {
  display: grid;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e3a8a;
  font-size: 12px;
  line-height: 1.55;
}
.task-action-note strong { color: #1e40af; }
.task-actions-btns { display: flex; gap: 8px; flex-wrap: wrap; }
.task-form-hint { margin-top: 8px; font-size: 12px; color: #6b7280; }
.task-spec-preview {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
}
.task-spec-preview-title { font-size: 13px; font-weight: 700; color: #1f2937; }
.task-spec-preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px 10px;
  margin-top: 8px;
  font-size: 12px;
}
.task-spec-preview-grid span { color: #64748b; }
.task-spec-preview-grid strong { color: #111827; font-weight: 700; }

/* ── Composer ── */
.composer {
  padding: 10px 16px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}
.edit-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #eff6ff;
  color: #1f2937;
  font-size: 12px;
}
.composer-attachments { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.stream-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 2px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
.prompt-template-entry {
  margin-bottom: 8px;
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
