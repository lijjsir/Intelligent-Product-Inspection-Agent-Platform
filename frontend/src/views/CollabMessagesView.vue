<script setup lang="ts">
import { Bell, Check, Close, Delete, Paperclip, Plus, Promotion, Select } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { meetingApi } from "@/api/meeting.api";
import ImageAttachmentCard from "@/components/common/ImageAttachmentCard.vue";
import ImagePreviewDialog from "@/components/common/ImagePreviewDialog.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useCollabStore } from "@/stores/collab.store";
import type {
  CollabMessage,
  CollabMessageType,
  CollabParticipantType,
  CollabTarget,
  CollabThreadCreatePayload,
} from "@/types/collab.types";
import type { MeetingMemory, MeetingRoom } from "@/types/meeting.types";
import { isImageAttachment } from "@/utils/attachments";
import { formatServerDateTime } from "@/utils/date-time";

const auth = useAuthStore();
const store = useCollabStore();
const route = useRoute();

const composer = ref("");
const selectedMessageType = ref<CollabMessageType>("text");
const fileInputRef = ref<HTMLInputElement | null>(null);
const previewImage = ref({ url: "", name: "" });
const imagePreviewVisible = ref(false);
const createDialogVisible = ref(false);
const creatingThread = ref(false);
const lastAutoCreateTitle = ref("");
const sourceMode = ref<"manual" | "meeting_memory">("manual");
const sourceManualLabel = ref("");
const sourceRoomId = ref("");
const sourceMemoryId = ref("");
const sourceRooms = ref<MeetingRoom[]>([]);
const sourceMemories = ref<MeetingMemory[]>([]);
const loadingSourceRooms = ref(false);
const loadingSourceMemories = ref(false);

const createForm = reactive<CollabThreadCreatePayload>({
  target_type: "user",
  target_id: "",
  title: "",
});
const createSourceContext = reactive<Record<string, unknown>>({
  source_type: "manual",
  label: "手动说明",
});
const activeSourceContext = reactive<Record<string, unknown>>({
  source_type: "manual",
  label: "手动说明",
});
const draftMemoryCard = reactive<Record<string, unknown>>({});

const messageTypeOptions: Array<{ label: string; value: CollabMessageType; hint: string }> = [
  { label: "普通说明", value: "text", hint: "不携带处理动作的说明" },
  { label: "图片/文件", value: "file", hint: "携带附件和说明" },
  { label: "记忆卡片", value: "memory_card", hint: "请求对方确认沉淀" },
  { label: "处理请求", value: "action_request", hint: "需要接受、拒绝或完成" },
];

const targetTypeOptions: Array<{ label: string; value: CollabParticipantType; hint: string }> = [
  { label: "成员", value: "user", hint: "发给具体用户" },
  { label: "会议室", value: "meeting_room", hint: "发给会议室及其成员" },
];

const activeTitle = computed(() => (store.activeThread ? targetDisplayName(store.activeThread) : "选择一个协作通道"));
const activeTarget = computed(() => {
  const thread = store.activeThread;
  if (!thread) return "";
  return `${participantTypeLabel(thread.target_type)} · ${targetDisplayName(thread)}`;
});
const activeThreadSource = computed(() => store.activeThread ? threadSourceLabel(store.activeThread) : "");
const activeThreadFlow = computed(() => {
  const thread = store.activeThread;
  if (!thread) return "选择目标后，会创建或复用一条协作通道。";
  return `来源：${threadSourceLabel(thread)} · 目标：${participantTypeLabel(thread.target_type)} ${targetDisplayName(thread)}`;
});
const activeSourceLabel = computed(() => sourceLabelFromContext(activeSourceContext));
const createSourceLabel = computed(() => sourceLabelFromContext(createSourceContext));
const hasActiveSource = computed(() => activeSourceLabel.value !== "手动说明");
const hasDraftMemoryCard = computed(() => Boolean(
  cleanText(draftMemoryCard.memory_id || draftMemoryCard.id)
    || cleanText(draftMemoryCard.title || draftMemoryCard.memory_title)
    || cleanText(draftMemoryCard.summary || draftMemoryCard.content),
));
const targetOptions = computed(() => store.targets.filter((target) => target.target_type === createForm.target_type));
const selectedTarget = computed(() => targetOptions.value.find((target) => target.target_id === createForm.target_id) || null);
const selectedSourceRoom = computed(() => sourceRooms.value.find((room) => room.id === sourceRoomId.value) || null);
const selectedSourceMemory = computed(() => sourceMemories.value.find((memory) => memory.memory_id === sourceMemoryId.value) || null);
const sourceMemoryOptions = computed(() => sourceMemories.value.filter((memory) => memory.status !== "rejected"));

function formatTime(value?: string | null) {
  return formatServerDateTime(value, { compactDate: true, includeSeconds: false }) || "刚刚";
}

function formatBytes(value?: number | null) {
  const bytes = Number(value || 0);
  if (bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function collabAttachmentName(file: { file_name?: string | null; name?: string | null }) {
  return String(file.file_name || file.name || "附件");
}

function openCollabImagePreview(file: { url?: string | null; file_name?: string | null; name?: string | null }) {
  previewImage.value = { url: String(file.url || ""), name: collabAttachmentName(file) };
  imagePreviewVisible.value = true;
}

function participantTypeLabel(type?: string | null) {
  if (type === "user") return "成员";
  if (type === "meeting_room") return "会议室";
  if (type === "agent") return "Agent";
  return type || "未知";
}

function targetOptionLabel(target: CollabTarget) {
  return `${target.label} · ${participantTypeLabel(target.target_type)}`;
}

function targetDisplayName(thread: { title?: string | null; target_type?: string | null; target_id?: string | null }) {
  const knownTarget = store.targets.find((target) => (
    target.target_type === thread.target_type && target.target_id === thread.target_id
  ));
  return knownTarget?.label || cleanText(thread.title) || participantTypeLabel(thread.target_type);
}

function memoryStatusLabel(status?: string | null) {
  if (status === "candidate") return "候选";
  if (status === "confirmed" || status === "active") return "已确认";
  if (status === "archived") return "已归档";
  if (status === "disputed") return "有质疑";
  if (status === "superseded") return "已修订";
  return status || "记忆";
}

function memoryOptionLabel(memory: MeetingMemory) {
  return `${memory.title || "会议记忆"} · ${memoryStatusLabel(memory.status)}`;
}

function memoryThreadTitle(memory: MeetingMemory | Record<string, unknown>) {
  return `请确认：${cleanText((memory as MeetingMemory).title || (memory as Record<string, unknown>).memory_title) || "会议记忆"}`;
}

function messageTypeLabel(type?: string | null) {
  if (type === "memory_card") return "记忆卡片";
  if (type === "action_request") return "处理请求";
  if (type === "image") return "图片";
  if (type === "file") return "文件";
  if (type === "system") return "系统";
  return "普通说明";
}

function actionStatusLabel(status?: string | null) {
  if (status === "accepted") return "已接受";
  if (status === "rejected") return "已拒绝";
  if (status === "done") return "已完成";
  return "待处理";
}

function memoryCardActionStatusLabel(status?: string | null) {
  if (status === "rejected") return "已拒绝";
  if (status === "done") return "已确认";
  if (status === "accepted") return "已接受";
  return "待确认";
}

function actionStatusType(status?: string | null) {
  if (status === "done") return "success";
  if (status === "accepted") return "primary";
  if (status === "rejected") return "danger";
  return "warning";
}

function myReceipt(message: CollabMessage) {
  const selfId = String(auth.userId || "");
  return message.receipts.find((receipt) => receipt.recipient_type === "user" && receipt.recipient_id === selfId) || null;
}

function myActionStatus(message: CollabMessage) {
  return myReceipt(message)?.action_status || "pending";
}

function activeThreadTargetsMeetingRoom() {
  return store.activeThread?.target_type === "meeting_room";
}

function isCurrentUserMeetingRoomHost() {
  if (!activeThreadTargetsMeetingRoom()) return false;
  return Boolean(store.activeThread?.participants.some((participant) =>
    participant.participant_type === "user"
    && participant.participant_id === auth.userId
    && participant.role === "host",
  ));
}

function actionableReceipts(message: CollabMessage) {
  return message.receipts.filter((receipt) => {
    if (receipt.recipient_type !== "user") return false;
    return !(message.sender_type === "user" && receipt.recipient_id === message.sender_id);
  });
}

function handledActionReceipt(message: CollabMessage) {
  return actionOutcomeReceipts(message)[0] || null;
}

function meetingRoomActionStatus(message: CollabMessage) {
  if (!activeThreadTargetsMeetingRoom()) return myActionStatus(message);
  return handledActionReceipt(message)?.action_status || "pending";
}

function canHandleMessageAction(message: CollabMessage) {
  if (isOwnMessage(message)) return false;
  if (activeThreadTargetsMeetingRoom()) {
    return isCurrentUserMeetingRoomHost() && meetingRoomActionStatus(message) === "pending";
  }
  return !["done", "rejected"].includes(myActionStatus(message));
}

function meetingRoomHostHint(message: CollabMessage) {
  if (!activeThreadTargetsMeetingRoom()) return "";
  if (meetingRoomActionStatus(message) !== "pending") return "";
  if (isOwnMessage(message) || isCurrentUserMeetingRoomHost()) return "";
  return "等待会议室主持人处理";
}

function receiptDisplayName(recipientId: string) {
  if (recipientId === auth.userId) return "我";
  const target = store.targets.find((item) => item.target_type === "user" && item.target_id === recipientId);
  return target?.label || `成员 ${recipientId.slice(0, 8)}`;
}

function actionOutcomeReceipts(message: CollabMessage) {
  return actionableReceipts(message)
    .filter((receipt) => receipt.action_status && receipt.action_status !== "pending")
    .sort((a, b) => new Date(b.acted_at || b.read_at || 0).getTime() - new Date(a.acted_at || a.read_at || 0).getTime());
}

function actionReceiptSummary(message: CollabMessage) {
  const receipts = actionableReceipts(message);
  if (!receipts.length) return "暂无接收方回执";
  if (activeThreadTargetsMeetingRoom()) {
    const handled = handledActionReceipt(message);
    if (!handled) return "会议室待处理";
    return `会议室已处理：${receiptDisplayName(handled.recipient_id)}${actionStatusLabel(handled.action_status)}`;
  }
  const countByStatus = receipts.reduce<Record<string, number>>((acc, receipt) => {
    const status = receipt.action_status || "pending";
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});
  const parts = [
    countByStatus.done ? `${countByStatus.done} 已确认/完成` : "",
    countByStatus.accepted ? `${countByStatus.accepted} 已接受` : "",
    countByStatus.rejected ? `${countByStatus.rejected} 已拒绝` : "",
    countByStatus.pending ? `${countByStatus.pending} 待处理` : "",
  ].filter(Boolean);
  return `接收方：${parts.join("，")}`;
}

function memoryCardVisibleStatus(message: CollabMessage) {
  if (activeThreadTargetsMeetingRoom()) return meetingRoomActionStatus(message);
  if (!isOwnMessage(message)) return myActionStatus(message);
  const receipts = actionableReceipts(message);
  if (receipts.some((receipt) => receipt.action_status === "done")) return "done";
  if (receipts.some((receipt) => receipt.action_status === "rejected")) return "rejected";
  if (receipts.some((receipt) => receipt.action_status === "accepted")) return "accepted";
  return "pending";
}

function isOwnMessage(message: CollabMessage) {
  return message.sender_type === "user" && message.sender_id === auth.userId;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function cleanText(value: unknown) {
  return String(value || "").trim();
}

function unwrap<T>(payload: unknown): T {
  return ((payload as { data?: T }).data || payload) as T;
}

function sourceTypeLabel(type?: string | null) {
  if (type === "meeting_room" || type === "meeting") return "会议室";
  if (type === "memory") return "记忆";
  if (type === "message" || type === "meeting_message") return "会议消息";
  if (type === "agent") return "Agent";
  if (type === "user") return "成员";
  if (type === "manual") return "手动说明";
  return cleanText(type) || "手动说明";
}

function sourceContextFromMetadata(metadata?: Record<string, unknown> | null) {
  const root = asRecord(metadata);
  const direct = asRecord(root.source_context || root.source || root.origin);
  if (Object.keys(direct).length) return direct;
  const memory = asRecord(root.memory || root.memory_card || root.memory_item);
  if (Object.keys(memory).length) {
    return {
      source_type: "memory",
      source_id: memory.memory_id || memory.id,
      source_title: memory.title || memory.memory_title,
      source_room_id: memory.source_room_id || memory.meeting_room_id || memory.room_id,
      source_message_id: memory.source_message_id,
    };
  }
  return {};
}

function defaultSourceContext() {
  return {
    source_type: "manual",
    label: "手动说明",
  };
}

function manualSourceContext() {
  const label = cleanText(sourceManualLabel.value);
  return label ? { source_type: "manual", label } : defaultSourceContext();
}

function memoryCardPayload(memory: MeetingMemory, room: MeetingRoom) {
  return {
    memory_id: memory.memory_id,
    title: memory.title,
    summary: memory.summary || memory.content,
    content: memory.content,
    memory_type: memory.memory_type,
    memory_category: memory.memory_category,
    status: memory.status,
    recommended_scope: memory.recommended_scope,
    recommended_scope_id: memory.recommended_scope_id,
    source_room_id: room.id,
    source_room_title: room.title,
    source_message_id: memory.source_message_id || null,
    affected_objects: memory.affected_objects || null,
    tags: memory.tags || [],
  };
}

function replaceRecord(target: Record<string, unknown>, value: Record<string, unknown>) {
  Object.keys(target).forEach((key) => delete target[key]);
  Object.assign(target, value);
}

function normalizeSourceContext(value?: Record<string, unknown> | null) {
  const context = asRecord(value);
  const sourceType = cleanText(context.source_type || context.type) || "manual";
  const next: Record<string, unknown> = {
    ...context,
    source_type: sourceType,
  };
  const label = cleanText(context.label || context.source_label || context.source_title || context.title);
  if (label) next.label = label;
  if (sourceType === "manual" && !label) next.label = defaultSourceContext().label;
  if (sourceType === "meeting_room" && cleanText(context.source_id) && !cleanText(context.source_room_id)) {
    next.source_room_id = cleanText(context.source_id);
  }
  return next;
}

function applySourceContext(value?: Record<string, unknown> | null) {
  const next = Object.keys(asRecord(value)).length
    ? normalizeSourceContext(value)
    : defaultSourceContext();
  replaceRecord(activeSourceContext, next);
  replaceRecord(createSourceContext, next);
}

function sourceLabelFromContext(context: Record<string, unknown>) {
  const label = cleanText(context.label || context.source_label || context.title);
  if (label) return label;
  const title = cleanText(context.source_title || context.room_title || context.meeting_title || context.memory_title);
  const sourceType = cleanText(context.source_type || context.type);
  const sourceId = cleanText(context.source_id || context.id || context.memory_id || context.room_id || context.source_room_id);
  if (title) return `${sourceTypeLabel(sourceType)} ${title}`;
  if (sourceId) return `${sourceTypeLabel(sourceType)}已选择`;
  const sourceMessageId = cleanText(context.source_message_id || context.message_id);
  if (sourceMessageId) return "会议消息已选择";
  return "手动说明";
}

function routeWantsCreateDialog() {
  const intent = cleanText(
    route.query.open_create
      || route.query.create
      || route.query.mode
      || route.query.action
      || route.query.open,
  ).toLowerCase();
  return ["1", "true", "yes", "create", "send", "share"].includes(intent);
}

function threadSourceLabel(thread: { source_type?: string | null; source_id?: string | null; metadata_json?: Record<string, unknown> | null }) {
  const context = sourceContextFromMetadata(thread.metadata_json);
  const fromMetadata = sourceLabelFromContext(context);
  if (fromMetadata !== "手动说明") return fromMetadata;
  if (thread.source_type === "user" && thread.source_id === auth.userId) return "我直接发起";
  if (thread.source_type || thread.source_id) return `${sourceTypeLabel(thread.source_type)} ${thread.source_id || ""}`.trim();
  return "手动说明";
}

function threadFlowLabel(thread: { target_type?: string | null; target_id?: string | null; metadata_json?: Record<string, unknown> | null; source_type?: string | null; source_id?: string | null }) {
  return `${threadSourceLabel(thread)} → ${participantTypeLabel(thread.target_type)} ${targetDisplayName(thread)}`.trim();
}

function messageSourceLabel(message: CollabMessage) {
  const context = sourceContextFromMetadata(message.metadata_json);
  const fromMessage = sourceLabelFromContext(context);
  if (fromMessage !== "手动说明") return fromMessage;
  return store.activeThread ? threadSourceLabel(store.activeThread) : "手动说明";
}

function memorySourceRows(message: CollabMessage) {
  const metadata = asRecord(message.metadata_json);
  const memory = memoryPayload(message);
  const context = sourceContextFromMetadata(metadata);
  const rows: Array<{ label: string; value: string }> = [];
  const roomId = cleanText(memory.source_room_id || memory.meeting_room_id || context.source_room_id || context.room_id);
  const messageId = cleanText(memory.source_message_id || context.source_message_id || context.message_id);
  const memoryId = cleanText(memory.memory_id || memory.id || context.source_id);
  if (roomId) rows.push({ label: "来源会议室", value: sourceRoomName(roomId, memory, context) });
  if (messageId) rows.push({ label: "来源消息", value: "来源消息已记录" });
  if (memoryId) rows.push({ label: "来源记忆", value: cleanText(memory.title || memory.memory_title || context.source_title) || "会议记忆" });
  if (!rows.length) rows.push({ label: "来源", value: messageSourceLabel(message) });
  return rows;
}

function sourceRoomName(roomId: string, memory: Record<string, unknown>, context: Record<string, unknown>) {
  return cleanText(memory.source_room_title || memory.meeting_room_title || context.source_room_title || context.room_title)
    || sourceRooms.value.find((room) => room.id === roomId)?.title
    || store.targets.find((target) => target.target_type === "meeting_room" && target.target_id === roomId)?.label
    || "来源会议室";
}

function memoryPayload(message: CollabMessage) {
  const metadata = asRecord(message.metadata_json);
  return asRecord(metadata.memory || metadata.memory_card || metadata.memory_item);
}

function memoryTitle(message: CollabMessage) {
  const memory = memoryPayload(message);
  return String(memory.title || memory.memory_title || "待确认记忆");
}

function memorySummary(message: CollabMessage) {
  const memory = memoryPayload(message);
  return String(memory.summary || memory.content || message.content || "接收方确认后可进入对应作用域。");
}

function receiptSummary(message: CollabMessage) {
  const unread = message.receipts.filter((receipt) => !receipt.read_at && receipt.recipient_type === "user").length;
  if (unread > 0) return `${unread} 人未读`;
  if (activeThreadTargetsMeetingRoom() && ["memory_card", "action_request"].includes(message.message_type)) {
    const handled = handledActionReceipt(message);
    if (handled) return `会议室已由${receiptDisplayName(handled.recipient_id)}处理`;
  }
  const pending = message.receipts.filter((receipt) => receipt.action_status === "pending").length;
  if (message.message_type === "action_request" && pending > 0) return `${pending} 个待处理`;
  if (message.message_type === "memory_card" && pending > 0) return `${pending} 个待确认`;
  return "已送达";
}

function resetCreateForm() {
  createForm.target_type = "user";
  createForm.target_id = "";
  createForm.title = "";
  lastAutoCreateTitle.value = "";
  createForm.metadata_json = null;
  replaceRecord(createSourceContext, { ...activeSourceContext });
  if (Object.keys(draftMemoryCard).length) {
    sourceMode.value = "meeting_memory";
  }
}

function clearActiveSource() {
  applySourceContext(defaultSourceContext());
  sourceMode.value = "manual";
  sourceRoomId.value = "";
  sourceMemoryId.value = "";
  sourceMemories.value = [];
  replaceRecord(draftMemoryCard, {});
  if (selectedMessageType.value === "memory_card") selectedMessageType.value = "text";
}

async function loadSourceRooms() {
  loadingSourceRooms.value = true;
  try {
    const { data } = await meetingApi.listRooms();
    sourceRooms.value = ((data as { data?: MeetingRoom[] }).data || data) as MeetingRoom[];
    return sourceRooms.value;
  } finally {
    loadingSourceRooms.value = false;
  }
}

async function loadSourceMemories(roomId: string) {
  if (!roomId) {
    sourceMemories.value = [];
    return [];
  }
  loadingSourceMemories.value = true;
  try {
    const { data } = await meetingApi.listMemories(roomId);
    sourceMemories.value = ((data as { data?: MeetingMemory[] }).data || data) as MeetingMemory[];
    return sourceMemories.value;
  } finally {
    loadingSourceMemories.value = false;
  }
}

function applyManualSource() {
  sourceMode.value = "manual";
  sourceManualLabel.value = "";
  sourceRoomId.value = "";
  sourceMemoryId.value = "";
  sourceMemories.value = [];
  applySourceContext(defaultSourceContext());
  replaceRecord(draftMemoryCard, {});
  if (selectedMessageType.value === "memory_card") selectedMessageType.value = "text";
}

function syncManualSource() {
  if (sourceMode.value !== "manual") return;
  applySourceContext(manualSourceContext());
}

async function onSourceModeChange() {
  if (sourceMode.value === "manual") {
    applyManualSource();
    return;
  }
  replaceRecord(draftMemoryCard, {});
  selectedMessageType.value = "memory_card";
  if (!sourceRooms.value.length) {
    await loadSourceRooms().catch(() => {
      ElMessage.warning("来源会议室加载失败，请稍后刷新。");
    });
  }
}

async function onSourceRoomChange(roomId: string) {
  sourceMemoryId.value = "";
  replaceRecord(draftMemoryCard, {});
  if (createForm.title === lastAutoCreateTitle.value) {
    createForm.title = "";
  }
  lastAutoCreateTitle.value = "";
  const room = sourceRooms.value.find((item) => item.id === roomId);
  if (!room) {
    applySourceContext(defaultSourceContext());
    return;
  }
  applySourceContext({
    source_type: "meeting_room",
    source_id: room.id,
    source_room_id: room.id,
    source_title: room.title,
    label: `会议室 ${room.title}`,
  });
  await loadSourceMemories(room.id).catch(() => {
    ElMessage.warning("会议室记忆加载失败，请稍后刷新。");
  });
}

function onSourceMemoryChange(memoryId: string) {
  const memory = sourceMemories.value.find((item) => item.memory_id === memoryId);
  const room = selectedSourceRoom.value;
  if (!memory || !room) return;
  const sourceContext = {
    source_type: "memory",
    source_id: memory.memory_id,
    source_title: memory.title,
    source_room_id: room.id,
    source_message_id: memory.source_message_id || null,
    label: `记忆 ${memory.title || memory.memory_id}`,
  };
  applySourceContext(sourceContext);
  replaceRecord(draftMemoryCard, memoryCardPayload(memory, room));
  selectedMessageType.value = "memory_card";
  if (!composer.value.trim()) {
    composer.value = "请确认这条会议记忆是否需要沉淀到你的作用域。";
  }
  const nextAutoTitle = memoryThreadTitle(memory);
  if (!createForm.title.trim() || createForm.title === lastAutoCreateTitle.value) {
    createForm.title = nextAutoTitle;
  }
  lastAutoCreateTitle.value = nextAutoTitle;
}

function prefillCreateFormFromRoute() {
  const shouldOpenCreateDialog = routeWantsCreateDialog();
  const targetType = cleanText(route.query.target_type);
  const targetId = cleanText(route.query.target_id);
  if (targetType === "user" || targetType === "meeting_room") {
    createForm.target_type = targetType;
  }
  if (targetId) createForm.target_id = targetId;
  createForm.title = cleanText(route.query.title);

  const draft = readDraftFromRoute();
  const sourceType = cleanText(route.query.source_type);
  const sourceId = cleanText(route.query.source_id);
  const sourceLabel = cleanText(route.query.source_label);
  const routeSourceRoomId = cleanText(route.query.source_room_id);
  const sourceMessageId = cleanText(route.query.source_message_id);
  const sourceContext = normalizeSourceContext({
    ...(asRecord(draft.source_context)),
    ...(sourceType || sourceId || sourceLabel || routeSourceRoomId || sourceMessageId
      ? {
          source_type: sourceType || asRecord(draft.source_context).source_type || "manual",
          source_id: sourceId || asRecord(draft.source_context).source_id,
          source_title: sourceLabel || asRecord(draft.source_context).source_title,
          source_room_id: routeSourceRoomId || asRecord(draft.source_context).source_room_id,
          source_message_id: sourceMessageId || asRecord(draft.source_context).source_message_id,
          label: sourceLabel || asRecord(draft.source_context).label,
        }
      : {}),
  });
  if (sourceContext.source_type !== "manual" || cleanText(sourceContext.label) !== "手动说明") {
    applySourceContext(sourceContext);
  }

  const memory = asRecord(draft.memory || draft.memory_card);
  if (Object.keys(memory).length) {
    sourceMode.value = "meeting_memory";
    sourceRoomId.value = cleanText(memory.source_room_id || memory.meeting_room_id || routeSourceRoomId);
    sourceMemoryId.value = cleanText(memory.memory_id || memory.id);
    if (sourceRoomId.value) {
      void loadSourceMemories(sourceRoomId.value).catch(() => {
        // 草稿已经携带了记忆卡片，加载完整列表失败也不阻塞发送。
      });
    }
    replaceRecord(draftMemoryCard, memory);
    selectedMessageType.value = "memory_card";
    if (!composer.value.trim()) {
      composer.value = cleanText(draft.content)
        || "请确认这条会议记忆是否需要沉淀到你的作用域。";
    }
    const draftTitle = cleanText(draft.title);
    const nextAutoTitle = memoryThreadTitle(memory);
    if (!createForm.title) {
      createForm.title = draftTitle || nextAutoTitle;
      lastAutoCreateTitle.value = draftTitle ? "" : nextAutoTitle;
    }
  }
  createDialogVisible.value = shouldOpenCreateDialog;
}

function readDraftFromRoute() {
  const draftKey = cleanText(route.query.draft_key);
  if (!draftKey || typeof window === "undefined") return {};
  const storageKey = `collab:draft:${draftKey}`;
  try {
    const raw = window.sessionStorage.getItem(storageKey);
    if (!raw) return {};
    window.sessionStorage.removeItem(storageKey);
    return asRecord(JSON.parse(raw));
  } catch {
    return {};
  }
}

async function createThread() {
  if (!createForm.target_id.trim()) {
    ElMessage.warning("请选择接收目标");
    return;
  }
  if (sourceMode.value === "meeting_memory" && !selectedSourceMemory.value) {
    ElMessage.warning("请选择要分享的具体记忆");
    return;
  }
  creatingThread.value = true;
  try {
    await store.createThread({
      target_type: createForm.target_type,
      target_id: createForm.target_id.trim(),
      title: createForm.title?.trim() || selectedTarget.value?.label || null,
      metadata_json: {
        source_context: { ...createSourceContext },
      },
    });
    applySourceContext(createSourceContext);
    createDialogVisible.value = false;
    resetCreateForm();
  } finally {
    creatingThread.value = false;
  }
}

async function sendMessage() {
  const content = composer.value.trim();
  const isDraftMemoryMessage = selectedMessageType.value === "memory_card" && hasDraftMemoryCard.value;
  if (!content && store.pendingAttachments.length === 0 && !isDraftMemoryMessage) {
    ElMessage.warning("请输入内容或添加附件");
    return;
  }
  const attachmentType = store.pendingAttachments.some((item) => String(item.content_type || "").startsWith("image/"))
    ? "image"
    : "file";
  const messageType = selectedMessageType.value === "file" && store.pendingAttachments.length ? attachmentType : selectedMessageType.value;
  const threadSourceContext = sourceContextFromMetadata(store.activeThread?.metadata_json);
  const sourceContext = hasActiveSource.value
    ? { ...activeSourceContext }
    : (threadSourceContext.source_type ? threadSourceContext : defaultSourceContext());
  const metadata: Record<string, unknown> = {
    source_context: sourceContext,
  };
  if (messageType === "memory_card" && hasDraftMemoryCard.value) {
    metadata.memory = { ...draftMemoryCard };
  }
  await store.sendMessage(content, messageType, {
    ...metadata,
  });
  composer.value = "";
  selectedMessageType.value = "text";
  replaceRecord(draftMemoryCard, {});
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!files.length) return;
  await store.uploadAttachments(files);
  input.value = "";
}

async function updateAction(message: CollabMessage, status: "accepted" | "rejected" | "done") {
  try {
    await store.updateAction(message.id, status);
    if (message.message_type === "memory_card") {
      ElMessage.success(status === "rejected" ? "记忆卡片已拒绝。" : "记忆已确认沉淀。");
      return;
    }
    ElMessage.success(actionStatusLabel(status));
  } catch (error) {
    if (activeThreadTargetsMeetingRoom()) {
      ElMessage.warning("这条会议室请求已由其他成员处理。");
      return;
    }
    throw error;
  }
}

async function deleteActiveThread() {
  if (!store.activeThread) return;
  try {
    await ElMessageBox.confirm("删除后该协作记录会从协作消息列表中移除，相关后台审计痕迹仍会保留。", "删除协作记录", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await store.deleteThread(store.activeThread.id);
    ElMessage.success("协作记录已删除。");
  } catch {
    // cancelled
  }
}

async function deleteCollabMessage(message: CollabMessage) {
  try {
    await ElMessageBox.confirm("删除后该消息会从协作记录中隐藏，但后台仍保留审计痕迹。", "删除协作消息", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await store.deleteMessage(message.id);
    ElMessage.success("消息已删除。");
  } catch {
    // cancelled
  }
}

function onTargetTypeChange() {
  createForm.target_id = "";
}

onMounted(() => {
  prefillCreateFormFromRoute();
  store.loadThreads(true).catch(() => {
    ElMessage.warning("协作消息加载失败，请稍后刷新。");
  });
  store.loadTargets().catch(() => {
    ElMessage.warning("目标列表加载失败，请稍后刷新。");
  });
  loadSourceRooms().catch(() => {
    // 来源会议室只影响手动选择记忆，不阻塞协作消息主流程。
  });
  store.connectStream();
});

onBeforeUnmount(() => {
  store.disconnectStream();
});
</script>

<template>
  <main class="collab-page">
    <aside class="thread-rail">
      <div class="rail-hero">
        <div>
          <p class="eyebrow">Collaboration Inbox</p>
          <h1>协作消息</h1>
          <span class="rail-subtitle">成员与会议室的共享、确认及处理入口</span>
        </div>
        <el-badge :value="store.totalUnread" :hidden="store.totalUnread === 0" type="danger">
          <el-button :icon="Plus" circle @click="createDialogVisible = true" />
        </el-badge>
      </div>

      <el-scrollbar class="thread-list" v-loading="store.loadingThreads">
        <button
          v-for="thread in store.threads"
          :key="thread.id"
          type="button"
          class="thread-card"
          :class="{ 'thread-card-active': thread.id === store.activeThreadId }"
          @click="store.openThread(thread.id)"
        >
          <span class="thread-kind">{{ participantTypeLabel(thread.target_type) }}</span>
          <strong>{{ targetDisplayName(thread) }}</strong>
          <small class="thread-flow">{{ threadFlowLabel(thread) }}</small>
          <small v-if="thread.status === 'archived'" class="thread-archived">已归档</small>
          <small>{{ formatTime(thread.last_message_at || thread.updated_at || thread.created_at) }}</small>
          <em v-if="thread.unread_count">{{ thread.unread_count }}</em>
        </button>
        <div v-if="!store.threads.length && !store.loadingThreads" class="empty-thread">
          <Bell />
          <p>还没有分享或请求</p>
          <span>选择成员或会议室后即可发送共享、确认或处理请求。</span>
        </div>
      </el-scrollbar>

    </aside>

    <section class="message-stage">
      <header class="stage-header">
        <div>
          <p class="eyebrow">Channel</p>
          <h2>{{ activeTitle }}</h2>
          <span>{{ activeThreadFlow }}</span>
          <small v-if="activeTarget" class="stage-source-line">当前来源：{{ activeThreadSource }}；接收方会在协作消息中看到提醒和回执。</small>
        </div>
        <div class="stage-actions">
          <el-button v-if="store.activeThread" :icon="Delete" type="danger" plain @click="deleteActiveThread">删除</el-button>
          <el-button :icon="Plus" type="primary" @click="createDialogVisible = true">发送给目标</el-button>
        </div>
      </header>

      <el-scrollbar class="message-list" v-loading="store.loadingMessages">
        <div v-if="!store.activeThread" class="empty-stage">
          <Select />
          <h3>选择左侧记录开始</h3>
          <p>协作消息用于向成员或会议室发送说明、附件、记忆卡片和处理请求。</p>
        </div>
        <article
          v-for="message in store.activeMessages"
          :key="message.id"
          class="message-bubble"
          :class="{ 'message-bubble-own': isOwnMessage(message) }"
        >
          <div class="message-meta">
            <span>{{ isOwnMessage(message) ? "我" : participantTypeLabel(message.sender_type) }}</span>
            <el-tag size="small" effect="plain">{{ messageTypeLabel(message.message_type) }}</el-tag>
            <small>{{ formatTime(message.created_at) }}</small>
          </div>
          <div class="message-source-line">
            来源：{{ messageSourceLabel(message) }} · 目标：{{ activeTarget || "当前协作目标" }}
          </div>

          <div v-if="message.message_type === 'memory_card'" class="memory-card">
            <strong>{{ memoryTitle(message) }}</strong>
            <p>{{ memorySummary(message) }}</p>
            <div class="memory-source-grid">
              <span v-for="row in memorySourceRows(message)" :key="`${row.label}-${row.value}`">
                {{ row.label }}：{{ row.value }}
              </span>
            </div>
            <span>接收方确认后，会沉淀到这条协作记录的目标作用域。</span>
            <div class="memory-card-actions">
              <span class="memory-status-pill" :class="`memory-status-${memoryCardVisibleStatus(message) || 'pending'}`">
                {{ memoryCardActionStatusLabel(memoryCardVisibleStatus(message)) }}
              </span>
              <template v-if="canHandleMessageAction(message)">
                <el-button size="small" :icon="Close" @click="updateAction(message, 'rejected')">拒绝</el-button>
                <el-button size="small" type="success" :icon="Check" @click="updateAction(message, 'done')">确认沉淀</el-button>
              </template>
              <small v-else-if="meetingRoomHostHint(message)" class="meeting-host-hint">{{ meetingRoomHostHint(message) }}</small>
            </div>
            <div v-if="isOwnMessage(message)" class="action-receipt-summary">{{ actionReceiptSummary(message) }}</div>
          </div>

          <p v-if="message.content" class="message-content">{{ message.content }}</p>

          <div v-if="message.attachments.length" class="attachment-grid">
            <template v-for="file in message.attachments" :key="file.id">
              <ImageAttachmentCard
                v-if="isImageAttachment(file)"
                :src="file.url"
                :name="collabAttachmentName(file)"
                @preview="openCollabImagePreview(file)"
              />
              <a
                v-else
                class="attachment-chip"
                :href="file.url"
                target="_blank"
                rel="noreferrer"
              >
                <Paperclip />
                <span>{{ collabAttachmentName(file) }}</span>
                <small>{{ formatBytes(file.size_bytes) }}</small>
              </a>
            </template>
          </div>

          <div class="message-footer">
            <span>{{ receiptSummary(message) }}</span>
            <template v-if="message.message_type === 'action_request'">
              <el-tag size="small" :type="actionStatusType(meetingRoomActionStatus(message))" effect="light">
                {{ actionStatusLabel(meetingRoomActionStatus(message)) }}
              </el-tag>
              <div v-if="canHandleMessageAction(message)" class="action-buttons">
                <el-button size="small" :icon="Check" @click="updateAction(message, 'accepted')">接受</el-button>
                <el-button size="small" :icon="Close" @click="updateAction(message, 'rejected')">拒绝</el-button>
                <el-button size="small" type="success" @click="updateAction(message, 'done')">完成</el-button>
              </div>
              <small v-else-if="meetingRoomHostHint(message)" class="meeting-host-hint">{{ meetingRoomHostHint(message) }}</small>
            </template>
            <span v-if="isOwnMessage(message) && message.message_type === 'action_request'" class="action-receipt-summary">
              {{ actionReceiptSummary(message) }}
            </span>
            <el-button v-if="isOwnMessage(message)" size="small" text :icon="Delete" @click="deleteCollabMessage(message)">
              删除
            </el-button>
          </div>
          <div v-if="isOwnMessage(message) && actionOutcomeReceipts(message).length" class="action-outcomes">
            <span v-for="receipt in actionOutcomeReceipts(message)" :key="receipt.id">
              {{ receiptDisplayName(receipt.recipient_id) }}：{{ actionStatusLabel(receipt.action_status) }}
            </span>
          </div>
        </article>
      </el-scrollbar>

      <footer class="composer" :class="{ 'composer-disabled': !store.activeThread }">
        <div v-if="hasActiveSource || hasDraftMemoryCard" class="source-context-card">
          <div>
            <span>本次分享来源</span>
            <strong>{{ activeSourceLabel }}</strong>
            <small v-if="hasDraftMemoryCard">将随消息携带记忆卡片，接收方可确认后沉淀到对应作用域。</small>
            <small v-else>这次发送会保留该来源；复用旧通道时也不会丢失。</small>
          </div>
          <el-button text size="small" @click="clearActiveSource">改为手动来源</el-button>
        </div>

        <div v-if="hasDraftMemoryCard" class="draft-memory-card">
          <span>待发送记忆卡片</span>
          <strong>{{ cleanText(draftMemoryCard.title || draftMemoryCard.memory_title) || "会议记忆" }}</strong>
          <p>{{ cleanText(draftMemoryCard.summary || draftMemoryCard.content) || "接收方确认后可沉淀到对应作用域。" }}</p>
        </div>

        <div class="composer-toolbar">
          <el-select v-model="selectedMessageType" size="small" class="message-type-select">
            <el-option
              v-for="option in messageTypeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            >
              <span>{{ option.label }}</span>
              <small>{{ option.hint }}</small>
            </el-option>
          </el-select>
          <input ref="fileInputRef" class="hidden-file" type="file" multiple @change="onFileChange" />
          <el-button :icon="Paperclip" :loading="store.uploading" @click="fileInputRef?.click()">附件</el-button>
        </div>

        <div v-if="store.pendingAttachments.length" class="pending-files">
          <button
            v-for="file in store.pendingAttachments"
            :key="file.id"
            type="button"
            @click="store.removePendingAttachment(file.id)"
          >
            {{ file.name }} · {{ formatBytes(file.size_bytes) }}
          </button>
        </div>

        <div class="composer-row">
          <el-input
            v-model="composer"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            resize="none"
            :disabled="!store.activeThread"
            placeholder="输入协作说明。可发送图片、文件、记忆卡片或处理请求。"
            @keydown.ctrl.enter.prevent="sendMessage"
          />
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="store.sending"
            :disabled="!store.activeThread"
            @click="sendMessage"
          >
            发送
          </el-button>
        </div>
      </footer>
    </section>

    <el-dialog v-model="createDialogVisible" title="发送给目标" width="560px" @closed="resetCreateForm">
      <el-form label-position="top">
        <el-form-item label="分享来源">
          <div class="source-picker">
            <el-segmented
              v-model="sourceMode"
              :options="[
                { label: '手动说明', value: 'manual' },
                { label: '会议室记忆', value: 'meeting_memory' },
              ]"
              @change="onSourceModeChange"
            />
            <div v-if="sourceMode === 'manual'" class="dialog-source-card">
              <strong>{{ createSourceLabel }}</strong>
              <el-input
                v-model="sourceManualLabel"
                clearable
                placeholder="可选，例如：线下评审、外部文件、临时说明"
                @input="syncManualSource"
              />
              <span>用于临时说明、普通文件或处理请求；不会自动携带会议室记忆。</span>
            </div>
            <div v-else class="source-memory-picker">
              <el-select
                v-model="sourceRoomId"
                class="target-select"
                filterable
                :loading="loadingSourceRooms"
                placeholder="先选择来源会议室"
                no-data-text="暂无可选会议室"
                @change="onSourceRoomChange"
              >
                <el-option
                  v-for="room in sourceRooms"
                  :key="room.id"
                  :label="room.title"
                  :value="room.id"
                >
                  <div class="target-option">
                    <strong>{{ room.title }}</strong>
                    <span>{{ room.member_count || 0 }} 位成员 · {{ room.status }}</span>
                  </div>
                </el-option>
              </el-select>
              <el-select
                v-model="sourceMemoryId"
                class="target-select"
                filterable
                :disabled="!sourceRoomId"
                :loading="loadingSourceMemories"
                placeholder="再选择具体记忆"
                no-data-text="该会议室暂无可分享记忆"
                @change="onSourceMemoryChange"
              >
                <el-option
                  v-for="memory in sourceMemoryOptions"
                  :key="memory.memory_id"
                  :label="memoryOptionLabel(memory)"
                  :value="memory.memory_id"
                >
                  <div class="target-option memory-source-option">
                    <strong>{{ memory.title || "会议记忆" }}</strong>
                    <span>{{ memoryStatusLabel(memory.status) }} · {{ memory.summary || memory.content }}</span>
                  </div>
                </el-option>
              </el-select>
              <p class="target-helper">
                选择会议室只是定位来源；真正分享的是下面选中的那一条记忆卡片。
              </p>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-segmented
            v-model="createForm.target_type"
            :options="targetTypeOptions.map((item) => ({ label: item.label, value: item.value }))"
            @change="onTargetTypeChange"
          />
        </el-form-item>
        <el-form-item label="选择目标">
          <el-select
            v-model="createForm.target_id"
            class="target-select"
            filterable
            :loading="store.loadingTargets"
            :placeholder="`选择${participantTypeLabel(createForm.target_type)}`"
            no-data-text="暂无可选目标"
          >
            <el-option
              v-for="target in targetOptions"
              :key="`${target.target_type}-${target.target_id}`"
              :label="targetOptionLabel(target)"
              :value="target.target_id"
            >
              <div class="target-option">
                <strong>{{ target.label }}</strong>
                <span>{{ target.description || participantTypeLabel(target.target_type) }}</span>
              </div>
            </el-option>
          </el-select>
          <p class="target-helper">
            不需要记 ID；成员来自组织用户，会议室来自你已加入的会议室。
          </p>
        </el-form-item>
        <el-form-item label="协作标题">
          <el-input v-model="createForm.title" placeholder="可选，例如：请确认这条会议记忆" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingThread" @click="createThread">发送给目标</el-button>
      </template>
    </el-dialog>

    <ImagePreviewDialog v-model="imagePreviewVisible" :src="previewImage.url" :title="previewImage.name" />
  </main>
</template>

<style scoped>
.collab-page {
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  gap: 18px;
  min-height: calc(100vh - 96px);
  padding: 20px;
  background:
    radial-gradient(circle at 12% 18%, rgba(44, 123, 229, 0.16), transparent 28%),
    linear-gradient(135deg, #f7f3ea 0%, #eef5f0 48%, #f7fafc 100%);
}

.thread-rail,
.message-stage {
  border: 1px solid rgba(27, 42, 65, 0.08);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 24px 60px rgba(33, 45, 66, 0.12);
  backdrop-filter: blur(18px);
}

.thread-rail {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.rail-hero,
.stage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px;
  border-bottom: 1px solid rgba(27, 42, 65, 0.08);
}

.eyebrow {
  margin: 0 0 6px;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1,
h2,
h3 {
  margin: 0;
  color: #172033;
}

.rail-hero span,
.stage-header span,
.empty-thread span,
.empty-stage p {
  color: #64748b;
  font-size: 13px;
}

.rail-subtitle {
  display: block;
  max-width: 18em;
  line-height: 1.7;
  text-wrap: balance;
}

.stage-source-line {
  display: block;
  margin-top: 5px;
  color: #64748b;
  font-size: 12px;
}

.stage-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.thread-list {
  min-height: 0;
  flex: 1;
  padding: 14px;
}

.thread-card {
  position: relative;
  display: grid;
  width: 100%;
  gap: 5px;
  margin-bottom: 10px;
  padding: 15px 16px;
  border: 1px solid rgba(27, 42, 65, 0.08);
  border-radius: 18px;
  background: #fffaf0;
  color: #172033;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.thread-card:hover,
.thread-card-active {
  transform: translateY(-1px);
  border-color: rgba(24, 94, 112, 0.32);
  box-shadow: 0 14px 32px rgba(24, 94, 112, 0.14);
}

.thread-card strong {
  padding-right: 28px;
}

.thread-card small,
.thread-kind {
  color: #64748b;
  font-size: 12px;
}

.thread-flow {
  display: block;
  padding-right: 28px;
}

.thread-card em {
  position: absolute;
  top: 14px;
  right: 14px;
  min-width: 22px;
  padding: 2px 6px;
  border-radius: 999px;
  background: #dc2626;
  color: white;
  font-size: 12px;
  font-style: normal;
  text-align: center;
}

.thread-archived {
  width: fit-content;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.12);
  color: #475569;
}

.empty-thread,
.empty-stage {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 260px;
  color: #64748b;
  text-align: center;
}

.empty-thread svg,
.empty-stage svg {
  width: 42px;
  height: 42px;
  color: #185e70;
}

.message-stage {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.message-list {
  min-height: 0;
  padding: 22px;
}

.message-bubble {
  max-width: 760px;
  margin: 0 0 14px;
  padding: 16px;
  border: 1px solid rgba(27, 42, 65, 0.08);
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(30, 41, 59, 0.08);
}

.message-bubble-own {
  margin-left: auto;
  background: #eef8f3;
  border-color: rgba(22, 101, 52, 0.14);
}

.message-meta,
.message-footer,
.composer-toolbar,
.composer-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.message-meta {
  margin-bottom: 10px;
  color: #64748b;
  font-size: 12px;
}

.message-meta span {
  color: #172033;
  font-weight: 700;
}

.message-source-line {
  margin: -4px 0 10px;
  color: #64748b;
  font-size: 12px;
}

.message-content {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #243044;
}

.memory-card {
  margin-bottom: 12px;
  padding: 14px;
  border-radius: 8px;
  background: linear-gradient(135deg, #102a43, #185e70);
  color: white;
}

.memory-card p {
  margin: 8px 0;
  color: rgba(255, 255, 255, 0.88);
}

.memory-card span {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
}

.memory-card :deep(.el-button) {
  margin-top: 8px;
  color: #0f172a;
  background: #ffffff;
  border-color: rgba(255, 255, 255, 0.78);
  font-weight: 700;
}

.memory-card :deep(.el-button:hover) {
  color: #0f172a;
  background: #f8fafc;
  border-color: #ffffff;
}

.memory-card :deep(.el-button--success) {
  color: #ffffff;
  background: #16a34a;
  border-color: #16a34a;
}

.memory-card :deep(.el-button--success:hover) {
  color: #ffffff;
  background: #15803d;
  border-color: #15803d;
}

.memory-source-grid {
  display: grid;
  gap: 4px;
  margin: 10px 0;
}

.memory-source-grid span {
  color: rgba(255, 255, 255, 0.78);
}

.memory-card-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.memory-status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.38);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
}

.memory-status-pending,
.memory-status-accepted {
  background: #fef3c7;
  border-color: #f59e0b;
  color: #78350f;
}

.memory-status-done {
  background: #dcfce7;
  border-color: #22c55e;
  color: #14532d;
}

.memory-status-rejected {
  background: #fee2e2;
  border-color: #ef4444;
  color: #7f1d1d;
}

.memory-card .memory-status-pending,
.memory-card .memory-status-accepted {
  color: #78350f;
}

.memory-card .memory-status-done {
  color: #14532d;
}

.memory-card .memory-status-rejected {
  color: #7f1d1d;
}

.meeting-host-hint {
  color: rgba(255, 255, 255, 0.78);
  font-size: 12px;
  font-weight: 700;
}

.attachment-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
}

.attachment-chip,
.pending-files button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(24, 94, 112, 0.18);
  border-radius: 999px;
  background: #f8fbfb;
  color: #185e70;
  text-decoration: none;
}

.attachment-chip {
  justify-content: space-between;
  padding: 9px 12px;
}

.attachment-chip svg {
  width: 16px;
}

.message-footer {
  justify-content: space-between;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
}

.action-receipt-summary {
  color: #475569;
  font-weight: 700;
}

.message-footer .meeting-host-hint {
  color: #64748b;
}

.action-outcomes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.action-outcomes span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 9px;
  border: 1px solid rgba(24, 94, 112, 0.18);
  border-radius: 999px;
  background: #f8fbfb;
  color: #185e70;
  font-size: 12px;
  font-weight: 700;
}

.action-buttons {
  display: inline-flex;
  gap: 6px;
}

.source-context-card,
.draft-memory-card,
.dialog-source-card {
  border: 1px solid rgba(24, 94, 112, 0.14);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(24, 94, 112, 0.08), rgba(245, 247, 242, 0.9));
}

.source-picker,
.source-memory-picker {
  display: grid;
  gap: 10px;
}

.source-context-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  padding: 12px 14px;
}

.source-context-card div,
.dialog-source-card {
  display: grid;
  gap: 4px;
}

.source-context-card span,
.draft-memory-card span,
.dialog-source-card span {
  color: #64748b;
  font-size: 12px;
}

.source-context-card strong,
.draft-memory-card strong,
.dialog-source-card strong {
  color: #172033;
}

.source-context-card small {
  color: #64748b;
}

.draft-memory-card {
  display: grid;
  gap: 5px;
  margin-bottom: 12px;
  padding: 12px 14px;
  background: linear-gradient(135deg, #102a43, #185e70);
}

.draft-memory-card strong {
  color: #ffffff;
}

.draft-memory-card p {
  margin: 0;
  color: rgba(255, 255, 255, 0.82);
  line-height: 1.6;
}

.composer {
  padding: 16px;
  border-top: 1px solid rgba(27, 42, 65, 0.08);
  background: rgba(255, 255, 255, 0.7);
}

.composer-disabled {
  opacity: 0.78;
}

.composer-toolbar {
  justify-content: space-between;
  margin-bottom: 10px;
}

.message-type-select {
  width: 170px;
}

.target-select {
  width: 100%;
}

.target-option {
  display: grid;
  gap: 2px;
  padding: 3px 0;
}

.target-option strong {
  color: #172033;
  font-size: 13px;
}

.target-option span,
.target-helper {
  color: #64748b;
  font-size: 12px;
}

.memory-source-option span {
  display: block;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-helper {
  margin: 8px 0 0;
  line-height: 1.5;
}

.hidden-file {
  display: none;
}

.pending-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.pending-files button {
  padding: 7px 10px;
  cursor: pointer;
}

.composer-row {
  align-items: stretch;
}

.composer-row .el-button {
  min-width: 108px;
}

.dialog-source-card {
  width: 100%;
  padding: 12px 14px;
}

@media (max-width: 900px) {
  .collab-page {
    grid-template-columns: 1fr;
    padding: 12px;
  }

  .thread-rail {
    min-height: 360px;
  }

  .message-stage {
    min-height: 620px;
  }
}
</style>
