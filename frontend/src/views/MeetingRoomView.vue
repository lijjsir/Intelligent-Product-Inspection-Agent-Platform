<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, ChatDotRound, Check, Close, CopyDocument, Delete, EditPen, FullScreen, Key, MagicStick, Minus, Paperclip, Plus, Promotion, RefreshRight, ScaleToOriginal, Share, User } from "@element-plus/icons-vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type StyleValue } from "vue";
import { useRouter } from "vue-router";
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
const router = useRouter();
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
const privateRosterCollapsed = ref(false);
const privateRosterShowAll = ref(false);
const privateMemberSearch = ref("");
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
  target_key: "current_meeting_room" as MemoryPublishTargetKey,
  title: "",
  content: "",
  scope: "meeting_room" as MeetingMemoryPublishScope,
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
type MemoryAffectedObjects = {
  inspection_task_ids: string[];
  product_ids: string[];
  batch_nos: string[];
  standard_ids: string[];
};
type MemoryPublishTargetKey =
  | "current_meeting_room"
  | "target_meeting_room"
  | "org_space"
  | "user"
  | "agent";
type MemoryPublishTargetOption = {
  label: string;
  value: string;
  description?: string;
};
type MemoryPublishScopeOption = {
  key: MemoryPublishTargetKey;
  label: string;
  value: MeetingMemoryPublishScope;
  scopeId: string;
  requiresTargetId?: boolean;
  targetLabel?: string;
  targetPlaceholder?: string;
  targetOptions?: MemoryPublishTargetOption[];
  targetEmptyText?: string;
  note: string;
};

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
  boundary: true,
  candidateMemory: true,
  confirmedMemory: false,
  actions: true,
  audit: true,
  events: true,
});

const memoryCategoryLabels: Record<string, string> = {
  business_memory: "专业经验",
  meeting_memory: "会议内记忆",
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
  collab_thread: "协作通道",
  user: "个人记忆",
  agent: "Agent 记忆",
  org_space: "组织共享空间",
  workspace: "组织共享空间",
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
    { id: "general_agent", agent_name: "会议Agent", description: "总结会议、回答问题、提取候选记忆" },
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
  return meetingRoomStatusLabel(store.activeRoom?.status || "") || "未选择";
});
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
const allPrivateMessages = computed(() => store.activeRoomMessages.filter((message) => Boolean(privatePartnerId(message))));
const privateConversationPartnerIds = computed(() => new Set(allPrivateMessages.value.map(privatePartnerId).filter(Boolean)));
const privateConversationCount = computed(() => privateConversationPartnerIds.value.size);
const privateRosterMembers = computed(() => {
  const query = privateMemberSearch.value.trim().toLowerCase();
  const shouldShowAll = privateRosterShowAll.value || Boolean(query) || privateConversationPartnerIds.value.size === 0;
  return privatePartners.value.filter((member) => {
    const isSelected = member.user_id === activePrivateUserId.value;
    const hasConversation = privateConversationPartnerIds.value.has(member.user_id);
    const matchesQuery = !query
      || member.username.toLowerCase().includes(query)
      || member.user_id.toLowerCase().includes(query);
    return matchesQuery && (shouldShowAll || hasConversation || isSelected);
  });
});
const privateRosterEmptyText = computed(() => {
  if (privateMemberSearch.value.trim()) return "没有匹配成员";
  if (!privatePartners.value.length) return "暂无成员";
  return "暂无私聊会话，可搜索成员发起私聊";
});
const hiddenPrivatePartnerCount = computed(() => Math.max(privatePartners.value.length - privateRosterMembers.value.length, 0));
const privateThreadSubtitle = computed(() => {
  if (!store.activeRoom) return "未进入会议";
  if (!currentPrivateMember.value) return privatePartners.value.length ? "选择会议成员开始私聊" : "当前会议暂无其他成员";
  return `${privateMessagesByUser(currentPrivateMember.value.user_id).length} 条会议内私聊`;
});
const visibleAgentPanelMessages = computed(() => store.agentPanelMessages.filter(canShowInAgentPanel));
const summaryMessages = computed(() => store.systemPanelMessages.filter((message) => message.message_type === "summary"));
const latestSummaryMessage = computed(() => summaryMessages.value[summaryMessages.value.length - 1] || null);
const agentConversationGroups = computed(() => {
  const groups: Array<{ id: string; question: MeetingMessage | null; replies: MeetingMessage[] }> = [];
  let currentGroup: { id: string; question: MeetingMessage | null; replies: MeetingMessage[] } | null = null;
  for (const message of visibleAgentPanelMessages.value) {
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
const contextBoundary = computed(() => {
  const preview = store.contextPreview;
  const roomConfiguredDomains = preview?.room_configured_domains?.length
    ? preview.room_configured_domains
    : store.activeRoom?.allowed_data_domains || [];
  const effectiveDomains = preview?.effective_domains?.length
    ? preview.effective_domains
    : preview?.allowed_domains || roomConfiguredDomains;
  return {
    effectiveDomains,
    roomConfiguredDomains,
    sensitiveDomains: preview?.sensitive_domains || [],
    deniedReasons: preview?.denied_reasons || {},
    agentPermissions: preview?.agent_permissions || [],
    guardrails: preview?.guardrails || [],
    queryExamples: preview?.query_examples || [],
  };
});
const domainGroups = computed(() => buildDomainGroups(contextBoundary.value.roomConfiguredDomains));
const effectiveDomainGroups = computed(() => buildDomainGroups(contextBoundary.value.effectiveDomains));
const sensitiveDomainGroups = computed(() => buildDomainGroups(contextBoundary.value.sensitiveDomains));
const memoryPublishPreview = computed<MeetingMemory | null>(() => buildMemoryPublishPreview(selectedCandidateMemory.value));
const memoryPublishScopeOptions = computed(() => buildMemoryPublishScopeOptions(memoryPublishPreview.value));
const selectedMemoryPublishScopeOption = computed(() => (
  memoryPublishScopeOptions.value.find((item) => item.key === memoryPublishForm.target_key) || memoryPublishScopeOptions.value[0]
));
const memoryPublishTargetOptions = computed(() => selectedMemoryPublishScopeOption.value?.targetOptions || []);
const memoryPublishTargetRequired = computed(() => Boolean(selectedMemoryPublishScopeOption.value?.requiresTargetId));
const selectedMemoryPublishTarget = computed(() => (
  memoryPublishTargetOptions.value.find((item) => item.value === memoryPublishForm.scope_id) || null
));
const memoryPublishTargetPreview = computed(() => {
  const option = selectedMemoryPublishScopeOption.value;
  if (!option) return null;
  const requiresTarget = Boolean(option.requiresTargetId);
  const target = selectedMemoryPublishTarget.value;
  return {
    type: memoryPublishTargetTypeLabel(option.key),
    label: requiresTarget ? target?.label || "请选择共享目标" : option.label,
    description: requiresTarget ? target?.description || option.targetPlaceholder || "从可见列表中选择目标" : option.note,
    pending: requiresTarget && !target,
  };
});
const memoryPublishSubmitDisabled = computed(() => (
  !memoryPublishForm.title.trim()
    || !memoryPublishForm.content.trim()
    || (memoryPublishTargetRequired.value && !memoryPublishForm.scope_id.trim())
));
const memoryPublishSubmitText = computed(() => {
  if (memoryPublishForm.target_key === "current_meeting_room") return "确认并沉淀";
  if (memoryPublishForm.target_key === "target_meeting_room") return "确认并共享给会议室";
  if (memoryPublishForm.target_key === "user") return "确认并共享给成员";
  if (memoryPublishForm.target_key === "agent") return "共享给 Agent 记忆";
  if (memoryPublishForm.target_key === "org_space") return "沉淀到组织空间";
  return "确认并共享";
});

function canDeleteRoom(room: MeetingRoom) {
  return room.created_by === auth.userId;
}

function canLeaveRoom(room: MeetingRoom) {
  return room.created_by !== currentUserId.value;
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

function meetingRoomStatusLabel(status?: string | null) {
  if (status === "active") return "进行中";
  if (status === "closed") return "已结束";
  return status || "";
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

function domainLabel(value: string) {
  const map: Record<string, string> = {
    quality: "质量",
    "quality.task": "质检任务",
    "quality.result": "质检结果",
    "quality.review": "专家复核",
    "quality.analytics": "质量分析",
    standard: "标准",
    "standard.library": "标准库",
    "standard.rule": "标准规则",
    "standard.version": "标准版本",
    "standard.approval": "标准审批",
    meeting: "会议",
    "meeting.message": "会议消息",
    "meeting.summary": "会议总结",
    "meeting.action_item": "会议待办",
    "meeting.private_message": "会议私密消息",
    memory: "记忆",
    "memory.user": "个人记忆",
    "memory.meeting": "会议记忆",
    "memory.agent": "Agent 记忆",
    "memory.org_space": "组织空间记忆",
    "memory.business": "业务记忆",
    platform_ops: "平台运营",
    "ops.agent": "Agent",
    "ops.prompt": "Prompt",
    "ops.route": "路由",
    "ops.tool": "工具",
    "ops.release": "发布",
    "ops.trace": "Trace",
    model_billing: "模型与计费",
    "model.catalog": "模型目录",
    "model.config": "模型配置",
    "model.experiment": "实验",
    "model.deployment": "部署",
    "model.experiment_cost": "实验成本",
    "model.org_usage": "组织用量",
    "billing.invoice": "账单",
    org_admin: "组织治理",
    "org.member": "成员",
    "org.role": "角色",
    "org.department": "部门",
    "org.policy": "策略",
    data_access: "数据访问",
    "data.dataset": "数据集",
    "data.sample": "样本",
    "data.rag_space": "RAG 空间",
    "data.connector": "连接器",
    "data.import_job": "导入任务",
    security_audit: "安全审计",
    "audit.auth": "认证审计",
    "audit.tool_execution": "工具执行审计",
    "audit.agent_query": "Agent 查询审计",
    "audit.approval": "审批审计",
    ai_conversation: "AI 会话",
    "conversation.own": "自己的会话",
    "conversation.meeting": "会议会话",
    "conversation.private": "私聊原文",
    "conversation.trace_redacted": "脱敏 Trace",
  };
  const key = String(value || "").trim();
  return map[key] || key;
}

function domainGroupLabel(value: string) {
  const prefix = value.includes(".") ? value.split(".")[0] : value;
  const groupMap: Record<string, string> = {
    quality: "质量域",
    standard: "标准域",
    meeting: "会议域",
    memory: "记忆域",
    ops: "平台运营域",
    model: "模型与计费域",
    billing: "模型与计费域",
    org: "组织治理域",
    data: "数据访问域",
    audit: "安全审计域",
    conversation: "AI 会话域",
    platform_ops: "平台运营域",
    model_billing: "模型与计费域",
    org_admin: "组织治理域",
    data_access: "数据访问域",
    security_audit: "安全审计域",
    ai_conversation: "AI 会话域",
  };
  return groupMap[prefix] || prefix;
}

function hasDomainGroup(domains: string[], group: string) {
  return domains.some((domain) => domain === group || domain.startsWith(`${group}.`));
}

function domainGroupKey(value: string) {
  const prefix = value.includes(".") ? value.split(".")[0] : value;
  if (prefix === "model" || prefix === "billing") return "model_billing";
  if (prefix === "org") return "org_admin";
  if (prefix === "data") return "data_access";
  if (prefix === "audit") return "security_audit";
  if (prefix === "conversation") return "ai_conversation";
  if (prefix === "ops") return "platform_ops";
  return prefix;
}

function buildDomainGroups(domains: string[]) {
  const groups = new Map<string, string[]>();
  for (const domain of domains || []) {
    const key = domainGroupKey(domain);
    const items = groups.get(key) || [];
    if (!items.includes(domain)) {
      items.push(domain);
      groups.set(key, items);
    }
  }
  return Array.from(groups.entries()).map(([key, items]) => ({ key, label: domainGroupLabel(key), items }));
}

function unwrap<T>(payload: unknown): T {
  return ((payload as { data?: T }).data || payload) as T;
}

function inferMemoryType(title: string, content: string): MeetingMemory["memory_type"] {
  const text = `${title}\n${content}`.toLowerCase();
  if (["风险洞察", "预测", "预警", "未来", "risk forecast"].some((term) => text.includes(term))) return "risk_insight";
  if (["问题模式", "反复出现", "集中出现", "常见失败", "quality pattern"].some((term) => text.includes(term))) return "quality_pattern";
  if (["行动项", "待办", "责任人", "建议动作", "action"].some((term) => text.includes(term))) return "action_suggestion";
  if (["质检", "检测", "评分", "不合格", "合格", "耗时", "模型", "inspection", "quality"].some((term) => text.includes(term))) return "quality_fact";
  return "decision";
}

function inferMemoryCategory(
  memoryType: MeetingMemory["memory_type"],
  title: string,
  content: string,
  affectedObjects?: MemoryAffectedObjects,
): MeetingMemory["memory_category"] {
  const text = `${title}\n${content}`.toLowerCase();
  const hasBinding = hasAffectedObjects(mergeAffectedObjects(contextAffectedObjects(), affectedObjects));
  if (memoryType === "quality_fact") return "business_memory";
  if (memoryType === "risk_insight" || memoryType === "quality_pattern") return hasBinding ? "business_memory" : "meeting_memory";
  const businessTerms = ["质检", "检测", "任务", "产品", "批次", "标准", "复核", "抽检", "缺陷", "风险", "判定", "审核", "inspection", "quality", "standard", "batch", "product"];
  if (hasBinding && businessTerms.some((term) => text.includes(term))) return "business_memory";
  return "meeting_memory";
}

function buildMemoryShareability(
  memoryCategory: MeetingMemory["memory_category"],
  memoryType: MeetingMemory["memory_type"],
  affectedObjects: MemoryAffectedObjects,
  objectResolutionStatus?: string | null,
) {
  const context = mergeAffectedObjects(contextAffectedObjects(), affectedObjects);
  const hasBusinessTags = hasAffectedObjects(context);
  const allowedScopes = ["meeting_room", "org_space", "user", "agent", "collab_thread"];
  return {
    allowed_scopes: Array.from(new Set(allowedScopes)),
    missing_bindings: [],
    requires_host_confirmation: true,
    cross_room_allowed: true,
    organization_scope_enabled: true,
    business_tags_optional: true,
    has_business_tags: hasBusinessTags,
    suggested_flow: memoryType === "risk_insight" || memoryType === "quality_pattern" || memoryCategory === "business_memory"
      ? "confirm_or_share"
      : "confirm_first",
    object_resolution_status: objectResolutionStatus || "unresolved",
  };
}

function recommendedMemoryScope(
  memoryType: MeetingMemory["memory_type"],
  memoryCategory: MeetingMemory["memory_category"],
  affectedObjects: MemoryAffectedObjects,
  objectResolutionStatus?: string | null,
) {
  const context = mergeAffectedObjects(contextAffectedObjects(), affectedObjects);
  const hasBusinessTags = hasAffectedObjects(context);
  if (memoryType === "quality_pattern" || memoryType === "risk_insight") return { scope: "org_space", scopeId: "current" };
  if (memoryCategory === "business_memory" && hasBusinessTags && objectResolutionStatus === "resolved") return { scope: "org_space", scopeId: "current" };
  return { scope: "meeting_room", scopeId: null };
}

function buildMemoryWarnings(
  memoryCategory: MeetingMemory["memory_category"],
  memoryType: MeetingMemory["memory_type"],
  _affectedObjects: MemoryAffectedObjects,
  _objectResolutionStatus?: string | null,
  baseWarnings: string[] = [],
) {
  const warnings = new Set(baseWarnings.filter((warning) => !isBusinessTagWarning(warning)));
  if (memoryCategory === "meeting_memory") warnings.add("该记忆默认沉淀到当前会议室；需要跨范围使用时，可共享给其他会议室、成员个人记忆、Agent 记忆或组织共享空间。");
  if (memoryType === "risk_insight") {
    warnings.add("风险洞察是预测候选，需人工确认后才能沉淀或共享；不会自动触发外部处置。");
  }
  return Array.from(warnings);
}

function buildMemoryPublishPreview(memory?: MeetingMemory | null): MeetingMemory | null {
  if (!memory) return null;
  const title = memoryPublishForm.title.trim() || memory.title;
  const content = memoryPublishForm.content.trim() || memory.content;
  const affectedObjects = memoryAffectedObjects(memory);
  const objectResolutionStatus = memory.object_resolution_status || (hasAffectedObjects(affectedObjects) ? "resolved" : "unresolved");
  const memoryType = inferMemoryType(title, content);
  const memoryCategory = inferMemoryCategory(memoryType, title, content, affectedObjects);
  const recommendation = recommendedMemoryScope(memoryType, memoryCategory, affectedObjects, objectResolutionStatus);
  return {
    ...memory,
    title,
    content,
    memory_type: memoryType,
    memory_category: memoryCategory,
    affected_objects: affectedObjects,
    object_resolution_status: objectResolutionStatus,
    recommended_scope: recommendation.scope,
    recommended_scope_id: recommendation.scopeId,
    shareability: buildMemoryShareability(memoryCategory, memoryType, affectedObjects, objectResolutionStatus),
    warnings: buildMemoryWarnings(memoryCategory, memoryType, affectedObjects, objectResolutionStatus, memory.warnings || []),
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

function roomNameById(roomId?: string | null) {
  const cleanId = String(roomId || "").trim();
  if (!cleanId || cleanId === "current") return store.activeRoom?.title || "当前会议室";
  const room = store.rooms.find((item) => item.id === cleanId);
  return room ? roomDisplayTitle(room) : "";
}

function agentNameById(agentId?: string | null) {
  const cleanId = String(agentId || "").trim();
  if (!cleanId) return "";
  if (cleanId === "general_agent") return "会议Agent";
  return store.agents.find((agent) => agent.agent_id === cleanId)?.agent_name || "";
}

function memoryPublishTargetTypeLabel(key: MemoryPublishTargetKey) {
  if (key === "current_meeting_room" || key === "target_meeting_room") return "会议室";
  if (key === "user") return "成员";
  if (key === "agent") return "Agent";
  if (key === "org_space") return "组织空间";
  return "目标";
}

function scopeObjectLabel(memory: MeetingMemory) {
  const scope = String(memory.scope || memory.scope_type || "meeting");
  const scopeId = String(memory.scope_id || "").trim();
  if (scope === "meeting" || scope === "meeting_room") {
    if (scopeId && scopeId !== store.activeRoom?.id) return `会议室：${roomNameById(scopeId) || "已共享会议室"}`;
    return store.activeRoom?.title ? `当前会议室：${store.activeRoom.title}` : "当前会议室";
  }
  if (scope === "org_space" || scope === "workspace") return "组织共享空间";
  if (scope === "collab_thread") return "协作确认流";
  if (scope === "user") return scopeId ? `成员个人记忆：${memberDisplayName(scopeId)}` : "成员个人记忆";
  if (scope === "agent") return scopeId ? `Agent 记忆：${agentNameById(scopeId) || "指定 Agent"}` : "Agent 记忆";
  if (scope === "inspection_task") {
    const task = currentBusinessContext.value?.tasks?.find((item) => item.id === scopeId);
    if (task?.spec_code) return `历史线索：${task.spec_code}`;
    return "历史线索";
  }
  if (scope === "product") return scopeId && !isUuidLike(scopeId) ? `历史线索：${scopeId}` : "历史线索";
  if (scope === "batch") return scopeId && !isUuidLike(scopeId) ? `历史线索：${scopeId}` : "历史线索";
  if (scope === "standard") return scopeId && !isUuidLike(scopeId) ? `历史线索：${scopeId}` : "历史线索";
  if (scope === "workspace") return `组织共享空间${scopeId ? `：${scopeId}` : ""}`;
  return memoryScopeLabel(scope);
}

function scopeVisibilityNote(memory: MeetingMemory) {
  const scope = String(memory.scope || memory.scope_type || "meeting");
  if (scope === "org_space" || scope === "workspace") return "组织内可检索，可被有权限的会议室、成员和 Agent 召回";
  if (scope === "collab_thread") return "仅对应协作通道可见";
  if (scope === "user") return "仅对应成员身份可见";
  if (scope === "agent") return "仅对目标 Agent 身份可见";
  if (["inspection_task", "product", "batch", "standard"].includes(scope)) return "历史兼容数据；仅作为检索线索参与召回";
  if (scope === "workspace") return "组织共享空间历史兼容数据";
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
    object_resolution_status: memory.object_resolution_status || null,
    object_candidates: memory.object_candidates || [],
    source_spans: memory.source_spans || [],
    value_score: memory.value_score || null,
    dedupe_key: memory.dedupe_key || null,
    related_memory_ids: memory.related_memory_ids || [],
    extraction_reason: memory.extraction_reason || null,
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

function openMemoryCollabShare(memory: MeetingMemory) {
  if (!store.activeRoom) return;
  const room = store.activeRoom;
  const sourceMessage = sourceMessageId(memory);
  const draftKey = `${memory.memory_id}-${Date.now()}`;
  const sourceContext = {
    source_type: "meeting_room",
    source_id: room.id,
    source_title: room.title,
    source_room_id: room.id,
    source_message_id: sourceMessage || undefined,
    label: `会议室${room.title}`,
  };
  const draft = {
    title: `请确认：${memory.title || "会议记忆"}`,
    content: "请确认这条会议记忆是否需要沉淀到你的作用域，或共享给你负责的会议协作范围。",
    source_context: sourceContext,
    memory: {
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
      source_message_id: sourceMessage || null,
      source_label: sourceMessageLabel(memory),
      affected_objects: memory.affected_objects || null,
      tags: memory.tags || [],
    },
  };
  try {
    window.sessionStorage.setItem(`collab:draft:${draftKey}`, JSON.stringify(draft));
  } catch {
    ElMessage.warning("浏览器暂存失败，将只带入会议室来源。");
  }
  void router.push({
    path: "/app/collab",
    query: {
      draft_key: draftKey,
      source_type: "meeting_room",
      source_id: room.id,
      source_label: room.title,
      source_room_id: room.id,
      ...(sourceMessage ? { source_message_id: sourceMessage } : {}),
      title: draft.title,
    },
  });
}

function memoryStatusLabel(status?: string | null) {
  if (status === "confirmed") return "已确认";
  if (status === "short_term") return "短期";
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
  if (memory?.memory_type === "risk_insight") return "风险洞察是预测候选，确认后可沉淀到当前会议室，也可共享给其他会议室、成员个人记忆、Agent 记忆或组织共享空间。";
  if (memory?.memory_type === "quality_fact") return "单次质量事实可先在会议室确认，再按需要共享给会议室、成员、Agent 或组织空间。";
  if (memory?.memory_type === "quality_pattern") return "可复用的问题模式建议沉淀到组织共享空间，或共享到 Agent 记忆供后续召回。";
  if (category === "business_memory") return "这类专业经验确认后按目标作用域沉淀或共享。";
  if (category === "rejected_noise") return "噪声不建议确认为记忆，只能丢弃或保留为普通会议消息。";
  return "会议内记忆可先在当前会议室沉淀，需要协同时再共享给明确目标。";
}

function isBusinessTagWarning(warning?: string | null) {
  const text = String(warning || "");
  return [
    "业务标签",
    "任务、产品、批次、标准",
    "质检任务",
    "默认发布到质检任务",
    "不能直接进入组织共享记忆",
    "不允许跨业务范围共享",
  ].some((keyword) => text.includes(keyword));
}

function normalizeMemoryWarning(warning: string) {
  const text = String(warning || "").trim();
  if (!text) return "";
  if (isBusinessTagWarning(text)) return "";
  if (text.includes("预警中心")) return "风险洞察是预测候选，需人工确认后才能沉淀或共享；不会自动触发外部处置。";
  if (text.includes("确认发布")) return text.replaceAll("确认发布", "确认");
  return text;
}

function visibleMemoryWarnings(memory?: MeetingMemory | null) {
  return (memory?.warnings || [])
    .map((warning) => normalizeMemoryWarning(warning))
    .filter(Boolean);
}

function publishDecisionRows(memory?: MeetingMemory | null) {
  if (!memory) return [];
  const rows: Array<{ label: string; value: string }> = [
    { label: "识别结果", value: `${memoryCategoryLabel(memory.memory_category)} · ${memoryTypeLabel(memory.memory_type)}` },
    { label: "推荐落点", value: memory.recommended_scope ? memoryScopeLabel(memory.recommended_scope) : "当前会议室" },
  ];
  if (memory.memory_type === "quality_fact") {
    rows.push({
      label: "沉淀判断",
      value: "这是一次专业事实，可直接沉淀到会议室，也可共享给其他会议室、成员、Agent 或组织空间。",
    });
  } else if (memory.memory_type === "risk_insight") {
    rows.push({
      label: "沉淀判断",
      value: "这是预测候选，需人工确认；确认后可沉淀到会议室或共享给组织空间、其他会议室、成员、Agent。",
    });
  } else if (memory.memory_type === "quality_pattern") {
    rows.push({
      label: "沉淀判断",
      value: "这是可复用模式，建议进入组织共享空间，或通过协作消息发送给需要处理的目标。",
    });
  } else {
    rows.push({ label: "沉淀判断", value: "可保存为当前会议室结论，也可共享给明确协作目标。" });
  }
  rows.push({
    label: "共享规则",
    value: "记忆归属看目标作用域；共享目标只选择会议室、成员、Agent、组织空间或协作确认流。",
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

function dedupeObjectValues(values: Array<string | number | null | undefined>) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const text = String(value || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
  }
  return result;
}

function emptyAffectedObjects(): MemoryAffectedObjects {
  return {
    inspection_task_ids: [],
    product_ids: [],
    batch_nos: [],
    standard_ids: [],
  };
}

function contextAffectedObjects(): MemoryAffectedObjects {
  const context = currentBusinessContext.value;
  return {
    inspection_task_ids: dedupeObjectValues(context?.task_ids || []),
    product_ids: dedupeObjectValues(context?.product_ids || []),
    batch_nos: dedupeObjectValues(context?.batch_nos || []),
    standard_ids: dedupeObjectValues(context?.standard_ids || []),
  };
}

function mergeAffectedObjects(...items: Array<Partial<MemoryAffectedObjects> | null | undefined>): MemoryAffectedObjects {
  const merged = emptyAffectedObjects();
  for (const item of items) {
    if (!item) continue;
    merged.inspection_task_ids.push(...dedupeObjectValues(item.inspection_task_ids || []));
    merged.product_ids.push(...dedupeObjectValues(item.product_ids || []));
    merged.batch_nos.push(...dedupeObjectValues(item.batch_nos || []));
    merged.standard_ids.push(...dedupeObjectValues(item.standard_ids || []));
  }
  return {
    inspection_task_ids: dedupeObjectValues(merged.inspection_task_ids),
    product_ids: dedupeObjectValues(merged.product_ids),
    batch_nos: dedupeObjectValues(merged.batch_nos),
    standard_ids: dedupeObjectValues(merged.standard_ids),
  };
}

function memoryAffectedObjects(memory?: MeetingMemory | null): MemoryAffectedObjects {
  const objects = memory?.affected_objects || {};
  return {
    inspection_task_ids: Array.isArray(objects.inspection_task_ids) ? objects.inspection_task_ids.map(String) : [],
    product_ids: Array.isArray(objects.product_ids) ? objects.product_ids.map(String) : [],
    batch_nos: Array.isArray(objects.batch_nos) ? objects.batch_nos.map(String) : [],
    standard_ids: Array.isArray(objects.standard_ids) ? objects.standard_ids.map(String) : [],
  };
}

function hasAffectedObjects(objects: MemoryAffectedObjects) {
  return Boolean(
    objects.inspection_task_ids.length
      || objects.product_ids.length
      || objects.batch_nos.length
      || objects.standard_ids.length,
  );
}

function sourceSpanSummary(memory?: MeetingMemory | null) {
  const spans = memory?.source_spans || [];
  if (!spans.length) return "";
  return spans.slice(0, 3).map((span, index) => {
    const text = String(span.text || "").replace(/\s+/g, " ").trim();
    return text ? `片段 ${index + 1}：${clipText(text, 70)}` : `片段 ${index + 1}`;
  }).join("、");
}

function relatedMemorySummary(memory?: MeetingMemory | null) {
  const ids = memory?.related_memory_ids || [];
  return ids.length ? ids.slice(0, 3).join("、") : "";
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
    `读取记忆：${auditMemoryCount(audit)} 条`,
  ].join("\n"), "审计信息已复制");
}

async function questionAuditAnswer() {
  const audit = selectedAudit.value;
  if (!audit) return;
  try {
    const { value } = await ElMessageBox.prompt("说明这次 AI 回答哪里需要质疑", "质疑这次回答", {
      inputType: "textarea",
      inputPlaceholder: "例如：回答引用了有争议记忆，或结论需要主持人复核",
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
      "请主持人复核本次回答的记忆来源和结论是否可靠。",
    ].join("\n");
    auditDetailVisible.value = false;
    await nextTick();
    inputRef.value?.focus();
    ElMessage.success("已生成会议消息草稿，请确认后发送。");
  } catch {
    // cancelled
  }
}

function buildMemoryPublishScopeOptions(memory?: MeetingMemory | null) {
  const allowed = new Set((memory?.shareability?.allowed_scopes || ["meeting_room", "org_space", "user", "agent", "collab_thread"]).map(String));
  const targetMeetingRooms = store.rooms
    .filter((room) => room.id !== store.activeRoom?.id)
    .map((room) => ({
      label: roomDisplayTitle(room),
      value: room.id,
      description: `${room.member_count || 0} 位成员· ${meetingRoomStatusLabel(room.status) || "未知状态"}`,
    }));
  const memberTargets = store.members
    .filter((member) => member.user_id !== currentUserId.value)
    .map((member) => ({
      label: member.username,
      value: member.user_id,
      description: memberRoleLabel(member.role),
    }));
  const agentTargets = store.agents.map((agent) => ({
    label: agent.agent_name,
    value: agent.agent_id,
    description: agent.role === "observer" ? "观察者 Agent" : "参会 Agent",
  }));
  const options: MemoryPublishScopeOption[] = [
    {
      key: "current_meeting_room",
      label: "当前会议室沉淀",
      value: "meeting_room",
      scopeId: "",
      note: "保存为当前会议室的已确认记忆，后续本会议室成员和会议 Agent 可召回。",
    },
    {
      key: "target_meeting_room",
      label: "共享给其他会议室",
      value: "meeting_room",
      scopeId: "",
      requiresTargetId: true,
      targetLabel: "选择会议室",
      targetPlaceholder: "搜索你已加入的会议室",
      targetOptions: targetMeetingRooms,
      targetEmptyText: "暂无可共享的其他会议室",
      note: "直接成为目标会议室可检索的共享记忆，目标会议室成员和会议 Agent 后续可召回。",
    },
  ];
  if (allowed.has("org_space") || allowed.has("workspace")) {
    options.push({
      key: "org_space",
      label: "组织共享空间",
      value: "org_space",
      scopeId: "current",
      note: "进入组织共享记忆，供有权限的会议室、成员和 Agent 后续召回。",
    });
  }
  if (allowed.has("user")) {
    options.push({
      key: "user",
      label: "共享给成员",
      value: "user",
      scopeId: "",
      requiresTargetId: true,
      targetLabel: "选择成员",
      targetPlaceholder: "搜索当前会议室成员",
      targetOptions: memberTargets,
      targetEmptyText: "当前会议室暂无其他成员",
      note: "进入成员个人记忆；后续该成员触发会议 Agent 时可作为本人授权上下文召回。",
    });
  }
  if (allowed.has("agent")) {
    options.push({
      key: "agent",
      label: "共享给 Agent 记忆",
      value: "agent",
      scopeId: "",
      requiresTargetId: true,
      targetLabel: "选择 Agent",
      targetPlaceholder: "搜索当前会议室Agent",
      targetOptions: agentTargets,
      targetEmptyText: "当前会议室暂无可共享给 Agent",
      note: "进入目标 Agent 的可检索记忆，用于后续在该 Agent 身份下召回和推理。",
    });
  }
  return options;
}

function applyMemoryPublishOption(key: MemoryPublishTargetKey) {
  const option = memoryPublishScopeOptions.value.find((item) => item.key === key) || memoryPublishScopeOptions.value[0];
  memoryPublishForm.target_key = option.key;
  memoryPublishForm.scope = option.value;
  memoryPublishForm.scope_id = option.requiresTargetId ? "" : option.scopeId;
}

function syncMemoryPublishSelectionWithPreview() {
  const preview = memoryPublishPreview.value;
  if (!preview) return;
  const options = buildMemoryPublishScopeOptions(preview);
  if (options.some((item) => item.key === memoryPublishForm.target_key)) return;
  const recommended = options.find((item) => (
    item.value === preview.recommended_scope
    && !item.requiresTargetId
    && (item.value === "meeting" || item.scopeId === String(preview.recommended_scope_id || ""))
  ));
  const selected = recommended || options[0];
  memoryPublishForm.target_key = selected.key;
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
    && !item.requiresTargetId
    && (item.value === "meeting" || item.scopeId === String(preview.recommended_scope_id || ""))
  ));
  const selected = recommended || options[0];
  memoryPublishForm.target_key = selected.key;
  memoryPublishForm.scope = selected.value;
  memoryPublishForm.scope_id = selected.scopeId;
  memoryPublishForm.publish_reason = "";
}

function quotedMessageTitle(messageId?: string | null) {
  if (!messageId) return "";
  const message = store.activeRoomMessages.find((item) => item.id === messageId);
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

function messageVisibility(message: MeetingMessage) {
  const metadata = messageMetadata(message);
  const visibility = String(metadata.visibility || "").trim();
  if (visibility) return visibility;
  return privateRecipientUserId(message) ? "private" : "room";
}

function messageVisibilityLabel(message: MeetingMessage) {
  return messageVisibility(message) === "private" ? "仅自己可见" : "公开";
}

function shareTargetLabel(scopeType: string, scopeId: string) {
  if (scopeType === "meeting_room") {
    const room = store.rooms.find((item) => item.id === scopeId);
    return room?.title || "目标会议室";
  }
  if (scopeType === "org_space") return "组织共享空间";
  if (scopeType === "user") return memberDisplayName(scopeId);
  if (scopeType === "agent") return scopeId === "general_agent" ? "会议Agent" : scopeId;
  if (scopeType === "collab_thread") return "协作通道";
  return scopeId || scopeType;
}

function conflictTypeLabel(value: string) {
  const map: Record<string, string> = {
    preference: "偏好冲突",
    task: "任务冲突",
    resource: "资源冲突",
    knowledge: "知识冲突",
  };
  return map[value] || value || "冲突";
}

async function resolveConflictCard(conflictId: string, selectedAction: "approve" | "queue" | "reject" | "candidate_only") {
  await store.resolveConflict(conflictId, selectedAction);
  ElMessage.success("冲突已处理");
}

async function approveMemoryShare(transferId: string) {
  await store.approveMemoryShare(transferId);
  ElMessage.success("共享请求已通过");
}

async function rejectMemoryShare(transferId: string) {
  await store.rejectMemoryShare(transferId);
  ElMessage.success("共享请求已拒绝");
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

function messageHasAgentMention(message: MeetingMessage) {
  return Array.isArray(message.mentions)
    && message.mentions.some((mention) => Boolean(mention?.agent_id || mention?.agent_name));
}

function canShowInAgentPanel(message: MeetingMessage) {
  const selfId = currentUserId.value;
  if (!selfId) return false;
  const recipientId = privateRecipientUserId(message);
  if (recipientId) return message.user_id === selfId || recipientId === selfId;
  if (["agent", "agent_streaming"].includes(message.message_type)) return message.user_id === selfId;
  if (message.message_type === "user" && messageHasAgentMention(message)) return message.user_id === selfId;
  return false;
}

function privateMessagesByUser(userId: string) {
  return store.activeRoomMessages.filter((message) => privatePartnerId(message) === userId);
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

async function quoteSummaryToMain(message: MeetingMessage) {
  const content = displayMessageContent(message).trim();
  if (!content) return;
  quoteSnapshot.value = {
    source: "agent",
    author: "会议总结",
    content,
    created_at: message.created_at || null,
  };
  quotedMessage.value = null;
  input.value = "";
  store.clearPendingAttachments();
  await nextTick();
  inputRef.value?.focus();
  ElMessage.success("已引用会议总结到主会场输入框。");
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
  const targets = target === "main"
    ? [messageListRef.value]
    : target === "agent"
      ? [agentPanelListRef.value]
      : [privatePanelListRef.value];
  for (const el of targets) {
    if (el) el.scrollTop = el.scrollHeight;
  }
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
  if (!store.activeRoom) {
    ElMessage.warning("请先进入会议室。");
    return;
  }
  if (store.generalAgentRunning) {
    ElMessage.warning("会议Agent正在回复，请先停止或等待完成后再重新问。");
    return;
  }
  if (agentEditingMessageId.value !== message.id || message.message_type !== "user" || messageMetadata(message).recalled_at) {
    ElMessage.warning("这条提问当前不能修改并重新问。");
    return;
  }
  const question = agentEditingContent.value.trim();
  if (!question) {
    ElMessage.warning("请输入要重新提问的内容。");
    return;
  }
  const attachments = messageAttachments(message);
  try {
    try {
      await store.updateMessage(message.id, `@会议Agent ${question}`);
    } catch (error) {
      ElMessage.warning("原提问未能更新，已直接按修改后的内容重新提问。");
      console.warn("Failed to update original agent question before rerun", error);
    }
    cancelModifyAgentQuestion();
    const result = await store.runGeneralAgent("auto", question, { attachments });
    if (!result) {
      ElMessage.warning("会议Agent暂未开始回复，请稍后再试。");
      return;
    }
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
  const recent = members.find((member) => privateConversationPartnerIds.value.has(member.user_id));
  if (recent) {
    activePrivateUserId.value = recent.user_id;
    return recent;
  }
  activePrivateUserId.value = "";
  return null;
}

function openPrivateDialog(member?: MeetingRoomMember) {
  if (member) {
    activePrivateUserId.value = member.user_id;
    privateRosterShowAll.value = false;
    privateMemberSearch.value = "";
  } else {
    ensureActivePrivateMember();
  }
  rightPanelTab.value = "private";
  rightPanelCollapsed.value = false;
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
    ElMessage.error("私聊消息发送失败，请稍后重试。");
    console.error(error);
  }
}

function openCollabMessages(member?: MeetingRoomMember) {
  const query: Record<string, string> = {};
  if (member) {
    query.target_type = "user";
    query.target_id = member.user_id;
    query.title = `发给 ${member.username}`;
  }
  if (store.activeRoom) {
    query.source_type = "meeting_room";
    query.source_id = store.activeRoom.id;
    query.source_label = store.activeRoom.title;
  }
  void router.push({ path: "/app/collab", query });
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
  const cleanScopeId = memoryPublishForm.scope_id.trim();
  if (memoryPublishTargetRequired.value && !cleanScopeId) {
    ElMessage.warning("请选择共享目标");
    return;
  }
  try {
    memoryPublishSubmitting.value = true;
    const isCandidate = memory.status === "candidate";
    const isLocalRevision = memoryPublishForm.target_key === "current_meeting_room";
    const resolvedScopeId = cleanScopeId || selectedMemoryPublishScopeOption.value?.scopeId || "current";
    if (isCandidate || isLocalRevision) {
      await store.confirmMemory(memory.memory_id, {
        title: memoryPublishForm.title.trim(),
        content: memoryPublishForm.content.trim(),
        scope: memoryPublishForm.scope,
        scope_id: resolvedScopeId,
        publish_reason: memoryPublishForm.publish_reason.trim() || null,
        related_memory_ids: memory.related_memory_ids || [],
      });
    } else {
      await store.shareMemory(memory.memory_id, {
        target_scope_type: memoryPublishForm.scope,
        target_scope_id: resolvedScopeId,
        share_reason: memoryPublishForm.publish_reason.trim() || null,
      });
    }
    memoryPublishDialogVisible.value = false;
    selectedCandidateMemory.value = null;
    if (memoryPublishForm.target_key === "agent") {
      ElMessage.success("记忆已共享到 Agent 记忆");
    } else if (memoryPublishForm.target_key === "current_meeting_room") {
      ElMessage.success(isCandidate ? "记忆已确认沉淀" : "记忆修订已沉淀");
    } else {
      ElMessage.success(isCandidate ? "记忆已确认共享" : "记忆已共享");
    }
  } catch (error) {
    ElMessage.error("记忆沉淀或共享失败，请稍后重试。");
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
    ElMessage.success(`已设为 ${memberRoleLabel(role)}`);
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
      inputErrorMessage: "标题长度需为 1 到 120 个字符",
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
    await ElMessageBox.confirm("结束会议后将停止发送新消息和新成员加入，历史内容仍可查看。", "结束会议", {
      confirmButtonText: "结束",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.closeRoom();
    ElMessage.success("会议已结束。");
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
    ElMessage.info("这条消息已超过 2 分钟，不能撤回");
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
  await store.loadMembers();
  const results = await Promise.allSettled([
    store.loadMessages(0),
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
  try {
    await store.loadRooms(true);
  } catch (error) {
    console.warn("Failed to load meeting rooms", error);
    ElMessage.error("会议室列表加载失败，请确认后端服务已启动后重试。");
  }
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
          <h2>会议列表</h2>
          <div class="room-list-actions">
            <el-button text :icon="RefreshRight" :loading="store.loadingRooms" @click="store.loadRooms()" aria-label="刷新会议列表" />
          </div>
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
              aria-label="退出会议
              title="退出会议
              @click.stop="handleLeaveRoom(room)"
            >
              退出            </el-button>
          </span>
          <span class="room-meta">
            <span>{{ room.access_code }} · {{ room.member_count }} 位</span>
            <span>{{ meetingRoomStatusLabel(room.status) || "未知状态" }}</span>
            <span v-if="roomRecentLabel(room)">最近{{ roomRecentLabel(room) }}</span>
          </span>
        </div>
        <p v-if="!store.rooms.length && !store.loadingRooms" class="empty-note">
          暂无会议
        </p>
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
            <span class="host-pill">主持人{{ hostMember.username }}</span>
            <span class="status-pill" :class="`status-${store.activeRoom.status}`">{{ roomStatusLabel }}</span>
          </div>
        </div>
        <div v-if="store.activeRoom" class="room-header-right">
          <div class="room-toolbar-main">
            <div class="room-code">
              <span>会议室</span>
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
                <strong>{{ visibleMemberCount }} 位</strong>
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
                    aria-label="发起私聊"
                    title="发起私聊"
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
                <span>会议室</span>
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
              结束
            </el-button>
          </div>
        </div>
        <p v-else class="room-hint">创建或加入会议后开始聊天，也可以点 @会议Agent。</p>
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
          <div class="mention-menu-head">选择 @ 的对象</div>
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
          :placeholder="store.activeRoom?.status === 'active' ? '输入公共消息' : '会议已结束，只能查看历史。'"
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
        :aria-label="rightPanelCollapsed ? '展开记忆与协作面板' : '收起记忆与协作面板'"
        :title="rightPanelCollapsed ? '展开记忆与协作面板' : '收起记忆与协作面板'"
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
            记忆与协作          </button>
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
            <section v-for="(group, groupIndex) in store.activeRoom ? agentConversationGroups : []" :key="group.id" class="agent-qa-group">
              <div class="agent-qa-index">问 {{ groupIndex + 1 }}</div>
              <article v-if="group.question" class="agent-thread-item agent-thread-question">
                <div class="agent-thread-meta">
                  <span>提问 · {{ group.question.username }}</span>
                  <time>{{ formatTime(group.question.created_at) }}</time>
                </div>
                <div v-if="agentEditingMessageId === group.question.id" class="agent-message-edit">
                  <el-input v-model="agentEditingContent" type="textarea" :rows="3" resize="vertical" />
                  <div class="agent-message-edit-actions">
                    <el-button size="small" @click.stop="cancelModifyAgentQuestion">取消</el-button>
                    <el-button size="small" type="primary" :loading="store.generalAgentRunning" @click.stop="saveModifiedAgentQuestion(group.question)">修改并重新问</el-button>
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
                  <b class="visibility-pill" :class="`visibility-${messageVisibility(reply)}`">{{ messageVisibilityLabel(reply) }}</b>
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
          <div v-if="store.activeRoom" class="agent-composer" @paste="handleComposerPaste($event, 'agent')">
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
            <div>
              <h2>私聊</h2>
              <span>{{ privateThreadSubtitle }}</span>
            </div>
            <div class="private-sidecar-head-actions">
              <span class="private-sidecar-count">{{ privateConversationCount }}</span>
              <el-button
                text
                size="small"
                :icon="FullScreen"
                :disabled="!currentPrivateMember"
                aria-label="弹出私聊窗口"
                title="弹出私聊窗口"
                @click="openPrivateDialog(currentPrivateMember || undefined)"
              />
            </div>
          </div>
          <div class="private-launcher private-sidecar-roster">
            <div class="private-roster-tools">
              <el-input v-model="privateMemberSearch" size="small" clearable placeholder="搜索成员" />
              <el-button size="small" text @click="privateRosterShowAll = !privateRosterShowAll">
                {{ privateRosterShowAll ? "只看会话" : "显示全部" }}
              </el-button>
            </div>
            <div class="private-launcher-list">
              <button
                v-for="member in privateRosterMembers"
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
              <div v-if="!privateRosterMembers.length" class="private-empty">{{ privateRosterEmptyText }}</div>
              <button
                v-if="!privateRosterShowAll && !privateMemberSearch.trim() && hiddenPrivatePartnerCount > 0"
                type="button"
                class="private-show-all-button"
                @click="privateRosterShowAll = true"
              >
                显示另外 {{ hiddenPrivatePartnerCount }} 位成员              </button>
            </div>
          </div>
          <div class="private-popup-hint">
            <span>点击成员打开会议室内私聊弹窗</span>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!currentPrivateMember"
              @click="openPrivateDialog(currentPrivateMember || undefined)"
            >
              打开弹窗
            </el-button>
          </div>
        </section>

        <section v-show="rightPanelTab === 'context'" class="context-pane sidecar-pane">
          <section class="context-card boundary-card" :class="{ 'context-card-collapsed': !isContextExpanded('boundary') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">边界</p>
                <h2>边界与记忆</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ contextBoundary.effectiveDomains.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('boundary')" @click="toggleContextSection('boundary')">
                  <ArrowUp v-if="isContextExpanded('boundary')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>

            <div class="boundary-grid">
              <article class="boundary-block">
                <div class="boundary-block-head">
                  <strong>我的有效权限</strong>
                  <span>{{ contextBoundary.effectiveDomains.length }}</span>
                </div>
                <div v-if="effectiveDomainGroups.length" class="domain-group-list">
                  <div v-for="group in effectiveDomainGroups" :key="`effective-${group.key}`" class="domain-group">
                    <span>{{ group.label }}</span>
                    <div class="domain-chip-row">
                      <b v-for="domain in group.items" :key="domain" class="domain-chip">
                        {{ domainLabel(domain) }}
                      </b>
                    </div>
                  </div>
                </div>
                <p v-else class="context-empty context-empty-compact">暂无可用域</p>
              </article>

              <article class="boundary-block">
                <div class="boundary-block-head">
                  <strong>会议室开放域</strong>
                  <span>{{ contextBoundary.roomConfiguredDomains.length }}</span>
                </div>
                <div v-if="domainGroups.length" class="domain-group-list">
                  <div v-for="group in domainGroups" :key="`room-${group.key}`" class="domain-group">
                    <span>{{ group.label }}</span>
                    <div class="domain-chip-row">
                      <b v-for="domain in group.items" :key="domain" class="domain-chip domain-chip-room">
                        {{ domainLabel(domain) }}
                      </b>
                    </div>
                  </div>
                </div>
                <p v-else class="context-empty context-empty-compact">沿用默认会议域</p>
              </article>

              <article class="boundary-block">
                <div class="boundary-block-head">
                  <strong>敏感回复</strong>
                  <span>{{ contextBoundary.sensitiveDomains.length }}</span>
                </div>
                <div v-if="sensitiveDomainGroups.length" class="domain-group-list">
                  <div v-for="group in sensitiveDomainGroups" :key="`sensitive-${group.key}`" class="domain-group">
                    <span>{{ group.label }}</span>
                    <div class="domain-chip-row">
                      <b v-for="domain in group.items" :key="domain" class="domain-chip domain-chip-sensitive">
                        {{ domainLabel(domain) }}
                      </b>
                    </div>
                  </div>
                </div>
                <p v-else class="context-note">涉及密钥、Token、密码、连接串时仍只返回脱敏状态。</p>
              </article>
            </div>

            <div class="agent-domain-panel">
              <div class="agent-domain-head">
                <strong>Agent 允许域</strong>
                <span>{{ contextBoundary.agentPermissions.length }}</span>
              </div>
              <div v-if="contextBoundary.agentPermissions.length" class="agent-domain-list">
                <article v-for="agent in contextBoundary.agentPermissions" :key="agent.agent_id" class="agent-domain-item">
                  <div>
                    <strong>{{ agent.agent_name || agent.agent_id }}</strong>
                    <small>{{ agent.role === "observer" ? "观察者" : "参与者" }}</small>
                  </div>
                  <div class="domain-chip-row">
                    <b v-for="domain in agent.allowed_domains.slice(0, 8)" :key="domain" class="domain-chip domain-chip-agent">
                      {{ domainLabel(domain) }}
                    </b>
                    <b v-if="agent.allowed_domains.length > 8" class="domain-chip domain-chip-muted">+{{ agent.allowed_domains.length - 8 }}</b>
                  </div>
                </article>
              </div>
              <p v-else class="context-empty context-empty-compact">暂无已加入的会议 Agent</p>
            </div>

            <div v-if="Object.keys(contextBoundary.deniedReasons).length" class="denied-reason-list">
              <span v-for="(reason, domain) in contextBoundary.deniedReasons" :key="domain">
                {{ domainLabel(domain) }}：{{ reason }}
              </span>
            </div>
          </section>

          <section class="context-card summary-card" :class="{ 'context-card-collapsed': !isContextExpanded('summary') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">总结</p>
                <h2>会议总结</h2>
              </div>
              <div class="context-head-actions">
                <el-button
                  text
                  size="small"
                  :loading="store.summarizing"
                  :disabled="!store.activeRoom"
                  @click="store.summarizeMeeting()"
                >
                  生成
                </el-button>
                <span class="count-pill">{{ summaryMessages.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('summary')" @click="toggleContextSection('summary')">
                  <ArrowUp v-if="isContextExpanded('summary')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <article v-if="latestSummaryMessage" class="summary-item">
              <div class="summary-item-head">
                <strong>最近一次总结</strong>
                <time>{{ formatTime(latestSummaryMessage.created_at) }}</time>
              </div>
              <p>{{ clipText(displayMessageContent(latestSummaryMessage), 420) }}</p>
              <div class="summary-actions">
                <el-button size="small" text @click="quoteSummaryToMain(latestSummaryMessage)">引用</el-button>
                <el-button
                  v-if="canReviewMemory"
                  size="small"
                  text
                  :loading="store.memoryExtracting"
                  @click="extractCandidateMemories"
                >
                  提取候选                </el-button>
              </div>
            </article>
            <div v-else class="context-empty context-empty-compact">暂无会议总结</div>
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
            <p v-if="store.candidateMemories.length" class="context-note">候选记忆先由会议室确认；确认时可沉淀到当前会议室，也可共享到其他会议室、成员个人记忆、Agent 记忆或组织共享空间。</p>
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
                <span>来源：本会议室</span>
              </div>
              <p>{{ memoryPreview(memory, 180) }}</p>
              <div class="memory-evidence-panel">
                <span v-if="memory.extraction_reason">提取理由：{{ memory.extraction_reason }}</span>
                <span v-if="sourceSpanSummary(memory)">来源片段：{{ sourceSpanSummary(memory) }}</span>
                <span v-if="relatedMemorySummary(memory)">关联记忆：{{ relatedMemorySummary(memory) }}</span>
              </div>
              <div v-if="memory.memory_type === 'risk_insight'" class="risk-insight-strip">
                <span>风险：{{ riskLevelLabel(memory.risk_level) }}</span>
                <span v-if="forecastWindowLabel(memory)">关注：{{ forecastWindowLabel(memory) }}</span>
              </div>
              <small class="memory-source">{{ memoryCategoryHint(memory) }}</small>
              <div v-if="visibleMemoryWarnings(memory).length" class="memory-warning-list">
                <span v-for="warning in visibleMemoryWarnings(memory)" :key="warning">{{ warning }}</span>
              </div>
              <div v-if="canReviewMemory" class="memory-actions">
                <el-button size="small" type="primary" :icon="Check" @click="confirmCandidateMemory(memory)">确认/共享</el-button>
                <el-button size="small" :icon="Promotion" @click="openMemoryCollabShare(memory)">请求确认</el-button>
                <el-button size="small" :icon="Close" @click="rejectCandidateMemory(memory)">拒绝</el-button>
              </div>
            </article>
          </section>

          <section class="context-card" :class="{ 'context-card-collapsed': !isContextExpanded('confirmedMemory') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">确认</p>
                <h2>会议内确认 / 已沉淀记忆</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.confirmedMemories.length }}</span>
                <button type="button" class="context-collapse-button" :aria-expanded="isContextExpanded('confirmedMemory')" @click="toggleContextSection('confirmedMemory')">
                  <ArrowUp v-if="isContextExpanded('confirmedMemory')" />
                  <ArrowDown v-else />
                </button>
              </div>
            </div>
            <p v-if="store.confirmedMemories.length" class="context-note">确认后仍保留来源；共享目标由会议室、成员个人记忆、Agent 记忆、组织空间或协作通道决定。</p>
            <div v-if="!store.confirmedMemories.length" class="context-empty context-empty-compact">暂无会议内确认记忆</div>
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
                <span>沉淀/共享目标：{{ scopeObjectLabel(memory) }}</span>
              </div>
              <p>{{ memoryPreview(memory) }}</p>
              <small class="memory-source">来源：本会议室· {{ scopeVisibilityNote(memory) }}</small>
              <div v-if="memory.memory_type === 'risk_insight'" class="risk-insight-strip">
                <span>风险：{{ riskLevelLabel(memory.risk_level) }}</span>
                <span v-if="forecastWindowLabel(memory)">关注：{{ forecastWindowLabel(memory) }}</span>
              </div>
              <div class="memory-actions">
                <el-button size="small" text @click="openMemoryDetail(memory)">{{ memorySourceSummary(memory) }}</el-button>
                <template v-if="canReviewMemory && memory.status !== 'superseded'">
                  <el-button size="small" text @click="disputeSharedMemory(memory)">质疑</el-button>
                  <el-button size="small" text type="primary" @click="confirmCandidateMemory(memory)">共享/修订</el-button>
                  <el-button size="small" text @click="openMemoryCollabShare(memory)">请求确认</el-button>
                </template>
              </div>
            </article>
          </section>

          <section v-if="canReviewMemory" class="context-card">
            <div class="context-head">
              <div>
                <p class="section-kicker">审批</p>
                <h2>待审批共享</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.pendingMemoryShares.length }}</span>
              </div>
            </div>
            <div v-if="!store.pendingMemoryShares.length" class="context-empty context-empty-compact">暂无待审批共享</div>
            <article v-for="share in store.pendingMemoryShares" :key="share.id" class="governance-item">
              <div class="governance-item-head">
                <strong>{{ share.memory_title || share.memory_id }}</strong>
                <span>{{ share.status }}</span>
              </div>
              <p>{{ shareTargetLabel(share.from_scope_type, share.from_scope_id) }} → {{ shareTargetLabel(share.to_scope_type, share.to_scope_id) }}</p>
              <small>{{ share.transfer_reason || "暂无说明" }}</small>
              <div v-if="share.can_approve !== false" class="memory-actions">
                <el-button size="small" type="primary" @click="approveMemoryShare(share.id)">批准</el-button>
                <el-button size="small" @click="rejectMemoryShare(share.id)">拒绝</el-button>
              </div>
              <div v-else class="context-empty context-empty-compact">等待目标会议室审批</div>
            </article>
          </section>

          <section v-if="canReviewMemory" class="context-card">
            <div class="context-head">
              <div>
                <p class="section-kicker">处理</p>
                <h2>冲突处理</h2>
              </div>
              <div class="context-head-actions">
                <span class="count-pill">{{ store.conflictEvents.length }}</span>
              </div>
            </div>
            <div v-if="!store.conflictEvents.length" class="context-empty context-empty-compact">暂无冲突事件</div>
            <article v-for="conflict in store.conflictEvents" :key="conflict.id" class="governance-item">
              <div class="governance-item-head">
                <strong>{{ conflictTypeLabel(conflict.conflict_type) }}</strong>
                <span>{{ conflict.status }}</span>
              </div>
              <p>{{ conflict.resource_key }}</p>
              <small>{{ formatTime(conflict.created_at) }}</small>
              <div v-if="conflict.status === 'pending'" class="memory-actions">
                <el-button size="small" type="primary" @click="resolveConflictCard(conflict.id, 'approve')">批准</el-button>
                <el-button size="small" @click="resolveConflictCard(conflict.id, 'queue')">排队</el-button>
                <el-button size="small" @click="resolveConflictCard(conflict.id, 'candidate_only')">转候选</el-button>
                <el-button size="small" @click="resolveConflictCard(conflict.id, 'reject')">拒绝</el-button>
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
            <p class="context-note">AI 使用记录不可修改，用于回看 Agent 的回答问题、使用时间和记忆引用情况。</p>
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
      <div v-show="!privateWindowMinimized" class="private-dialog-body" :class="{ 'private-dialog-body-roster-collapsed': privateRosterCollapsed }">
        <aside v-if="!privateRosterCollapsed" class="private-dialog-roster">
          <div class="private-roster-tools private-dialog-roster-tools">
            <el-input v-model="privateMemberSearch" size="small" clearable placeholder="搜索成员" />
            <el-button size="small" text @click="privateRosterShowAll = !privateRosterShowAll">
              {{ privateRosterShowAll ? "只看会话" : "显示全部" }}
            </el-button>
            <el-button size="small" text @click="privateRosterCollapsed = true">收起</el-button>
          </div>
          <button
            v-for="member in privateRosterMembers"
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
          <div v-if="!privateRosterMembers.length" class="private-empty">{{ privateRosterEmptyText }}</div>
          <button
            v-if="!privateRosterShowAll && !privateMemberSearch.trim() && hiddenPrivatePartnerCount > 0"
            type="button"
            class="private-show-all-button"
            @click="privateRosterShowAll = true"
          >
            显示另外 {{ hiddenPrivatePartnerCount }} 位成员          </button>
        </aside>
        <section class="private-thread-pane private-dialog-thread">
          <div class="private-thread-head" :class="{ 'private-thread-head-roster-collapsed': privateRosterCollapsed }">
            <button
              v-if="privateRosterCollapsed"
              type="button"
              class="private-roster-expand-button"
              title="展开私聊列表"
              @click="privateRosterCollapsed = false"
            >
              <ArrowRight />
            </button>
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
          <p class="context-note">AI 使用记录不可修改，用于回看 Agent 的回答问题、使用时间和记忆引用情况。</p>
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
          <h3>读取记忆</h3>
          <div v-if="selectedAudit.memory_reads.length" class="detail-ref-list">
            <button v-for="(ref, index) in selectedAudit.memory_reads" :key="index" type="button" @click="openAuditMemory(ref)">
              {{ extractRefId(ref) || `记忆 ${index + 1}` }}
            </button>
          </div>
          <p v-else class="context-empty context-empty-compact">暂无记录</p>
        </section>
        <div class="detail-actions">
          <el-button size="small" :icon="CopyDocument" @click="copyAuditDetail">复制审计信息</el-button>
          <el-button size="small" @click="reuseAuditQuestion">重新提问</el-button>
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
          <h3>来源</h3>
          <div class="detail-meta-grid">
            <span>来源位置</span>
            <strong>本会议室</strong>
            <span>来源消息</span>
            <strong>{{ sourceMessageLabel(selectedSharedMemory) }}</strong>
            <span>父版本</span>
            <strong>{{ selectedSharedMemory.version_parent_id ? "由上一版修订而来" : "暂无历史版本" }}</strong>
            <span>确认人</span>
            <strong>{{ memberDisplayName(selectedSharedMemory.confirmed_by || selectedSharedMemory.created_by) }}</strong>
            <span>确认时间</span>
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
          </div>
          <div v-if="selectedSharedMemory.recommended_actions?.length" class="recommended-action-list">
            <span v-for="action in selectedSharedMemory.recommended_actions" :key="action">{{ action }}</span>
          </div>
        </section>
        <section class="detail-section">
          <h3>沉淀与共享</h3>
          <div class="detail-meta-grid">
            <span>作用域</span>
            <strong>{{ memoryScopeLabel(selectedSharedMemory.scope || selectedSharedMemory.scope_type) }}</strong>
            <span>目标</span>
            <strong>{{ scopeObjectLabel(selectedSharedMemory) }}</strong>
            <span>可见范围</span>
            <strong>{{ scopeVisibilityNote(selectedSharedMemory) }}</strong>
            <span>确认说明</span>
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
          <el-button size="small" type="primary" @click="confirmCandidateMemory(selectedSharedMemory)">共享/修订</el-button>
          <el-button size="small" @click="openMemoryCollabShare(selectedSharedMemory)">请求确认</el-button>
        </div>
      </div>
    </el-drawer>
    <el-dialog
      v-model="memoryPublishDialogVisible"
      class="memory-publish-dialog"
      title="记忆沉淀/共享"
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
          <span>来源：本会议室· {{ sourceMessageLabel(selectedCandidateMemory) }}</span>
        </div>
        <div v-if="visibleMemoryWarnings(memoryPublishPreview).length" class="memory-warning-list">
          <span v-for="warning in visibleMemoryWarnings(memoryPublishPreview)" :key="warning">{{ warning }}</span>
        </div>
        <div class="memory-publish-evidence">
          <div v-if="selectedCandidateMemory.extraction_reason" class="memory-publish-evidence-row">
            <span>提取理由</span>
            <strong>{{ selectedCandidateMemory.extraction_reason }}</strong>
          </div>
          <div v-if="sourceSpanSummary(selectedCandidateMemory)" class="memory-publish-evidence-row">
            <span>来源片段</span>
            <strong>{{ sourceSpanSummary(selectedCandidateMemory) }}</strong>
          </div>
          <div v-if="relatedMemorySummary(selectedCandidateMemory)" class="memory-publish-evidence-row">
            <span>关联记忆</span>
            <strong>{{ relatedMemorySummary(selectedCandidateMemory) }}</strong>
          </div>
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
          <span>沉淀回本会议室不会生成预警。</span>
        </div>
        <div v-if="memoryPublishTargetPreview" class="memory-publish-flow" :class="{ 'memory-publish-flow-pending': memoryPublishTargetPreview.pending }">
          <div class="memory-publish-flow-node">
            <span>来源</span>
            <strong>{{ store.activeRoom?.title || "当前会议室" }}</strong>
          </div>
          <div class="memory-publish-flow-arrow">→</div>
          <div class="memory-publish-flow-node">
            <span>{{ memoryPublishTargetPreview.type }}</span>
            <strong>{{ memoryPublishTargetPreview.label }}</strong>
            <small>{{ memoryPublishTargetPreview.description }}</small>
          </div>
        </div>
        <el-form label-position="top" class="memory-publish-form">
          <el-form-item label="共享目标">
            <el-select
              v-model="memoryPublishForm.target_key"
              class="memory-publish-scope-select"
              @update:model-value="applyMemoryPublishOption"
            >
              <el-option
                v-for="option in memoryPublishScopeOptions"
                :key="option.key"
                :label="option.label"
                :value="option.key"
              >
                <div class="memory-scope-option">
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.note }}</small>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item v-if="memoryPublishTargetRequired" :label="selectedMemoryPublishScopeOption?.targetLabel || '目标对象'">
            <el-select
              v-model="memoryPublishForm.scope_id"
              class="memory-publish-target-select"
              filterable
              clearable
              :placeholder="selectedMemoryPublishScopeOption?.targetPlaceholder || '搜索并选择目标'"
              :no-data-text="selectedMemoryPublishScopeOption?.targetEmptyText || '暂无可选目标'"
            >
              <el-option
                v-for="target in memoryPublishTargetOptions"
                :key="target.value"
                :label="target.label"
                :value="target.value"
              >
                <div class="memory-target-option">
                  <strong>{{ target.label }}</strong>
                  <small>{{ target.description }}</small>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="说明">
            <el-input
              v-model="memoryPublishForm.publish_reason"
              type="textarea"
              :rows="2"
              maxlength="1000"
              show-word-limit
              placeholder="可选：说明为什么要沉淀或共享这条记忆，便于后续追溯"
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="memoryPublishDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="memoryPublishSubmitting"
          :disabled="memoryPublishSubmitDisabled"
          @click="submitMemoryPublish"
        >
          {{ memoryPublishSubmitText }}
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

.private-sidecar-head > div:first-child {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.private-sidecar-head span {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.private-sidecar-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
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

.visibility-pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 11px;
  font-weight: 800;
}

.visibility-room {
  background: #dcfce7;
  color: #166534;
}

.visibility-private {
  background: #fef3c7;
  color: #92400e;
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

.private-sidecar-roster {
  flex: 0 0 auto;
}

.private-sidecar-roster .private-launcher-list {
  max-height: 176px;
  overflow-y: auto;
  padding-right: 2px;
}

.private-roster-tools {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
}

.private-dialog-roster-tools {
  grid-template-columns: minmax(0, 1fr) auto auto;
  position: sticky;
  top: 0;
  z-index: 1;
  padding-bottom: 4px;
  background: #fafafa;
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

.private-show-all-button {
  width: 100%;
  min-height: 32px;
  border: 1px dashed #d4d4d8;
  border-radius: 8px;
  background: #fff;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.private-show-all-button:hover {
  border-color: #a1a1aa;
  background: #f8fafc;
}

.private-popup-hint {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px dashed #d4d4d8;
  border-radius: 8px;
  background: #fafafa;
}

.private-popup-hint span {
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
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

.private-dialog-body-roster-collapsed {
  grid-template-columns: minmax(0, 1fr);
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
  grid-template-columns: auto 30px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.private-thread-head:not(.private-thread-head-roster-collapsed) {
  grid-template-columns: 30px minmax(0, 1fr);
}

.private-roster-expand-button {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid #e4e4e7;
  border-radius: 7px;
  background: #fff;
  color: #52525b;
  cursor: pointer;
}

.private-roster-expand-button:hover {
  border-color: #d4d4d8;
  background: #f4f4f5;
}

.private-roster-expand-button svg {
  width: 14px;
  height: 14px;
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

.room-list-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.room-list-actions button {
  height: 26px;
  padding: 0 8px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  background: #fff;
  color: #52525b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.room-list-actions button:hover,
.room-list-filter-active {
  border-color: #18181b;
  background: #18181b;
  color: #fff;
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

.context-note {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.boundary-card {
  background: #fcfcfd;
}

.boundary-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.boundary-block,
.agent-domain-panel {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #edf0f3;
  border-radius: 8px;
  background: #fff;
}

.boundary-block-head,
.agent-domain-head,
.agent-domain-item {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.boundary-block-head strong,
.agent-domain-head strong,
.agent-domain-item strong {
  min-width: 0;
  overflow: hidden;
  color: #111827;
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.boundary-block-head span,
.agent-domain-head span {
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 900;
}

.domain-group-list,
.agent-domain-list {
  display: grid;
  gap: 7px;
}

.domain-group {
  display: grid;
  gap: 5px;
}

.domain-group > span,
.agent-domain-item small {
  color: #71717a;
  font-size: 11px;
  font-weight: 800;
}

.domain-chip-row {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.domain-chip {
  max-width: 100%;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border: 1px solid #dbeafe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.domain-chip-room {
  border-color: #dcfce7;
  background: #f0fdf4;
  color: #166534;
}

.domain-chip-sensitive {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.domain-chip-agent {
  border-color: #e9d5ff;
  background: #faf5ff;
  color: #6b21a8;
}

.domain-chip-muted {
  border-color: #e4e4e7;
  background: #f4f4f5;
  color: #52525b;
}

.agent-domain-list {
  max-height: 220px;
  overflow: auto;
  padding-right: 2px;
}

.agent-domain-item {
  align-items: flex-start;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
}

.agent-domain-item:first-child {
  padding-top: 0;
  border-top: 0;
}

.agent-domain-item > div:first-child {
  min-width: 96px;
  display: grid;
  gap: 2px;
}

.denied-reason-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.denied-reason-list span {
  max-width: 100%;
  padding: 3px 7px;
  border: 1px solid #fee2e2;
  border-radius: 999px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 11px;
  font-weight: 800;
  overflow-wrap: anywhere;
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
.shared-memory,
.governance-item {
  padding: 10px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #fafafa;
}

.governance-item {
  display: grid;
  gap: 7px;
}

.governance-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.governance-item-head strong {
  min-width: 0;
  color: #111827;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.governance-item-head span {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 800;
}

.governance-item p {
  margin: 0;
  color: #374151;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.governance-item small {
  color: #71717a;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
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

.summary-item {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
}

.summary-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.summary-item-head strong {
  color: #111827;
  font-size: 13px;
}

.summary-item-head time {
  flex: 0 0 auto;
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.summary-item p {
  margin: 0;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.summary-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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

.memory-evidence-panel {
  display: grid;
  gap: 5px;
  margin-top: 8px;
  padding: 8px;
  border: 1px solid #e4e4e7;
  border-radius: 7px;
  background: #fff;
}

.memory-evidence-panel span {
  color: #52525b;
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
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

.memory-publish-evidence {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.memory-publish-evidence-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.memory-publish-evidence-row span {
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 900;
}

.memory-publish-evidence-row strong {
  color: #1f2937;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
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

.memory-publish-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
  padding: 12px;
  border: 1px solid #d7e2dc;
  border-radius: 14px;
  background:
    radial-gradient(circle at 12% 20%, rgba(45, 138, 104, 0.12), transparent 28%),
    linear-gradient(135deg, #f8fbf7 0%, #eef5f1 100%);
}

.memory-publish-flow-pending {
  border-color: #ead8a3;
  background:
    radial-gradient(circle at 12% 20%, rgba(196, 140, 34, 0.12), transparent 28%),
    linear-gradient(135deg, #fffaf0 0%, #f7f1df 100%);
}

.memory-publish-flow-node {
  min-width: 0;
  display: grid;
  gap: 4px;
  align-content: center;
  padding: 10px;
  border: 1px solid rgba(32, 93, 71, 0.12);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
}

.memory-publish-flow-node span,
.memory-publish-flow-node small {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.memory-publish-flow-node strong {
  min-width: 0;
  color: #1f3f34;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-publish-flow-arrow {
  display: grid;
  place-items: center;
  color: #2f7d5d;
  font-size: 18px;
  font-weight: 900;
}

.memory-publish-scope-select,
.memory-publish-target-select {
  width: 100%;
}

.memory-scope-option,
.memory-target-option {
  display: grid;
  gap: 2px;
  line-height: 1.25;
}

.memory-scope-option small,
.memory-target-option small {
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

  .memory-publish-evidence-row {
    grid-template-columns: 1fr;
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
