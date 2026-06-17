<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, ChatDotRound, Check, Close, CopyDocument, Delete, EditPen, FolderOpened, FullScreen, Key, MagicStick, Minus, Paperclip, Plus, Promotion, RefreshRight, ScaleToOriginal, Share, User } from "@element-plus/icons-vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type StyleValue } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import ImagePreviewDialog from "@/components/common/ImagePreviewDialog.vue";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useMeetingStore } from "@/stores/meeting.store";
import { useUserStore } from "@/stores/user.store";
import type { MeetingAgentQueryAudit, MeetingAttachment, MeetingDataDomain, MeetingMemory, MeetingMemoryPublishScope, MeetingMessage, MeetingQuoteSnapshot, MeetingRoom, MeetingRoomMember } from "@/types/meeting.types";
import { normalizeAiResponseText } from "@/utils/ai-response";
import { writeTextToClipboard } from "@/utils/clipboard";

const auth = useAuthStore();
const store = useMeetingStore();
const userStore = useUserStore();
const MESSAGE_RECALL_WINDOW_MS = 2 * 60 * 1000;
const IMAGE_ATTACHMENT_EXT_PATTERN = /\.(?:apng|avif|bmp|gif|ico|jpe?g|png|svg|webp)(?:[?#].*)?$/i;

const roomTitle = ref("会议室");
const roomPassword = ref("");
const joinCode = ref("");
const joinPassword = ref("");
const hubMode = ref<"create" | "join">("create");
const input = ref("");
const agentInput = ref("");
const privateInput = ref("");
const actionTitle = ref("");
const actionDescription = ref("");
const actionOwnerId = ref("");
const quotedMessage = ref<MeetingMessage | null>(null);
const quoteSnapshot = ref<MeetingQuoteSnapshot | null>(null);
const agentEditingMessageId = ref("");
const agentEditingContent = ref("");
const privateEditingMessageId = ref("");
const privateEditingContent = ref("");
const nowTick = ref(Date.now());
const rightPanelTab = ref<"ai" | "private" | "context">("ai");
const activePrivateUserId = ref("");
const privateDialogVisible = ref(false);
const privateWindowMinimized = ref(false);
const privateWindowMaximized = ref(false);
const mentionMenuOpen = ref(false);
const mentionQuery = ref("");
const mentionRange = ref<{ start: number; end: number } | null>(null);
const activeMentionIndex = ref(0);
const agentAttachments = ref<MeetingAttachment[]>([]);
const privateAttachments = ref<MeetingAttachment[]>([]);
const previewImage = ref({ url: "", name: "" });
const imagePreviewVisible = ref(false);
const memoryPublishDialogVisible = ref(false);
const memoryPublishSubmitting = ref(false);
const selectedCandidateMemory = ref<MeetingMemory | null>(null);
const selectedAudit = ref<MeetingAgentQueryAudit | null>(null);
const auditDetailVisible = ref(false);
const selectedSharedMemory = ref<MeetingMemory | null>(null);
const memoryDetailVisible = ref(false);
const memoryPublishForm = reactive({
  title: "",
  content: "",
  scope: "meeting" as MeetingMemoryPublishScope,
  scope_id: "",
  publish_reason: "",
});
const messageListRef = ref<HTMLElement | null>(null);
const agentPanelListRef = ref<HTMLElement | null>(null);
const privatePanelListRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);
const agentInputRef = ref<HTMLTextAreaElement | null>(null);
const privateInputRef = ref<HTMLTextAreaElement | null>(null);
const attachmentInputRef = ref<HTMLInputElement | null>(null);
const agentAttachmentInputRef = ref<HTMLInputElement | null>(null);
const privateAttachmentInputRef = ref<HTMLInputElement | null>(null);
const leftPanelWidth = ref(260);
const rightPanelWidth = ref(360);
const leftPanelCollapsed = ref(false);
const rightPanelCollapsed = ref(false);
const resizingPanel = ref<"" | "left" | "right">("");
let stopResizeListeners: (() => void) | null = null;
let stopPrivateWindowListeners: (() => void) | null = null;
let privateRecallTimer: number | null = null;

type PrivateWindowResizeDirection = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const PANEL_WIDTHS = {
  left: { min: 220, max: 420 },
  right: { min: 320, max: 620 },
};
const PRIVATE_WINDOW_LIMITS = {
  minWidth: 520,
  minHeight: 360,
  defaultWidth: 920,
  defaultHeight: 620,
};

const privateWindowRect = reactive({
  x: 0,
  y: 0,
  width: PRIVATE_WINDOW_LIMITS.defaultWidth,
  height: PRIVATE_WINDOW_LIMITS.defaultHeight,
});

const privateWindowResizeHandles: Array<{ direction: PrivateWindowResizeDirection; className: string; ariaLabel: string }> = [
  { direction: "n", className: "private-window-resizer-n private-window-resizer-edge", ariaLabel: "从上方调整私聊窗口大小" },
  { direction: "s", className: "private-window-resizer-s private-window-resizer-edge", ariaLabel: "从下方调整私聊窗口大小" },
  { direction: "e", className: "private-window-resizer-e private-window-resizer-edge", ariaLabel: "从右侧调整私聊窗口大小" },
  { direction: "w", className: "private-window-resizer-w private-window-resizer-edge", ariaLabel: "从左侧调整私聊窗口大小" },
  { direction: "ne", className: "private-window-resizer-ne private-window-resizer-corner", ariaLabel: "从右上角调整私聊窗口大小" },
  { direction: "nw", className: "private-window-resizer-nw private-window-resizer-corner", ariaLabel: "从左上角调整私聊窗口大小" },
  { direction: "se", className: "private-window-resizer-se private-window-resizer-corner", ariaLabel: "从右下角调整私聊窗口大小" },
  { direction: "sw", className: "private-window-resizer-sw private-window-resizer-corner", ariaLabel: "从左下角调整私聊窗口大小" },
];

const collapsedContextSections = reactive<Record<string, boolean>>({
  boundary: false,
  candidateMemory: true,
  confirmedMemory: false,
  actions: true,
  audit: true,
  events: true,
});

const domainLabels: Record<string, string> = {
  quality: "质检业务",
  standard: "质检标准",
  meeting: "会议协作",
  memory: "记忆",
  platform_ops: "平台运营",
  model_billing: "模型计费",
  org_admin: "组织管理",
  data_access: "数据接入",
  security_audit: "安全审计",
  ai_conversation: "AI 会话",
};
const memoryCategoryLabels: Record<string, string> = {
  business_memory: "业务记忆",
  meeting_memory: "会议记忆",
  rejected_noise: "噪声",
};
const memoryTypeLabels: Record<string, string> = {
  decision: "会议结论",
  quality_fact: "质检事实",
  risk_insight: "风险洞察",
  quality_pattern: "问题模式",
  action_suggestion: "行动建议",
};
const memoryScopeLabels: Record<string, string> = {
  meeting: "本会议室",
  meeting_room: "本会议室",
  inspection_task: "质检任务",
  product: "产品",
  batch: "批次",
  standard: "标准/规则知识库",
  workspace: "质检风险库/问题模式库",
};
const bindingLabels: Record<string, string> = {
  inspection_task: "质检任务",
  product: "产品",
  batch: "批次",
  standard: "标准/规则",
};

const meetingLayoutStyle = computed<StyleValue>(() => ({
  "--left-panel-width": leftPanelCollapsed.value ? "52px" : `${leftPanelWidth.value}px`,
  "--right-panel-width": rightPanelCollapsed.value ? "52px" : `${rightPanelWidth.value}px`,
}));

const privateWindowStyle = computed<StyleValue>(() => {
  if (privateWindowMaximized.value) {
    return {
      left: "16px",
      top: "16px",
      width: "calc(100vw - 32px)",
      height: "calc(100vh - 32px)",
    };
  }
  if (privateWindowMinimized.value) {
    return {
      left: `${privateWindowRect.x}px`,
      top: `${privateWindowRect.y}px`,
      width: "260px",
      height: "48px",
    };
  }
  return {
    left: `${privateWindowRect.x}px`,
    top: `${privateWindowRect.y}px`,
    width: `${privateWindowRect.width}px`,
    height: `${privateWindowRect.height}px`,
  };
});

const mentionTargets = computed(() => {
  const entries = [
    { id: "general_agent", agent_name: "会议Agent", description: "总结、查询边界内数据、提取候选记忆" },
    ...store.agents
      .filter((agent) => agent.role === "participant")
      .map((agent) => ({
        id: agent.agent_id,
        agent_name: agent.agent_name,
        description: "会议参与 Agent",
      })),
  ];
  const seen = new Set<string>();
  return entries.filter((item) => {
    const key = item.agent_name.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
});
const filteredMentionTargets = computed(() => {
  const query = mentionQuery.value.trim().toLowerCase();
  if (!query) return mentionTargets.value;
  return mentionTargets.value.filter((item) => item.agent_name.toLowerCase().includes(query));
});
const activeMeetingLink = computed(() => {
  const code = store.activeRoom?.access_code;
  if (!code) return "";
  const url = new URL(window.location.href);
  url.searchParams.set("room", code);
  url.hash = "";
  return url.toString();
});
const hostMember = computed(() => {
  const creatorId = store.activeRoom?.created_by;
  return store.members.find((member) => member.role === "host")
    || store.members.find((member) => member.user_id === creatorId)
    || null;
});
const visibleMemberCount = computed(() => store.members.length || store.activeRoom?.member_count || 0);
const canManageRoom = computed(() => Boolean(store.activeRoom && store.activeRoom.created_by === auth.userId));
const canReviewMemory = computed(() => {
  if (!store.activeRoom) return false;
  if (store.activeRoom.created_by === auth.userId) return true;
  return store.members.some((member) => member.user_id === auth.userId && member.role === "host");
});
const roomTitleCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const room of store.rooms) {
    const title = room.title.trim() || "会议室";
    counts.set(title, (counts.get(title) || 0) + 1);
  }
  return counts;
});
const roomStatusLabel = computed(() => {
  const status = store.activeRoom?.status || "";
  if (status === "active") return "进行中";
  if (status === "closed") return "已关闭";
  if (status === "archived") return "已归档";
  return status || "未选择";
});
const contextAllowedDomains = computed(() => {
  const domains = store.contextPreview?.allowed_domains || store.activeRoom?.allowed_data_domains || [];
  return domains;
});
const contextDeniedDomains = computed(() => store.contextPreview?.denied_domains || []);
const businessBindingGroups = computed(() => {
  const context = currentBusinessContext.value;
  return [
    { key: "task", label: "质检任务", values: context?.task_ids || [] },
    { key: "product", label: "产品", values: context?.product_ids || [] },
    { key: "batch", label: "批次", values: context?.batch_nos || [] },
    { key: "standard", label: "标准", values: context?.standard_ids || [] },
  ].map((group) => ({
    ...group,
    values: group.values.map((value) => String(value || "").trim()).filter(Boolean),
  }));
});
const hasBusinessBindings = computed(() => businessBindingGroups.value.some((group) => group.values.length > 0));
const memoryGovernanceHint = computed(() => {
  const memory = selectedSharedMemory.value;
  if (!memory) return "暂无记录";
  const relatedAudits = store.agentQueryAudits.filter((audit) => auditUsesMemory(audit, memory.memory_id));
  return relatedAudits.length ? `${relatedAudits.length} 次 AI 使用记录引用过这条记忆` : "暂无被引用记录";
});
const currentUserId = computed(() => {
  const profileUserId = String(userStore.current?.id || "").trim();
  if (profileUserId) return profileUserId;
  const authUserId = String(auth.userId || "").trim();
  if (authUserId && store.members.some((member) => member.user_id === authUserId)) return authUserId;
  const currentMember = store.members.find((member) => member.username === auth.username);
  return currentMember?.user_id || "";
});
const privatePartners = computed(() => store.members.filter((member) => member.user_id !== currentUserId.value));
const currentPrivateMember = computed(() => store.members.find((member) => member.user_id === activePrivateUserId.value) || null);
const selectedPrivateMessages = computed(() => activePrivateUserId.value ? privateMessagesByUser(activePrivateUserId.value) : []);
const allPrivateMessages = computed(() => store.messages.filter((message) => Boolean(privatePartnerId(message))));
const privateConversationCount = computed(() => new Set(allPrivateMessages.value.map(privatePartnerId).filter(Boolean)).size);
const agentConversationGroups = computed(() => {
  const groups: Array<{ id: string; question: MeetingMessage | null; replies: MeetingMessage[] }> = [];
  let currentGroup: { id: string; question: MeetingMessage | null; replies: MeetingMessage[] } | null = null;
  for (const message of store.agentPanelMessages) {
    if (message.message_type === "user") {
      currentGroup = { id: message.id, question: message, replies: [] };
      groups.push(currentGroup);
      continue;
    }
    if (!currentGroup) {
      currentGroup = { id: `agent-${message.id}`, question: null, replies: [] };
      groups.push(currentGroup);
    }
    currentGroup.replies.push(message);
  }
  return groups;
});
const agentQuestionCount = computed(() => agentConversationGroups.value.length);
const currentBusinessContext = computed(() => store.contextPreview?.business_context || store.activeRoom?.business_context || null);
const memoryPublishPreview = computed<MeetingMemory | null>(() => buildMemoryPublishPreview(selectedCandidateMemory.value));
const memoryPublishScopeOptions = computed(() => buildMemoryPublishScopeOptions(memoryPublishPreview.value));

function canDeleteRoom(room: MeetingRoom) {
  return room.created_by === auth.userId;
}

function canLeaveRoom(room: MeetingRoom) {
  return room.created_by !== currentUserId.value;
}

function domainLabel(value: string) {
  return domainLabels[value] || value;
}

function visibleDomainLabels(domains?: string[] | null, fallback = "") {
  const labels = (domains || [])
    .map(domainLabel);
  return labels.join("、") || fallback;
}

function roomDomainPreview(room: MeetingRoom) {
  const domains = room.allowed_data_domains || [];
  if (!domains.length) return "会议协作";
  return domains.slice(0, 2).map(domainLabel).join("、") + (domains.length > 2 ? ` +${domains.length - 2}` : "");
}

function auditDecisionLabel(value: string) {
  if (value === "allowed") return "允许";
  if (value === "partial") return "部分";
  if (value === "denied") return "拒绝";
  return value || "未知";
}

function auditDecisionClass(value: string) {
  if (value === "allowed") return "audit-allowed";
  if (value === "partial") return "audit-partial";
  if (value === "denied") return "audit-denied";
  return "";
}

function hasMeetingAgentMention(content: string) {
  const compact = content.replace(/\s+/g, "").toLowerCase();
  return compact.includes("@会议agent") || compact.includes("@会议室agent") || compact.includes("@ai助手");
}

function stripMeetingAgentMention(content: string) {
  return content
    .replace(/@会议\s*Agent/gi, "")
    .replace(/@会议室\s*Agent/gi, "")
    .replace(/@AI\s*助手/gi, "")
    .trim();
}

function memberRoleLabel(role: string) {
  return role === "host" ? "主持人" : "成员";
}

function normalizedMemberRole(role: string): "host" | "member" {
  return role === "host" ? "host" : "member";
}

function memberInitial(name: string) {
  return (name || "?").trim().slice(0, 1).toUpperCase();
}

function parseApiTime(value?: string | null) {
  if (!value) return null;
  const raw = String(value).trim();
  const isoLike = raw.includes("T") ? raw : raw.replace(" ", "T");
  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(isoLike);
  const date = new Date(hasTimezone ? isoLike : `${isoLike}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = parseApiTime(value);
  if (!date) return value;
  return date.toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function roomDisplayTitle(room: { title: string; access_code: string }) {
  const title = room.title.trim() || "会议室";
  return (roomTitleCounts.value.get(title) || 0) > 1 ? `${title} · ${room.access_code}` : title;
}

function roomRecentLabel(room: { last_message_at?: string | null; updated_at?: string | null; created_at?: string | null }) {
  const value = room.last_message_at || room.updated_at || room.created_at;
  return formatTime(value);
}

function memoryConfidence(memory: MeetingMemory) {
  if (typeof memory.confidence !== "number") return "";
  return `${Math.round(memory.confidence * 100)}%`;
}

function memoryCategoryLabel(value?: string | null) {
  return memoryCategoryLabels[String(value || "meeting_memory")] || String(value || "会议记忆");
}

function memoryTypeLabel(value?: string | null) {
  return memoryTypeLabels[String(value || "decision")] || String(value || "记忆");
}

function memoryScopeLabel(value?: string | null) {
  return memoryScopeLabels[String(value || "meeting")] || String(value || "本会议室");
}

function inferMemoryType(title: string, content: string): MeetingMemory["memory_type"] {
  const text = `${title}\n${content}`.toLowerCase();
  if (["风险洞察", "预测", "预警", "未来", "risk forecast"].some((term) => text.includes(term))) return "risk_insight";
  if (["问题模式", "反复出现", "集中出现", "常见失败", "quality pattern"].some((term) => text.includes(term))) return "quality_pattern";
  if (["行动项", "待办", "责任人", "建议动作", "action"].some((term) => text.includes(term))) return "action_suggestion";
  if (["质检", "检测", "评分", "不合格", "合格", "耗时", "模型", "inspection", "quality"].some((term) => text.includes(term))) return "quality_fact";
  return "decision";
}

function inferMemoryCategory(memoryType: MeetingMemory["memory_type"], title: string, content: string): MeetingMemory["memory_category"] {
  const text = `${title}\n${content}`.toLowerCase();
  const context = currentBusinessContext.value;
  const hasBinding = Boolean(
    context?.task_ids?.length
      || context?.product_ids?.length
      || context?.batch_nos?.length
      || context?.standard_ids?.length,
  );
  if (memoryType === "quality_fact") return "business_memory";
  if (memoryType === "risk_insight" || memoryType === "quality_pattern") return hasBinding ? "business_memory" : "meeting_memory";
  const businessTerms = ["质检", "检测", "任务", "产品", "批次", "标准", "复核", "抽检", "缺陷", "风险", "判定", "审核", "inspection", "quality", "standard", "batch", "product"];
  if (hasBinding && businessTerms.some((term) => text.includes(term))) return "business_memory";
  return "meeting_memory";
}

function buildMemoryShareability(memoryCategory: MeetingMemory["memory_category"], memoryType: MeetingMemory["memory_type"]) {
  const context = currentBusinessContext.value;
  const allowedScopes = ["meeting"];
  const missingBindings: string[] = [];
  if (memoryCategory === "business_memory") {
    if (context?.task_ids?.length) allowedScopes.push("inspection_task");
    else if (memoryType === "quality_fact") missingBindings.push("inspection_task");
    if (context?.product_ids?.length) allowedScopes.push("product");
    else missingBindings.push("product");
    if (context?.batch_nos?.length) allowedScopes.push("batch");
    else missingBindings.push("batch");
    if (context?.standard_ids?.length) allowedScopes.push("standard");
    else missingBindings.push("standard");
    if (context?.task_ids?.length || context?.product_ids?.length || context?.batch_nos?.length) allowedScopes.push("workspace");
  }
  return {
    allowed_scopes: Array.from(new Set(allowedScopes)),
    missing_bindings: Array.from(new Set(missingBindings)).sort(),
    requires_host_confirmation: true,
    cross_room_allowed: allowedScopes.length > 1,
    organization_scope_enabled: false,
  };
}

function recommendedMemoryScope(memoryType: MeetingMemory["memory_type"], memoryCategory: MeetingMemory["memory_category"]) {
  const context = currentBusinessContext.value;
  if (memoryCategory !== "business_memory") return { scope: "meeting", scopeId: null };
  if (memoryType === "quality_pattern") return { scope: "workspace", scopeId: "quality_risk_library" };
  if (memoryType === "risk_insight") {
    if (context?.batch_nos?.[0]) return { scope: "batch", scopeId: context.batch_nos[0] };
    if (context?.product_ids?.[0]) return { scope: "product", scopeId: context.product_ids[0] };
    if (context?.task_ids?.[0]) return { scope: "inspection_task", scopeId: context.task_ids[0] };
    return { scope: "meeting", scopeId: null };
  }
  if (memoryType === "quality_fact" && context?.task_ids?.[0]) return { scope: "inspection_task", scopeId: context.task_ids[0] };
  if (context?.product_ids?.[0]) return { scope: "product", scopeId: context.product_ids[0] };
  return { scope: "meeting", scopeId: null };
}

function buildMemoryWarnings(memoryCategory: MeetingMemory["memory_category"], memoryType: MeetingMemory["memory_type"], baseWarnings: string[] = []) {
  const warnings = new Set(baseWarnings);
  const context = currentBusinessContext.value;
  const hasAnyBinding = Boolean(
    context?.task_ids?.length
      || context?.product_ids?.length
      || context?.batch_nos?.length
      || context?.standard_ids?.length,
  );
  if (memoryCategory === "meeting_memory") warnings.add("该记忆仅适合保存在本会议室，不允许跨业务范围共享。");
  if (memoryCategory === "business_memory" && !hasAnyBinding) {
    warnings.add("该记忆属于质检相关信息，但当前会议室没有绑定质检任务、产品、批次或标准，只能先保存到本会议室。");
  }
  if (memoryType === "quality_fact" && !context?.task_ids?.length) {
    warnings.add("单次质检事实默认发布到质检任务；当前缺少质检任务绑定，不能发布到产品、批次或预警中心。");
  }
  if (memoryType === "risk_insight") {
    warnings.add("风险洞察是预测候选，需人工确认后才可发布；没有绑定业务对象时不能进入预警中心。");
  }
  return Array.from(warnings);
}

function buildMemoryPublishPreview(memory?: MeetingMemory | null): MeetingMemory | null {
  if (!memory) return null;
  const title = memoryPublishForm.title.trim() || memory.title;
  const content = memoryPublishForm.content.trim() || memory.content;
  const memoryType = inferMemoryType(title, content);
  const memoryCategory = inferMemoryCategory(memoryType, title, content);
  const recommendation = recommendedMemoryScope(memoryType, memoryCategory);
  return {
    ...memory,
    title,
    content,
    memory_type: memoryType,
    memory_category: memoryCategory,
    recommended_scope: recommendation.scope,
    recommended_scope_id: recommendation.scopeId,
    shareability: buildMemoryShareability(memoryCategory, memoryType),
    warnings: buildMemoryWarnings(memoryCategory, memoryType, memory.warnings || []),
  };
}

function isUuidLike(value?: string | null) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value || "").trim());
}

function sourceMessageId(memory: MeetingMemory) {
  if (memory.source_message_id) return memory.source_message_id;
  const ref = (memory.source_refs || []).find((item) => String(item.type || "") === "meeting_message" && item.id);
  return ref ? String(ref.id) : "";
}

function sourceMessageLabel(memory: MeetingMemory) {
  const messageId = sourceMessageId(memory);
  if (!messageId) return "当前会议";
  const message = store.messages.find((item) => item.id === messageId);
  if (!message) return "当前会议中的一条来源消息";
  const summary = clipText(displayMessageContent(message) || "附件消息", 42);
  return `消息 #${message.seq_no} · ${message.username}：${summary}`;
}

function memberDisplayName(userId?: string | null) {
  const cleanId = String(userId || "").trim();
  if (!cleanId) return "暂无记录";
  if (cleanId === currentUserId.value) return "我";
  const member = store.members.find((item) => item.user_id === cleanId);
  if (member?.username) return member.username;
  if (cleanId === store.activeRoom?.created_by) return "会议创建者";
  return "未知成员";
}

function scopeObjectLabel(memory: MeetingMemory) {
  const scope = String(memory.scope || memory.scope_type || "meeting");
  const scopeId = String(memory.scope_id || "").trim();
  if (scope === "meeting" || scope === "meeting_room") {
    return store.activeRoom?.title ? `当前会议室：${store.activeRoom.title}` : "当前会议室";
  }
  if (scope === "inspection_task") {
    const task = currentBusinessContext.value?.tasks?.find((item) => item.id === scopeId);
    if (task?.spec_code) return `质检任务：${task.spec_code}`;
    return "当前绑定质检任务";
  }
  if (scope === "product") return scopeId && !isUuidLike(scopeId) ? `产品：${scopeId}` : "当前绑定产品";
  if (scope === "batch") return scopeId && !isUuidLike(scopeId) ? `批次：${scopeId}` : "当前绑定批次";
  if (scope === "standard") return scopeId && !isUuidLike(scopeId) ? `标准/规则：${scopeId}` : "当前绑定标准/规则知识库";
  if (scope === "workspace") return scopeId === "quality_risk_library" ? "质检风险库/问题模式库" : `工作区：${scopeId || "当前工作区"}`;
  return memoryScopeLabel(scope);
}

function scopeVisibilityNote(memory: MeetingMemory) {
  const scope = String(memory.scope || memory.scope_type || "meeting");
  if (scope === "inspection_task") return "绑定同一质检任务的上下文可检索";
  if (scope === "product") return "绑定同一产品的上下文可检索";
  if (scope === "batch") return "绑定同一批次的上下文可检索";
  if (scope === "standard") return "绑定同一标准/规则知识库的上下文可检索";
  if (scope === "workspace") return "具备质检风险库权限的人员可在风险库或告警中心查看";
  return "仅当前会议室可见";
}

function memoryTechnicalInfo(memory: MeetingMemory) {
  return stableJson({
    memory_id: memory.memory_id,
    source_message_id: sourceMessageId(memory) || null,
    version_parent_id: memory.version_parent_id || null,
    created_by: memory.created_by || null,
    confirmed_by: memory.confirmed_by || null,
    scope: memory.scope || memory.scope_type || null,
    scope_id: memory.scope_id || null,
    memory_type: memory.memory_type || null,
    affected_objects: memory.affected_objects || null,
    evidence_refs: memory.evidence_refs || [],
    risk_level: memory.risk_level || null,
    forecast_window: memory.forecast_window || null,
    source_refs: memory.source_refs || [],
  });
}

function memorySourceLabel(memory: MeetingMemory) {
  const refs = memory.source_refs || [];
  if (!refs.length && !memory.source_message_id) return "来源：当前会议";
  return `来源：${sourceMessageLabel(memory)}`;
}

function memorySourceSummary(memory: MeetingMemory) {
  if (memory.source_message_id || memory.source_refs?.length) return "查看来源";
  return "当前会议";
}

function memoryStatusLabel(status?: string | null) {
  if (status === "active") return "有效";
  if (status === "candidate") return "候选";
  if (status === "disputed") return "争议中";
  if (status === "superseded") return "已修订";
  if (status === "isolated") return "已隔离";
  if (status === "disabled" || status === "deleted") return "已停用";
  if (status === "rejected") return "已拒绝";
  return status || "未知";
}

function memoryCategoryHint(memory?: MeetingMemory | null) {
  const category = memory?.memory_category;
  if (memory?.memory_type === "risk_insight") return "风险洞察是预测候选，确认后可发布到产品、批次、质检风险库或预警中心。";
  if (memory?.memory_type === "quality_fact") return "单次质检事实优先绑定到质检任务；缺少任务绑定时只能先留在本会议室。";
  if (memory?.memory_type === "quality_pattern") return "可复用的问题模式可发布到质检风险库/问题模式库；普通知识库不作为默认记忆出口。";
  if (category === "business_memory") return "业务记忆发布到稳定对象后，后续绑定同一对象的会议室可检索。";
  if (category === "rejected_noise") return "噪声不允许发布为已确认记忆，只能丢弃或保留为普通会议消息。";
  return "会议记忆仅保存在本会议室，不会跨会议室共享。";
}

function missingBindingLabels(memory?: MeetingMemory | null) {
  return (memory?.shareability?.missing_bindings || [])
    .map((item) => bindingLabels[String(item)] || String(item))
    .filter(Boolean);
}

function publishDecisionRows(memory?: MeetingMemory | null) {
  if (!memory) return [];
  const allowed = new Set((memory.shareability?.allowed_scopes || ["meeting"]).map(String));
  const rows: Array<{ label: string; value: string }> = [
    { label: "识别结果", value: `${memoryCategoryLabel(memory.memory_category)} · ${memoryTypeLabel(memory.memory_type)}` },
    { label: "推荐落点", value: memory.recommended_scope ? memoryScopeLabel(memory.recommended_scope) : "本会议室" },
  ];
  const missing = missingBindingLabels(memory);
  if (missing.length) {
    rows.push({ label: "缺少绑定", value: missing.join("、") });
  }
  if (memory.memory_type === "quality_fact") {
    rows.push({
      label: "发布判断",
      value: allowed.has("inspection_task")
        ? "这是单次质检事实，可发布到绑定的质检任务。"
        : "这是质检事实，但缺少质检任务绑定，暂不能发到产品、批次或预警中心。",
    });
  } else if (memory.memory_type === "risk_insight") {
    rows.push({
      label: "发布判断",
      value: allowed.has("workspace")
        ? "有业务对象绑定，可发布到产品、批次、质检风险库，并同步形成预警记录。"
        : "缺少产品、批次或任务绑定，只能留在本会议室。",
    });
  } else if (memory.memory_type === "quality_pattern") {
    rows.push({
      label: "发布判断",
      value: allowed.has("workspace")
        ? "可作为跨对象复用的问题模式进入质检风险库/问题模式库。"
        : "缺少业务对象绑定，暂不能进入质检风险库。",
    });
  } else if (allowed.size <= 1) {
    rows.push({ label: "发布判断", value: "不涉及稳定业务对象，只保存为本会议室结论。" });
  }
  rows.push({
    label: "知识库规则",
    value: "标准/规则知识库只收判定口径、阈值和标准沉淀；质检风险库只收风险洞察和问题模式；普通 RAG 知识库不是会议记忆的默认发布对象。",
  });
  return rows;
}

function riskLevelLabel(value?: string | null) {
  if (value === "critical") return "严重";
  if (value === "high") return "高";
  if (value === "medium") return "中";
  if (value === "low") return "低";
  return value || "待评估";
}

function forecastWindowLabel(memory: MeetingMemory) {
  const value = memory.forecast_window;
  if (!value || typeof value !== "object") return "";
  const label = value.label;
  if (typeof label === "string" && label.trim()) return label.trim();
  return "";
}

function memoryPreview(memory: MeetingMemory, maxLength = 120) {
  return clipText(memory.summary || memory.content || "", maxLength);
}

function stableJson(value: unknown) {
  if (value === null || value === undefined) return "暂无记录";
  if (Array.isArray(value) && value.length === 0) return "暂无记录";
  if (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0) return "暂无记录";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function extractRefId(ref: Record<string, unknown>) {
  return String(ref.memory_id || ref.id || ref.source_id || ref.item_id || ref.ref_id || "").trim();
}

function auditUsesMemory(audit: MeetingAgentQueryAudit, memoryId: string) {
  const target = String(memoryId || "").trim();
  if (!target) return false;
  const refs = [...(audit.memory_reads || []), ...(audit.source_refs || [])];
  return refs.some((ref) => extractRefId(ref) === target);
}

function auditMemoryCount(audit: MeetingAgentQueryAudit) {
  return (audit.memory_reads || []).length;
}

function openAuditDetail(audit: MeetingAgentQueryAudit) {
  selectedAudit.value = audit;
  auditDetailVisible.value = true;
}

function openMemoryDetail(memory: MeetingMemory) {
  selectedSharedMemory.value = memory;
  memoryDetailVisible.value = true;
}

function findVisibleMemoryFromRef(ref: Record<string, unknown>) {
  const id = extractRefId(ref);
  if (!id) return null;
  return store.confirmedMemories.find((memory) => memory.memory_id === id) || null;
}

function openAuditMemory(ref: Record<string, unknown>) {
  const memory = findVisibleMemoryFromRef(ref);
  if (!memory) {
    ElMessage.info("该记忆不在当前可见范围。");
    return;
  }
  openMemoryDetail(memory);
}

function reuseAuditQuestion() {
  if (!selectedAudit.value) return;
  agentInput.value = selectedAudit.value.question;
  rightPanelTab.value = "ai";
  auditDetailVisible.value = false;
  nextTick(() => agentInputRef.value?.focus());
}

async function copyAuditDetail() {
  const audit = selectedAudit.value;
  if (!audit) return;
  await copyToClipboard([
    `问题：${audit.question}`,
    `时间：${formatTime(audit.created_at) || "未知"}`,
    `决策：${auditDecisionLabel(audit.decision)}`,
    `允许域：${visibleDomainLabels(audit.allowed_domains, "无")}`,
    `拒绝域：${visibleDomainLabels(audit.denied_domains, "无")}`,
    `读取记忆：${auditMemoryCount(audit)} 条`,
  ].join("\n"), "审计信息已复制");
}

async function questionAuditAnswer() {
  const audit = selectedAudit.value;
  if (!audit) return;
  try {
    const { value } = await ElMessageBox.prompt("说明这次 AI 回答哪里需要质疑", "质疑这次回答", {
      inputType: "textarea",
      inputPlaceholder: "例如：回答引用了有争议记忆，或没有说明不可访问的数据边界",
      inputPattern: /^.{1,1000}$/,
      inputErrorMessage: "请输入 1 到 1000 个字符",
      confirmButtonText: "生成会议草稿",
      cancelButtonText: "取消",
    });
    input.value = [
      "【AI 使用记录质疑】",
      `问题：${audit.question}`,
      `时间：${formatTime(audit.created_at) || "未知"}`,
      `质疑原因：${String(value || "").trim()}`,
      "请主持人复核本次回答使用的数据边界、记忆来源和结论是否可靠。",
    ].join("\n");
    auditDetailVisible.value = false;
    await nextTick();
    inputRef.value?.focus();
    ElMessage.success("已生成会议消息草稿，请确认后发送。");
  } catch {
    // cancelled
  }
}

function isBusinessMemory(memory?: MeetingMemory | null) {
  return memory?.memory_category === "business_memory";
}

function buildMemoryPublishScopeOptions(memory?: MeetingMemory | null) {
  const options: Array<{ label: string; value: MeetingMemoryPublishScope; scopeId: string; disabled?: boolean; note: string }> = [
    { label: "本会议室", value: "meeting", scopeId: "", note: "只在当前会议室可见" },
  ];
  if (!memory || !isBusinessMemory(memory)) return options;
  const allowed = new Set((memory.shareability?.allowed_scopes || ["meeting"]).map(String));
  const context = currentBusinessContext.value;
  const addScope = (value: MeetingMemoryPublishScope, ids?: string[] | null, notePrefix = "") => {
    if (!allowed.has(value)) return;
    for (const id of ids || []) {
      const cleanId = String(id || "").trim();
      if (!cleanId) continue;
      options.push({
        label: `${memoryScopeLabel(value)}：${cleanId}`,
        value,
        scopeId: cleanId,
        note: `${notePrefix || memoryScopeLabel(value)}绑定上下文可检索，不按相关会议室推送`,
      });
    }
  };
  addScope("inspection_task", context?.task_ids, "同任务");
  addScope("product", context?.product_ids, "同产品");
  addScope("batch", context?.batch_nos, "同批次");
  addScope("standard", context?.standard_ids, "同标准/规则");
  if (allowed.has("workspace") && (memory.memory_type === "risk_insight" || memory.memory_type === "quality_pattern")) {
    options.push({
      label: "质检风险库/问题模式库",
      value: "workspace",
      scopeId: "quality_risk_library",
      note: "进入质检风险库/问题模式库；风险洞察确认发布后会同步形成预警中心记录",
    });
  }
  return options;
}

function selectedMemoryPublishOptionValue() {
  const scopeId = memoryPublishForm.scope === "meeting" ? "" : memoryPublishForm.scope_id;
  return `${memoryPublishForm.scope}:${scopeId}`;
}

function applyMemoryPublishOption(value: string) {
  const [scope, ...scopeIdParts] = value.split(":");
  memoryPublishForm.scope = (scope || "meeting") as MeetingMemoryPublishScope;
  memoryPublishForm.scope_id = scope === "meeting" ? "" : scopeIdParts.join(":");
}

function syncMemoryPublishSelectionWithPreview() {
  const preview = memoryPublishPreview.value;
  if (!preview) return;
  const options = buildMemoryPublishScopeOptions(preview);
  const current = selectedMemoryPublishOptionValue();
  if (options.some((item) => `${item.value}:${item.scopeId}` === current)) return;
  const recommended = options.find((item) => (
    item.value === preview.recommended_scope
    && (item.value === "meeting" || item.scopeId === String(preview.recommended_scope_id || ""))
  ));
  const selected = recommended || options[0];
  memoryPublishForm.scope = selected.value;
  memoryPublishForm.scope_id = selected.scopeId;
}

function resetMemoryPublishForm(memory: MeetingMemory) {
  selectedCandidateMemory.value = memory;
  memoryPublishForm.title = memory.title;
  memoryPublishForm.content = memory.content;
  const preview = buildMemoryPublishPreview(memory) || memory;
  const options = buildMemoryPublishScopeOptions(preview);
  const recommended = options.find((item) => (
    item.value === preview.recommended_scope
    && (item.value === "meeting" || item.scopeId === String(preview.recommended_scope_id || ""))
  ));
  const selected = recommended || options[0];
  memoryPublishForm.scope = selected.value;
  memoryPublishForm.scope_id = selected.scopeId;
  memoryPublishForm.publish_reason = "";
}

function quotedMessageTitle(messageId?: string | null) {
  if (!messageId) return "";
  const message = store.messages.find((item) => item.id === messageId);
  if (!message) return "引用的会议消息已不可见。";
  return `${message.username}: ${displayMessageContent(message).slice(0, 80)}`;
}

function clipText(value: string, maxLength: number) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
}

function displayMessageContent(message: MeetingMessage): string {
  if (messageMetadata(message).recalled_at) return "已撤回";
  if (message.message_type === "agent_streaming") return "会议Agent正在整理回复...";
  return message.message_type === "agent" ? normalizeAiResponseText(message.content).content : message.content;
}

function messageMetadata(message: MeetingMessage) {
  return message.metadata_json || {};
}

function messageQuoteSnapshot(message: MeetingMessage): MeetingQuoteSnapshot | null {
  const value = messageMetadata(message).quote_snapshot;
  if (!value || typeof value !== "object") return null;
  const snapshot = value as Partial<MeetingQuoteSnapshot>;
  const content = typeof snapshot.content === "string" ? snapshot.content.trim() : "";
  if (!content) return null;
  return {
    source: typeof snapshot.source === "string" ? snapshot.source : "agent",
    author: typeof snapshot.author === "string" && snapshot.author.trim() ? snapshot.author.trim() : "会议Agent",
    content,
    created_at: typeof snapshot.created_at === "string" ? snapshot.created_at : null,
  };
}

function quoteSnapshotTitle(snapshot?: MeetingQuoteSnapshot | null) {
  return snapshot ? `${snapshot.author}: ${clipText(snapshot.content, 120)}` : "";
}

function messageAttachments(message: MeetingMessage): MeetingAttachment[] {
  const attachments = messageMetadata(message).attachment_echo;
  return Array.isArray(attachments) ? attachments as MeetingAttachment[] : [];
}

function isImageAttachment(attachment: MeetingAttachment) {
  const kind = String(attachment.kind || "").toLowerCase();
  const contentType = String(attachment.content_type || "").toLowerCase();
  const name = String(attachment.name || "");
  const url = String(attachment.url || "");
  return kind === "image" || contentType.startsWith("image/") || IMAGE_ATTACHMENT_EXT_PATTERN.test(name) || IMAGE_ATTACHMENT_EXT_PATTERN.test(url);
}

function openImagePreview(attachment: MeetingAttachment) {
  previewImage.value = { url: attachment.url, name: attachment.name };
  imagePreviewVisible.value = true;
}

function copyMessageContent(message: MeetingMessage) {
  const attachments = messageAttachments(message).map((item) => item.url).filter(Boolean);
  return [displayMessageContent(message), ...attachments].filter(Boolean).join("\n");
}

function privateRecipientUserId(message: MeetingMessage) {
  const directValue = message.private_recipient_user_id;
  if (typeof directValue === "string" && directValue.trim()) return directValue.trim();
  const metadataValue = messageMetadata(message).private_recipient_user_id;
  return typeof metadataValue === "string" && metadataValue.trim() ? metadataValue.trim() : "";
}

function privatePartnerId(message: MeetingMessage) {
  if (message.message_type !== "user") return "";
  const recipientId = privateRecipientUserId(message);
  if (!recipientId) return "";
  const selfId = currentUserId.value;
  if (!selfId) return "";
  if (recipientId === selfId && message.user_id === selfId) return "";
  if (message.user_id === selfId) return recipientId;
  if (recipientId === selfId) return message.user_id;
  return "";
}

function privateMessagesByUser(userId: string) {
  return store.messages.filter((message) => privatePartnerId(message) === userId);
}

function canMutateMessage(message: MeetingMessage) {
  if (message.user_id !== currentUserId.value || message.message_type !== "user") return false;
  if (messageMetadata(message).recalled_at) return false;
  return true;
}

function canRecallMessage(message: MeetingMessage) {
  if (!canMutateMessage(message)) return false;
  nowTick.value;
  const createdAt = parseApiTime(message.created_at)?.getTime();
  if (!Number.isFinite(createdAt)) return false;
  return Date.now() - createdAt <= MESSAGE_RECALL_WINDOW_MS;
}

function canReEditMessage(message: MeetingMessage) {
  if (message.user_id !== currentUserId.value || message.message_type !== "user") return false;
  return Boolean(messageMetadata(message).recalled_at && messageMetadata(message).original_content);
}

function isContextExpanded(key: string) {
  return !collapsedContextSections[key];
}

function toggleContextSection(key: string) {
  collapsedContextSections[key] = !collapsedContextSections[key];
}

function clampPanelWidth(panel: "left" | "right", value: number) {
  const limits = PANEL_WIDTHS[panel];
  return Math.min(limits.max, Math.max(limits.min, Math.round(value)));
}

function stopPanelResize() {
  if (stopResizeListeners) {
    stopResizeListeners();
    stopResizeListeners = null;
  }
  resizingPanel.value = "";
}

function viewportSize() {
  return {
    width: Math.max(window.innerWidth || 0, 360),
    height: Math.max(window.innerHeight || 0, 360),
  };
}

function clampPrivateWindowRect() {
  const viewport = viewportSize();
  const minWidth = Math.min(PRIVATE_WINDOW_LIMITS.minWidth, viewport.width - 24);
  const minHeight = Math.min(PRIVATE_WINDOW_LIMITS.minHeight, viewport.height - 24);
  const maxWidth = Math.max(minWidth, viewport.width - 32);
  const maxHeight = Math.max(minHeight, viewport.height - 32);
  const visibleWidth = privateWindowMinimized.value ? 260 : privateWindowRect.width;
  const visibleHeight = privateWindowMinimized.value ? 48 : privateWindowRect.height;
  privateWindowRect.width = Math.min(maxWidth, Math.max(minWidth, privateWindowRect.width));
  privateWindowRect.height = Math.min(maxHeight, Math.max(minHeight, privateWindowRect.height));
  privateWindowRect.x = Math.min(viewport.width - visibleWidth - 12, Math.max(12, privateWindowRect.x));
  privateWindowRect.y = Math.min(viewport.height - visibleHeight - 12, Math.max(12, privateWindowRect.y));
}

function resetPrivateWindowPlacement() {
  const viewport = viewportSize();
  const minWidth = Math.min(PRIVATE_WINDOW_LIMITS.minWidth, viewport.width - 24);
  const minHeight = Math.min(PRIVATE_WINDOW_LIMITS.minHeight, viewport.height - 24);
  privateWindowRect.width = Math.min(PRIVATE_WINDOW_LIMITS.defaultWidth, Math.max(minWidth, viewport.width - 48));
  privateWindowRect.height = Math.min(PRIVATE_WINDOW_LIMITS.defaultHeight, Math.max(minHeight, viewport.height - 64));
  privateWindowRect.x = Math.max(16, Math.min(viewport.width - privateWindowRect.width - 24, Math.round(viewport.width - privateWindowRect.width - 36)));
  privateWindowRect.y = Math.max(16, Math.min(viewport.height - privateWindowRect.height - 24, 72));
}

function stopPrivateWindowInteraction() {
  if (stopPrivateWindowListeners) {
    stopPrivateWindowListeners();
    stopPrivateWindowListeners = null;
  }
}

function startPrivateWindowDrag(event: PointerEvent) {
  if (event.button !== 0 || privateWindowMaximized.value) return;
  event.preventDefault();
  stopPrivateWindowInteraction();
  const startX = event.clientX;
  const startY = event.clientY;
  const startLeft = privateWindowRect.x;
  const startTop = privateWindowRect.y;
  const previousUserSelect = document.body.style.userSelect;
  document.body.style.userSelect = "none";

  const onPointerMove = (moveEvent: PointerEvent) => {
    privateWindowRect.x = startLeft + moveEvent.clientX - startX;
    privateWindowRect.y = startTop + moveEvent.clientY - startY;
    clampPrivateWindowRect();
  };
  const onPointerUp = () => {
    document.body.style.userSelect = previousUserSelect;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    stopPrivateWindowListeners = null;
  };

  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  stopPrivateWindowListeners = onPointerUp;
}

function privateWindowResizeCursor(direction: PrivateWindowResizeDirection) {
  if (direction === "n" || direction === "s") return "ns-resize";
  if (direction === "e" || direction === "w") return "ew-resize";
  if (direction === "ne" || direction === "sw") return "nesw-resize";
  return "nwse-resize";
}

function startPrivateWindowResize(direction: PrivateWindowResizeDirection, event: PointerEvent) {
  if (event.button !== 0 || privateWindowMaximized.value || privateWindowMinimized.value) return;
  event.preventDefault();
  stopPrivateWindowInteraction();
  const startX = event.clientX;
  const startY = event.clientY;
  const startLeft = privateWindowRect.x;
  const startTop = privateWindowRect.y;
  const startWidth = privateWindowRect.width;
  const startHeight = privateWindowRect.height;
  const previousCursor = document.body.style.cursor;
  const previousUserSelect = document.body.style.userSelect;
  const resizeFromLeft = direction.includes("w");
  const resizeFromRight = direction.includes("e");
  const resizeFromTop = direction.includes("n");
  const resizeFromBottom = direction.includes("s");
  const cursor = privateWindowResizeCursor(direction);
  document.body.style.cursor = cursor;
  document.body.style.userSelect = "none";

  const onPointerMove = (moveEvent: PointerEvent) => {
    const deltaX = moveEvent.clientX - startX;
    const deltaY = moveEvent.clientY - startY;
    const viewport = viewportSize();
    const minWidth = Math.min(PRIVATE_WINDOW_LIMITS.minWidth, viewport.width - 24);
    const minHeight = Math.min(PRIVATE_WINDOW_LIMITS.minHeight, viewport.height - 24);
    const maxWidth = Math.max(minWidth, viewport.width - 32);
    const maxHeight = Math.max(minHeight, viewport.height - 32);

    if (resizeFromLeft) {
      const nextWidth = Math.min(maxWidth, Math.max(minWidth, startWidth - deltaX));
      privateWindowRect.width = nextWidth;
      privateWindowRect.x = startLeft + startWidth - nextWidth;
    } else if (resizeFromRight) {
      privateWindowRect.width = Math.min(maxWidth, Math.max(minWidth, startWidth + deltaX));
    }

    if (resizeFromTop) {
      const nextHeight = Math.min(maxHeight, Math.max(minHeight, startHeight - deltaY));
      privateWindowRect.height = nextHeight;
      privateWindowRect.y = startTop + startHeight - nextHeight;
    } else if (resizeFromBottom) {
      privateWindowRect.height = Math.min(maxHeight, Math.max(minHeight, startHeight + deltaY));
    }

    clampPrivateWindowRect();
  };
  const onPointerUp = () => {
    document.body.style.cursor = previousCursor;
    document.body.style.userSelect = previousUserSelect;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    stopPrivateWindowListeners = null;
  };

  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  stopPrivateWindowListeners = onPointerUp;
}

function minimizePrivateWindow() {
  privateWindowMaximized.value = false;
  privateWindowMinimized.value = true;
  const viewport = viewportSize();
  privateWindowRect.x = Math.min(viewport.width - 272, Math.max(12, privateWindowRect.x));
  privateWindowRect.y = Math.min(viewport.height - 60, Math.max(12, privateWindowRect.y));
  clampPrivateWindowRect();
}

function togglePrivateWindowMaximized() {
  privateWindowMinimized.value = false;
  privateWindowMaximized.value = !privateWindowMaximized.value;
  if (!privateWindowMaximized.value) clampPrivateWindowRect();
  nextTick(() => scrollToBottom("private"));
}

function restorePrivateWindow() {
  privateWindowMinimized.value = false;
  privateWindowMaximized.value = false;
  clampPrivateWindowRect();
  nextTick(() => {
    scrollToBottom("private");
    privateInputRef.value?.focus();
  });
}

function closePrivateWindow() {
  privateDialogVisible.value = false;
  privateWindowMinimized.value = false;
  privateWindowMaximized.value = false;
  stopPrivateWindowInteraction();
}

function startPanelResize(panel: "left" | "right", event: PointerEvent) {
  if (event.button !== 0) return;
  event.preventDefault();
  stopPanelResize();

  const startX = event.clientX;
  const startWidth = panel === "left" ? leftPanelWidth.value : rightPanelWidth.value;
  const previousCursor = document.body.style.cursor;
  const previousUserSelect = document.body.style.userSelect;
  resizingPanel.value = panel;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";

  const onPointerMove = (moveEvent: PointerEvent) => {
    const delta = panel === "left" ? moveEvent.clientX - startX : startX - moveEvent.clientX;
    const nextWidth = clampPanelWidth(panel, startWidth + delta);
    if (panel === "left") {
      leftPanelWidth.value = nextWidth;
    } else {
      rightPanelWidth.value = nextWidth;
    }
  };
  const onPointerUp = () => {
    document.body.style.cursor = previousCursor;
    document.body.style.userSelect = previousUserSelect;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    stopResizeListeners = null;
    resizingPanel.value = "";
  };

  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  stopResizeListeners = onPointerUp;
}

async function copyToClipboard(text: string, successText = "已复制") {
  try {
    const copied = await writeTextToClipboard(text);
    if (!copied) throw new Error("clipboard unavailable");
    ElMessage.success(successText);
  } catch {
    ElMessage.error("复制失败，请手动复制。");
  }
}

function buildAgentShareContent(message: MeetingMessage) {
  const body = message.message_type === "user"
    ? stripMeetingAgentMention(displayMessageContent(message))
    : displayMessageContent(message);
  return body.trim();
}

function canQuoteMessage(message: MeetingMessage) {
  return Boolean(displayMessageContent(message).trim());
}

function canQuoteAgentMessageToMain(message: MeetingMessage) {
  return message.message_type !== "agent_streaming" && Boolean(buildAgentShareContent(message));
}

async function quoteAgentMessageToMain(message: MeetingMessage) {
  if (!canQuoteAgentMessageToMain(message)) return;
  const content = buildAgentShareContent(message);
  quoteSnapshot.value = {
    source: "agent",
    author: message.message_type === "user" ? (message.username || "我") : "会议Agent",
    content: content || "附件",
    created_at: message.created_at || null,
  };
  quotedMessage.value = null;
  input.value = "";
  store.clearPendingAttachments();
  store.pendingAttachments.push(...messageAttachments(message));
  await nextTick();
  inputRef.value?.focus();
  ElMessage.success("已引用到主会场输入框，确认后发送");
}

async function askAgentAboutMessage(message: MeetingMessage) {
  const content = displayMessageContent(message).trim();
  const author = message.username || "成员";
  const time = formatTime(message.created_at);
  agentInput.value = [
    `请结合会议上下文分析这条主会场消息：`,
    "",
    `「${content || "附件"}」`,
    "",
    `发送者：${author}${time ? `，时间：${time}` : ""}`,
  ].join("\n");
  agentAttachments.value = messageAttachments(message);
  rightPanelTab.value = "ai";
  await nextTick();
  agentInputRef.value?.focus();
}

async function reEditRecalledPublicMessage(message: MeetingMessage) {
  if (!canReEditMessage(message)) return;
  const original = String(messageMetadata(message).original_content || "").trim();
  if (!original) return;
  input.value = original;
  store.clearPendingAttachments();
  store.pendingAttachments.push(...messageAttachments(message));
  quotedMessage.value = null;
  quoteSnapshot.value = null;
  await nextTick();
  inputRef.value?.focus();
}

async function reEditRecalledPrivateMessage(message: MeetingMessage) {
  if (!canReEditMessage(message)) return;
  const original = String(messageMetadata(message).original_content || "").trim();
  if (!original) return;
  privateInput.value = original;
  privateAttachments.value = messageAttachments(message);
  privateEditingMessageId.value = "";
  privateEditingContent.value = "";
  const partnerId = privatePartnerId(message);
  if (partnerId) activePrivateUserId.value = partnerId;
  privateDialogVisible.value = true;
  privateWindowMinimized.value = false;
  rightPanelTab.value = "private";
  await nextTick();
  privateInputRef.value?.focus();
}

function buildInviteText() {
  if (!store.activeRoom) return "";
  return [
    `请加入会议：${store.activeRoom.title}`,
    `会议码：${store.activeRoom.access_code}`,
    `加入链接：${activeMeetingLink.value}`,
    "如果会议设置了密码，请向邀请人获取。",
  ].join("\n");
}

function copyInvite() {
  const text = buildInviteText();
  if (!text) return;
  copyToClipboard(text, "邀请信息已复制");
}

async function scrollToBottom(target: "main" | "agent" | "private" = "main") {
  await nextTick();
  const el = target === "main" ? messageListRef.value : target === "agent" ? agentPanelListRef.value : privatePanelListRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

// Feedback

async function submitMeetingFeedback(message: MeetingMessage, feedbackType: "up" | "down") {
  const previous = store.messageReactions[message.id];
  store.setReaction(message.id, feedbackType);
  try {
    await feedbackApi.submitMessage("meeting", message.id, {
      feedback_type: feedbackType,
      rating: feedbackType === "up" ? 5 : 1,
      category: (feedbackType === "up" ? "meeting_helpful" : "meeting_not_helpful") as any,
      comment: `meeting_room:${message.room_id}`,
    });
    ElMessage.success(feedbackType === "up" ? "已标记为有帮助" : "已标记为无帮助");
  } catch (error) {
    store.setReaction(message.id, previous || "");
    ElMessage.error("反馈提交失败，请稍后重试。");
    console.error(error);
  }
}

// Input

function updateMentionMenu() {
  const el = inputRef.value;
  if (!el) {
    mentionMenuOpen.value = false;
    mentionRange.value = null;
    mentionQuery.value = "";
    return;
  }
  const cursor = el.selectionStart ?? input.value.length;
  const beforeCursor = input.value.slice(0, cursor);
  const match = beforeCursor.match(/(^|\s)@([^\s@]*)$/);
  if (!match) {
    mentionMenuOpen.value = false;
    mentionRange.value = null;
    mentionQuery.value = "";
    return;
  }
  const atIndex = beforeCursor.lastIndexOf("@");
  mentionRange.value = { start: atIndex, end: cursor };
  mentionQuery.value = match[2] || "";
  mentionMenuOpen.value = true;
  activeMentionIndex.value = Math.min(activeMentionIndex.value, Math.max(filteredMentionTargets.value.length - 1, 0));
}

function closeMentionMenu() {
  mentionMenuOpen.value = false;
  mentionRange.value = null;
  mentionQuery.value = "";
  activeMentionIndex.value = 0;
}

function onInputChanged() {
  updateMentionMenu();
}

function onInputClicked() {
  updateMentionMenu();
}

async function selectMentionTarget(index = activeMentionIndex.value) {
  const target = filteredMentionTargets.value[index];
  if (!target) return;
  const mention = `@${target.agent_name} `;
  const range = mentionRange.value;
  const el = inputRef.value;
  const start = range?.start ?? input.value.length;
  const end = range?.end ?? start;
  input.value = `${input.value.slice(0, start)}${mention}${input.value.slice(end)}`;
  closeMentionMenu();
  await nextTick();
  el?.focus();
  const cursor = start + mention.length;
  el?.setSelectionRange(cursor, cursor);
}

function onInputKeydown(event: KeyboardEvent) {
  if (mentionMenuOpen.value) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeMentionIndex.value = (activeMentionIndex.value + 1) % Math.max(filteredMentionTargets.value.length, 1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      const total = Math.max(filteredMentionTargets.value.length, 1);
      activeMentionIndex.value = (activeMentionIndex.value - 1 + total) % total;
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      if (filteredMentionTargets.value.length) {
        event.preventDefault();
        selectMentionTarget();
        return;
      }
      closeMentionMenu();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeMentionMenu();
      return;
    }
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function onAgentInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendAgentQuestion();
  }
}

function onPrivateInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendPrivateMessage();
  }
}

function triggerAttachmentSelect(target: "main" | "agent" | "private") {
  if (target === "main") attachmentInputRef.value?.click();
  else if (target === "agent") agentAttachmentInputRef.value?.click();
  else privateAttachmentInputRef.value?.click();
}

async function uploadFiles(files: File[], target: "main" | "agent" | "private") {
  if (!files.length) return;
  try {
    if (target === "main") {
      await store.uploadPendingAttachments(files);
    } else {
      const items = await store.uploadAttachments(files);
      if (target === "agent") agentAttachments.value = [...agentAttachments.value, ...items];
      else privateAttachments.value = [...privateAttachments.value, ...items];
    }
  } catch (error) {
    ElMessage.error("附件上传失败，请稍后重试。");
    console.error(error);
  }
}

async function handleAttachmentSelected(event: Event, target: "main" | "agent" | "private") {
  const inputEl = event.target as HTMLInputElement;
  await uploadFiles(Array.from(inputEl.files || []), target);
  inputEl.value = "";
}

async function handleComposerPaste(event: ClipboardEvent, target: "main" | "agent" | "private") {
  const files = Array.from(event.clipboardData?.files || []).filter((file) => file.type.startsWith("image/"));
  if (!files.length) return;
  event.preventDefault();
  await uploadFiles(files, target);
}

function removeAttachment(id: string, target: "main" | "agent" | "private") {
  if (target === "main") store.removePendingAttachment(id);
  else if (target === "agent") agentAttachments.value = agentAttachments.value.filter((item) => item.id !== id);
  else privateAttachments.value = privateAttachments.value.filter((item) => item.id !== id);
}

// Actions

async function createRoom() {
  try {
    const room = await store.createRoom(roomTitle.value.trim() || "会议室", roomPassword.value.trim() || null);
    roomTitle.value = "会议室";
    roomPassword.value = "";
    ElMessage.success(`会议室已创建，会议码 ${room.access_code}`);
  } catch (error) {
    ElMessage.error("创建会议室失败，请稍后重试。");
    console.error(error);
  }
}

async function joinRoom() {
  if (!joinCode.value.trim()) return;
  try {
    await store.joinRoom(joinCode.value.trim(), joinPassword.value.trim() || null);
    joinCode.value = "";
    joinPassword.value = "";
    ElMessage.success("已加入会议室。");
  } catch (error) {
    ElMessage.error("加入失败，请检查会议码或密码。");
    console.error(error);
  }
}

async function sendMessage() {
  if (!store.canSend) return;
  const content = input.value.trim();
  if (!content && !store.pendingAttachments.length && !quoteSnapshot.value) return;
  closeMentionMenu();
  if (hasMeetingAgentMention(content)) {
    agentInput.value = stripMeetingAgentMention(content);
    input.value = "";
    quoteSnapshot.value = null;
    rightPanelTab.value = "ai";
    await nextTick();
    agentInputRef.value?.focus();
    await sendAgentQuestion();
    return;
  }
  try {
    const message = await store.sendMessage(content, quotedMessage.value?.id || null, {
      attachments: [...store.pendingAttachments],
      quoteSnapshot: quoteSnapshot.value,
    });
    if (!message) return;
    input.value = "";
    quotedMessage.value = null;
    quoteSnapshot.value = null;
    await scrollToBottom();
  } catch (error) {
    ElMessage.error("消息发送失败，请稍后重试。");
    console.error(error);
  }
}

async function sendAgentQuestion() {
  if (!store.canSend || store.generalAgentRunning) return;
  const content = agentInput.value.trim();
  const attachments = [...agentAttachments.value];
  if (!content && !attachments.length) return;
  try {
    const question = content || "请查看附件。";
    await store.sendMessage(`@会议Agent ${question}`, null, {
      skipAgentTrigger: true,
      attachments,
    });
    agentInput.value = "";
    agentAttachments.value = [];
    await store.runGeneralAgent("auto", question, { attachments });
    await scrollToBottom("agent");
  } catch (error) {
    if (axios.isCancel(error) || (error as { name?: string })?.name === "CanceledError") return;
    ElMessage.error("会议Agent回应失败，请稍后重试。");
    console.error(error);
  }
}

async function stopGeneralAgent() {
  const restored = await store.cancelGeneralAgentRun();
  if (!restored) return;
  agentInput.value = restored.question || agentInput.value;
  agentAttachments.value = restored.attachments || [];
  await nextTick();
  agentInputRef.value?.focus();
  ElMessage.success("已停止回复，可继续修改问题。");
}

async function runGeneralAgent(query = "") {
  agentInput.value = query || agentInput.value;
  rightPanelTab.value = "ai";
  await sendAgentQuestion();
}

function canModifyAgentQuestion(message: MeetingMessage) {
  return message.user_id === currentUserId.value
    && message.message_type === "user"
    && !messageMetadata(message).recalled_at
    && !store.generalAgentRunning;
}

function startModifyAgentQuestion(message: MeetingMessage) {
  if (!canModifyAgentQuestion(message)) return;
  agentEditingMessageId.value = message.id;
  agentEditingContent.value = stripMeetingAgentMention(message.content || "");
}

function cancelModifyAgentQuestion() {
  agentEditingMessageId.value = "";
  agentEditingContent.value = "";
}

async function saveModifiedAgentQuestion(message: MeetingMessage) {
  if (!canModifyAgentQuestion(message)) return;
  const question = agentEditingContent.value.trim();
  if (!question) return;
  const attachments = messageAttachments(message);
  try {
    await store.updateMessage(message.id, `@会议Agent ${question}`);
    cancelModifyAgentQuestion();
    await store.runGeneralAgent("auto", question, { attachments });
    await scrollToBottom("agent");
  } catch (error) {
    ElMessage.error("修改后重新提问失败，请稍后重试。");
    console.error(error);
  }
}

function ensureActivePrivateMember() {
  const members = privatePartners.value;
  if (!members.length) {
    activePrivateUserId.value = "";
    return null;
  }
  const current = members.find((member) => member.user_id === activePrivateUserId.value);
  if (current) return current;
  activePrivateUserId.value = members[0].user_id;
  return members[0];
}

function openPrivateDialog(member?: MeetingRoomMember) {
  if (member) {
    activePrivateUserId.value = member.user_id;
  } else {
    ensureActivePrivateMember();
  }
  rightPanelTab.value = "private";
  privateDialogVisible.value = true;
  privateWindowMinimized.value = false;
  if (!privateWindowRect.x && !privateWindowRect.y) resetPrivateWindowPlacement();
  else clampPrivateWindowRect();
  privateEditingMessageId.value = "";
  privateEditingContent.value = "";
  nextTick(() => {
    scrollToBottom("private");
    privateInputRef.value?.focus();
  });
}

function selectPrivateMember(member: MeetingRoomMember) {
  activePrivateUserId.value = member.user_id;
  privateEditingMessageId.value = "";
  privateEditingContent.value = "";
  nextTick(() => {
    scrollToBottom("private");
    privateInputRef.value?.focus();
  });
}

async function sendPrivateMessage() {
  const member = ensureActivePrivateMember();
  if (!store.canSend || !member) return;
  const content = privateInput.value.trim();
  const attachments = [...privateAttachments.value];
  if (!content && !attachments.length) return;
  try {
    await store.sendMessage(content, null, {
      skipAgentTrigger: true,
      privateRecipientUserId: member.user_id,
      attachments,
    });
    privateInput.value = "";
    privateAttachments.value = [];
    await scrollToBottom("private");
  } catch (error) {
    ElMessage.error("私聊发送失败，请稍后重试。");
    console.error(error);
  }
}

async function extractCandidateMemories() {
  if (!store.activeRoom || !canReviewMemory.value) return;
  try {
    const list = await store.extractMemories();
    ElMessage.success(list.length ? "候选记忆已提取。" : "暂无可提取的候选记忆。");
  } catch (error) {
    ElMessage.error("提取候选记忆失败，请稍后重试。");
    console.error(error);
  }
}

async function confirmCandidateMemory(memory: MeetingMemory) {
  if (!canReviewMemory.value) return;
  resetMemoryPublishForm(memory);
  memoryPublishDialogVisible.value = true;
}

async function submitMemoryPublish() {
  const memory = selectedCandidateMemory.value;
  if (!memory || !canReviewMemory.value) return;
  try {
    memoryPublishSubmitting.value = true;
    await store.confirmMemory(memory.memory_id, {
      title: memoryPublishForm.title.trim(),
      content: memoryPublishForm.content.trim(),
      scope: memoryPublishForm.scope,
      scope_id: memoryPublishForm.scope === "meeting" ? null : memoryPublishForm.scope_id,
      publish_reason: memoryPublishForm.publish_reason.trim() || null,
    });
    memoryPublishDialogVisible.value = false;
    selectedCandidateMemory.value = null;
    ElMessage.success("记忆已确认发布");
  } catch (error) {
    ElMessage.error("确认发布失败，请稍后重试");
    console.error(error);
  } finally {
    memoryPublishSubmitting.value = false;
  }
}

async function rejectCandidateMemory(memory: MeetingMemory) {
  if (!canReviewMemory.value) return;
  try {
    await store.rejectMemory(memory.memory_id);
    ElMessage.success("候选记忆已拒绝");
  } catch (error) {
    ElMessage.error("拒绝记忆失败，请稍后重试。");
    console.error(error);
  }
}

async function disputeSharedMemory(memory: MeetingMemory) {
  if (!store.activeRoom) return;
  try {
    const { value } = await ElMessageBox.prompt("说明这条记忆哪里需要质疑或修订", "提交记忆质疑", {
      inputType: "textarea",
      inputPlaceholder: "例如：会议室 B 认为该结论与人工复核记录不一致",
      inputPattern: /^.{1,1000}$/,
      inputErrorMessage: "请输入 1 到 1000 个字符",
      confirmButtonText: "提交质疑",
      cancelButtonText: "取消",
    });
    await store.disputeMemory(memory.memory_id, { reason: String(value || "").trim() });
    ElMessage.success("质疑已记录，记忆进入争议状态");
  } catch {
    // cancelled
  }
}

async function updateMemberRole(member: MeetingRoomMember, role: "host" | "member") {
  if (!store.activeRoom || !canManageRoom.value || normalizedMemberRole(member.role) === role) return;
  try {
    await store.updateMemberRole(member.user_id, role);
    ElMessage.success(`已设为${memberRoleLabel(role)}`);
  } catch (error) {
    ElMessage.error("成员权限更新失败，请稍后重试。");
    console.error(error);
  }
}

async function createActionItem() {
  const title = actionTitle.value.trim();
  if (!title) return;
  try {
    await store.createActionItem({
      title,
      description: actionDescription.value.trim() || null,
      owner_id: actionOwnerId.value || null,
    });
    actionTitle.value = "";
    actionDescription.value = "";
    actionOwnerId.value = "";
    ElMessage.success("会议待办已新增");
  } catch (error) {
    ElMessage.error("新增会议待办失败，请稍后重试。");
    console.error(error);
  }
}

async function completeActionItem(actionItemId: string) {
  try {
    await store.completeActionItem(actionItemId);
    ElMessage.success("会议待办已完成");
  } catch (error) {
    ElMessage.error("更新会议待办失败，请稍后重试。");
    console.error(error);
  }
}

async function editRoomTitle() {
  if (!store.activeRoom) return;
  try {
    const { value } = await ElMessageBox.prompt("修改会议标题", "会议设置", {
      inputValue: store.activeRoom.title,
      inputPattern: /^.{1,120}$/,
      inputErrorMessage: "标题长度需为 1 到 120 个字符。",
      confirmButtonText: "保存",
      cancelButtonText: "取消",
    });
    await store.updateRoomTitle(String(value || "").trim());
    ElMessage.success("会议标题已更新。");
  } catch {
    // cancelled
  }
}

async function closeRoom() {
  if (!store.activeRoom) return;
  try {
    await ElMessageBox.confirm("关闭会议后将停止发送新消息，历史内容仍可查看。", "关闭会议", {
      confirmButtonText: "关闭",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.closeRoom();
    ElMessage.success("会议已关闭。");
  } catch {
    // cancelled
  }
}

async function archiveRoom() {
  if (!store.activeRoom) return;
  try {
    await ElMessageBox.confirm("归档后会议会保留为历史记录，可继续查看。", "归档会议", {
      confirmButtonText: "归档",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.archiveRoom();
    ElMessage.success("会议已归档。");
  } catch {
    // cancelled
  }
}

async function insertAgentMention(agentName: string) {
  const index = mentionTargets.value.findIndex((item) => item.agent_name === agentName);
  await selectMentionTarget(index >= 0 ? index : 0);
}

async function quoteMessage(message: MeetingMessage) {
  if (!canQuoteMessage(message)) return;
  quotedMessage.value = message;
  quoteSnapshot.value = null;
  await nextTick();
  inputRef.value?.focus();
}

function startEditMessage(message: MeetingMessage) {
  if (!canMutateMessage(message) && !canReEditMessage(message)) return;
  const original = messageMetadata(message).original_content;
  privateEditingMessageId.value = message.id;
  privateEditingContent.value = String(original || message.content || "");
}

function cancelEditMessage() {
  privateEditingMessageId.value = "";
  privateEditingContent.value = "";
}

async function saveEditedMessage(message: MeetingMessage) {
  const content = privateEditingContent.value.trim();
  if (!content) return;
  try {
    await store.updateMessage(message.id, content);
    cancelEditMessage();
    ElMessage.success("已保存");
  } catch (error) {
    ElMessage.error("保存失败，请确认消息仍可编辑且会议室处于进行中。");
    console.error(error);
  }
}

async function recallMessage(message: MeetingMessage) {
  if (!canRecallMessage(message)) {
    ElMessage.info("这条消息已超过 2 分钟，不能撤回。");
    return;
  }
  try {
    await store.recallMessage(message.id);
    ElMessage.success("已撤回");
  } catch (error) {
    ElMessage.info("这条消息现在不能撤回，可能已超过 2 分钟或会议状态已变化。");
    console.error(error);
  }
}

async function handleDeleteRoom(room: MeetingRoom) {
  if (!canDeleteRoom(room)) return;
  try {
    await ElMessageBox.confirm(
      `确定删除会议室「${room.title}」吗？删除后所有成员都将无法继续访问。`,
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
    await store.deleteRoom(room.id);
    ElMessage.success("会议室已删除");
  } catch {
    // cancelled or error
  }
}

async function handleLeaveRoom(room: MeetingRoom) {
  if (!canLeaveRoom(room)) return;
  try {
    await ElMessageBox.confirm(
      `确定退出会议室「${roomDisplayTitle(room)}」吗？退出后需要会议码才能重新加入。`,
      "退出会议",
      { confirmButtonText: "退出", cancelButtonText: "取消", type: "warning" }
    );
    await store.leaveRoom(room.id);
    ElMessage.success("已退出会议");
  } catch {
    // cancelled or error
  }
}

// Lifecycle

async function loadActiveRoomData(newId: string) {
  if (!newId) {
    store.disconnectStream();
    closeMentionMenu();
    await store.loadMembers();
    return;
  }

  closeMentionMenu();
  const results = await Promise.allSettled([
    store.loadMessages(0),
    store.loadMembers(),
    store.loadAgents(),
    store.loadMeetingContext(),
  ]);
  const failed = results.find((item) => item.status === "rejected");
  if (failed) {
    console.error("Failed to load meeting room data", failed.reason);
  }
  store.connectStream();
  await scrollToBottom();
}

watch(() => store.activeRoomId, async (newId) => {
  closeMentionMenu();
  try {
    await loadActiveRoomData(newId);
  } catch (error) {
    console.error("Failed to switch meeting room", error);
  }
});

watch(() => store.conversationMessages.length, async () => {
  await scrollToBottom();
});

watch(() => agentConversationGroups.value.map((group) => {
  const questionKey = group.question ? `${group.question.id}:${group.question.content.length}` : "no-question";
  const replyKey = group.replies.map((item) => `${item.id}:${item.content.length}`).join(",");
  return `${group.id}:${questionKey}:${replyKey}`;
}).join("|"), async () => {
  await scrollToBottom("agent");
});

watch(() => selectedPrivateMessages.value.map((item) => `${item.id}:${item.content.length}`).join("|"), async () => {
  await scrollToBottom("private");
});

watch(privatePartners, (members) => {
  const currentStillVisible = members.some((member) => member.user_id === activePrivateUserId.value);
  if (!currentStillVisible) ensureActivePrivateMember();
});

watch(currentUserId, () => {
  const selectedSelf = activePrivateUserId.value && activePrivateUserId.value === currentUserId.value;
  if (selectedSelf || !privatePartners.value.some((member) => member.user_id === activePrivateUserId.value)) {
    ensureActivePrivateMember();
  }
});

watch(() => store.candidateMemories.length, (count) => {
  collapsedContextSections.candidateMemory = count === 0;
});

watch(
  () => `${memoryPublishPreview.value?.recommended_scope || ""}:${memoryPublishPreview.value?.recommended_scope_id || ""}:${(memoryPublishPreview.value?.shareability?.allowed_scopes || []).join(",")}`,
  () => {
    syncMemoryPublishSelectionWithPreview();
  },
);

watch(rightPanelTab, async (tab) => {
  if (tab !== "private") return;
  ensureActivePrivateMember();
});

onMounted(async () => {
  resetPrivateWindowPlacement();
  privateRecallTimer = window.setInterval(() => {
    nowTick.value = Date.now();
  }, 15_000);
  void userStore.fetchCurrentUser().catch((error) => {
    console.warn("Failed to refresh current user before loading meeting room", error);
  });
  const invitedCode = new URLSearchParams(window.location.search).get("room")?.trim().toUpperCase() || "";
  if (invitedCode) {
    joinCode.value = invitedCode;
    hubMode.value = "join";
  }
  await store.loadRooms(true);
  if (invitedCode) {
    const matchedRoom = store.rooms.find((room) => room.access_code.toUpperCase() === invitedCode);
    store.activeRoomId = matchedRoom?.id || "";
  }
  window.addEventListener("resize", clampPrivateWindowRect);
});

onBeforeUnmount(() => {
  stopPanelResize();
  stopPrivateWindowInteraction();
  if (privateRecallTimer !== null) {
    window.clearInterval(privateRecallTimer);
    privateRecallTimer = null;
  }
  window.removeEventListener("resize", clampPrivateWindowRect);
  store.disconnectStream();
});
</script>

<template>
  <div
    class="meeting-page"
    :class="{
      'is-left-collapsed': leftPanelCollapsed,
      'is-right-collapsed': rightPanelCollapsed,
      'is-resizing-left': resizingPanel === 'left',
      'is-resizing-right': resizingPanel === 'right',
    }"
    :style="meetingLayoutStyle"
  >
    <aside class="meeting-sidebar" :class="{ 'panel-collapsed': leftPanelCollapsed }">
      <button
        type="button"
        class="panel-toggle panel-toggle-left"
        :aria-label="leftPanelCollapsed ? '展开会议入口' : '收起会议入口'"
        :title="leftPanelCollapsed ? '展开会议入口' : '收起会议入口'"
        @click="leftPanelCollapsed = !leftPanelCollapsed"
      >
        <ArrowRight v-if="leftPanelCollapsed" />
        <ArrowLeft v-else />
      </button>
      <div class="panel-collapsed-label">会议入口</div>
      <div class="panel-content">
        <section class="sidebar-section">
        <p class="section-kicker">会议入口</p>
        <h1>会议室</h1>
        <p class="section-copy">创建新会议，或使用别人发来的会议码加入。</p>

        <div class="hub-mode" role="tablist" aria-label="会议室操作">
          <button
            type="button"
            :class="{ 'hub-mode-active': hubMode === 'create' }"
            role="tab"
            :aria-selected="hubMode === 'create'"
            @click="hubMode = 'create'"
          >
            创建会议
          </button>
          <button
            type="button"
            :class="{ 'hub-mode-active': hubMode === 'join' }"
            role="tab"
            :aria-selected="hubMode === 'join'"
            @click="hubMode = 'join'"
          >
            加入会议
          </button>
        </div>

        <div v-if="hubMode === 'create'" class="form-stack">
          <label>
            <span>会议标题</span>
            <el-input v-model="roomTitle" placeholder="会议室" />
          </label>
          <label>
            <span>入会密码（可选）</span>
            <el-input v-model="roomPassword" type="password" show-password placeholder="可留空" />
          </label>
          <el-button :icon="Plus" @click="createRoom">创建会议室</el-button>
        </div>

        <div v-else class="form-stack">
          <label>
            <span>会议码</span>
            <el-input v-model="joinCode" placeholder="会议码" />
          </label>
          <label>
            <span>入会密码</span>
            <el-input v-model="joinPassword" type="password" show-password placeholder="无密码可留空" @keydown.enter="joinRoom" />
          </label>
          <el-button :icon="Key" @click="joinRoom">加入会议</el-button>
        </div>
        </section>

        <section class="room-list">
        <div class="room-list-head">
          <h2>我加入过的会议</h2>
          <el-button text :icon="RefreshRight" :loading="store.loadingRooms" @click="store.loadRooms()" aria-label="刷新会议列表" />
        </div>
        <div
          v-for="room in store.rooms"
          :key="room.id"
          class="room-item"
          :class="{ 'room-item-active': room.id === store.activeRoomId }"
          role="button"
          tabindex="0"
          @click="store.activeRoomId = room.id"
          @keydown.enter="store.activeRoomId = room.id"
        >
          <span class="room-item-head">
            <span class="room-title">{{ roomDisplayTitle(room) }}</span>
            <el-button
              v-if="canDeleteRoom(room)"
              text
              type="danger"
              size="small"
              :icon="Delete"
              class="room-delete-button"
              aria-label="删除会议"
              title="删除会议"
              @click.stop="handleDeleteRoom(room)"
            />
            <el-button
              v-else-if="canLeaveRoom(room)"
              text
              type="warning"
              size="small"
              class="room-delete-button"
              aria-label="退出会议"
              title="退出会议"
              @click.stop="handleLeaveRoom(room)"
            >
              退出
            </el-button>
          </span>
          <span class="room-meta">
            <span>{{ room.access_code }} · {{ room.member_count }} 人</span>
            <span>{{ roomDomainPreview(room) }}</span>
            <span v-if="roomRecentLabel(room)">最近 {{ roomRecentLabel(room) }}</span>
          </span>
        </div>
        <p v-if="!store.rooms.length && !store.loadingRooms" class="empty-note">暂无加入过的会议</p>
        </section>
      </div>
      <div
        v-if="!leftPanelCollapsed"
        class="panel-resizer panel-resizer-left"
        role="separator"
        aria-label="调整左侧面板宽度"
        aria-orientation="vertical"
        @pointerdown="startPanelResize('left', $event)"
      />
    </aside>

    <section class="meeting-room">
      <header class="room-header">
        <div class="room-title-block">
          <p class="section-kicker">实时会议</p>
          <h2>{{ store.activeRoom?.title || "实时会议协作" }}</h2>
          <div v-if="store.activeRoom && hostMember" class="room-submeta">
            <span class="host-pill">主持人 {{ hostMember.username }}</span>
            <span class="status-pill" :class="`status-${store.activeRoom.status}`">{{ roomStatusLabel }}</span>
          </div>
        </div>
        <div v-if="store.activeRoom" class="room-header-right">
          <div class="room-toolbar-main">
            <div class="room-code">
              <span>会议码</span>
              <strong>{{ store.activeRoom.access_code }}</strong>
            </div>
          <el-popover
            placement="bottom-end"
            :width="340"
            trigger="click"
            @show="store.loadMembers()"
          >
            <template #reference>
              <el-button size="small" :icon="User">
                成员 ({{ visibleMemberCount }})
              </el-button>
            </template>
            <div class="member-panel">
              <div class="member-panel-head">
                <span>会议成员</span>
                <strong>{{ visibleMemberCount }} 人</strong>
              </div>
              <div v-if="store.members.length === 0" class="member-panel-empty">
                暂无成员信息
              </div>
              <div v-for="member in store.members" :key="member.id" class="member-item">
                <span class="member-avatar">{{ memberInitial(member.username) }}</span>
                <span class="member-main">
                  <strong>{{ member.username }}</strong>
                  <small>{{ member.user_id === currentUserId ? "当前账号" : member.user_id.slice(-8) }}</small>
                </span>
                <span class="member-actions">
                  <el-button
                    v-if="member.user_id !== currentUserId"
                    text
                    size="small"
                    :icon="ChatDotRound"
                    aria-label="私聊"
                    title="私聊"
                    @click="openPrivateDialog(member)"
                  />
                  <el-select
                    v-if="canManageRoom && member.user_id !== store.activeRoom.created_by"
                    :model-value="normalizedMemberRole(member.role)"
                    size="small"
                    class="member-role-select"
                    @change="(role) => updateMemberRole(member, role as 'host' | 'member')"
                  >
                    <el-option label="主持人" value="host" />
                    <el-option label="成员" value="member" />
                  </el-select>
                  <span v-else class="member-role" :class="{ 'member-role-host': member.role === 'host' }">
                    {{ memberRoleLabel(member.role) }}
                  </span>
                </span>
              </div>
            </div>
          </el-popover>

          <el-popover
            placement="bottom-end"
            :width="360"
            trigger="click"
          >
            <template #reference>
              <el-button size="small" type="primary" plain :icon="Share">
                邀请成员
              </el-button>
            </template>
            <div class="invite-panel">
              <div class="invite-panel-head">
                <span>会议码</span>
                <strong>{{ store.activeRoom.access_code }}</strong>
              </div>
              <p class="invite-note">复制给成员后，对方打开链接会自动填入会议码。</p>
              <div class="invite-link">{{ activeMeetingLink }}</div>
              <div class="invite-actions">
                <el-button size="small" :icon="CopyDocument" @click="copyToClipboard(store.activeRoom.access_code, '会议码已复制')">
                  复制会议码
                </el-button>
                <el-button size="small" type="primary" :icon="Share" @click="copyInvite">
                  复制邀请
                </el-button>
              </div>
            </div>
          </el-popover>

          </div>
          <div v-if="canManageRoom" class="room-toolbar-admin">
            <el-button size="small" :icon="EditPen" @click="editRoomTitle">
              改标题
            </el-button>
            <el-button v-if="store.activeRoom.status === 'active'" size="small" :icon="Close" @click="closeRoom">
              关闭
            </el-button>
            <el-button v-if="store.activeRoom.status !== 'archived'" size="small" :icon="FolderOpened" @click="archiveRoom">
              归档
            </el-button>
          </div>
        </div>
        <p v-else class="room-hint">创建或加入会议后开始聊天，也可以点名 @会议Agent。</p>
      </header>

      <div ref="messageListRef" v-loading="store.loadingMessages" class="message-list">
        <div v-if="!store.activeRoom" class="empty-state">
          <ChatDotRound />
          <h3>会议内容将在这里实时同步</h3>
        </div>

        <div v-else-if="store.conversationMessages.length === 0 && !store.loadingMessages" class="empty-state">
          <ChatDotRound />
          <h3>暂无公共发言</h3>
        </div>

        <article
          v-for="message in store.conversationMessages"
          :key="message.id"
          :id="`meeting-message-${message.id}`"
          class="message-row"
          :class="{
            'message-row-own': message.user_id === currentUserId,
          }"
        >
          <div class="message-meta">
            <span>{{ message.username }}</span>
            <time>{{ formatTime(message.created_at) }}</time>
          </div>
          <div v-if="message.quote_message_id" class="quoted-message">
            {{ quotedMessageTitle(message.quote_message_id) }}
          </div>
          <div v-else-if="messageQuoteSnapshot(message)" class="quoted-message quoted-message-snapshot">
            {{ quoteSnapshotTitle(messageQuoteSnapshot(message)) }}
          </div>
          <div v-if="messageMetadata(message).recalled_at" class="message-recalled-line">
            <span>已撤回</span>
            <button v-if="canReEditMessage(message)" type="button" @click="reEditRecalledPublicMessage(message)">重新编辑</button>
          </div>
          <template v-else>
            <div v-if="displayMessageContent(message)" class="message-bubble">
              <span>{{ displayMessageContent(message) }}</span>
              <small v-if="messageMetadata(message).edited_at" class="message-edited-mark">已编辑</small>
            </div>
            <div v-if="messageAttachments(message).length" class="message-attachments">
              <template v-for="att in messageAttachments(message)" :key="att.id">
                <button
                  v-if="isImageAttachment(att)"
                  type="button"
                  class="att-image-button"
                  :title="att.name"
                  :aria-label="`预览图片 ${att.name}`"
                  @click="openImagePreview(att)"
                >
                  <img :src="att.url" :alt="att.name" loading="lazy" />
                  <span class="att-image-name">{{ att.name }}</span>
                </button>
                <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
              </template>
            </div>
          </template>
          <div v-if="!messageMetadata(message).recalled_at" class="message-toolbar">
            <MessageActionBar
              :reaction="store.messageReactions[message.id] || ''"
              show-ask-agent
              :show-share="false"
              @copy="copyToClipboard(copyMessageContent(message), '消息已复制')"
              @ask-agent="askAgentAboutMessage(message)"
            />
            <el-tooltip
              v-if="message.user_id === currentUserId"
              :content="canRecallMessage(message) ? '发送后 2 分钟内可撤回' : '已超过 2 分钟，不能撤回'"
              placement="bottom"
            >
              <el-button text size="small" :disabled="!canRecallMessage(message)" @click="recallMessage(message)">撤回</el-button>
            </el-tooltip>
            <el-tooltip v-if="canQuoteMessage(message)" content="引用" placement="bottom">
              <el-button text size="small" @click="quoteMessage(message)">引用</el-button>
            </el-tooltip>
          </div>
        </article>
      </div>

      <footer class="composer" @paste="handleComposerPaste($event, 'main')">
        <div v-if="quotedMessage || quoteSnapshot" class="composer-quote" :class="{ 'composer-quote-snapshot': quoteSnapshot }">
          <span v-if="quotedMessage">引用 {{ quotedMessage.username }}：{{ quotedMessage.content.slice(0, 80) }}</span>
          <span v-if="quoteSnapshot">引用 {{ quoteSnapshot.author }}：{{ clipText(quoteSnapshot.content, 120) }}</span>
          <el-button text size="small" :icon="Close" @click="quotedMessage = null; quoteSnapshot = null" />
        </div>
        <div v-if="store.pendingAttachments.length" class="composer-attachments">
          <el-tag v-for="att in store.pendingAttachments" :key="att.id" closable effect="plain" @close="removeAttachment(att.id, 'main')">
            {{ att.name }}
          </el-tag>
        </div>
        <div v-if="mentionMenuOpen" class="mention-menu" role="listbox" aria-label="@ 提及对象">
          <div class="mention-menu-head">选择要 @ 的对象</div>
          <button
            v-for="(target, index) in filteredMentionTargets"
            :key="target.id"
            type="button"
            class="mention-option"
            :class="{ 'mention-option-active': index === activeMentionIndex }"
            role="option"
            :aria-selected="index === activeMentionIndex"
            @mousedown.prevent="selectMentionTarget(index)"
          >
            <span>@{{ target.agent_name }}</span>
            <small>{{ target.description }}</small>
          </button>
          <div v-if="!filteredMentionTargets.length" class="mention-empty">没有匹配的 Agent</div>
        </div>
        <textarea
          ref="inputRef"
          v-model="input"
          class="composer-textarea"
          :disabled="!store.activeRoom || store.activeRoom.status !== 'active'"
          rows="1"
          :placeholder="store.activeRoom?.status === 'active' ? '输入公共消息' : '会议已关闭或归档，只能查看历史。'"
          @input="onInputChanged"
          @click="onInputClicked"
          @keyup="onInputClicked"
          @keydown="onInputKeydown"
        />
        <div class="composer-actions">
          <el-button :icon="Paperclip" :loading="store.attachmentUploading" :disabled="!store.canSend" @click="triggerAttachmentSelect('main')" aria-label="添加附件" />
          <el-button type="primary" :icon="Promotion" :loading="store.sending" :disabled="!store.canSend" @click="sendMessage">发送</el-button>
        </div>
        <input ref="attachmentInputRef" type="file" multiple hidden @change="handleAttachmentSelected($event, 'main')" />
      </footer>
    </section>

    <aside class="meeting-context" :class="{ 'panel-collapsed': rightPanelCollapsed }" v-loading="store.loadingContext">
      <button
        type="button"
        class="panel-toggle panel-toggle-right"
        :aria-label="rightPanelCollapsed ? '展开边界与记忆面板' : '收起边界与记忆面板'"
        :title="rightPanelCollapsed ? '展开边界与记忆面板' : '收起边界与记忆面板'"
        @click="rightPanelCollapsed = !rightPanelCollapsed"
      >
        <ArrowLeft v-if="rightPanelCollapsed" />
        <ArrowRight v-else />
      </button>
      <div class="panel-collapsed-label">侧栏</div>
      <div class="panel-content context-panel-content">
        <div class="sidecar-tabs" role="tablist" aria-label="会议侧栏">
          <button
            type="button"
            class="sidecar-tab"
            :class="{ 'sidecar-tab-active': rightPanelTab === 'ai' }"
            :aria-selected="rightPanelTab === 'ai'"
            @click="rightPanelTab = 'ai'"
          >
            AI <strong v-if="agentQuestionCount">{{ agentQuestionCount }}</strong>
          </button>
          <button
            type="button"
            class="sidecar-tab"
            :class="{ 'sidecar-tab-active': rightPanelTab === 'private' }"
            :aria-selected="rightPanelTab === 'private'"
            @click="rightPanelTab = 'private'"
          >
            私聊 <strong v-if="privateConversationCount">{{ privateConversationCount }}</strong>
          </button>
          <button
            type="button"
            class="sidecar-tab"
            :class="{ 'sidecar-tab-active': rightPanelTab === 'context' }"
            :aria-selected="rightPanelTab === 'context'"
            @click="rightPanelTab = 'context'"
          >
            边界与记忆
          </button>
        </div>

        <section v-show="rightPanelTab === 'ai'" class="agent-sidecar sidecar-pane">
          <div class="agent-sidecar-head">
            <h2>会议Agent</h2>
            <span class="agent-live-pill" :class="{ 'agent-live-pill-active': store.generalAgentRunning }">
              <span class="agent-live-dot" />{{ store.generalAgentRunning ? "思考中" : "在线" }}
            </span>
          </div>
          <div ref="agentPanelListRef" class="agent-thread-list">
            <div v-if="!store.activeRoom" class="agent-empty">未进入会议</div>
            <div v-else-if="!agentConversationGroups.length" class="agent-empty">暂无 AI 对话</div>
            <section v-for="(group, groupIndex) in agentConversationGroups" :key="group.id" class="agent-qa-group">
              <div class="agent-qa-index">第 {{ groupIndex + 1 }} 轮</div>
              <article v-if="group.question" class="agent-thread-item agent-thread-question">
                <div class="agent-thread-meta">
                  <span>提问 · {{ group.question.username }}</span>
                  <time>{{ formatTime(group.question.created_at) }}</time>
                </div>
                <div v-if="agentEditingMessageId === group.question.id" class="agent-message-edit">
                  <el-input v-model="agentEditingContent" type="textarea" :rows="3" resize="vertical" />
                  <div class="agent-message-edit-actions">
                    <el-button size="small" @click="cancelModifyAgentQuestion">取消</el-button>
                    <el-button size="small" type="primary" :loading="store.generalAgentRunning" @click="saveModifiedAgentQuestion(group.question)">修改并重新问</el-button>
                  </div>
                </div>
                <div v-else class="agent-thread-body">
                  <span>{{ displayMessageContent(group.question) }}</span>
                </div>
                <div v-if="agentEditingMessageId !== group.question.id && messageAttachments(group.question).length" class="message-attachments agent-thread-attachments">
                  <template v-for="att in messageAttachments(group.question)" :key="att.id">
                    <button v-if="isImageAttachment(att)" type="button" class="att-image-button" :aria-label="`预览图片 ${att.name}`" :title="att.name" @click="openImagePreview(att)">
                      <img :src="att.url" :alt="att.name" loading="lazy" />
                      <span class="att-image-name">{{ att.name }}</span>
                    </button>
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
                  </template>
                </div>
                <MessageActionBar
                  v-if="agentEditingMessageId !== group.question.id"
                  :reaction="store.messageReactions[group.question.id] || ''"
                  :show-edit="canModifyAgentQuestion(group.question)"
                  :show-feedback="false"
                  :show-share="false"
                  @copy="copyToClipboard(copyMessageContent(group.question), '消息已复制')"
                  @edit="startModifyAgentQuestion(group.question)"
                />
              </article>
              <article
                v-for="reply in group.replies"
                :key="reply.id"
                class="agent-thread-item agent-thread-reply"
                :class="{ 'agent-thread-streaming': reply.message_type === 'agent_streaming' }"
              >
                <div class="agent-thread-meta">
                  <span>回复 · 会议Agent</span>
                  <time>{{ formatTime(reply.created_at) }}</time>
                </div>
                <div class="agent-thread-body">
                  <span v-if="reply.message_type === 'agent_streaming'" class="inline-thinking-dots">
                    <span class="dot" /><span class="dot" /><span class="dot" />
                  </span>
                  <span>{{ displayMessageContent(reply) }}</span>
                </div>
                <div v-if="messageAttachments(reply).length" class="message-attachments agent-thread-attachments">
                  <template v-for="att in messageAttachments(reply)" :key="att.id">
                    <button v-if="isImageAttachment(att)" type="button" class="att-image-button" :aria-label="`预览图片 ${att.name}`" :title="att.name" @click="openImagePreview(att)">
                      <img :src="att.url" :alt="att.name" loading="lazy" />
                      <span class="att-image-name">{{ att.name }}</span>
                    </button>
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
                  </template>
                </div>
                <MessageActionBar
                  v-if="reply.message_type !== 'agent_streaming'"
                  :reaction="store.messageReactions[reply.id] || ''"
                  show-feedback
                  :show-share="canQuoteAgentMessageToMain(reply)"
                  share-label="引用到主会场"
                  @copy="copyToClipboard(copyMessageContent(reply), '消息已复制')"
                  @like="submitMeetingFeedback(reply, 'up')"
                  @dislike="submitMeetingFeedback(reply, 'down')"
                  @share="quoteAgentMessageToMain(reply)"
                />
              </article>
              <div v-if="!group.replies.length" class="agent-awaiting-reply">等待会议Agent回复</div>
            </section>
          </div>
          <div class="agent-composer" @paste="handleComposerPaste($event, 'agent')">
            <div v-if="agentAttachments.length" class="composer-attachments agent-composer-attachments">
              <el-tag v-for="att in agentAttachments" :key="att.id" closable effect="plain" @close="removeAttachment(att.id, 'agent')">
                {{ att.name }}
              </el-tag>
            </div>
            <div class="agent-composer-row">
              <el-button :icon="Paperclip" :loading="store.attachmentUploading" :disabled="!store.canSend" @click="triggerAttachmentSelect('agent')" aria-label="添加附件" />
              <textarea
                ref="agentInputRef"
                v-model="agentInput"
                :disabled="!store.activeRoom || store.activeRoom.status !== 'active'"
                rows="1"
                placeholder="问会议Agent"
                @keydown="onAgentInputKeydown"
              />
              <el-button v-if="store.generalAgentRunning" type="danger" @click="stopGeneralAgent">停止生成</el-button>
              <el-button v-else type="primary" :icon="Promotion" :disabled="!store.canSend" @click="sendAgentQuestion" />
            </div>
            <input ref="agentAttachmentInputRef" type="file" multiple hidden @change="handleAttachmentSelected($event, 'agent')" />
          </div>
        </section>

        <section v-show="rightPanelTab === 'private'" class="private-sidecar sidecar-pane">
          <div class="private-sidecar-head">
            <h2>私聊</h2>
            <span class="private-sidecar-count">{{ privateConversationCount }}</span>
          </div>
          <div class="private-launcher">
            <div class="private-launcher-list">
              <button
                v-for="member in privatePartners"
                :key="member.user_id"
                type="button"
                class="private-launcher-row"
                :class="{ 'private-launcher-row-active': member.user_id === activePrivateUserId }"
                @click="openPrivateDialog(member)"
              >
                <span class="member-avatar">{{ memberInitial(member.username) }}</span>
                <span>
                  <strong>{{ member.username }}</strong>
                  <small>{{ privateMessagesByUser(member.user_id).length }} 条</small>
                </span>
              </button>
              <div v-if="!privatePartners.length" class="private-empty">暂无成员</div>
            </div>
          </div>
        </section>

        <section v-show="rightPanelTab === 'context'" class="context-pane sidecar-pane">
          <section class="context-card boundary-card" :class="{ 'context-card-collapsed': !isContextExpanded('boundary') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">边界</p>
                <h2>查询边界</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ contextAllowedDomains.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('boundary')" @click="toggleContextSection('boundary')">
                  <ArrowUp v-if="isContextExpanded('boundary')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <p class="context-note">Agent 只能读取边界内数据作为回答上下文，不能修改质检结果或人工审核结论。</p>
            <div v-if="store.activeRoom" class="boundary-identity">
              <span>我的身份：{{ store.contextPreview?.user_role || "user" }}</span>
              <span>会议角色：{{ store.contextPreview?.room_role || "member" }}</span>
            </div>
            <div class="boundary-block">
              <strong>允许访问</strong>
              <div v-if="contextAllowedDomains.length" class="domain-chip-list">
                <span v-for="domain in contextAllowedDomains" :key="domain" class="domain-chip domain-chip-allowed">
                  {{ domainLabel(domain) }}
                </span>
              </div>
              <div v-else class="context-empty context-empty-compact">暂无允许访问范围</div>
            </div>
            <div class="boundary-block">
              <strong>不可访问</strong>
              <div v-if="contextDeniedDomains.length" class="domain-chip-list">
                <span v-for="domain in contextDeniedDomains" :key="domain" class="domain-chip domain-chip-denied">
                  {{ domainLabel(domain) }}
                </span>
              </div>
              <div v-else class="context-empty context-empty-compact">暂无禁止访问范围</div>
            </div>
            <div class="boundary-block">
              <strong>绑定对象</strong>
              <div v-if="hasBusinessBindings" class="business-binding-list">
                <div v-for="group in businessBindingGroups" v-show="group.values.length" :key="group.key" class="business-binding-row">
                  <span>{{ group.label }}</span>
                  <div>
                    <b v-for="value in group.values" :key="value">{{ value }}</b>
                  </div>
                </div>
              </div>
              <el-alert
                v-else
                type="info"
                show-icon
                :closable="false"
                title="未绑定业务对象，业务记忆只能保存到本会议室。"
              />
            </div>
            <div v-if="store.contextPreview?.agent_permissions.length" class="boundary-block">
              <strong>Agent 权限</strong>
              <div class="agent-permission-list">
                <div v-for="agent in store.contextPreview.agent_permissions" :key="agent.agent_id" class="agent-permission-item">
                  <strong>{{ agent.agent_name }}</strong>
                  <small>{{ visibleDomainLabels(agent.allowed_domains, "暂无可见数据域") }}</small>
                </div>
              </div>
            </div>
          </section>

          <section class="context-card" :class="{ 'context-card-collapsed': !isContextExpanded('candidateMemory') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">待确认</p>
                <h2>候选记忆</h2>
              </div>
              <div class="context-head-actions">
                <el-button
                  v-if="canReviewMemory"
                  text
                  size="small"
                  :icon="MagicStick"
                  :loading="store.memoryExtracting"
                  :disabled="!store.activeRoom"
                  @click="extractCandidateMemories"
                >
                  提取
                </el-button>
                <span class="count-pill">{{ store.candidateMemories.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('candidateMemory')" @click="toggleContextSection('candidateMemory')">
                  <ArrowUp v-if="isContextExpanded('candidateMemory')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <p v-if="store.candidateMemories.length" class="context-note">候选记忆先由会议室确认；跨范围发布只落到任务、产品、批次、标准或质检风险库，不按相关会议室推送。</p>
            <div v-if="!store.candidateMemories.length" class="context-empty context-empty-compact">暂无候选记忆，可由主持人点击“提取”。</div>
            <article v-for="memory in store.candidateMemories" :key="memory.memory_id" class="memory-item">
              <div class="memory-title-row">
                <strong>{{ memory.title }}</strong>
                <span v-if="memoryConfidence(memory)">{{ memoryConfidence(memory) }}</span>
              </div>
              <div class="memory-meta-row">
                <span :class="['memory-category-badge', `memory-category-${memory.memory_category || 'meeting_memory'}`]">
                  {{ memoryCategoryLabel(memory.memory_category) }}
                </span>
                <span>{{ memoryTypeLabel(memory.memory_type) }}</span>
                <span>推荐：{{ memoryScopeLabel(memory.recommended_scope) }}</span>
              </div>
              <p>{{ memoryPreview(memory, 180) }}</p>
              <div v-if="memory.memory_type === 'risk_insight'" class="risk-insight-strip">
                <span>风险：{{ riskLevelLabel(memory.risk_level) }}</span>
                <span v-if="forecastWindowLabel(memory)">关注：{{ forecastWindowLabel(memory) }}</span>
              </div>
              <small class="memory-source">{{ memoryCategoryHint(memory) }}</small>
              <div v-if="memory.warnings?.length" class="memory-warning-list">
                <span v-for="warning in memory.warnings" :key="warning">{{ warning }}</span>
              </div>
              <div v-if="canReviewMemory" class="memory-actions">
                <el-button size="small" type="primary" :icon="Check" @click="confirmCandidateMemory(memory)">确认发布</el-button>
                <el-button size="small" :icon="Close" @click="rejectCandidateMemory(memory)">拒绝</el-button>
              </div>
            </article>
          </section>

          <section class="context-card" :class="{ 'context-card-collapsed': !isContextExpanded('confirmedMemory') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">确认</p>
                <h2>已确认记忆</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.confirmedMemories.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('confirmedMemory')" @click="toggleContextSection('confirmedMemory')">
                  <ArrowUp v-if="isContextExpanded('confirmedMemory')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <p v-if="store.confirmedMemories.length" class="context-note">来源保留在本会议室；发布范围决定未来在哪些稳定对象上下文中可检索。</p>
            <div v-if="!store.confirmedMemories.length" class="context-empty context-empty-compact">暂无已确认记忆</div>
            <article
              v-for="memory in store.confirmedMemories"
              :key="memory.memory_id"
              class="shared-memory"
              :class="{ 'shared-memory-disputed': memory.status === 'disputed', 'shared-memory-superseded': memory.status === 'superseded' }"
            >
              <div class="memory-title-row">
                <strong>{{ memory.title }}</strong>
                <span>{{ memoryScopeLabel(memory.scope || memory.scope_type) }}</span>
              </div>
              <div class="memory-meta-row">
                <span :class="['memory-category-badge', `memory-category-${memory.memory_category || 'meeting_memory'}`]">
                  {{ memoryCategoryLabel(memory.memory_category) }}
                </span>
                <span>{{ memoryTypeLabel(memory.memory_type) }}</span>
                <span>{{ memoryStatusLabel(memory.status) }}</span>
                <span>发布范围：{{ scopeObjectLabel(memory) }}</span>
              </div>
              <p>{{ memoryPreview(memory) }}</p>
              <small class="memory-source">来源：本会议室 · {{ scopeVisibilityNote(memory) }}</small>
              <div v-if="memory.memory_type === 'risk_insight'" class="risk-insight-strip">
                <span>风险：{{ riskLevelLabel(memory.risk_level) }}</span>
                <span v-if="forecastWindowLabel(memory)">关注：{{ forecastWindowLabel(memory) }}</span>
              </div>
              <div class="memory-actions">
                <el-button size="small" text @click="openMemoryDetail(memory)">{{ memorySourceSummary(memory) }}</el-button>
                <template v-if="canReviewMemory && memory.status !== 'superseded'">
                  <el-button size="small" text @click="disputeSharedMemory(memory)">质疑</el-button>
                  <el-button size="small" text type="primary" @click="confirmCandidateMemory(memory)">修订发布</el-button>
                </template>
              </div>
            </article>
          </section>

          <section class="context-card" :class="{ 'context-card-collapsed': !isContextExpanded('actions') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">协作</p>
                <h2>会议待办</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.openActionItems.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('actions')" @click="toggleContextSection('actions')">
                  <ArrowUp v-if="isContextExpanded('actions')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <div class="action-create">
              <el-input v-model="actionTitle" size="small" placeholder="新待办" @keydown.enter="createActionItem" />
              <el-input v-model="actionDescription" size="small" placeholder="补充说明（可选）" />
              <el-select v-model="actionOwnerId" size="small" clearable placeholder="负责人">
                <el-option
                  v-for="member in store.members"
                  :key="member.user_id"
                  :label="member.username"
                  :value="member.user_id"
                />
              </el-select>
              <el-button size="small" type="primary" :icon="Plus" :loading="store.actionItemSaving" @click="createActionItem">
                新增
              </el-button>
            </div>
            <div v-if="!store.actionItems.length" class="context-empty context-empty-compact">暂无会议待办</div>
            <article v-for="item in store.actionItems" :key="item.id" class="action-item" :class="{ 'action-done': item.status === 'done' }">
              <div>
                <strong>{{ item.title }}</strong>
                <p v-if="item.description">{{ item.description }}</p>
                <small>{{ item.owner_name || "未分配" }} · {{ item.status === "done" ? "已完成" : "进行中" }}</small>
              </div>
              <el-button v-if="item.status !== 'done'" text :icon="Check" @click="completeActionItem(item.id)" />
            </article>
          </section>

          <section v-if="canReviewMemory" class="context-card audit-card" :class="{ 'context-card-collapsed': !isContextExpanded('audit') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">审计</p>
                <h2>AI 使用记录</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.agentQueryAudits.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('audit')" @click="toggleContextSection('audit')">
                  <ArrowUp v-if="isContextExpanded('audit')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <p class="context-note">AI 使用记录不可修改，用于回溯 Agent 使用了哪些数据、记忆和工具。</p>
            <div v-if="!store.agentQueryAudits.length" class="context-empty context-empty-compact">暂无 AI 使用记录</div>
            <button
              v-for="audit in store.agentQueryAudits.slice(0, 4)"
              :key="audit.id"
              type="button"
              class="audit-item audit-item-clickable"
              @click="openAuditDetail(audit)"
            >
              <div class="audit-item-head">
                <span :class="['audit-decision', auditDecisionClass(audit.decision)]">
                  {{ auditDecisionLabel(audit.decision) }}
                </span>
                <time>{{ formatTime(audit.created_at) }}</time>
              </div>
              <p>{{ audit.question }}</p>
              <small>{{ visibleDomainLabels(audit.allowed_domains, "无可见允许域") }}</small>
              <small v-if="auditMemoryCount(audit)">读取记忆 {{ auditMemoryCount(audit) }} 条</small>
            </button>
          </section>
        </section>
      </div>
      <div
        v-if="!rightPanelCollapsed"
        class="panel-resizer panel-resizer-right"
        role="separator"
        aria-label="调整右侧面板宽度"
        aria-orientation="vertical"
        @pointerdown="startPanelResize('right', $event)"
      />
    </aside>
    <section
      v-if="privateDialogVisible"
      class="private-floating-window"
      :class="{ 'private-floating-minimized': privateWindowMinimized, 'private-floating-maximized': privateWindowMaximized }"
      :style="privateWindowStyle"
    >
      <header class="private-floating-titlebar" @pointerdown="startPrivateWindowDrag">
        <div class="private-dialog-title">
          <strong>私聊</strong>
          <span>{{ currentPrivateMember?.username || `${privatePartners.length} 位成员` }}</span>
        </div>
        <div class="private-window-controls">
          <button type="button" :title="privateWindowMinimized ? '还原' : '最小化'" @pointerdown.stop @click="privateWindowMinimized ? restorePrivateWindow() : minimizePrivateWindow()">
            <ScaleToOriginal v-if="privateWindowMinimized" />
            <Minus v-else />
          </button>
          <button type="button" :title="privateWindowMaximized ? '还原' : '最大化'" @pointerdown.stop @click="togglePrivateWindowMaximized">
            <ScaleToOriginal v-if="privateWindowMaximized" />
            <FullScreen v-else />
          </button>
          <button type="button" title="关闭" @pointerdown.stop @click="closePrivateWindow">
            <Close />
          </button>
        </div>
      </header>
      <div v-show="!privateWindowMinimized" class="private-dialog-body">
        <aside class="private-dialog-roster">
          <button
            v-for="member in privatePartners"
            :key="member.user_id"
            type="button"
            class="private-member-row"
            :class="{ 'private-member-row-active': member.user_id === activePrivateUserId }"
            @click="selectPrivateMember(member)"
          >
            <span class="member-avatar">{{ memberInitial(member.username) }}</span>
            <span>
              <strong>{{ member.username }}</strong>
              <small>{{ privateMessagesByUser(member.user_id).length }} 条</small>
            </span>
          </button>
          <div v-if="!privatePartners.length" class="private-empty">暂无成员</div>
        </aside>
        <section class="private-thread-pane private-dialog-thread">
          <div class="private-thread-head">
            <span class="member-avatar private-thread-avatar">{{ currentPrivateMember ? memberInitial(currentPrivateMember.username) : "?" }}</span>
            <div>
              <strong>{{ currentPrivateMember?.username || "选择成员" }}</strong>
              <small v-if="currentPrivateMember">{{ selectedPrivateMessages.length }} 条消息</small>
            </div>
          </div>
          <div ref="privatePanelListRef" class="private-message-list">
            <div v-if="!currentPrivateMember" class="private-empty">选择成员</div>
            <div v-else-if="!selectedPrivateMessages.length" class="private-empty">暂无消息</div>
            <article
              v-for="message in selectedPrivateMessages"
              :key="message.id"
              class="private-chat-message"
              :class="{ 'private-chat-message-own': message.user_id === currentUserId }"
            >
              <small>{{ message.username }} · {{ formatTime(message.created_at) }}</small>
              <div v-if="privateEditingMessageId === message.id" class="private-message-edit">
                <el-input v-model="privateEditingContent" type="textarea" :rows="2" resize="vertical" />
                <div class="private-message-edit-actions">
                  <el-button size="small" @click="cancelEditMessage">取消</el-button>
                  <el-button size="small" type="primary" @click="saveEditedMessage(message)">保存</el-button>
                </div>
              </div>
              <div v-else-if="messageMetadata(message).recalled_at" class="private-message-recalled-line">
                <span>已撤回</span>
                <button v-if="canReEditMessage(message)" type="button" @click="reEditRecalledPrivateMessage(message)">重新编辑</button>
              </div>
              <template v-else>
                <p>{{ displayMessageContent(message) }}</p>
                <div v-if="messageAttachments(message).length" class="message-attachments private-message-attachments">
                  <template v-for="att in messageAttachments(message)" :key="att.id">
                    <button v-if="isImageAttachment(att)" type="button" class="att-image-button" :aria-label="`预览图片 ${att.name}`" :title="att.name" @click="openImagePreview(att)">
                      <img :src="att.url" :alt="att.name" loading="lazy" />
                      <span class="att-image-name">{{ att.name }}</span>
                    </button>
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ att.name }}</a>
                  </template>
                </div>
                <div v-if="message.user_id === currentUserId" class="private-message-actions">
                  <button type="button" :disabled="!canRecallMessage(message)" :title="canRecallMessage(message) ? '发送后 2 分钟内可撤回' : '已超过 2 分钟，不能撤回'" @click="recallMessage(message)">
                    撤回
                  </button>
                </div>
              </template>
            </article>
          </div>
          <div class="private-chat-composer" @paste="handleComposerPaste($event, 'private')">
            <div v-if="privateAttachments.length" class="composer-attachments private-composer-attachments">
              <el-tag v-for="att in privateAttachments" :key="att.id" closable effect="plain" @close="removeAttachment(att.id, 'private')">
                {{ att.name }}
              </el-tag>
            </div>
            <textarea
              ref="privateInputRef"
              v-model="privateInput"
              :disabled="!store.canSend || !currentPrivateMember"
              rows="2"
              placeholder="输入私聊消息"
              @keydown="onPrivateInputKeydown"
            />
            <div class="private-composer-actions">
              <el-button :icon="Paperclip" :loading="store.attachmentUploading" :disabled="!store.canSend || !currentPrivateMember" @click="triggerAttachmentSelect('private')" aria-label="添加附件" />
              <el-button type="primary" size="small" :disabled="!store.canSend || !currentPrivateMember" @click="sendPrivateMessage">发送</el-button>
            </div>
            <input ref="privateAttachmentInputRef" type="file" multiple hidden @change="handleAttachmentSelected($event, 'private')" />
          </div>
        </section>
      </div>
      <template v-if="!privateWindowMinimized && !privateWindowMaximized">
        <button
          v-for="handle in privateWindowResizeHandles"
          :key="handle.direction"
          type="button"
          class="private-window-resizer"
          :class="handle.className"
          :aria-label="handle.ariaLabel"
          tabindex="-1"
          @pointerdown="startPrivateWindowResize(handle.direction, $event)"
        />
      </template>
    </section>
    <el-drawer
      v-model="auditDetailVisible"
      title="AI 使用记录"
      size="420px"
      append-to-body
    >
      <div v-if="selectedAudit" class="detail-drawer-body">
        <section class="detail-section">
          <p class="context-note">AI 使用记录不可修改，用于回溯 Agent 使用了哪些数据、记忆和工具。</p>
          <h3>问题</h3>
          <p class="detail-main-text">{{ selectedAudit.question }}</p>
          <div class="detail-meta-grid">
            <span>时间</span>
            <strong>{{ formatTime(selectedAudit.created_at) || "未知" }}</strong>
            <span>决策</span>
            <strong>{{ auditDecisionLabel(selectedAudit.decision) }}</strong>
            <span>意图</span>
            <strong>{{ selectedAudit.intent || "暂无记录" }}</strong>
          </div>
        </section>
        <section class="detail-section">
          <h3>数据边界</h3>
          <div class="domain-chip-list">
            <span v-for="domain in selectedAudit.allowed_domains" :key="`allow-${domain}`" class="domain-chip domain-chip-allowed">{{ domainLabel(domain) }}</span>
            <span v-for="domain in selectedAudit.denied_domains" :key="`deny-${domain}`" class="domain-chip domain-chip-denied">{{ domainLabel(domain) }}</span>
          </div>
        </section>
        <section class="detail-section">
          <h3>读取记忆</h3>
          <div v-if="selectedAudit.memory_reads.length" class="detail-ref-list">
            <button v-for="(ref, index) in selectedAudit.memory_reads" :key="index" type="button" @click="openAuditMemory(ref)">
              {{ extractRefId(ref) || `记忆 ${index + 1}` }}
            </button>
          </div>
          <p v-else class="context-empty context-empty-compact">暂无记录</p>
        </section>
        <section class="detail-section">
          <h3>来源引用</h3>
          <pre>{{ stableJson(selectedAudit.source_refs) }}</pre>
        </section>
        <section class="detail-section">
          <h3>工具调用</h3>
          <pre>{{ stableJson(selectedAudit.tool_calls) }}</pre>
        </section>
        <section class="detail-section">
          <h3>脱敏字段</h3>
          <pre>{{ stableJson(selectedAudit.redacted_fields) }}</pre>
        </section>
        <div class="detail-actions">
          <el-button size="small" :icon="CopyDocument" @click="copyAuditDetail">复制审计信息</el-button>
          <el-button size="small" @click="reuseAuditQuestion">用同样边界重新提问</el-button>
          <el-button size="small" type="warning" @click="questionAuditAnswer">质疑这次回答</el-button>
        </div>
      </div>
    </el-drawer>
    <el-drawer
      v-model="memoryDetailVisible"
      title="已确认记忆详情"
      size="420px"
      append-to-body
    >
      <div v-if="selectedSharedMemory" class="detail-drawer-body">
        <section class="detail-section">
          <div class="memory-title-row">
            <strong>{{ selectedSharedMemory.title }}</strong>
            <span>{{ memoryScopeLabel(selectedSharedMemory.scope || selectedSharedMemory.scope_type) }}</span>
          </div>
          <p class="detail-main-text">{{ selectedSharedMemory.content || selectedSharedMemory.summary }}</p>
          <div class="memory-meta-row">
            <span :class="['memory-category-badge', `memory-category-${selectedSharedMemory.memory_category || 'meeting_memory'}`]">
              {{ memoryCategoryLabel(selectedSharedMemory.memory_category) }}
            </span>
            <span>{{ memoryTypeLabel(selectedSharedMemory.memory_type) }}</span>
            <span>{{ memoryStatusLabel(selectedSharedMemory.status) }}</span>
            <span>{{ scopeObjectLabel(selectedSharedMemory) }}</span>
          </div>
        </section>
        <section class="detail-section">
          <h3>来源链</h3>
          <div class="detail-meta-grid">
            <span>来源位置</span>
            <strong>本会议室</strong>
            <span>来源消息</span>
            <strong>{{ sourceMessageLabel(selectedSharedMemory) }}</strong>
            <span>父版本</span>
            <strong>{{ selectedSharedMemory.version_parent_id ? "由上一版修订而来" : "暂无历史版本" }}</strong>
            <span>发布人</span>
            <strong>{{ memberDisplayName(selectedSharedMemory.confirmed_by || selectedSharedMemory.created_by) }}</strong>
            <span>发布时间</span>
            <strong>{{ formatTime(selectedSharedMemory.confirmed_at || selectedSharedMemory.created_at) || "暂无记录" }}</strong>
          </div>
        </section>
        <section v-if="selectedSharedMemory.memory_type === 'risk_insight'" class="detail-section">
          <h3>风险洞察</h3>
          <div class="detail-meta-grid">
            <span>风险等级</span>
            <strong>{{ riskLevelLabel(selectedSharedMemory.risk_level) }}</strong>
            <span>关注窗口</span>
            <strong>{{ forecastWindowLabel(selectedSharedMemory) || "暂无记录" }}</strong>
            <span>影响对象</span>
            <strong>{{ stableJson(selectedSharedMemory.affected_objects || {}) }}</strong>
          </div>
          <div v-if="selectedSharedMemory.recommended_actions?.length" class="recommended-action-list">
            <span v-for="action in selectedSharedMemory.recommended_actions" :key="action">{{ action }}</span>
          </div>
        </section>
        <section class="detail-section">
          <h3>发布范围</h3>
          <div class="detail-meta-grid">
            <span>作用域</span>
            <strong>{{ memoryScopeLabel(selectedSharedMemory.scope || selectedSharedMemory.scope_type) }}</strong>
            <span>对象</span>
            <strong>{{ scopeObjectLabel(selectedSharedMemory) }}</strong>
            <span>可见范围</span>
            <strong>{{ scopeVisibilityNote(selectedSharedMemory) }}</strong>
            <span>发布理由</span>
            <strong>{{ selectedSharedMemory.publish_reason || "暂无记录" }}</strong>
          </div>
        </section>
        <section class="detail-section">
          <h3>被引用记录</h3>
          <p class="context-empty context-empty-compact">{{ memoryGovernanceHint }}</p>
        </section>
        <section class="detail-section detail-technical-section">
          <details>
            <summary>技术信息（ID）</summary>
            <pre>{{ memoryTechnicalInfo(selectedSharedMemory) }}</pre>
          </details>
        </section>
        <div class="detail-actions" v-if="canReviewMemory && selectedSharedMemory.status !== 'superseded'">
          <el-button size="small" @click="disputeSharedMemory(selectedSharedMemory)">质疑</el-button>
          <el-button size="small" type="primary" @click="confirmCandidateMemory(selectedSharedMemory)">修订发布</el-button>
        </div>
      </div>
    </el-drawer>
    <el-dialog
      v-model="memoryPublishDialogVisible"
      class="memory-publish-dialog"
      title="确认发布记忆"
      width="640px"
      destroy-on-close
    >
      <div v-if="selectedCandidateMemory" class="memory-publish-body">
        <div class="memory-publish-summary">
          <span :class="['memory-category-badge', `memory-category-${memoryPublishPreview?.memory_category || 'meeting_memory'}`]">
            {{ memoryCategoryLabel(memoryPublishPreview?.memory_category) }}
          </span>
          <span>{{ memoryTypeLabel(memoryPublishPreview?.memory_type) }}</span>
          <span>推荐：{{ memoryScopeLabel(memoryPublishPreview?.recommended_scope) }}</span>
          <span>来源：本会议室 · {{ sourceMessageLabel(selectedCandidateMemory) }}</span>
        </div>
        <el-alert
          v-if="memoryPublishPreview?.memory_type === 'risk_insight'"
          type="warning"
          show-icon
          :closable="false"
          title="风险洞察是预测候选；只有绑定产品、批次或质检任务后，才能发布到稳定对象、质检风险库或预警中心。"
        />
        <el-alert
          v-else-if="!isBusinessMemory(memoryPublishPreview)"
          type="info"
          show-icon
          :closable="false"
          title="非业务记忆只能保存到本会议室，不会发布到其他业务对象。"
        />
        <el-alert
          v-else
          type="warning"
          show-icon
          :closable="false"
          title="业务记忆只作为 Agent 上下文和历史经验，不会修改质检任务、人工审核结论或标准依据。"
        />
        <div v-if="memoryPublishPreview?.warnings?.length" class="memory-warning-list">
          <span v-for="warning in memoryPublishPreview.warnings" :key="warning">{{ warning }}</span>
        </div>
        <el-form label-position="top" class="memory-publish-form">
          <el-form-item label="标题">
            <el-input v-model="memoryPublishForm.title" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="内容">
            <el-input v-model="memoryPublishForm.content" type="textarea" :rows="5" maxlength="4000" show-word-limit />
          </el-form-item>
        </el-form>
        <div class="memory-publish-decision">
          <div v-for="row in publishDecisionRows(memoryPublishPreview)" :key="row.label" class="memory-publish-decision-row">
            <span>{{ row.label }}</span>
            <strong>{{ row.value }}</strong>
          </div>
        </div>
        <div v-if="memoryPublishPreview?.memory_type === 'risk_insight'" class="memory-risk-preview">
          <span>风险：{{ riskLevelLabel(memoryPublishPreview.risk_level) }}</span>
          <span v-if="forecastWindowLabel(memoryPublishPreview)">关注：{{ forecastWindowLabel(memoryPublishPreview) }}</span>
          <span>发布回本会议室不会生成预警。</span>
        </div>
        <el-form label-position="top" class="memory-publish-form">
          <el-form-item label="发布范围">
            <el-select
              :model-value="selectedMemoryPublishOptionValue()"
              class="memory-publish-scope-select"
              @update:model-value="applyMemoryPublishOption"
            >
              <el-option
                v-for="option in memoryPublishScopeOptions"
                :key="`${option.value}:${option.scopeId}`"
                :label="option.label"
                :value="`${option.value}:${option.scopeId}`"
              >
                <div class="memory-scope-option">
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.note }}</small>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="发布理由">
            <el-input
              v-model="memoryPublishForm.publish_reason"
              type="textarea"
              :rows="2"
              maxlength="1000"
              show-word-limit
              placeholder="说明为什么要保存或发布这条记忆，便于后续追溯"
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="memoryPublishDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="memoryPublishSubmitting"
          :disabled="!memoryPublishForm.title.trim() || !memoryPublishForm.content.trim()"
          @click="submitMemoryPublish"
        >
          发布记忆
        </el-button>
      </template>
    </el-dialog>
    <ImagePreviewDialog v-model="imagePreviewVisible" :src="previewImage.url" :title="previewImage.name" />
  </div>
</template>

<style scoped>
.meeting-page {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: var(--left-panel-width, 260px) minmax(520px, 1fr) var(--right-panel-width, 300px);
  gap: 12px;
  transition: grid-template-columns 180ms ease;
}

.meeting-page.is-resizing-left,
.meeting-page.is-resizing-right {
  cursor: col-resize;
  user-select: none;
}

.meeting-page.is-resizing-left .meeting-room,
.meeting-page.is-resizing-right .meeting-room {
  pointer-events: none;
}

.meeting-sidebar,
.meeting-room,
.meeting-context {
  min-height: 0;
  border: 1px solid #e4e4e7;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.meeting-sidebar {
  position: relative;
  overflow: hidden;
}

.meeting-context {
  position: relative;
  overflow: visible;
}

.panel-content {
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  transition: opacity 150ms ease, visibility 150ms ease;
}

.context-panel-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 46px 12px 12px;
}

.sidecar-tabs {
  position: sticky;
  z-index: 6;
  top: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid #e4e4e7;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
}

.sidecar-tab {
  min-width: 0;
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.sidecar-tab:hover,
.sidecar-tab-active {
  background: #18181b;
  color: #fff;
}

.sidecar-tab strong,
.private-sidecar-count {
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(24, 24, 27, 0.08);
  font-size: 11px;
  line-height: 1;
}

.sidecar-tab-active strong {
  background: rgba(255, 255, 255, 0.18);
}

.sidecar-pane {
  flex: 1 1 auto;
  min-height: 0;
}

.context-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-sidecar,
.private-sidecar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
}

.agent-sidecar {
  border-color: #bfdbfe;
  background: #f8fbff;
}

.agent-sidecar-head,
.private-sidecar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-sidecar-head h2,
.private-sidecar-head h2 {
  margin: 0;
  color: #111827;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0;
}

.agent-live-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: #fff;
  color: #475569;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.agent-live-pill-active {
  border-color: #bfdbfe;
  color: #1d4ed8;
}

.agent-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.agent-live-pill-active .agent-live-dot {
  background: #2563eb;
  animation: blink 1.4s infinite both;
}

.agent-thread-list,
.private-message-list {
  display: grid;
  align-content: start;
  gap: 8px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.agent-empty,
.private-empty {
  padding: 16px 8px;
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.agent-qa-group {
  position: relative;
  display: grid;
  gap: 8px;
  padding: 10px 0 12px 16px;
}

.agent-qa-group::before {
  content: "";
  position: absolute;
  top: 34px;
  bottom: 18px;
  left: 4px;
  width: 2px;
  border-radius: 999px;
  background: linear-gradient(180deg, #c7d2fe, #bfdbfe);
}

.agent-qa-index {
  width: fit-content;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 900;
}

.agent-thread-item {
  position: relative;
  display: grid;
  gap: 7px;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #fff;
}

.agent-thread-item::before {
  content: "";
  position: absolute;
  top: 18px;
  left: -16px;
  width: 8px;
  height: 8px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #94a3b8;
  box-shadow: 0 0 0 2px #cbd5e1;
}

.agent-thread-question {
  border-color: #e4e4e7;
  background: #fafafa;
}

.agent-thread-question::before {
  background: #64748b;
}

.agent-thread-reply {
  border-color: #bfdbfe;
  background: #f8fbff;
}

.agent-thread-reply::before {
  background: #2563eb;
  box-shadow: 0 0 0 2px #bfdbfe;
}

.agent-thread-streaming {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.agent-thread-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-thread-meta span {
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 800;
}

.agent-thread-question .agent-thread-meta span {
  color: #52525b;
}

.agent-thread-reply .agent-thread-meta span {
  color: #2563eb;
}

.agent-thread-meta time {
  flex: 0 0 auto;
  color: #94a3b8;
  font-size: 11px;
}

.agent-thread-body {
  color: #111827;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-awaiting-reply {
  padding: 8px 10px;
  border: 1px dashed #bfdbfe;
  border-radius: 8px;
  background: #f8fbff;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.agent-message-edit {
  display: grid;
  gap: 8px;
}

.agent-message-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.agent-composer {
  display: grid;
  gap: 8px;
  margin-top: auto;
}

.agent-composer-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
  min-width: 0;
}

.agent-composer textarea {
  width: 100%;
  min-height: 38px;
  max-height: 96px;
  padding: 9px 10px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #fff;
  color: #111827;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.55;
  resize: none;
  outline: none;
}

.private-launcher {
  display: grid;
  gap: 8px;
}

.private-launcher-list {
  display: grid;
  gap: 6px;
}

.private-launcher-row {
  width: 100%;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 46px;
  padding: 7px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fff;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.private-launcher-row:hover,
.private-launcher-row-active {
  border-color: #d4d4d8;
  background: #f8fafc;
}

.private-launcher-row span:nth-child(2) {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.private-launcher-row strong {
  overflow: hidden;
  color: #111827;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.private-launcher-row small {
  color: #71717a;
  font-size: 11px;
}

.private-dialog-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.private-dialog-title strong {
  color: #111827;
  font-size: 16px;
  font-weight: 900;
}

.private-dialog-title span {
  overflow: hidden;
  color: #71717a;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.private-floating-window {
  position: fixed;
  z-index: 40;
  display: grid;
  grid-template-rows: 46px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid #d4d4d8;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 22px 80px rgba(15, 23, 42, 0.22);
}

.private-floating-minimized {
  grid-template-rows: 48px;
}

.private-floating-maximized {
  border-radius: 10px;
}

.private-floating-titlebar {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 10px 0 14px;
  border-bottom: 1px solid #e4e4e7;
  background: #fafafa;
  cursor: move;
  touch-action: none;
}

.private-floating-minimized .private-floating-titlebar {
  border-bottom: 0;
}

.private-window-controls {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.private-window-controls button {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #52525b;
  cursor: pointer;
}

.private-window-controls button:hover {
  background: #eceff3;
  color: #111827;
}

.private-window-controls svg {
  width: 15px;
  height: 15px;
}

.private-window-resizer {
  position: absolute;
  z-index: 2;
  border: 0;
  background: transparent;
  padding: 0;
  touch-action: none;
}

.private-window-resizer-edge {
  border-radius: 999px;
}

.private-window-resizer-n,
.private-window-resizer-s {
  left: 14px;
  right: 14px;
  height: 8px;
  cursor: ns-resize;
}

.private-window-resizer-n {
  top: -4px;
}

.private-window-resizer-s {
  bottom: -4px;
}

.private-window-resizer-e,
.private-window-resizer-w {
  top: 14px;
  bottom: 14px;
  width: 8px;
  cursor: ew-resize;
}

.private-window-resizer-e {
  right: -4px;
}

.private-window-resizer-w {
  left: -4px;
}

.private-window-resizer-corner {
  width: 18px;
  height: 18px;
}

.private-window-resizer-ne {
  top: -5px;
  right: -5px;
  cursor: nesw-resize;
}

.private-window-resizer-nw {
  top: -5px;
  left: -5px;
  cursor: nwse-resize;
}

.private-window-resizer-se {
  right: -5px;
  bottom: -5px;
  cursor: nwse-resize;
}

.private-window-resizer-sw {
  bottom: -5px;
  left: -5px;
  cursor: nesw-resize;
}

.private-window-resizer-se::after {
  content: "";
  position: absolute;
  right: 5px;
  bottom: 5px;
  width: 8px;
  height: 8px;
  border-right: 2px solid #a1a1aa;
  border-bottom: 2px solid #a1a1aa;
}

.private-dialog-body {
  min-height: 0;
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
}

.private-dialog-roster {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  padding: 12px;
  border-right: 1px solid #e4e4e7;
  background: #fafafa;
}

.private-dialog-thread {
  padding: 12px;
  background: #fff;
}

.private-member-row {
  width: 100%;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-height: 44px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: #fff;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.private-member-row svg {
  display: none;
}

.private-member-row:hover,
.private-member-row-active {
  border-color: #d4d4d8;
  background: #f8fafc;
}

.private-member-row span:nth-child(2) {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.private-member-row strong,
.private-thread-head strong {
  overflow: hidden;
  color: #111827;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.private-member-row small,
.private-thread-head small {
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.private-thread-pane {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 7px;
  overflow: hidden;
}

.private-thread-head {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.private-thread-head div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.private-chat-message {
  max-width: min(92%, 420px);
  display: grid;
  gap: 4px;
  justify-self: start;
  min-width: 0;
}

.private-chat-message-own {
  justify-self: end;
}

.private-chat-message small {
  color: #71717a;
  font-size: 11px;
}

.private-chat-message p {
  margin: 0;
  padding: 7px 9px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
  color: #18181b;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.private-chat-message-own p {
  border-color: #18181b;
  background: #18181b;
  color: #fff;
}

.private-message-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}

.private-message-actions button {
  border: 0;
  background: transparent;
  color: #71717a;
  font: inherit;
  font-size: 11px;
  line-height: 1.4;
}

.private-message-actions button {
  padding: 0;
  cursor: pointer;
}

.private-message-actions button:hover {
  color: #111827;
  text-decoration: underline;
}

.private-message-actions button:disabled {
  color: #a1a1aa;
  cursor: not-allowed;
  text-decoration: none;
}

.private-message-actions button:disabled:hover {
  color: #a1a1aa;
  text-decoration: none;
}

.private-message-recalled-line,
.message-recalled-line {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: fit-content;
  max-width: 100%;
  min-height: 28px;
  padding: 3px 5px 3px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fafafa;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.35;
  white-space: nowrap;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
}

.private-chat-message-own .private-message-recalled-line {
  justify-self: end;
}

.private-message-recalled-line span,
.message-recalled-line span {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}

.private-message-recalled-line button,
.message-recalled-line button {
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid #d4d4d8;
  border-radius: 999px;
  background: #fff;
  color: #374151;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
}

.private-message-recalled-line button:hover,
.message-recalled-line button:hover {
  border-color: #a1a1aa;
  color: #111827;
  background: #f4f4f5;
}

.private-message-edit {
  display: grid;
  gap: 7px;
  min-width: min(240px, 100%);
}

.private-message-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.private-chat-composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 7px;
  align-items: end;
  padding-top: 8px;
  border-top: 1px solid #f4f4f5;
  min-width: 0;
}

.private-chat-composer textarea {
  min-width: 0;
  width: 100%;
  min-height: 38px;
  max-height: 88px;
  padding: 8px 9px;
  border: 1px solid #d4d4d8;
  border-radius: 8px;
  color: #18181b;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  outline: none;
}

.private-composer-actions {
  display: grid;
  grid-auto-flow: column;
  align-items: center;
  gap: 6px;
}

.private-composer-attachments {
  grid-column: 1 / -1;
  min-width: 0;
}

.private-thread-avatar {
  width: 30px;
  height: 30px;
  font-size: 12px;
}

.panel-toggle {
  position: absolute;
  z-index: 8;
  top: 10px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #52525b;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease, transform 150ms ease;
}

.panel-toggle:hover {
  border-color: #18181b;
  color: #111827;
}

.panel-toggle svg {
  width: 15px;
  height: 15px;
}

.panel-toggle-left {
  right: 8px;
}

.panel-toggle-right {
  left: 8px;
  right: auto;
}

.panel-collapsed {
  display: flex;
  align-items: center;
  justify-content: center;
}

.panel-collapsed .panel-content {
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
}

.panel-collapsed .panel-toggle {
  left: 50%;
  right: auto;
  transform: translateX(-50%);
}

.panel-collapsed-label {
  display: none;
  color: #71717a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  line-height: 1;
  writing-mode: vertical-rl;
}

.panel-collapsed .panel-collapsed-label {
  display: block;
}

.panel-resizer {
  position: absolute;
  z-index: 7;
  top: 0;
  bottom: 0;
  width: 12px;
  cursor: col-resize;
}

.panel-resizer::after {
  content: "";
  position: absolute;
  top: 14px;
  bottom: 14px;
  width: 2px;
  border-radius: 999px;
  background: transparent;
  transition: background 150ms ease;
}

.panel-resizer:hover::after,
.meeting-page.is-resizing-left .panel-resizer-left::after,
.meeting-page.is-resizing-right .panel-resizer-right::after {
  background: #18181b;
}

.panel-resizer-left {
  right: -7px;
}

.panel-resizer-left::after {
  right: 5px;
}

.panel-resizer-right {
  left: -7px;
}

.panel-resizer-right::after {
  left: 5px;
}

.sidebar-section {
  padding: 18px;
  border-bottom: 1px solid #f4f4f5;
}

.section-kicker {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sidebar-section h1,
.room-header h2,
.room-list h2 {
  color: #111827;
  font-weight: 700;
  letter-spacing: 0;
}

.sidebar-section h1 {
  margin-top: 8px;
  font-size: 18px;
}

.section-copy {
  margin-top: 6px;
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
}

.hub-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-top: 16px;
  padding: 4px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #f8fafc;
}

.hub-mode button {
  min-height: 32px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #52525b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease, box-shadow 150ms ease;
}

.hub-mode button:hover,
.hub-mode-active {
  background: #fff;
  color: #111827;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

label span {
  color: #3f3f46;
  font-size: 13px;
  font-weight: 500;
}

.room-list {
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.room-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.room-list h2 {
  font-size: 15px;
}

.room-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: background 150ms ease, border-color 150ms ease, color 150ms ease;
}

.room-item:hover,
.room-item-active {
  border-color: #18181b;
  background: #18181b;
  color: #fff;
}

.room-item-head {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.room-title {
  min-width: 0;
  color: inherit;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.room-delete-button {
  flex: 0 0 auto;
  opacity: 0;
  margin-top: -4px;
  margin-right: -6px;
  color: #dc2626;
}

.room-item:hover .room-delete-button,
.room-item:focus-visible .room-delete-button,
.room-item-active .room-delete-button {
  opacity: 1;
}

.room-item:hover .room-delete-button,
.room-item-active .room-delete-button {
  color: #fecaca;
}

.room-meta,
.empty-note {
  color: #71717a;
  font-size: 12px;
}

.room-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.room-item-active .room-meta,
.room-item:hover .room-meta {
  color: #d4d4d8;
}

/* Main room */
.meeting-room {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.room-header {
  min-height: 66px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #e4e4e7;
  flex-wrap: wrap;
}

.room-header h2 {
  margin-top: 4px;
  font-size: 18px;
}

.room-title-block {
  flex: 1 1 240px;
  min-width: 0;
}

.room-submeta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.host-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid #d6d3d1;
  border-radius: 999px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  font-weight: 600;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 600;
}

.status-closed {
  background: #f4f4f5;
  color: #52525b;
}

.status-archived {
  background: #ecfeff;
  color: #0e7490;
}

.room-type-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

.room-header-right {
  display: flex;
  flex: 1 1 360px;
  flex-direction: column;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 8px;
}

.room-toolbar-main,
.room-toolbar-admin {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.room-toolbar-admin {
  color: #71717a;
}

.room-toolbar-admin :deep(.el-button) {
  margin-left: 0;
}

.room-code {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 999px;
  background: #fafafa;
}

.room-code span,
.room-hint {
  color: #71717a;
  font-size: 12px;
}

.room-code strong {
  color: #18181b;
  font-size: 14px;
  font-weight: 700;
}

/* Invitation */
.invite-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.invite-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.invite-panel-head span {
  color: #71717a;
  font-size: 12px;
}

.invite-panel-head strong {
  color: #111827;
  font-size: 18px;
  letter-spacing: 0.04em;
}

.invite-note {
  color: #71717a;
  font-size: 13px;
  line-height: 1.6;
}

.invite-link {
  padding: 8px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}

.invite-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Members */
.member-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.member-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.member-panel-head span {
  color: #111827;
  font-size: 14px;
  font-weight: 700;
}

.member-panel-head strong {
  color: #71717a;
  font-size: 12px;
}

.member-panel-empty {
  padding: 18px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.member-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #fafafa;
}

.member-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #18181b;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.member-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.member-main strong {
  overflow: hidden;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-main small {
  color: #a1a1aa;
  font-size: 11px;
}

.member-role {
  padding: 2px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #71717a;
  font-size: 11px;
  font-weight: 600;
}

.member-role-host {
  background: #fff7ed;
  color: #9a3412;
}

.member-role-select {
  width: 86px;
}

.member-role-select :deep(.el-select__wrapper) {
  min-height: 26px;
  padding: 0 7px;
  border-radius: 999px;
  box-shadow: 0 0 0 1px #e4e4e7 inset;
}

.member-role-select :deep(.el-select__selected-item) {
  font-size: 11px;
  font-weight: 600;
}

/* Messages */
.message-list {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
}

.empty-state {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #71717a;
  text-align: center;
}

.empty-state svg {
  width: 48px;
  height: 48px;
  color: #a1a1aa;
}

.empty-state h3 {
  margin-top: 16px;
  color: #111827;
  font-size: 18px;
  font-weight: 700;
}

.empty-state p {
  max-width: 440px;
  margin-top: 8px;
  color: #71717a;
  line-height: 1.7;
}

.message-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  margin-bottom: 14px;
}

.message-row-own {
  align-items: flex-end;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #a1a1aa;
  font-size: 12px;
}

.message-meta span {
  color: #52525b;
  font-weight: 600;
}

.agent-tag {
  font-size: 10px;
  font-weight: 700;
  color: #2563eb;
  background: #dbeafe;
  padding: 1px 5px;
  border-radius: 4px;
}

.system-tag {
  font-size: 10px;
  font-weight: 700;
  color: #047857;
  background: #d1fae5;
  padding: 1px 5px;
  border-radius: 4px;
}

.quoted-message {
  max-width: min(640px, 80%);
  padding: 7px 10px;
  border-left: 3px solid #a3a3a3;
  border-radius: 6px;
  background: #f5f5f5;
  color: #52525b;
  font-size: 12px;
  line-height: 1.5;
}

.message-bubble {
  max-width: min(720px, 82%);
  padding: 11px 14px;
  border: 1px solid #e4e4e7;
  border-radius: 16px 16px 16px 5px;
  background: #fafafa;
  color: #111827;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-row-own .message-bubble {
  border-color: transparent;
  border-radius: 16px 16px 5px 16px;
  background: #1f2937;
  color: #fff;
}

.message-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.message-edited-mark {
  display: block;
  margin-top: 4px;
  color: #71717a;
  font-size: 11px;
}

.message-attachments,
.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.message-attachments {
  max-width: min(720px, 82%);
  margin-top: 2px;
  align-items: flex-start;
}

.message-row-own .message-attachments {
  justify-content: flex-end;
}

.att-link {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-height: 24px;
  padding: 2px 9px;
  border: 0;
  border-radius: 999px;
  background: #e5e7eb;
  color: #374151;
  font: inherit;
  font-size: 12px;
  line-height: 1.45;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.att-link:hover {
  background: #d1d5db;
}

.att-image-button {
  position: relative;
  display: block;
  width: min(220px, 58vw);
  aspect-ratio: 4 / 3;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 8px;
  background: #111827;
  cursor: zoom-in;
  font: inherit;
  line-height: 0;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.12);
}

.att-image-button img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: #f3f4f6;
  transition: transform 0.18s ease;
}

.att-image-button:hover img,
.att-image-button:focus-visible img {
  transform: scale(1.03);
}

.att-image-button:focus-visible {
  outline: 2px solid #60a5fa;
  outline-offset: 2px;
}

.att-image-name {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 22px 9px 8px;
  overflow: hidden;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: linear-gradient(to top, rgba(15, 23, 42, 0.82), rgba(15, 23, 42, 0));
}

.ai-thinking-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 13px;
}

.ai-thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #2563eb;
  animation: blink 1.4s infinite both;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}

/* Composer */
.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  padding: 12px;
  border-top: 1px solid #e4e4e7;
  background: #fff;
}

.composer-quote {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
  color: #52525b;
  font-size: 12px;
}

.composer-attachments {
  grid-column: 1 / -1;
}

.composer-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.composer-quote span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mention-bar {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mention-chip {
  border: 1px solid #d1d5db;
  border-radius: 999px;
  background: #fff;
  color: #374151;
  padding: 4px 10px;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
}

.mention-chip:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}

.mention-menu {
  grid-column: 1 / -1;
  display: grid;
  gap: 6px;
  max-width: 420px;
  padding: 8px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.14);
}

.mention-menu-head {
  padding: 0 4px 3px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.mention-option {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.mention-option:hover,
.mention-option-active {
  border-color: #dbeafe;
  background: #eff6ff;
}

.mention-option span {
  color: #111827;
  font-size: 13px;
  font-weight: 900;
}

.mention-option small {
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
}

.mention-empty {
  padding: 8px 10px;
  color: #94a3b8;
  font-size: 12px;
}

.composer-textarea {
  width: 100%;
  min-height: 40px;
  max-height: 120px;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  outline: none;
  font-family: inherit;
  transition: border-color 150ms ease;
}

.composer-textarea:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.composer-textarea:disabled {
  background: #f9fafb;
  color: #9ca3af;
}

/* Context panel */
.context-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
}

.context-card-collapsed {
  gap: 0;
}

.context-card-collapsed > :not(.context-head) {
  display: none !important;
}

.context-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.context-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.context-head-actions :deep(.el-button) {
  margin-left: 0;
}

.context-collapse-button {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
  color: #52525b;
  cursor: pointer;
}

.context-collapse-button svg {
  width: 14px;
  height: 14px;
}

.context-head h2 {
  margin-top: 3px;
  color: #111827;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.context-empty {
  padding: 14px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.context-empty-compact {
  padding: 6px 0;
  text-align: left;
}

.boundary-card {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.context-note {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.boundary-identity {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.boundary-identity span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 7px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}

.boundary-block {
  display: grid;
  gap: 7px;
}

.boundary-block > strong {
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

.business-binding-list {
  display: grid;
  gap: 7px;
}

.business-binding-row {
  display: grid;
  gap: 5px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.business-binding-row span {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
}

.business-binding-row div {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.business-binding-row b {
  display: inline-flex;
  max-width: 100%;
  min-height: 21px;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.domain-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.domain-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-height: 22px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.domain-chip-allowed {
  background: #dcfce7;
  color: #166534;
}

.domain-chip-denied {
  background: #f4f4f5;
  color: #71717a;
}

.agent-permission-list {
  display: grid;
  gap: 7px;
}

.agent-permission-item {
  display: grid;
  gap: 2px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.agent-permission-item strong {
  color: #111827;
  font-size: 12px;
}

.agent-permission-item small {
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.audit-card {
  background: #fff;
}

.audit-item {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 9px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
  color: inherit;
  font: inherit;
  text-align: left;
}

.audit-item-clickable {
  cursor: pointer;
}

.audit-item-clickable:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.audit-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.audit-item-head time {
  color: #a1a1aa;
  font-size: 11px;
}

.audit-decision {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 11px;
  font-weight: 700;
}

.audit-allowed {
  background: #dcfce7;
  color: #166534;
}

.audit-partial {
  background: #fef3c7;
  color: #92400e;
}

.audit-denied {
  background: #fee2e2;
  color: #991b1b;
}

.audit-item p {
  color: #111827;
  font-size: 12px;
  line-height: 1.5;
}

.audit-item small {
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.memory-item,
.action-item,
.shared-memory {
  padding: 10px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.memory-title-row,
.action-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.memory-title-row strong,
.action-item strong,
.shared-memory strong {
  color: #111827;
  font-size: 13px;
}

.memory-title-row span {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 700;
}

.memory-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.memory-category-badge,
.memory-status-disputed {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
}

.memory-category-business_memory {
  background: #dcfce7;
  color: #166534;
}

.memory-category-meeting_memory {
  background: #e0f2fe;
  color: #075985;
}

.memory-category-rejected_noise,
.memory-status-disputed {
  background: #fef3c7;
  color: #92400e;
}

.shared-memory-disputed {
  border-color: #fde68a;
  background: #fffbeb;
}

.shared-memory-superseded {
  opacity: 0.68;
}

.memory-item p,
.action-item p,
.shared-memory p {
  margin-top: 6px;
  color: #52525b;
  font-size: 12px;
  line-height: 1.6;
}

.memory-source {
  display: block;
  margin-top: 6px;
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.memory-warning-list {
  display: grid;
  gap: 5px;
  margin-top: 8px;
}

.memory-warning-list span {
  padding: 6px 8px;
  border: 1px solid #fde68a;
  border-radius: 7px;
  background: #fffbeb;
  color: #92400e;
  font-size: 11px;
  line-height: 1.45;
}

.risk-insight-strip,
.memory-risk-preview,
.recommended-action-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.risk-insight-strip span,
.memory-risk-preview span,
.recommended-action-list span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(14, 116, 144, 0.09);
  color: #155e75;
  font-size: 11px;
  line-height: 1.35;
}

.memory-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.detail-drawer-body {
  display: grid;
  gap: 14px;
}

.detail-section {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 10px;
  background: #fff;
}

.detail-section h3 {
  margin: 0;
  color: #111827;
  font-size: 13px;
  font-weight: 900;
}

.detail-main-text {
  margin: 0;
  color: #374151;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 7px 10px;
  align-items: start;
}

.detail-meta-grid span {
  color: #71717a;
  font-size: 12px;
  font-weight: 800;
}

.detail-meta-grid strong {
  min-width: 0;
  color: #111827;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.detail-section pre {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 9px;
  border-radius: 8px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.detail-technical-section {
  background: #fafafa;
}

.detail-technical-section details {
  display: grid;
  gap: 8px;
}

.detail-technical-section summary {
  color: #71717a;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}

.detail-technical-section pre {
  margin-top: 8px;
}

.detail-ref-list {
  display: grid;
  gap: 6px;
}

.detail-ref-list button {
  min-height: 30px;
  padding: 5px 8px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
  color: #1d4ed8;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  text-align: left;
  cursor: pointer;
  overflow-wrap: anywhere;
}

.detail-ref-list button:hover {
  border-color: #93c5fd;
  background: #dbeafe;
}

.detail-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.memory-publish-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}

.memory-publish-body,
.memory-publish-form {
  display: grid;
  gap: 12px;
}

.memory-publish-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.memory-publish-decision {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
}

.memory-publish-decision-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.memory-publish-decision-row span {
  color: #71717a;
  font-size: 12px;
  font-weight: 800;
}

.memory-publish-decision-row strong {
  color: #27272a;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.memory-publish-scope-select {
  width: 100%;
}

.memory-scope-option {
  display: grid;
  gap: 2px;
  line-height: 1.25;
}

.memory-scope-option small {
  color: #71717a;
  font-size: 11px;
}

.action-create {
  display: grid;
  gap: 8px;
}

.action-item small {
  display: inline-block;
  margin-top: 6px;
  color: #71717a;
  font-size: 11px;
}

.action-done {
  opacity: 0.62;
}

/* Responsive */
@media (max-width: 920px) {
  .meeting-page {
    grid-template-columns: 1fr;
    gap: 12px;
    overflow-y: auto;
  }

  .meeting-sidebar {
    min-height: 520px;
  }

  .meeting-room {
    min-height: 620px;
  }

  .meeting-context {
    min-height: 420px;
  }

  .panel-toggle,
  .panel-resizer,
  .panel-collapsed-label {
    display: none;
  }

  .panel-collapsed {
    display: block;
  }

  .panel-collapsed .panel-content {
    visibility: visible;
    opacity: 1;
    pointer-events: auto;
  }

  .context-panel-content {
    padding: 12px;
  }

  .private-dialog-body {
    height: min(76vh, 680px);
    min-height: 460px;
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .private-dialog-roster {
    max-height: 150px;
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: minmax(150px, 1fr);
    overflow-x: auto;
    overflow-y: hidden;
    border-right: 0;
    border-bottom: 1px solid #e4e4e7;
  }

  .private-dialog-thread {
    min-height: 0;
  }
}

@media (max-width: 640px) {
  .meeting-page {
    padding: 10px;
  }

  .composer {
    grid-template-columns: 1fr;
  }

  .private-dialog-body {
    min-height: 420px;
  }

  .private-chat-composer {
    grid-template-columns: 1fr;
  }

  .private-composer-actions {
    justify-content: end;
  }
}
</style>
