<script setup lang="ts">
import MaterialIntakeButton from "@/components/business/MaterialIntakeButton.vue";
import { CircleClose, CollectionTag, Paperclip, Promotion, WarningFilled, Plus, Top, Search } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { feedbackApi } from "@/api/feedback.api";
import { taskApi } from "@/api/task.api";
import AgentErrorAlert from "@/components/chat/AgentErrorAlert.vue";
import AgentTraceTimeline from "@/components/chat/AgentTraceTimeline.vue";
import ChatInspectionContextPanel from "@/components/chat/ChatInspectionContextPanel.vue";
import EvidencePacketCard from "@/components/chat/EvidencePacketCard.vue";
import LabDetectionCard from "@/components/chat/LabDetectionCard.vue";
import PromptTemplateTray from "@/components/chat/PromptTemplateTray.vue";
import ChatAnswer from "@/components/chat/ChatAnswer.vue";
import QualityAssessmentCard from "@/components/chat/QualityAssessmentCard.vue";
import VisualInspectionCard from "@/components/chat/VisualInspectionCard.vue";
import ImageAttachmentCard from "@/components/common/ImageAttachmentCard.vue";
import DocumentAttachmentCard from '@/components/common/DocumentAttachmentCard.vue';
import ImagePreviewDialog from "@/components/common/ImagePreviewDialog.vue";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useBillingStore } from "@/stores/billing.store";
import { useChatStore } from "@/stores/chat.store";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import { useAuthStore } from "@/stores/auth.store";
import type { AgentErrorPayload, ChatAttachment, ChatMessage, ChatTaskDraft } from "@/types/chat.types";
import type { InspectionTask, TaskCreate, TaskCreationStandardChoice } from "@/types/task.types";
import { attachmentDisplayName, isImageAttachment } from "@/utils/attachments";
import { writeTextToClipboard } from "@/utils/clipboard";
import { formatServerDateTime } from "@/utils/date-time";
import { agentErrorPayload, messageCardType } from "./chat-rendering";
import { canConfirmTaskAction, hasTaskAction } from "./chat-task-actions";
import { offersTaskCreation, platformTaskLinks, platformSources } from './chat-platform-actions';
import { taskStatusLabel } from '@/utils/task-status';

const router = useRouter();
const auth = useAuthStore();
const isOrdinaryUser = computed(() => auth.primaryRole === "user");
const isExpert = computed(() => auth.primaryRole === 'expert');
const usesSharedChatLayout = computed(() => isOrdinaryUser.value || isExpert.value);
const canCreateTask = computed(() => auth.hasPermission('task'));
const billingStore = useBillingStore();
const chatStore = useChatStore();
const taskStore = useTaskStore();
const inspectionSpecStore = useInspectionSpecStore();
const canBrowseInspectionSpecs = computed(() => !isOrdinaryUser.value && auth.hasPermission("inspection_spec_read"));
const ordinaryTaskChoices = ref<TaskCreationStandardChoice[]>([]);
const loadingTaskChoices = ref(false);

const input = ref("");
const messageListRef = ref<HTMLElement | null>(null);
const chatWasNearBottom = ref(true);
const chatNewMessageCount = ref(0);
const loadingOlderMessages = ref(false);
const attachmentInputRef = ref<HTMLInputElement | null>(null);
const uiNow = ref(Date.now());
const webSearchEnabled = ref(false);
const inspectionContextEnabled = false;
const selectedInspectionTasks = ref<InspectionTask[]>([]);
const previewImage = ref({ url: "", name: "" });
const imagePreviewVisible = ref(false);

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
const composerPlaceholder = computed(() => isOrdinaryUser.value ? '询问平台标准、本人任务，或上传图片和资料…' : isExpert.value ? '询问检测标准、风险研判和检测任务，或上传资料…' : '输入消息，Enter 发送，Shift+Enter 换行');
const sharedQuestionExamples = computed(() => isExpert.value ? [
  {label:'核对标准依据',query:'质检判断的标准条款和证据应该怎样核对？'},
  {label:'查看待复核任务',query:'查看当前权限范围内需要人工复核的检测任务及主要问题。'},
  {label:'整理风险线索',query:'我可以提供检测资料，请帮我整理风险线索和建议进一步核验的内容。'},
] : [
  {label:'检测前要准备什么？',query:'检测前需要准备哪些图片和资料？'},
  {label:'查看最近的检测任务',query:'帮我查看最近的检测任务和当前状态'},
  {label:'读懂检测报告',query:'检测报告里哪些内容需要重点关注？'},
]);
const starterQuestions = [
  { title: "平台使用", description: "我能问什么、做什么", query: "这个平台可以问些什么、做些什么？如何创建检测任务并导出报告？" },
  { title: "质检与质监", description: "了解概念与检测准备", query: "质检和质量监督有什么区别？提交产品检测前需要准备哪些材料？" },
  { title: "我的任务", description: "查看最近任务和结果", query: "查看我最近的检测任务状态和结果。" },
  { title: "日常问答", description: "学习、写作与一般问题", query: "帮我把一段文字整理得更清楚，我可以直接把内容发给你吗？" },
];

async function useStarterQuestion(query: string) {
  input.value = query;
  await nextTick();
  document.querySelector<HTMLTextAreaElement>(".composer-input textarea")?.focus();
}

function openPlatformTaskForm(message?: ChatMessage) {
  const index = message ? chatStore.messages.findIndex((item) => item.id === message.id) : chatStore.messages.length;
  const source = [...chatStore.messages.slice(0, index)].reverse().find((item) => item.role === 'user');
  const draft = message ? buildTaskDraft(message) : null;
  const attachments = message ? source?.payload?.attachment_echo || [] : chatStore.pendingAttachments;
  const imageUrls = draft?.image_urls?.length ? draft.image_urls : attachments.filter(isImageAttachment).map((item) => item.url);
  sessionStorage.setItem('piap_quality_task_draft', JSON.stringify({ ...draft, image_urls: imageUrls, metadata: { source: 'chat_draft', chat_source_message_id: source?.id } }));
  void router.push({ path: '/app/tasks', query: { create: '1', source: 'chat' } });
}

function handleAttachmentAction(command: string) {
  if (command === 'task' && canCreateTask.value) openPlatformTaskForm();
  else triggerAttachmentSelect();
}
let uiClockTimer: number | null = null;

function formatElapsed(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds} 秒`;
  return `${minutes} 分 ${seconds.toString().padStart(2, "0")} 秒`;
}

const streamStatusText = computed(() => {
  if (!chatStore.loading) return "";
  const now = uiNow.value;
  const elapsedText = chatStore.waitStartedAt ? formatElapsed(now - chatStore.waitStartedAt) : "0 秒";
  const idleSeconds = chatStore.lastStreamEventAt ? Math.floor((now - chatStore.lastStreamEventAt) / 1000) : 0;
  const phaseText =
    chatStore.streamPhase === "connecting"
      ? "正在建立实时连接"
      : chatStore.streamPhase === "polling"
        ? "连接波动，正在轮询后台结果"
        : chatStore.streamPhase === "reconnecting"
          ? "正在重连实时通道"
          : chatStore.streamPhase === "closing"
            ? "正在整理回复"
            : idleSeconds >= 10
              ? "后台仍在处理，连接保持中"
              : "智能体正在思考";
  const detail = chatStore.streamStatusMessage || "等待后台输出";
  return `${phaseText} · 已等待 ${elapsedText} · ${detail}`;
});
const FINAL_ASSISTANT_MESSAGE_TYPES = new Set([
  "assistant_text",
  "quality_answer",
  "evidence_answer",
  "visual_answer",
  "lab_answer",
  "file_answer",
  "report_answer",
  "task_status",
  "task_result",
  "image_analysis",
  "error",
  "interrupted",
]);
interface ChatSpecOption {
  id: string; name: string; spec_code?: string | null; is_active?: boolean;
  product_family?: string | null; product_id?: string | null;
  required_image_count?: number | null; required_views?: string[] | null;
  auto_pass_enabled?: boolean | null; ai_gate_confidence_threshold?: number | null;
}
const specOptions = computed<ChatSpecOption[]>(() => canBrowseInspectionSpecs.value ? inspectionSpecStore.items : ordinaryTaskChoices.value);
const filteredSpecOptions = computed(() =>
  specOptions.value.filter((item) => item.is_active),
);
const selectedTaskSpec = computed(() => specOptions.value.find((item) => item.spec_code === taskForm.value.spec_code) || null);
const totalTokenText = computed(() => (billingStore.myUsage?.total_tokens ?? 0).toLocaleString("zh-CN"));
const latestTokenCountedMessageId = computed(() => {
  const candidates = [...chatStore.messages].reverse();
  for (const message of candidates) {
    if (!isFinalAssistantMessage(message)) continue;
    return message.id;
  }
  return "";
});
const syncedUsageMessageId = ref("");
const messageReactions = ref<Record<string, "up" | "down">>({});
const editingMessageId = ref("");
const editingContent = ref("");

function formatTime(value?: string | null) {
  return formatServerDateTime(value, { includeSeconds: true });
}

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") return "你";
  if (role === "assistant") return "智能体";
  return "系统";
}

function isAttachmentOnlyMessage(message: ChatMessage) {
  return message.role === 'user' && Boolean(message.payload?.attachment_echo?.length) && message.content.trim() === '请先查看附件并说明你能识别到的信息。';
}

function isFinalAssistantMessage(message: ChatMessage) {
  return message.role === "assistant" && message.message_type !== "streaming" && FINAL_ASSISTANT_MESSAGE_TYPES.has(message.message_type);
}

function isVisibleAssistantAnswer(message: ChatMessage) {
  return isFinalAssistantMessage(message);
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
  if (!canBrowseInspectionSpecs.value && !canCreateTask.value) return;
  if (!force && specOptions.value.length > 0) return;
  if (!specsLoadPromise) {
    specsLoadPromise = (async () => {
      try {
        if (!canBrowseInspectionSpecs.value) {
          loadingTaskChoices.value = true;
          const { data } = await taskApi.creationOptions();
          ordinaryTaskChoices.value = data.data.standards;
        } else await inspectionSpecStore.fetchAll();
      } catch (error) {
        ElMessage.error("检测标准加载失败，请稍后重试。");
        console.error(error);
      } finally {
        loadingTaskChoices.value = false;
        specsLoadPromise = null;
      }
    })();
  }
  await specsLoadPromise;
}

async function openTaskDialog(message: ChatMessage) {
  if (!canBrowseInspectionSpecs.value) { openPlatformTaskForm(message); return; }
  await ensureInspectionSpecsLoaded(true);
  taskSourceMessage.value = message;
  fillTaskForm(message);
  taskDialogVisible.value = true;
}

async function openManualTaskDialog() {
  if (!canBrowseInspectionSpecs.value) { openPlatformTaskForm(); return; }
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
  if (isOrdinaryUser.value) chatStore.clearSelectedRagSpace();
  const message = input.value.trim() || "请先查看附件并说明你能识别到的信息。";
  try {
    chatStore.searchFocusSeq=null;
    if (chatStore.hasNewerMessages) await chatStore.reloadCurrentSessionMessages();
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

function openImagePreview(attachment: ChatAttachment) {
  previewImage.value = { url: attachment.url, name: attachmentDisplayName(attachment) };
  imagePreviewVisible.value = true;
}

// ── Typewriter effect ────────────────────────────────────────────
const typewriterPos = ref<Record<string, number>>({});
const typewriterTimers = new Map<string, ReturnType<typeof setInterval>>();

function getDisplayedContent(message: ChatMessage): string {
  if (message.role !== "assistant") return message.content;
  const pos = typewriterPos.value[message.id];
  if (pos === undefined) {
    if (message.message_type === "streaming") {
      if (message.content) return message.content;
      return streamingPlaceholder(message);
    }
    return message.content;
  }
  return message.content.slice(0, pos);
}

function streamingPlaceholder(message: ChatMessage) {
  const attachmentNames = (message.payload?.attachment_echo || []).map((item) => item.name.toLowerCase());
  if (attachmentNames.some((name) => name.endsWith(".docx") || name.endsWith(".tex"))) {
    return streamStatusText.value || "正在解析文档并检查格式...";
  }
  return streamStatusText.value || "智能体处理中...";
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
      .filter((m) => m.role === "assistant" && m.message_type === "streaming" && Boolean(m.content))
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
  if (sourceRag?.id && !isOrdinaryUser.value) {
    chatStore.selectRagSpace(sourceRag.id);
  } else {
    chatStore.clearSelectedRagSpace();
  }
  try {
    await chatStore.sendMessage({
      message: source.content,
      metadata: {
        edited_from_message_id: source.id,
        replace_assistant_message_id: message.id,
      },
      ext: {
        ui_mode: "auto",
      },
    });
  } catch (error) {
    ElMessage.error("重试失败，请稍后再试。");
    console.error(error);
  }
}

async function resendFromErrorMessage(message: ChatMessage) {
  await retryFromAssistantMessage(message);
}

function messageAgentError(message: ChatMessage) {
  return agentErrorPayload(message.payload);
}

function fallbackAgentError(message: ChatMessage): AgentErrorPayload {
  return {
    code: "AGENT_FAILED",
    title: "执行失败",
    message: message.content || "Agent 执行失败。",
    category: "internal",
    severity: "error",
    status: "failed",
    frontend_visible: true,
    retryable: false,
    detail: message.payload?.detail || null,
    workflow_run_id: message.payload?.workflow_run_id || null,
    trace_id: message.payload?.trace_id || null,
  };
}

function errorCardTitle(message: ChatMessage): string {
  const error = messageAgentError(message);
  if (error?.title) return error.title;
  const code = error?.code || "";
  if (code.startsWith("SHORT_TERM_")) return "短期记忆构建失败";
  if (code.startsWith("GRAPH_MEMORY_") || code.startsWith("NEO4J_")) return "图数据库服务异常";
  return "执行失败";
}

async function scrollToBottom() {
  if (chatStore.searchFocusSeq) return;
  await nextTick();
  const container = messageListRef.value;
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}

function isChatNearBottom(threshold = 72) {
  const container = messageListRef.value;
  if (!container) return true;
  return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
}

function onChatScroll() {
  chatWasNearBottom.value = isChatNearBottom();
  if (chatWasNearBottom.value) chatNewMessageCount.value = 0;
}

async function jumpToLatestChatMessage() {
  chatStore.searchFocusSeq=null;
  if (chatStore.hasNewerMessages) await chatStore.reloadCurrentSessionMessages();
  chatWasNearBottom.value = true;
  chatNewMessageCount.value = 0;
  await scrollToBottom();
}

async function loadOlderChatMessages() {
  const container = messageListRef.value;
  if (!container || loadingOlderMessages.value) return;
  loadingOlderMessages.value = true;
  const previousHeight = container.scrollHeight;
  const previousTop = container.scrollTop;
  try {
    const rows = await chatStore.loadOlderMessages();
    if (!rows.length) return;
    await nextTick();
    container.scrollTop = previousTop + container.scrollHeight - previousHeight;
    chatWasNearBottom.value = false;
  } finally {
    loadingOlderMessages.value = false;
  }
}

function taskState(taskId: string) { return taskStreamStates.value[taskId] || null; }

function disposeTaskStreams() {
  for (const dispose of taskStreamDisposers.values()) dispose();
  taskStreamDisposers.clear();
}

function ensureTaskStream(taskId: string) {
  if (!taskId || taskStreamDisposers.has(taskId)) return;
  taskStreamStates.value = { ...taskStreamStates.value, [taskId]: taskStreamStates.value[taskId] || { status: "running", message: "等待任务实时输出..." } };
  const dispose = taskStore.subscribeTaskStream(taskId, async (event) => {
    if (event.type === "ready" || event.type === "heartbeat") {
      taskStreamStates.value = {
        ...taskStreamStates.value,
        [taskId]: {
          status: taskStreamStates.value[taskId]?.status || "running",
          stage: taskStreamStates.value[taskId]?.stage,
          message: typeof event.message === "string" && event.message !== "stream_connected" ? event.message : "后台仍在处理，实时连接保持中...",
        },
      };
      return;
    }
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
  uiClockTimer = window.setInterval(() => {
    if (chatStore.loading) uiNow.value = Date.now();
  }, 1000);
  // AppLayout initializes the conversation once; remounting this view must not create another session.
  // General conversation has no dependency on task form options. Load them
  // only when a permitted task workflow opens its selection form.
  try { await billingStore.fetchMyUsage({ suppressErrorToast: true }); } catch { /* non-blocking */ }
  await scrollToBottom();
  syncTaskStreamsFromMessages();
  await loadMessageReactions();
});

onBeforeUnmount(() => {
  chatStore.stopStream();
  disposeTaskStreams();
  if (uiClockTimer != null) {
    window.clearInterval(uiClockTimer);
    uiClockTimer = null;
  }
});

watch(() => chatStore.messages.length, async (length, previousLength) => {
  syncTaskStreamsFromMessages();
  if (loadingOlderMessages.value || length <= previousLength) return;
  if (chatWasNearBottom.value) {
    await scrollToBottom();
  } else {
    chatNewMessageCount.value += length - previousLength;
  }
});
watch(() => chatStore.messages.map((item) => `${item.id}:${item.content.length}`).join("|"), async () => {
  syncTaskStreamsFromMessages();
  if (chatWasNearBottom.value && !loadingOlderMessages.value) await scrollToBottom();
});
watch(() => chatStore.session?.id, async () => {
  chatWasNearBottom.value = true;
  chatNewMessageCount.value = 0;
  await scrollToBottom();
});
watch(() => chatStore.messages.map((item) => item.id).join(","), loadMessageReactions);
watch(()=>chatStore.searchFocusSeq,async seq=> {
  if (!seq) return;
  chatWasNearBottom.value=false;
  await nextTick();
  messageListRef.value?.querySelector<HTMLElement>(`[data-message-seq="${seq}"]`)?.scrollIntoView({block:'center',behavior:'auto'});
});
watch(latestTokenCountedMessageId, async (messageId) => {
  if (!messageId || messageId === syncedUsageMessageId.value) return;
  syncedUsageMessageId.value = messageId;
  try { await billingStore.fetchMyUsage({ suppressErrorToast: true }); } catch { /* non-blocking */ }
});
</script>

<template>
  <div class="chat-page" :class="{ 'user-chat': usesSharedChatLayout, 'chat-is-empty': !chatStore.messages.length }">
    <div class="quality-material-action"><MaterialIntakeButton /></div>
    <!-- Toolbar -->
    <details v-if="!isOrdinaryUser" class="expert-chat-options">
    <summary>知识来源与常用提问<span v-if="chatStore.selectedRagSpace"> · {{ chatStore.selectedRagSpace.name }}</span></summary>
    <div class="toolbar">
      <div class="toolbar-left">
        <span v-if="!isOrdinaryUser" class="token-badge">Token: {{ totalTokenText }}</span>
        <el-select
          v-model="chatStore.selectedRagSpaceId"
          placeholder="自动选择知识来源"
          clearable
          size="small"
          class="rag-select"
          @change="(val: string) => val ? chatStore.selectRagSpace(val) : chatStore.clearSelectedRagSpace()"
        >
          <el-option label="自动选择知识来源" value="" />
          <el-option
            v-for="space in chatStore.ragSpaces"
            :key="space.id"
            :label="space.name"
            :value="space.id"
          />
        </el-select>
        <el-tooltip v-if="!usesSharedChatLayout" :content="webSearchEnabled ? '联网搜索已开启：Agent 必须使用网络检索' : '联网搜索已关闭：Agent 自行判断'" placement="bottom">
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
    <PromptTemplateTray v-model="input" button-label="常用提问" class="expert-prompt-options" />
    </details>

    <el-alert
      v-if="chatStore.ragSpacesError && !isOrdinaryUser"
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
      <div class="message-pane">
        <div ref="messageListRef" class="message-list" @scroll.passive="onChatScroll">
        <button
          v-if="chatStore.hasOlderMessages"
          type="button"
          class="chat-load-older"
          :disabled="loadingOlderMessages"
          @click="loadOlderChatMessages"
        >加载更早消息</button>
        <div v-if="chatStore.messages.length === 0" class="empty-state">
          <div class="empty-title">{{ usesSharedChatLayout ? '有什么可以帮你？' : '想了解什么，或检查什么？' }}</div>
          <div class="empty-desc">{{ isExpert ? '结合可访问的任务、标准与证据，开展质检分析和质量监督研判' : isOrdinaryUser ? '结合平台标准和本人任务提问，也可以上传图片、文件进行分析' : '可以咨询质检、质监和平台操作，也可以讨论日常问题。' }}</div>
          <div v-if="usesSharedChatLayout" class="platform-question-examples" aria-label="试试这样问">
            <button v-for="question in sharedQuestionExamples" :key="question.label" type="button" @click="useStarterQuestion(question.query)">{{ question.label }}</button>
          </div>
          <div v-if="!usesSharedChatLayout" class="starter-questions">
            <button v-for="question in starterQuestions" :key="question.title" type="button" class="starter-question" @click="useStarterQuestion(question.query)">
              <strong>{{ question.title }}</strong><span>{{ question.description }}</span>
            </button>
          </div>
          <el-button v-if="!usesSharedChatLayout && canCreateTask" link type="primary" class="starter-task-link" @click="router.push('/app/tasks')">创建检测任务或查看报告 →</el-button>
        </div>

        <div v-else class="message-group">
          <article
            v-for="message in chatStore.messages"
            :key="message.id"
            :id="`chat-message-${message.id}`"
            class="message-row"
            :data-message-seq="message.seq_no"
            :class="[message.role, { 'search-message-match': chatStore.searchFocusSeq===message.seq_no }]"
          >
            <div v-if="!usesSharedChatLayout" class="message-meta">
              <span class="role-name">{{ roleLabel(message.role) }}</span>
              <span class="time">{{ formatTime(message.created_at) }}</span>
            </div>
            <div v-if="usesSharedChatLayout && message.role === 'assistant'" class="assistant-identity"><img src="/piap-icon.svg?v=3" alt="" /><span>PIAP 助手</span></div>

            <div v-if="usesSharedChatLayout && message.role === 'user' && message.payload?.attachment_echo?.length" class="user-message-attachments">
              <template v-for="att in message.payload.attachment_echo" :key="att.id">
                <ImageAttachmentCard v-if="isImageAttachment(att)" :src="att.url" :name="attachmentDisplayName(att)" compact :show-name="false" @preview="openImagePreview(att)" />
                <DocumentAttachmentCard v-else :name="attachmentDisplayName(att)" :url="att.url" :size-bytes="att.size_bytes" />
              </template>
            </div>

            <div v-if="!(usesSharedChatLayout && isAttachmentOnlyMessage(message))" class="bubble" :class="message.role">
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
              <ChatAnswer v-else-if="usesSharedChatLayout && message.role === 'assistant'" :content="getDisplayedContent(message)" />
              <div v-else class="bubble-text">
                <template v-for="(seg, si) in renderRagCitations(getDisplayedContent(message))" :key="si">
                  <span v-if="seg.type === 'text'">{{ seg.value }}</span>
                  <span v-else class="rag-cite" :title="`RAG 引用 #${seg.value}`">RAG-{{ seg.value }}</span>
                </template>
                <span v-if="message.message_type === 'streaming' && chatStore.loading" class="cursor-blink">&nbsp;</span>
              </div>

              <details v-if="usesSharedChatLayout && platformSources(message).length" class="platform-answer-sources">
                <summary>参考资料 · {{ platformSources(message).length }} 份</summary>
                <div v-for="(source, index) in platformSources(message)" :key="index"><strong>{{ source.label }}</strong><p v-if="source.quote">{{ source.quote }}</p></div>
              </details>
              <section v-if="usesSharedChatLayout && platformTaskLinks(message).length" class="platform-task-results" aria-label="平台任务操作">
                <div v-for="task in platformTaskLinks(message)" :key="task.id" class="platform-task-row">
                  <div><strong>{{ task.product }}</strong><span>{{ taskStatusLabel(task.status) }}</span></div>
                  <div class="platform-task-buttons">
                    <el-button v-if="auth.hasPermission('task')" link type="primary" @click="router.push(`/app/tasks/${encodeURIComponent(task.id)}`)">查看任务</el-button>
                    <el-button v-if="task.hasResult && auth.hasPermission('result')" link type="primary" @click="router.push(`/app/results/${encodeURIComponent(task.id)}`)">查看结果</el-button>
                    <el-button v-if="task.hasResult && auth.hasPermission('feedback') && auth.hasPermission('task') && auth.hasPermission('result')" link type="primary" @click="router.push({ path: '/app/export', query: { task_id: task.id } })">导出报告</el-button>
                  </div>
                </div>
              </section>
              <div v-if="usesSharedChatLayout && canCreateTask && offersTaskCreation(message)" class="platform-task-handoff">
                <div><strong>准备好后，提交正式检测任务</strong><p>携带当前图片和资料，到任务页核对产品与标准。</p></div>
                <el-button link type="primary" @click="openPlatformTaskForm(message)">核对并创建任务 →</el-button>
              </div>

              <!-- Attachments -->
              <div v-if="message.payload?.attachment_echo?.length && !(usesSharedChatLayout && message.role === 'user')" class="bubble-attachments">
                <template v-for="att in message.payload.attachment_echo" :key="att.id">
                  <ImageAttachmentCard
                    v-if="isImageAttachment(att)"
                    :src="att.url"
                    :name="attachmentDisplayName(att)"
                    :show-name="!usesSharedChatLayout"
                    @preview="openImagePreview(att)"
                  />
                  <DocumentAttachmentCard v-else :name="attachmentDisplayName(att)" :url="att.url" :size-bytes="att.size_bytes" />
                </template>
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

              <!-- Error card -->
              <div v-if="message.message_type === 'error'" class="error-card">
                <div class="error-card-header">
                  <el-icon color="#dc2626"><WarningFilled /></el-icon>
                  <span class="error-card-title">{{ errorCardTitle(message) }}</span>
                </div>
                <div class="error-card-body">
                  <AgentErrorAlert :error="messageAgentError(message) || fallbackAgentError(message)" />
                </div>
                <div class="error-card-actions">
                  <el-button size="small" type="primary" @click="resendFromErrorMessage(message)" :disabled="chatStore.loading">重新发送</el-button>
                </div>
              </div>

              <!-- Evidence packet card -->
              <div v-if="!isOrdinaryUser && message.payload?.evidence_packet" class="agent-card-wrapper">
                <EvidencePacketCard
                  :rag-hit-count="(message.payload.evidence_packet.sources as any)?.rag?.hit_count"
                  :memory-count="(message.payload.evidence_packet.sources as any)?.memory?.items?.length"
                  :kg-path-count="(message.payload.evidence_packet.sources as any)?.quality_kg?.paths?.length"
                  :source-count="message.payload.evidence_packet.source_count"
                />
              </div>

              <!-- Visual inspection card -->
              <div v-if="message.payload?.visual_inspection_result" class="agent-card-wrapper">
                <VisualInspectionCard
                  :summary="message.payload.visual_inspection_result.summary"
                  :image-count="message.payload.visual_inspection_result.image_count"
                  :objects="message.payload.visual_inspection_result.objects"
                  :possible-defects="message.payload.visual_inspection_result.possible_defects"
                  :risk="message.payload.visual_inspection_result.risk"
                  :defects="message.payload.visual_inspection_result.defects"
                  :image-quality="message.payload.visual_inspection_result.image_quality"
                  :requires-recheck="message.payload.visual_inspection_result.requires_recheck"
                  :confidence="message.payload.visual_inspection_result.confidence"
                />
              </div>

              <!-- Lab detection card -->
              <div v-if="message.payload?.lab_detection_result" class="agent-card-wrapper">
                <LabDetectionCard
                  :sample-id="message.payload.lab_detection_result.sample_id"
                  :assessment-state="message.payload.lab_detection_result.assessment_state"
                  :abnormal-probability="message.payload.lab_detection_result.abnormal_probability"
                  :risk-level="message.payload.lab_detection_result.risk_level"
                  :data-completeness="message.payload.lab_detection_result.data_completeness"
                  :early-warning="message.payload.lab_detection_result.early_warning"
                  :can-make-final-verdict="message.payload.lab_detection_result.can_make_final_verdict"
                  :abnormal-indicators="message.payload.lab_detection_result.abnormal_indicators"
                  :next-test-priority="message.payload.lab_detection_result.next_test_priority"
                  :suggested-action="message.payload.lab_detection_result.suggested_action"
                  :confidence="message.payload.lab_detection_result.confidence"
                />
              </div>

              <!-- Quality assessment card -->
              <div v-if="!isOrdinaryUser && message.payload?.quality_final_assessment" class="agent-card-wrapper">
                <QualityAssessmentCard
                  :final-verdict="message.payload.quality_final_assessment.final_verdict"
                  :overall-score="message.payload.quality_final_assessment.overall_score"
                  :risk-level="message.payload.quality_final_assessment.risk_level"
                  :evidence-used="message.payload.quality_final_assessment.evidence_used"
                  :conflicts="message.payload.quality_final_assessment.conflicts"
                  :limitations="message.payload.quality_final_assessment.limitations"
                  :recommended-action="message.payload.quality_final_assessment.recommended_action"
                  :answer="message.payload.quality_final_assessment.answer"
                  :confidence="message.payload.quality_final_assessment.confidence"
                />
              </div>

              <!-- Agent trace timeline -->
              <div v-if="!isOrdinaryUser && (message.payload?.route_trace || message.payload?.capabilities_used?.length)" class="agent-card-wrapper">
                <AgentTraceTimeline
                  :trace="message.payload.route_trace"
                  :capabilities-used="message.payload.capabilities_used"
                />
              </div>

              <!-- Task actions -->
              <div v-if="message.role === 'assistant' && canCreateTask && hasTaskAction(message)" class="task-actions">
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
              :show-feedback="auth.hasPermission('feedback') && isVisibleAssistantAnswer(message)"
              :show-retry="isVisibleAssistantAnswer(message)"
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
        <button
          v-if="chatNewMessageCount || chatStore.hasNewerMessages || chatStore.searchFocusSeq"
          type="button"
          class="chat-new-message-jump"
          :aria-label="chatNewMessageCount ? `有 ${chatNewMessageCount} 条新消息，回到最新消息` : '返回最新对话'"
          @click="jumpToLatestChatMessage"
        >{{ chatNewMessageCount ? `有 ${chatNewMessageCount} 条新消息` : '返回最新对话' }}</button>
      </div>

      <!-- Composer -->
      <div class="composer">

        <div v-if="chatStore.pendingAttachments.length" class="composer-attachments">
          <div v-for="att in chatStore.pendingAttachments" :key="att.id" class="pending-attachment">
            <ImageAttachmentCard v-if="isImageAttachment(att)" :src="att.url" :name="attachmentDisplayName(att)" compact :show-name="false" @preview="openImagePreview(att)" />
            <DocumentAttachmentCard v-else :name="attachmentDisplayName(att)" :url="att.url" :size-bytes="att.size_bytes" compact />
            <button :aria-label="`移除附件 ${attachmentDisplayName(att)}`" class="attachment-remove" @click="removePendingAttachment(att.id)">×</button>
          </div>
        </div>
        <div v-if="streamStatusText" class="stream-status">
          <span class="stream-status-dot" />
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
        <div class="composer-row" @paste="handleComposerPaste">
          <el-input v-model="input" type="textarea" :rows="2" resize="none" :placeholder="composerPlaceholder" @keydown="onInputKeydown" class="composer-input" />
          <div class="composer-actions">
            <el-dropdown v-if="usesSharedChatLayout" trigger="click" @command="handleAttachmentAction">
              <button class="user-attachment-button" aria-label="添加资料或创建任务"><Plus /></button>
              <template #dropdown><el-dropdown-menu><el-dropdown-item command="upload">上传图片或文件</el-dropdown-item><el-dropdown-item v-if="canCreateTask" command="task">创建检测任务</el-dropdown-item></el-dropdown-menu></template>
            </el-dropdown>
            <el-button v-else size="small" :icon="Paperclip" aria-label="上传图片或文件" @click="triggerAttachmentSelect" />
            <el-button v-if="usesSharedChatLayout" text :icon="Search" :aria-pressed="webSearchEnabled" :class="{ 'search-enabled': webSearchEnabled }" @click="webSearchEnabled = !webSearchEnabled">联网搜索</el-button>
            <el-button v-if="!usesSharedChatLayout" size="small" :icon="CollectionTag" aria-label="清除已选知识库" @click="chatStore.selectedRagSpaceId ? chatStore.clearSelectedRagSpace() : undefined" :type="chatStore.selectedRagSpaceId ? 'warning' : 'default'" />
            <el-button v-if="usesSharedChatLayout" class="user-send-button" circle type="primary" :icon="Top" aria-label="发送" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage" />
            <el-button v-else type="primary" :icon="Promotion" :loading="chatStore.loading" :disabled="!canSend" @click="sendMessage">发送</el-button>
          </div>
        </div>
        <input ref="attachmentInputRef" type="file" multiple hidden @change="handleAttachmentSelected" />
      </div>
      <div v-if="usesSharedChatLayout" class="user-composer-hint">Enter 发送 · Shift + Enter 换行</div>
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
            <el-button link type="primary" :loading="canBrowseInspectionSpecs ? inspectionSpecStore.loading : loadingTaskChoices" @click="ensureInspectionSpecsLoaded(true)">刷新检测标准</el-button>
          </div>
          <div class="task-form-hint">
            &#x5F53;&#x524D;&#x53EF;&#x9009; {{ filteredSpecOptions.length }} &#x4E2A;&#x68C0;&#x6D4B;&#x6807;&#x51C6;&#x3002;
          </div>
          <div v-if="selectedTaskSpec" class="task-spec-preview">
            <div class="task-spec-preview-title">
              {{ selectedTaskSpec.spec_code }} · {{ selectedTaskSpec.name }}
            </div>
            <div v-if="canBrowseInspectionSpecs" class="task-spec-preview-grid">
              <span>&#x4EA7;&#x54C1;&#x7EBF;</span><strong v-if="selectedTaskSpec.product_id">{{ selectedTaskSpec.product_id }}</strong><strong v-else>&#x5168;&#x5C40;</strong>
              <span>&#x9700;&#x8981;&#x56FE;&#x7247;</span><strong>{{ selectedTaskSpec.required_image_count }}</strong>
              <span>&#x81EA;&#x52A8;&#x653E;&#x884C;</span><strong v-if="selectedTaskSpec.auto_pass_enabled">&#x5F00;&#x542F;</strong><strong v-else>&#x5173;&#x95ED;</strong>
              <span>&#x7F6E;&#x4FE1;&#x5EA6;&#x95E8;&#x9650;</span><strong>{{ selectedTaskSpec.ai_gate_confidence_threshold?.toFixed(2) }}</strong>
            </div>
            <p v-else class="task-form-hint">至少提供 {{ selectedTaskSpec.required_image_count || 1 }} 张清晰图片{{ selectedTaskSpec.required_views?.length ? `，包括${selectedTaskSpec.required_views.join('、')}视角` : '' }}。具体要求以已发布标准为准。</p>
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
    <ImagePreviewDialog v-model="imagePreviewVisible" :src="previewImage.url" :title="previewImage.name" />
  </div>
</template>

<style scoped>
.expert-chat-options { flex:none; padding:10px 24px; border-bottom:1px solid #edf1f6; background:#fff; font-size:12px; color:#7a90aa; }
.expert-chat-options>summary { cursor:pointer; }
.expert-chat-options>summary span { color:#4a78af; }
.expert-chat-options .toolbar { padding:12px 0 9px; border:0; }
.expert-prompt-options { padding-bottom:4px; }
.assistant-identity { display:flex; align-items:center; gap:8px; color:#8398b4; font-size:11px; margin-bottom:12px; }
.assistant-identity img { width:23px; height:23px; border-radius:7px; }
.user-chat .message-row.assistant { padding-bottom:5px; }
.user-chat .search-message-match { outline:1px solid #c6dbf5; outline-offset:8px; border-radius:8px; background:#f8fbff; content-visibility:visible; }
.user-message-attachments { display:flex; flex-wrap:wrap; align-items:flex-end; gap:9px; justify-content:flex-end; margin:0 0 9px; max-width:100%; }
.user-message-attachments :deep(.image-attachment-card.compact) { width:112px; height:112px; }
.user-chat .composer-attachments { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:13px; }
.pending-attachment { position:relative; max-width:100%; }
.attachment-remove { position:absolute; top:-6px; right:-6px; width:20px; height:20px; background:#f9fbfe; border:1px solid #dce5ef; border-radius:50%; color:#7b8fa8; cursor:pointer; z-index:1; line-height:16px; font-size:15px; }
.user-chat .message-row { contain-intrinsic-size: auto 90px; }
.user-chat .message-row.assistant { padding-top:2px; }
.user-chat :deep(.message-actions) { min-height:32px; margin-top:2px; }
.user-chat .empty-state { position:relative; }
.user-chat .empty-state::before { content:''; width:46px; height:3px; border-radius:2px; background:linear-gradient(90deg,#2687e8,#50c7cf); margin-bottom:22px; }
.user-chat .chat-shell { grid-template-rows: 1fr auto auto; }
.user-chat .message-list { padding: 28px 32px 35px; }
.user-chat .message-group { width: min(100%, 790px); margin: 0 auto; gap: 32px; }
.user-chat .message-row.assistant { width: 100%; }
.user-chat .bubble { font-size: 16px; line-height: 1.85; }
.user-chat .bubble.user { background: #f0f4f8; color: #2c3d51; border-radius: 20px; max-width: 86%; padding: 14px 20px; }
.user-chat .bubble.assistant { width: 100%; max-width: 100%; background: transparent; border: 0; padding: 0 4px; }
.user-chat .message-row.user :deep(.message-actions) { opacity: 0; }
.user-chat .message-row.user:hover :deep(.message-actions), .user-chat .message-row.user:focus-within :deep(.message-actions) { opacity: 1; }
.user-chat :deep(.message-actions .el-button) { min-width: 28px; width: 28px; height: 30px; padding: 4px; color: #8c98a6; }
.user-chat .composer { width: min(calc(100% - 64px), 790px); margin: 10px auto 0; padding: 15px 18px 12px; border: 1px solid #dfe5ed; border-radius: 23px; box-shadow: 0 4px 18px #25395608; }
.user-chat .composer-row { display: flex; flex-direction: column; align-items: stretch; gap: 9px; }
.user-chat .composer-input :deep(.el-textarea__inner) { padding: 0 4px; box-shadow: none !important; border: 0; font-size: 15px; line-height: 1.8; min-height: 44px !important; background: transparent; color: #334256; }
.user-chat .composer-actions { display: flex; align-items: center; width: 100%; gap: 8px; }
.user-chat .user-send-button { margin-left: auto; width: 34px; height: 34px; }
.user-chat .composer-actions .el-button.is-text { font-size: 12px; color: #7d8da1; padding: 6px; }
.user-chat .composer-actions .search-enabled { color: #2671d9 !important; background: #eff5ff; }
.user-attachment-button { display: grid; place-items: center; width: 31px; height: 31px; background: transparent; border: 0; color: #7d8da1; cursor: pointer; border-radius: 7px; }
.user-attachment-button:hover { background: #f0f5fb; }
.user-attachment-button svg { width: 19px; height: 19px; }
.user-attachment-button:focus-visible { outline: 2px solid #2671d9; }
.user-composer-hint { text-align: center; color: #a1abba; font-size: 10px; padding: 11px 0 18px; background: #fff; }
.user-chat.chat-is-empty .chat-shell { display: flex; flex-direction: column; justify-content: center; padding-bottom: 90px; }
.user-chat.chat-is-empty .message-pane { flex: none; overflow: visible; }
.user-chat.chat-is-empty .message-list { height: auto; overflow: visible; padding: 0 24px; }
.user-chat .empty-state { padding: 0; margin: 0 auto 20px; }
.user-chat .empty-state .empty-title { color: #26384f; font-size: 30px; font-weight: 500; margin-bottom: 13px; }
.user-chat .empty-desc { color: #8a97a8; font-size: 13px; }
.platform-question-examples { display:flex; flex-wrap:wrap; justify-content:center; gap:8px; margin-top:20px; }
.platform-question-examples button { background:#f8fafd; border:1px solid #e8eef5; border-radius:18px; padding:7px 12px; color:#7388a2; font:inherit; font-size:11px; cursor:pointer; }
.platform-question-examples button:hover { background:#edf4fe; color:#356fae; border-color:#d6e5f7; }
.platform-question-examples button:focus-visible { outline:2px solid #87b3ec; outline-offset:2px; }
.user-chat.chat-is-empty .composer { margin-top: 8px; }
.platform-task-results { margin-top: 21px; border: 1px solid #e3ebf5; border-radius: 12px; padding: 2px 15px; }
.platform-answer-sources { margin-top: 16px; color: #6f85a0; font-size: 12px; }
.platform-answer-sources summary { cursor: pointer; }
.platform-answer-sources > div { margin-top: 10px; padding: 10px 13px; border-left: 2px solid #dce7f5; background: #f8fafd; }
.platform-answer-sources strong { font-weight: 500; }
.platform-answer-sources p { font-size: 12px; color: #8b99ab; line-height: 1.7; margin: 5px 0 0; }
.platform-task-row { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding: 12px 0; border-bottom: 1px solid #edf2f8; }
.platform-task-row:last-child { border-bottom: 0; }
.platform-task-row strong { display: block; font-size: 13px; font-weight: 500; }
.platform-task-row span { font-size: 11px; color: #91a0b3; }
.platform-task-buttons { display: flex; gap: 5px; white-space: nowrap; }
.platform-task-buttons .el-button { margin: 0; font-size: 11px; }
.user-chat .platform-task-buttons :deep(.el-button.is-link), .user-chat .platform-task-handoff :deep(.el-button.is-link) { box-shadow: none !important; background: transparent !important; }
.platform-task-handoff { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 20px; padding: 16px; border: 1px solid #e2ebf7; border-radius: 12px; background: #f7faff; }
.platform-task-handoff strong { font-size: 13px; font-weight: 500; }
.platform-task-handoff p { font-size: 12px; color: #8b9bb0; margin: 5px 0 0; }
@media(max-width:700px) { .user-chat .message-list { padding: 22px 16px; } .user-chat .composer { width: calc(100% - 30px); padding: 13px; } .user-chat .empty-state .empty-title { font-size: 25px; } .user-chat.chat-is-empty .chat-shell { padding-bottom: 55px; } .user-chat .bubble { font-size: 14px; } .platform-task-row, .platform-task-handoff { flex-direction: column; align-items: flex-start; } .user-message-attachments :deep(.image-attachment-card.compact) { width:76px; height:76px; } }
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0;
}

.agent-card-wrapper {
  margin-top: 8px;
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
.message-pane {
  position: relative;
  min-height: 0;
  overflow: hidden;
}
.message-list {
  height: 100%;
  overflow-y: auto;
  padding: 12px 20px;
  overflow-anchor: none;
}
.chat-load-older,
.chat-new-message-jump {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  margin: 0 auto 14px;
  padding: 0 16px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.chat-load-older:hover,
.chat-new-message-jump:hover { border-color: #166534; color: #166534; }
.chat-load-older:focus-visible,
.chat-new-message-jump:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
.chat-load-older:disabled { cursor: wait; opacity: 0.55; }
.chat-new-message-jump {
  position: absolute;
  z-index: 8;
  left: 50%;
  bottom: 12px;
  margin: 0;
  transform: translateX(-50%);
  border-color: #86efac;
  background: #f0fdf4;
  color: #166534;
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
.empty-state .empty-title { color: #18181b; font-size: 24px; }
.empty-state .empty-desc { max-width: 570px; text-align: center; line-height: 1.8; }
.starter-questions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: min(100%, 570px); margin-top: 26px; }
.starter-question { display: flex; flex-direction: column; gap: 6px; padding: 16px 18px; text-align: left; border: 1px solid #e4e4e7; border-radius: 10px; background: white; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.starter-question strong { color: #27272a; font-size: 14px; font-weight: 600; }
.starter-question span { color: #71717a; font-size: 12px; }
.starter-question:hover { background: #f8fafc; border-color: #93c5fd; }
.starter-question:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
.starter-task-link { margin-top: 18px; }
@media (max-width: 480px) { .starter-questions { grid-template-columns: 1fr; } .empty-state { padding: 36px 12px; } }

.message-group { display: flex; flex-direction: column; gap: 12px; }

.message-row { content-visibility: auto; contain-intrinsic-size: auto 180px; }
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

.bubble-attachments { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; margin-top: 8px; }
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

/* ── Error card ── */
.error-card {
  margin-top: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #fecaca;
  background: #fef2f2;
}
.error-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.error-card-title {
  font-weight: 700;
  font-size: 15px;
  color: #991b1b;
}
.error-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}
.error-hint {
  font-size: 13px;
  line-height: 1.5;
  color: #991b1b;
}
.error-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.error-label {
  font-size: 11px;
  font-weight: 600;
  color: #b91c1c;
  text-transform: uppercase;
}
.error-message-text {
  font-size: 13px;
  color: #7f1d1d;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.error-detail-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border-radius: 6px;
  background: #fee2e2;
}
.error-detail-row {
  font-size: 12px;
  color: #991b1b;
  line-height: 1.5;
}
.error-detail-key {
  font-weight: 600;
  color: #7f1d1d;
}
.error-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

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
.stream-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4);
  animation: stream-status-pulse 1.4s ease-out infinite;
}
@keyframes stream-status-pulse {
  70% {
    box-shadow: 0 0 0 8px rgba(37, 99, 235, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0);
  }
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
