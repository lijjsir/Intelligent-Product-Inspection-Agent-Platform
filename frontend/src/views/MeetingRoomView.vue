<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Bell, ChatDotRound, Check, Close, CopyDocument, DataAnalysis, Delete, EditPen, FullScreen, Grid, Key, List, MagicStick, Menu, Minus, Paperclip, Plus, Promotion, RefreshRight, ScaleToOriginal, Setting, Share, User, View } from "@element-plus/icons-vue";
import axios from "axios";
import { ElMessage, ElMessageBox, ElNotification } from "element-plus";
import "element-plus/es/components/notification/style/css";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type StyleValue } from "vue";
import { useRouter } from "vue-router";
import { feedbackApi } from "@/api/feedback.api";
import ImageAttachmentCard from "@/components/common/ImageAttachmentCard.vue";
import ImagePreviewDialog from "@/components/common/ImagePreviewDialog.vue";
import MessageActionBar from "@/components/common/MessageActionBar.vue";
import { useAuthStore } from "@/stores/auth.store";
import { useMeetingStore } from "@/stores/meeting.store";
import { useUserStore } from "@/stores/user.store";
import type { MeetingAgentQueryAudit, MeetingAttachment, MeetingAutoParticipationMode, MeetingDataDomain, MeetingMemory, MeetingMemoryPublishScope, MeetingMessage, MeetingQuoteSnapshot, MeetingRoom, MeetingRoomMember } from "@/types/meeting.types";
import { normalizeAiResponseText } from "@/utils/ai-response";
import { attachmentDisplayName, isImageAttachment } from "@/utils/attachments";
import { writeTextToClipboard } from "@/utils/clipboard";

const auth = useAuthStore();
const store = useMeetingStore();
const userStore = useUserStore();
const router = useRouter();
const MESSAGE_RECALL_WINDOW_MS = 2 * 60 * 1000;

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
const aiConversationTab = ref<"private" | "public" | "auto">("private");
type MeetingLayoutMode = "workspace" | "classic";
type MeetingWorkspaceSection = "live" | "ai" | "private" | "overview" | "memory" | "tasks" | "audit";
type WorkspaceMemoryTab = "candidate" | "confirmed" | "governance";
const MEETING_LAYOUT_MODE_KEY = "piap_meeting_layout_mode";

function storedMeetingLayoutMode(): MeetingLayoutMode {
  try {
    return window.localStorage.getItem(MEETING_LAYOUT_MODE_KEY) === "classic" ? "classic" : "workspace";
  } catch {
    return "workspace";
  }
}

const meetingLayoutMode = ref<MeetingLayoutMode>(storedMeetingLayoutMode());
const workspaceSection = ref<MeetingWorkspaceSection>("live");
const workspaceStageRef = ref<HTMLElement | null>(null);
const workspaceMemoryTab = ref<WorkspaceMemoryTab>("candidate");
const workspaceSelectedMemoryId = ref("");
const linkedMemoryId = ref("");
const autoParticipationUnreadCount = ref(0);
const autoParticipationTrackingRoomId = ref("");
let knownAutoParticipationReplyIds = new Set<string>();
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
const autoParticipationSaving = ref(false);
const agentQuestionSources = ref<Array<{
  message_id: string;
  seq_no: number;
  author: string;
  selected_text?: string;
  content?: string;
}>>([]);
const agentShareDialogVisible = ref(false);
const agentShareSubmitting = ref(false);
const agentShareMessage = ref<MeetingMessage | null>(null);
const agentShareContent = ref("");
const businessObjectDrawerVisible = ref(false);
const businessObjectCorrection = ref("");
const businessObjectCorrectionSaving = ref(false);
const businessObjectRemovingId = ref("");
const messageSelectionMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  below: false,
  text: "",
  message: null as MeetingMessage | null,
});
const newMainMessageCount = ref(0);
const mainWasNearBottom = ref(true);
const selectedSharedMemory = ref<MeetingMemory | null>(null);
const memoryDetailVisible = ref(false);
const rejectingMemoryId = ref("");
const memoryPublishForm = reactive({
  target_key: "current_meeting_room" as MemoryPublishTargetKey,
  title: "",
  content: "",
  scope: "meeting_room" as MeetingMemoryPublishScope,
  scope_id: "",
  publish_reason: "",
  idempotency_key: "",
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
  | "user"
  | "org_space";
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
type AutoParticipationDecisionRef = {
  type: "auto_participation_decision";
  mode?: MeetingAutoParticipationMode;
  decision?: string;
  trigger_type?: string;
  action_type?: string;
  target_role?: string | null;
  confidence?: number;
  resource_key?: string;
  reason?: string;
  human_is_handling?: boolean;
  evidence_refs?: Array<Record<string, unknown>>;
  suppression_reasons?: string[];
};
type AutoParticipationMessageMetadata = {
  audit_id?: string;
  trigger_message_id?: string;
  trigger_type?: string;
  action_type?: string;
  target_role?: string | null;
  confidence?: number;
  resource_key?: string;
  reason?: string;
  evidence_refs?: Array<Record<string, unknown>>;
};
type AuditEvidenceView = {
  key: string;
  title: string;
  meta: string;
  content: string;
  traceId: string;
  traceLabel: string;
  ref: Record<string, unknown>;
  memoryAvailable: boolean;
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
  decision: "待确认结论",
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
const qdlKnowledgeLevelLabels: Record<string, string> = {
  fact: "事实",
  decision: "决策",
  rule: "规则",
  pattern: "模式",
  concept: "概念",
  hypothesis: "假设",
};
const qdlPropertyLabels: Record<string, string> = {
  abstraction: "抽象性",
  environment: "环境相关",
  boundary: "边界性",
  dynamic: "动态性",
  social: "社会性",
  tacit: "默会性",
  hierarchy: "层次性",
  stability: "稳定性",
};
const qdlPropertyLevelLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  unknown: "待判断",
};
const qdlEntityTypeLabels: Record<string, string> = {
  product: "产品",
  batch: "批次",
  task: "任务",
  standard: "标准",
  role: "角色",
  other: "其他",
};
const qdlRelationLabels: Record<string, string> = {
  supports: "支持",
  contradicts: "矛盾",
  supplements: "补充",
  refines: "细化",
  depends_on: "依赖",
  derived_from: "来源于",
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
    { id: "general_agent", agent_name: "会议Agent", description: "回答、启发、校核与总结" },
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
const canManageRoom = computed(() => {
  if (!store.activeRoom) return false;
  if (store.activeRoom.created_by === auth.userId) return true;
  return store.members.some((member) => member.user_id === auth.userId && member.role === "host");
});
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
const autoParticipationMode = computed<MeetingAutoParticipationMode>(() => {
  const policy = store.activeRoom?.audit_policy;
  const mode = String(policy?.auto_participation_mode || "off");
  return mode === "live" ? mode : "off";
});
const autoParticipationOptions: Array<{
  value: MeetingAutoParticipationMode;
  label: string;
  description: string;
}> = [
  {
    value: "off",
    label: "关闭",
    description: "不读取公共发言用于主动判断，不调用模型、不写审计；手动 @会议Agent 仍可使用。",
  },
  {
    value: "live",
    label: "开启",
    description: "基于公共讨论提供追问、调和、启发、标准提醒与决策建议；每次参与都保留依据和置信度。",
  },
];
const autoParticipationDescription = computed(() => (
  autoParticipationOptions.find((item) => item.value === autoParticipationMode.value)?.description
  || autoParticipationOptions[0].description
));
const memoryGovernanceHint = computed(() => {
  const memory = selectedSharedMemory.value;
  if (!memory) return "暂无记录";
  const relatedAudits = store.agentQueryAudits.filter((audit) => auditUsesMemory(audit, memory.memory_id));
  return relatedAudits.length ? `${relatedAudits.length} 次 AI 使用记录引用过这条记忆` : "暂无被引用记录";
});
const selectedMemoryIsCandidate = computed(() => selectedSharedMemory.value?.status === "candidate");
const memoryDetailTitle = computed(() => (
  selectedMemoryIsCandidate.value ? "待确认知识完整详情" : "已确认知识详情"
));
const workspaceMemoryItems = computed<MeetingMemory[]>(() => (
  workspaceMemoryTab.value === "candidate"
    ? store.candidateMemories
    : workspaceMemoryTab.value === "confirmed"
      ? store.confirmedMemories
      : []
));
const workspaceSelectedMemory = computed<MeetingMemory | null>(() => (
  workspaceMemoryItems.value.find((memory) => memory.memory_id === workspaceSelectedMemoryId.value)
  || workspaceMemoryItems.value[0]
  || null
));
const workspaceGovernanceCount = computed(() => (
  store.pendingMemoryShares.length + store.conflictEvents.filter((conflict) => conflict.status === "pending").length
));
const selectedAuditEvidenceViews = computed(() => (
  autoAuditEvidence(selectedAudit.value).map(evidenceRefView)
));
const selectedAuditMemoryViews = computed(() => (
  (selectedAudit.value?.memory_reads || []).map(evidenceRefView)
));
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
const autoParticipationReplies = computed(() => store.activeRoomMessages.filter(isAutoParticipationReply));
const manualPublicAgentMessages = computed(() => (
  store.publicAgentMessages.filter((message) => !isAutoParticipationReply(message))
));
const visibleAgentPanelMessages = computed(() => {
  if (aiConversationTab.value === "private") {
    return store.privateAgentMessages.filter(canShowInAgentPanel);
  }
  if (aiConversationTab.value === "auto") return autoParticipationReplies.value;
  return manualPublicAgentMessages.value;
});
const agentConversationEmptyText = computed(() => {
  if (aiConversationTab.value === "private") return "暂无私人 AI 对话";
  if (aiConversationTab.value === "auto") return "暂无 Agent 主动介入";
  return "暂无公开问答";
});
const agentPanelVisible = computed(() => (
  rightPanelTab.value === "ai"
  && !rightPanelCollapsed.value
  && (meetingLayoutMode.value === "classic" || workspaceSection.value === "ai")
));
const visibleBusinessObjects = computed(() => store.businessObjects.filter((item) => item.status !== "rejected"));
const publicAgentRepliesByTrigger = computed(() => {
  const result = new Map<string, MeetingMessage[]>();
  for (const message of store.publicAgentMessages) {
    if (!["agent", "agent_streaming"].includes(message.message_type)) continue;
    const metadata = messageMetadata(message);
    const triggerId = String(metadata.question_message_id || metadata.trigger_message_id || "");
    if (!triggerId) continue;
    result.set(triggerId, [...(result.get(triggerId) || []), message]);
  }
  return result;
});
const summaryMessages = computed(() => store.systemPanelMessages.filter((message) => message.message_type === "summary"));
const latestSummaryMessage = computed(() => summaryMessages.value[summaryMessages.value.length - 1] || null);
type AgentConversationGroup = {
  id: string;
  kind: "question" | "auto";
  questionNumber: number | null;
  question: MeetingMessage | null;
  replies: MeetingMessage[];
  staleReplyCount: number;
  autoParticipation: AutoParticipationMessageMetadata | null;
};

const agentConversationGroups = computed(() => {
  const groups: AgentConversationGroup[] = [];
  const groupsByQuestionId = new Map<string, AgentConversationGroup>();
  let currentGroup: AgentConversationGroup | null = null;
  let questionNumber = 0;

  const createQuestionGroup = (id: string, question: MeetingMessage | null = null) => {
    questionNumber += 1;
    const group: AgentConversationGroup = {
      id,
      kind: "question",
      questionNumber,
      question,
      replies: [],
      staleReplyCount: 0,
      autoParticipation: null,
    };
    groups.push(group);
    return group;
  };

  for (const message of visibleAgentPanelMessages.value) {
    if (message.message_type === "user") {
      currentGroup = groupsByQuestionId.get(message.id) || createQuestionGroup(message.id, message);
      // A reply may be present before its question in a reconnect snapshot.
      // Fill the synthetic group instead of creating a second visual target.
      currentGroup.question = message;
      groupsByQuestionId.set(message.id, currentGroup);
      continue;
    }
    const autoParticipation = autoParticipationMessageMetadata(message);
    if (isAutoParticipationReply(message)) {
      currentGroup = null;
      groups.push({
        id: `auto-${message.id}`,
        kind: "auto",
        questionNumber: null,
        question: null,
        replies: [message],
        staleReplyCount: 0,
        autoParticipation: autoParticipation || {},
      });
      continue;
    }

    const metadata = messageMetadata(message);
    const linkedQuestionId = String(metadata.question_message_id || metadata.trigger_message_id || "").trim();
    if (linkedQuestionId) {
      // Replies can arrive after several repeated or concurrent questions.
      // The linkage ID is authoritative; relying on the latest question in
      // the render loop makes an earlier reply disappear from the AI panel.
      currentGroup = groupsByQuestionId.get(linkedQuestionId)
        || createQuestionGroup(`agent-${linkedQuestionId}`);
      groupsByQuestionId.set(linkedQuestionId, currentGroup);
      currentGroup.replies.push(message);
      continue;
    }

    if (!currentGroup) {
      currentGroup = createQuestionGroup(`agent-${message.id}`);
    }
    if (!currentGroup.question || isCurrentAgentReplyForQuestion(currentGroup.question, message)) {
      currentGroup.replies.push(message);
    } else {
      currentGroup.staleReplyCount += 1;
    }
  }
  for (const group of groups) {
    if (group.replies.length <= 1) continue;
    group.staleReplyCount += group.replies.length - 1;
    group.replies = [group.replies[group.replies.length - 1]];
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
  if (memoryPublishForm.target_key === "target_meeting_room") return "确认并申请共享";
  if (memoryPublishForm.target_key === "user") return "确认并申请共享给成员";
  if (memoryPublishForm.target_key === "org_space") return "确认并申请组织共享";
  return "确认并共享";
});

function canDeleteRoom(room: MeetingRoom) {
  return room.created_by === auth.userId;
}

function canLeaveRoom(room: MeetingRoom) {
  return room.created_by !== currentUserId.value;
}

function auditDecisionLabel(audit: MeetingAgentQueryAudit) {
  const value = audit.decision;
  if (value === "silent") return "Agent 未发言";
  if (value === "observe") return "Agent 继续观察";
  if (value === "participate") return "Agent 已发言";
  if (value === "allowed") return "全部数据可用";
  if (value === "partial") return "部分数据可用";
  if (value === "denied") return "数据访问受限";
  return value || "结果未知";
}

function auditDecisionDescription(audit: MeetingAgentQueryAudit) {
  if (audit.decision === "silent") return "识别到候选问题，但硬抑制规则要求保持沉默。";
  if (audit.decision === "observe") return "暂不打断会议，等待下一条相关人类发言。";
  if (audit.decision === "participate") return "判断通过，Agent 已在会议中公开提醒。";
  if (audit.decision === "allowed") return "本次回答可以使用请求的全部数据。";
  if (audit.decision === "partial") return "本次回答只使用获准的数据，其他数据未读取。";
  if (audit.decision === "denied") return "请求的数据不可用，Agent 未读取受限数据。";
  return "暂无结果说明。";
}

function auditIntentLabel(value?: string | null) {
  const labels: Record<string, string> = {
    auto_evidence_gap: "主动参与：证据缺失",
    auto_unresolved_conflict: "主动参与：未决冲突",
    auto_history_conflict: "主动参与：历史约束冲突",
    general_chat: "普通 AI 回答",
    quality_task_status: "质检任务查询",
    error: "回答异常记录",
  };
  const normalized = String(value || "").trim();
  return labels[normalized] || normalized || "暂无记录";
}

function auditEvidenceSectionTitle(audit: MeetingAgentQueryAudit) {
  return autoAuditDecision(audit) ? "判断依据" : "关联消息";
}

function auditDecisionClass(value: string) {
  if (value === "silent") return "audit-silent";
  if (value === "observe") return "audit-observe";
  if (value === "participate") return "audit-participate";
  if (value === "allowed") return "audit-allowed";
  if (value === "partial") return "audit-partial";
  if (value === "denied") return "audit-denied";
  return "";
}

function autoParticipationModeLabel(mode?: string | null) {
  if (mode === "live") return "主动参与已开启";
  return "关闭";
}

function autoParticipationTriggerLabel(value?: string | null) {
  if (value === "evidence_gap") return "证据缺失";
  if (value === "unresolved_conflict") return "未决冲突";
  if (value === "history_conflict") return "历史约束冲突";
  if (value === "discussion_stall") return "讨论停滞";
  if (value === "decision_ready") return "方案待收敛";
  return "无触发";
}

function autoParticipationActionLabel(value?: string | null) {
  if (value === "evidence_query") return "追问证据";
  if (value === "clarify") return "澄清争议";
  if (value === "standard_remind") return "提醒标准";
  if (value === "brainstorm") return "启发讨论";
  if (value === "decision_support") return "方案比较";
  return "无动作";
}

function autoParticipationTargetLabel(value?: string | null) {
  if (value === "expert") return "领域专家";
  if (value === "algorithm_engineer") return "算法工程师";
  if (value === "platform_operator") return "平台运营人员";
  if (value === "user") return "参会成员";
  return "未指定";
}

function autoParticipationMessageMetadata(message?: MeetingMessage | null): AutoParticipationMessageMetadata | null {
  const value = message?.metadata_json?.auto_participation;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as AutoParticipationMessageMetadata;
}

function isAutoParticipationReply(message: MeetingMessage) {
  return ["agent", "agent_streaming"].includes(message.message_type)
    && (
      Boolean(message.metadata_json?.auto_participation)
      || String(message.metadata_json?.interaction_mode || "") === "auto_participation"
    );
}

function autoParticipationConfidenceLabel(value?: number | null) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function autoParticipationSuppressionLabel(value: string) {
  const labels: Record<string, string> = {
    invalid_decision: "模型决策格式无效",
    confidence_below_threshold: "诊断置信度低于阈值",
    no_valid_evidence: "没有可验证依据",
    missing_resource_key: "缺少稳定资源键（修复前记录）",
    missing_trigger: "缺少有效触发类型",
    missing_action: "缺少可执行动作",
    target_role_not_present: "目标角色不在会议中",
    human_is_handling: "人类正在处理",
    no_active_history_basis: "没有有效历史依据",
    duplicate_without_new_evidence: "三轮内重复且没有新证据",
    insufficient_human_turns: "相关人工讨论不足四轮",
    model_unavailable: "诊断模型不可用",
    invalid_model_json: "诊断模型返回格式无效",
    evaluation_failed: "主动参与判断失败",
  };
  return labels[value] || value;
}

function autoAuditSuppressionSummary(audit?: MeetingAgentQueryAudit | null) {
  const reasons = autoAuditDecision(audit)?.suppression_reasons || [];
  return reasons.map(autoParticipationSuppressionLabel).join("、");
}

function autoAuditDecision(audit?: MeetingAgentQueryAudit | null): AutoParticipationDecisionRef | null {
  if (!audit) return null;
  const ref = (audit.source_refs || []).find((item) => item.type === "auto_participation_decision");
  return ref ? ref as AutoParticipationDecisionRef : null;
}

function autoAuditEvidence(audit?: MeetingAgentQueryAudit | null) {
  if (!audit) return [];
  const diagnostic = autoAuditDecision(audit);
  const refs = diagnostic?.evidence_refs?.length
    ? diagnostic.evidence_refs
    : (audit.source_refs || []).filter((item) => item.type !== "auto_participation_decision");
  const seen = new Set<string>();
  return refs.filter((ref) => {
    if (String(ref.type || "") === "memory") return false;
    const key = `${String(ref.type || "evidence")}:${extractRefId(ref)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function shortenedTraceId(value: string) {
  if (value.length <= 18) return value;
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function evidenceRefView(ref: Record<string, unknown>, index: number): AuditEvidenceView {
  const type = String(ref.type || "");
  const id = extractRefId(ref);
  const fallbackKey = `${type || "evidence"}-${id || index}`;
  const traceLabel = id ? `追溯编号 ${shortenedTraceId(id)}` : `依据 ${index + 1}`;

  if (type === "meeting_message") {
    const message = store.activeRoomMessages.find((item) => item.id === id);
    if (message) {
      return {
        key: fallbackKey,
        title: `会议消息 #${message.seq_no}`,
        meta: `${message.username} · ${formatTime(message.created_at) || "时间未知"}`,
        content: clipText(displayMessageContent(message), 220),
        traceId: id,
        traceLabel,
        ref,
        memoryAvailable: false,
      };
    }
    return {
      key: fallbackKey,
      title: "会议消息（当前未加载）",
      meta: "来源消息不在当前加载范围",
      content: "可根据下方追溯编号在完整会议记录中查询。",
      traceId: id,
      traceLabel,
      ref,
      memoryAvailable: false,
    };
  }

  if (type === "memory") {
    const memory = store.memories.find((item) => item.memory_id === id);
    if (memory) {
      return {
        key: fallbackKey,
        title: `会议记忆 · ${memory.title}`,
        meta: `${memoryStatusLabel(memory.status)} · ${memoryScopeLabel(memory.scope || memory.scope_type)}`,
        content: memoryPreview(memory, 220),
        traceId: id,
        traceLabel,
        ref,
        memoryAvailable: true,
      };
    }
    return {
      key: fallbackKey,
      title: "会议记忆（当前不可见）",
      meta: String(ref.scope || "记忆引用"),
      content: "该记忆可能已被替代、移出当前范围或尚未加载。",
      traceId: id,
      traceLabel,
      ref,
      memoryAvailable: false,
    };
  }

  if (type === "inspection_task") {
    const task = currentBusinessContext.value?.tasks?.find((item) => item.id === id);
    return {
      key: fallbackKey,
      title: `质检任务 · ${task?.spec_code || "未命名任务"}`,
      meta: task ? `状态 ${task.status} · ${task.has_result ? "已有结果" : "暂无结果"}` : "任务详情当前未加载",
      content: task ? `产品 ${task.product_id}` : "可根据下方追溯编号查询质检任务。",
      traceId: id,
      traceLabel,
      ref,
      memoryAvailable: false,
    };
  }

  if (type === "conflict") {
    const conflict = store.conflictEvents.find((item) => item.id === id);
    return {
      key: fallbackKey,
      title: `冲突事件 · ${conflict ? conflictTypeLabel(conflict.conflict_type) : "详情未加载"}`,
      meta: conflict ? `状态 ${conflict.status}` : "冲突详情当前未加载",
      content: conflict?.selected_action ? `已选择处理方式：${conflict.selected_action}` : "尚未记录最终处理方式。",
      traceId: id,
      traceLabel,
      ref,
      memoryAvailable: false,
    };
  }

  if (type === "standard") {
    return {
      key: fallbackKey,
      title: "会议绑定标准",
      meta: "质检标准依据",
      content: id || "标准编号未记录",
      traceId: id,
      traceLabel,
      ref,
      memoryAvailable: false,
    };
  }

  return {
    key: fallbackKey,
    title: "其他判断依据",
    meta: type || "类型未记录",
    content: "该依据暂无可读摘要，可使用追溯编号查询原始记录。",
    traceId: id,
    traceLabel,
    ref,
    memoryAvailable: false,
  };
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

function qdlValidationLabel(memory: MeetingMemory) {
  if (memory.qdl_validation_status === "valid") return "Schema 已通过";
  if (memory.qdl_validation_status === "legacy_mapped") return "v1 已兼容映射";
  if (memory.qdl_validation_status === "invalid") return "Schema 未通过";
  return "暂无 QDL";
}

function qdlExtractionMethodLabel(value?: string | null) {
  if (value === "mixed") return "LLM 语义提取 + 程序校验";
  if (value === "llm") return "LLM 语义提取";
  if (value === "heuristic") return "规则兜底提取";
  return "未记录";
}

function qdlKnowledgeLevelLabel(memory: MeetingMemory) {
  const level = memory.qdl_json?.knowledge_level || "";
  return qdlKnowledgeLevelLabels[level] || level || "待判断";
}

function qdlPropertyRows(memory: MeetingMemory) {
  const properties = memory.qdl_json?.properties;
  if (!properties) return [];
  const fixedRows = Object.entries(qdlPropertyLabels).map(([key, label]) => {
    const assessment = properties[key as keyof typeof properties];
    if (!assessment || typeof assessment !== "object" || !("level" in assessment)) return null;
    return {
      key,
      label,
      level: assessment.level,
      levelLabel: qdlPropertyLevelLabels[assessment.level] || assessment.level,
      confidence: typeof assessment.confidence === "number" ? `${Math.round(assessment.confidence * 100)}%` : "",
      rationale: assessment.rationale || "",
    };
  }).filter((item): item is NonNullable<typeof item> => Boolean(item));
  const extensionRows = Object.entries(properties.extensions || {}).map(([key, assessment]) => ({
    key: `extension-${key}`,
    label: key,
    level: assessment.level,
    levelLabel: qdlPropertyLevelLabels[assessment.level] || assessment.level,
    confidence: typeof assessment.confidence === "number" ? `${Math.round(assessment.confidence * 100)}%` : "",
    rationale: assessment.rationale || "",
  }));
  return [...fixedRows, ...extensionRows];
}

function qdlEntityRows(memory: MeetingMemory) {
  return (memory.qdl_json?.entities || []).map((entity, index) => ({
    key: `${entity.entity_type}-${entity.entity_id || entity.value}-${index}`,
    type: qdlEntityTypeLabels[entity.entity_type] || entity.entity_type,
    value: entity.name || entity.value,
    status: entity.resolution_status === "resolved" ? "已解析" : entity.resolution_status === "ambiguous" ? "有歧义" : "未解析",
    confidence: typeof entity.confidence === "number" ? `${Math.round(entity.confidence * 100)}%` : "",
  }));
}

function qdlBusinessTags(memory: MeetingMemory) {
  const tags = memory.qdl_json?.applicability.business_tags || {};
  return Object.entries(tags).flatMap(([key, values]) => values.map((value) => ({ key: `${key}-${value}`, label: value })));
}

function qdlEvidenceRows(memory: MeetingMemory) {
  return (memory.qdl_json?.evidence || []).map((evidence, index) => {
    const messageId = String(evidence.message_id || (evidence.source_type === "meeting_message" ? evidence.source_id : "") || "");
    const message = messageId ? store.messages.find((item) => item.id === messageId) : null;
    return {
      key: `${evidence.source_type}-${evidence.source_id || messageId}-${index}`,
      messageId,
      label: message ? `消息 #${message.seq_no} · ${message.username}` : evidence.source_type === "meeting_room" ? "当前会议室" : "来源记录",
      quote: evidence.quote_text || (message ? displayMessageContent(message) : ""),
    };
  });
}

function qdlRelationRows(memory: MeetingMemory) {
  return (memory.qdl_json?.relations || []).map((relation, index) => ({
    key: `${relation.relation_type}-${relation.target_id}-${index}`,
    label: qdlRelationLabels[relation.relation_type] || relation.relation_type,
    target: relation.target_id,
    note: relation.note || "",
  }));
}

function memoryExtractionStatusLabel() {
  if (store.memoryExtractionStatus === "running") return "正在整理公共发言";
  if (store.memoryExtractionStatus === "success") return "本次已生成候选知识";
  if (store.memoryExtractionStatus === "empty") return "本次没有可沉淀内容";
  if (store.memoryExtractionStatus === "error") return "整理失败，可重新尝试";
  return "自动整理已启用";
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
  if (memoryCategory === "meeting_memory") warnings.add("该知识默认沉淀到当前会议室；需要跨范围使用时，可共享给其他会议室或组织共享空间。");
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

function pendingMemoryShare(memory: MeetingMemory) {
  const request = (memory.pending_share_requests || []).find((item) => item.status === "pending_approval")
    || (memory.pending_transfer_id ? {
      id: memory.pending_transfer_id,
      target_scope_type: memory.requested_scope_type,
      target_scope_id: memory.requested_scope_id,
    } : null);
  return request as Record<string, unknown> | null;
}

function pendingMemoryShareLabel(memory: MeetingMemory) {
  const request = pendingMemoryShare(memory);
  if (!request) return "";
  const scopeType = String(request.target_scope_type || "");
  if (scopeType === "org_space") return "等待管理员确认";
  if (scopeType === "user") return "等待目标成员确认";
  if (scopeType === "meeting_room") return "等待目标会议室主持人确认";
  return "等待目标范围确认";
}

function openMemoryShareInCollab(memory: MeetingMemory) {
  const request = pendingMemoryShare(memory);
  const transferId = String(request?.id || memory.pending_transfer_id || "");
  void router.push({
    path: "/app/collab",
    query: {
      view: "initiated",
      ...(transferId ? { work_item: `memory_share:${transferId}` } : {}),
    },
  });
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
    qdl_schema_version: memory.qdl_schema_version || null,
    qdl_validation_status: memory.qdl_validation_status || null,
    extraction_method: memory.extraction_method || null,
    extraction_model_id: memory.extraction_model_id || null,
    extraction_metrics: memory.extraction_metrics || null,
    qdl_json: memory.qdl_json || null,
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
  if (status === "confirmed") return "已确认";
  if (status === "short_term" || status === "candidate") return "待补证";
  if (status === "active") return "已确认";
  if (status === "disputed") return "存在争议";
  if (status === "superseded") return "已替代";
  if (status === "isolated") return "已隔离";
  if (status === "disabled" || status === "deleted") return "已停用";
  if (status === "rejected") return "已拒绝";
  return status || "未知";
}

function memoryCategoryHint(memory?: MeetingMemory | null) {
  const category = memory?.memory_category;
  if (memory?.memory_type === "risk_insight") return "风险洞察仍需人工确认，确认后可沉淀到当前会议室，也可共享给其他会议室或组织共享空间。";
  if (memory?.memory_type === "quality_fact") return "单次质量事实可先在会议室确认，再按需要共享给其他会议室或组织空间。";
  if (memory?.memory_type === "quality_pattern") return "可复用的问题模式建议沉淀到组织共享空间，供有权限的会议Agent后续召回。";
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
      value: "这是可复用模式，建议进入组织共享空间，或在协作中心发起结构化处理请求。",
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

function memorySourceSpans(memory?: MeetingMemory | null) {
  return (memory?.source_spans || []).map((span, index) => ({
    key: `${String(span.message_id || "source")}-${String(span.span_index || index + 1)}-${index}`,
    label: `来源片段 ${String(span.span_index || index + 1)}`,
    text: String(span.text || span.content || "").trim(),
  })).filter((span) => span.text);
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

async function copyMemoryDetail() {
  const memory = selectedSharedMemory.value;
  if (!memory) return;
  const sources = memorySourceSpans(memory)
    .map((span) => `${span.label}\n${span.text}`)
    .join("\n\n");
  const text = [memory.title, memory.content || memory.summary, sources].filter(Boolean).join("\n\n");
  await copyToClipboard(text, "完整记忆已复制");
}

function setMeetingLayoutMode(mode: MeetingLayoutMode) {
  meetingLayoutMode.value = mode;
  try {
    window.localStorage.setItem(MEETING_LAYOUT_MODE_KEY, mode);
  } catch {
    // Preference persistence is optional; the active layout still changes.
  }
}

function openWorkspaceSection(section: MeetingWorkspaceSection) {
  workspaceSection.value = section;
  if (section === "ai") {
    rightPanelTab.value = "ai";
    void scrollAgentPanelToLatest();
  }
  if (section === "private") rightPanelTab.value = "private";
  if (section === "overview") rightPanelTab.value = "context";
  if (section === "memory" && workspaceMemoryTab.value !== "governance") {
    workspaceSelectedMemoryId.value = workspaceMemoryItems.value[0]?.memory_id || "";
  }
  if (["memory", "tasks", "audit"].includes(section)) {
    void nextTick(() => {
      if (!window.matchMedia("(max-width: 920px)").matches) return;
      workspaceStageRef.value?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
        inline: "nearest",
      });
    });
  }
}

function selectWorkspaceMemoryTab(tab: WorkspaceMemoryTab) {
  workspaceMemoryTab.value = tab;
  workspaceSelectedMemoryId.value = tab === "candidate"
    ? store.candidateMemories[0]?.memory_id || ""
    : tab === "confirmed"
      ? store.confirmedMemories[0]?.memory_id || ""
      : "";
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
    `处理结果：${auditDecisionLabel(audit)}`,
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

function buildMemoryPublishScopeOptions(_memory?: MeetingMemory | null) {
  const targetMeetingRooms = store.rooms
    .filter((room) => room.id !== store.activeRoom?.id)
    .map((room) => ({
      label: roomDisplayTitle(room),
      value: room.id,
      description: `${room.member_count || 0} 位成员· ${meetingRoomStatusLabel(room.status) || "未知状态"}`,
    }));
  const targetMembers = store.members.map((member) => ({
    label: member.user_id === currentUserId.value ? `${member.username || "我"}（我）` : member.username || member.user_id,
    value: member.user_id,
    description: member.role === "host" ? "会议主持人 · 由本人确认后进入个人记忆" : "会议成员 · 由本人确认后进入个人记忆",
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
      note: "先沉淀到当前会议室，再提交目标会议室主持人审批；通过后目标会议室成员和会议 Agent 才可召回。",
    },
  ];
  options.push({
    key: "user",
    label: "共享给成员个人记忆",
    value: "user",
    scopeId: "",
    requiresTargetId: true,
    targetLabel: "选择成员",
    targetPlaceholder: "搜索当前会议室成员",
    targetOptions: targetMembers,
    targetEmptyText: "当前会议室暂无可选成员",
    note: "先沉淀到当前会议室，再由目标成员本人确认；批准后只增加个人记忆作用域。",
  });
  options.push({
    key: "org_space",
    label: "组织共享空间",
    value: "org_space",
    scopeId: "current",
    note: "先沉淀到当前会议室，再提交管理员进行组织级审批；通过后才进入组织共享检索。",
  });
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
  memoryPublishForm.idempotency_key = `meeting-share:${memory.memory_id}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
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

function agentQuestionRevision(message: MeetingMessage) {
  const editedAt = messageMetadata(message).edited_at;
  if (typeof editedAt === "string" && editedAt.trim()) return editedAt.trim();
  return message.updated_at || message.created_at || message.id;
}

function isCurrentAgentReplyForQuestion(question: MeetingMessage, reply: MeetingMessage) {
  const metadata = messageMetadata(reply);
  const linkedQuestionId = String(metadata.question_message_id || "").trim();
  if (linkedQuestionId && linkedQuestionId !== question.id) return false;
  const replyRevision = String(metadata.question_revision || "").trim();
  if (replyRevision) return replyRevision === agentQuestionRevision(question);
  const editedAt = messageMetadata(question).edited_at;
  if (typeof editedAt !== "string" || !editedAt.trim()) return true;
  const editedTime = new Date(editedAt).getTime();
  const replyTime = new Date(reply.created_at || "").getTime();
  if (!Number.isFinite(editedTime) || !Number.isFinite(replyTime)) return true;
  return replyTime > editedTime;
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
  try {
    const { value } = await ElMessageBox.prompt("请填写拒绝理由；原范围中的记忆会继续保留。", "拒绝共享申请", {
      confirmButtonText: "确认拒绝",
      cancelButtonText: "取消",
      inputPlaceholder: "例如：证据不足，暂不扩大共享范围",
      inputValidator: (input) => Boolean(String(input || "").trim()) || "请填写拒绝理由",
    });
    await store.rejectMemoryShare(transferId, String(value || "").trim());
    ElMessage.success("共享请求已拒绝，原范围记忆不受影响");
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  }
}

async function cancelMemoryShare(transferId: string) {
  try {
    await ElMessageBox.confirm("撤回后，本次共享申请不再审批；已经沉淀在原会议室的记忆仍会保留。", "撤回共享申请", {
      confirmButtonText: "确认撤回",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.cancelMemoryShare(transferId);
    ElMessage.success("共享申请已撤回，原会议室记忆不受影响");
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  }
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

function openImagePreview(attachment: MeetingAttachment) {
  previewImage.value = { url: attachment.url, name: attachmentDisplayName(attachment) };
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
  if (isAutoParticipationReply(message) && messageVisibility(message) === "room") return true;
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

function closeMessageSelectionMenu(event?: Event) {
  const target = event?.target;
  if (target instanceof Element && target.closest(".message-selection-menu")) return;
  messageSelectionMenu.visible = false;
}

function handleMessageSelection(message: MeetingMessage, event: MouseEvent) {
  const article = event.currentTarget;
  const selection = window.getSelection();
  if (!(article instanceof HTMLElement) || !selection || selection.isCollapsed || !selection.rangeCount) {
    closeMessageSelectionMenu();
    return;
  }
  const range = selection.getRangeAt(0);
  if (!article.contains(range.commonAncestorContainer)) {
    closeMessageSelectionMenu();
    return;
  }
  const text = selection.toString().trim();
  if (!text) {
    closeMessageSelectionMenu();
    return;
  }
  const rect = range.getBoundingClientRect();
  messageSelectionMenu.text = text.slice(0, 2000);
  messageSelectionMenu.message = message;
  messageSelectionMenu.x = Math.max(146, Math.min(window.innerWidth - 146, rect.left + rect.width / 2));
  messageSelectionMenu.below = rect.top < 72;
  messageSelectionMenu.y = messageSelectionMenu.below ? rect.bottom + 10 : rect.top - 10;
  messageSelectionMenu.visible = true;
}

function selectedTextQuestionSource(message: MeetingMessage, selectedText: string) {
  const author = message.username || "成员";
  const time = formatTime(message.created_at);
  return {
    message_id: message.id,
    seq_no: message.seq_no,
    author: `${author}${time ? ` · ${time}` : ""}`,
    selected_text: selectedText,
    content: displayMessageContent(message).trim() || "附件",
  };
}

async function focusAgentDraft() {
  aiConversationTab.value = "private";
  rightPanelTab.value = "ai";
  openWorkspaceSection("ai");
  closeMessageSelectionMenu();
  window.getSelection()?.removeAllRanges();
  await nextTick();
  agentInputRef.value?.focus();
}

async function askAgentAboutSelection() {
  const message = messageSelectionMenu.message;
  const selectedText = messageSelectionMenu.text.trim();
  if (!message || !selectedText) return;
  if (agentInput.value.trim() || agentQuestionSources.value.length) {
    try {
      await ElMessageBox.confirm("当前已有 AI 提问草稿。开始新提问会替换现有草稿。", "开始新提问", {
        confirmButtonText: "替换草稿",
        cancelButtonText: "保留当前草稿",
        type: "warning",
      });
    } catch {
      return;
    }
  }
  agentInput.value = "请结合会议公共上下文分析所选内容。";
  agentQuestionSources.value = [selectedTextQuestionSource(message, selectedText)];
  agentAttachments.value = [];
  await focusAgentDraft();
}

async function addSelectionToAgentDraft() {
  const message = messageSelectionMenu.message;
  const selectedText = messageSelectionMenu.text.trim();
  if (!message || !selectedText) return;
  const source = selectedTextQuestionSource(message, selectedText);
  const duplicate = agentQuestionSources.value.some((item) => (
    item.message_id === source.message_id && item.selected_text === source.selected_text
  ));
  if (!duplicate) agentQuestionSources.value.push(source);
  await focusAgentDraft();
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
  return message.message_type !== "agent_streaming"
    && messageVisibility(message) === "private"
    && message.user_id === currentUserId.value
    && Boolean(buildAgentShareContent(message));
}

function anchoredAgentReplies(messageId: string) {
  return publicAgentRepliesByTrigger.value.get(messageId) || [];
}

function anchoredReplySummary(message: MeetingMessage) {
  if (message.message_type === "agent_streaming") return "AI正在分析";
  if (messageMetadata(message).source_recalled) return "来源已撤回，此回复不再进入待确认知识";
  if (messageMetadata(message).source_revised) return "来源已修改，此回复已标记为旧版本";
  const summary = String(messageMetadata(message).summary || "").trim();
  return clipText(summary || displayMessageContent(message).split(/\r?\n/).find(Boolean) || "会议Agent已回复", 96);
}

function anchoredReplyType(message: MeetingMessage) {
  const metadata = autoParticipationMessageMetadata(message);
  if (metadata) return autoParticipationTriggerLabel(metadata.trigger_type);
  const selected = String(messageMetadata(message).selected_subgraph || "");
  const labels: Record<string, string> = {
    evidence_query: "证据追问",
    standard_explain: "标准校核",
    risk_forecast: "风险提醒",
    meeting_summary: "会议总结",
    action_items: "行动建议",
  };
  return labels[selected] || "公开回复";
}

function anchoredReplySourceCount(message: MeetingMessage) {
  const metadata = messageMetadata(message);
  const refs = [
    ...(Array.isArray(metadata.question_sources) ? metadata.question_sources : []),
    ...(Array.isArray(metadata.source_scope_refs) ? metadata.source_scope_refs : []),
    ...(Array.isArray(metadata.citations) ? metadata.citations : []),
  ];
  return new Set(refs.map((item) => JSON.stringify(item))).size;
}

function businessObjectTypeLabel(value: string) {
  const labels: Record<string, string> = {
    task: "任务",
    product: "产品",
    batch: "批次",
    standard: "标准",
    unknown: "待识别对象",
  };
  return labels[value] || value;
}

function businessObjectStatusLabel(value: string) {
  const labels: Record<string, string> = {
    candidate: "候选线索",
    verified: "已核验",
    corrected: "已纠正",
    rejected: "已移除",
  };
  return labels[value] || value;
}

async function submitBusinessObjectCorrection() {
  const correction = businessObjectCorrection.value.trim();
  if (!correction || businessObjectCorrectionSaving.value) return;
  businessObjectCorrectionSaving.value = true;
  try {
    await store.correctBusinessObject(correction);
    businessObjectCorrection.value = "";
    ElMessage.success("讨论对象已纠正并保留审计记录");
  } catch {
    ElMessage.error("未找到需要纠正的对象，请使用“不是A17，是A18”的格式");
  } finally {
    businessObjectCorrectionSaving.value = false;
  }
}

async function removeBusinessObject(candidateId: string, objectValue: string) {
  if (businessObjectRemovingId.value) return;
  try {
    await ElMessageBox.confirm(`移除讨论对象“${objectValue}”？记录仍会保留在审计信息中。`, "移除讨论对象", {
      confirmButtonText: "移除",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  businessObjectRemovingId.value = candidateId;
  try {
    await store.correctBusinessObject(`移除${objectValue}`, candidateId, undefined, "reject");
    ElMessage.success("讨论对象已移除");
  } catch {
    ElMessage.error("讨论对象移除失败，请刷新后重试");
  } finally {
    businessObjectRemovingId.value = "";
  }
}

async function openBusinessObjectSource(messageId: string) {
  businessObjectDrawerVisible.value = false;
  workspaceSection.value = "live";
  await nextTick();
  const element = document.getElementById(`meeting-message-${messageId}`);
  if (!element) {
    ElMessage.info("来源消息不在当前已加载范围，请先加载更早消息");
    return;
  }
  element.scrollIntoView({ block: "center" });
  element.focus({ preventScroll: true });
}

async function openPublicAgentReply(message: MeetingMessage) {
  aiConversationTab.value = "public";
  rightPanelTab.value = "ai";
  rightPanelCollapsed.value = false;
  openWorkspaceSection("ai");
  await nextTick();
  await nextTick();

  const list = agentPanelListRef.value;
  const target = document.getElementById(`agent-reply-${message.id}`);
  if (!list || !target) {
    ElMessage.info("完整回复暂未加载，请稍后重试");
    return;
  }

  const listRect = list.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const targetTop = list.scrollTop
    + targetRect.top
    - listRect.top
    - Math.max(0, (list.clientHeight - targetRect.height) / 2);
  list.scrollTo({ top: Math.max(0, targetTop), behavior: "auto" });
  list.querySelectorAll(".agent-thread-reply-targeted").forEach((element) => {
    element.classList.remove("agent-thread-reply-targeted");
  });
  void target.offsetWidth;
  target.classList.add("agent-thread-reply-targeted");
  target.focus({ preventScroll: true });
  window.setTimeout(() => target.classList.remove("agent-thread-reply-targeted"), 1400);
}

function openAgentSharePreview(message: MeetingMessage) {
  if (!canQuoteAgentMessageToMain(message)) return;
  agentShareMessage.value = message;
  agentShareContent.value = buildAgentShareContent(message);
  agentShareDialogVisible.value = true;
}

async function confirmAgentShare() {
  const message = agentShareMessage.value;
  const content = agentShareContent.value.trim();
  if (!message || !content || agentShareSubmitting.value) return;
  agentShareSubmitting.value = true;
  try {
    const metadata = messageMetadata(message);
    const sourceMessageIds = [
      String(metadata.question_message_id || ""),
      ...((Array.isArray(metadata.question_sources) ? metadata.question_sources : [])
        .map((item) => String((item as Record<string, unknown>).message_id || (item as Record<string, unknown>).id || ""))),
    ].filter(Boolean);
    await store.shareAgentAnswer(message, content, sourceMessageIds);
    agentShareDialogVisible.value = false;
    agentShareMessage.value = null;
    ElMessage.success("会议Agent回答已分享到会场");
  } finally {
    agentShareSubmitting.value = false;
  }
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
  agentInput.value = "请结合会议上下文分析这条消息。";
  agentQuestionSources.value = [{
    message_id: message.id,
    seq_no: message.seq_no,
    author: `${author}${time ? ` · ${time}` : ""}`,
    content: content || "附件",
  }];
  agentAttachments.value = messageAttachments(message);
  aiConversationTab.value = "private";
  rightPanelTab.value = "ai";
  openWorkspaceSection("ai");
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

async function scrollAgentPanelToLatest() {
  await nextTick();
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  await scrollToBottom("agent");
}

function isNearBottom(element?: HTMLElement | null, threshold = 72) {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

function onMainMessageScroll() {
  closeMessageSelectionMenu();
  mainWasNearBottom.value = isNearBottom(messageListRef.value);
  if (mainWasNearBottom.value) newMainMessageCount.value = 0;
}

async function jumpToLatestMessages() {
  mainWasNearBottom.value = true;
  newMainMessageCount.value = 0;
  await scrollToBottom("main");
}

async function loadOlderMessages() {
  const element = messageListRef.value;
  if (!element) return;
  const anchor = element.querySelector<HTMLElement>(".message-row");
  const anchorId = anchor?.id;
  const previousAnchorTop = anchor?.getBoundingClientRect().top;
  await store.loadOlderMessages();
  await nextTick();
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
  const currentAnchor = anchorId ? document.getElementById(anchorId) : null;
  if (currentAnchor && previousAnchorTop !== undefined) {
    element.scrollTop += currentAnchor.getBoundingClientRect().top - previousAnchorTop;
  }
  mainWasNearBottom.value = false;
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
  try {
    const message = await store.sendMessage(content, quotedMessage.value?.id || null, {
      attachments: [...store.pendingAttachments],
      quoteSnapshot: quoteSnapshot.value,
    });
    if (!message) return;
    input.value = "";
    quotedMessage.value = null;
    quoteSnapshot.value = null;
    mainWasNearBottom.value = true;
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
    const message = await store.sendMessage(`@会议Agent ${question}`, null, {
      skipAgentTrigger: true,
      attachments,
    });
    agentInput.value = "";
    agentAttachments.value = [];
    const questionSources = agentQuestionSources.value.map((source) => ({ ...source, kind: "public_message" }));
    agentQuestionSources.value = [];
    await store.runGeneralAgent("auto", question, {
      attachments,
      parentMessageId: message?.id,
      questionRevision: message ? agentQuestionRevision(message) : "",
      interactionMode: "private_chat",
      questionSources,
    });
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

async function saveModifiedAgentQuestion(message: MeetingMessage, group?: AgentConversationGroup) {
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
  let questionRevision = agentQuestionRevision(message);
  const replacementMessageId = group?.replies[group.replies.length - 1]?.id || "";
  try {
    try {
      const updatedMessage = await store.updateMessage(message.id, `@会议Agent ${question}`);
      if (updatedMessage) questionRevision = agentQuestionRevision(updatedMessage);
    } catch (error) {
      ElMessage.warning("原提问未能更新，已直接按修改后的内容重新提问。");
      console.warn("Failed to update original agent question before rerun", error);
    }
    cancelModifyAgentQuestion();
    const result = await store.runGeneralAgent("auto", question, {
      attachments,
      parentMessageId: message.id,
      questionRevision,
      replaceMessageId: replacementMessageId,
    });
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
    ElMessage.success(list.length ? "待确认知识已整理。" : "暂无可整理的待确认知识。");
  } catch (error) {
    ElMessage.error("整理待确认知识失败，请稍后重试。");
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
    if (isLocalRevision) {
      await store.confirmMemory(memory.memory_id, {
        title: memoryPublishForm.title.trim(),
        content: memoryPublishForm.content.trim(),
        scope: "meeting_room",
        scope_id: "current",
        publish_reason: memoryPublishForm.publish_reason.trim() || null,
        related_memory_ids: memory.related_memory_ids || [],
      });
    }
    if (!isLocalRevision) {
      await store.shareMemory(memory.memory_id, {
        target_scope_type: memoryPublishForm.scope,
        target_scope_id: resolvedScopeId,
        share_reason: memoryPublishForm.publish_reason.trim() || null,
        title: memoryPublishForm.title.trim(),
        content: memoryPublishForm.content.trim(),
        related_memory_ids: memory.related_memory_ids || [],
        affected_objects: memory.affected_objects || null,
        idempotency_key: memoryPublishForm.idempotency_key,
      });
    }
    memoryPublishDialogVisible.value = false;
    selectedCandidateMemory.value = null;
    if (memoryPublishForm.target_key === "current_meeting_room") {
      ElMessage.success(isCandidate ? "记忆已确认沉淀" : "记忆修订已沉淀");
    } else if (memoryPublishForm.target_key === "org_space") {
      ElMessage.success(isCandidate ? "已沉淀到本会议室，并提交组织共享审批" : "已提交组织共享审批");
    } else if (memoryPublishForm.target_key === "target_meeting_room") {
      ElMessage.success(isCandidate ? "已沉淀到本会议室，并提交目标会议室审批" : "已提交目标会议室审批");
    } else if (memoryPublishForm.target_key === "user") {
      ElMessage.success(isCandidate ? "已沉淀到本会议室，并提交目标成员确认" : "已提交目标成员确认");
    } else {
      ElMessage.success(isCandidate ? "记忆已确认并提交共享" : "记忆已共享");
    }
  } catch (error) {
    ElMessage.error("记忆沉淀或共享失败，请稍后重试。");
    console.error(error);
  } finally {
    memoryPublishSubmitting.value = false;
  }
}

async function rejectCandidateMemory(memory: MeetingMemory) {
  if (!canReviewMemory.value || rejectingMemoryId.value) return;
  rejectingMemoryId.value = memory.memory_id;
  try {
    await store.rejectMemory(memory.memory_id);
    if (selectedSharedMemory.value?.memory_id === memory.memory_id) {
      memoryDetailVisible.value = false;
    }
    ElMessage.success("待确认知识已拒绝");
  } catch (error) {
    ElMessage.error("拒绝记忆失败，请稍后重试。");
    console.error(error);
  } finally {
    rejectingMemoryId.value = "";
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

async function updateAutoParticipationMode(mode: MeetingAutoParticipationMode) {
  if (!store.activeRoom || !canManageRoom.value || mode === autoParticipationMode.value) return;
  autoParticipationSaving.value = true;
  try {
    await store.updateRoomSettings({ auto_participation_mode: mode });
    ElMessage.success(`会议Agent主动参与已设为“${autoParticipationModeLabel(mode)}”。`);
  } catch (error) {
    ElMessage.error("主动参与模式更新失败，请稍后重试。");
    console.error(error);
  } finally {
    autoParticipationSaving.value = false;
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

function openAutoParticipationPanel() {
  rightPanelCollapsed.value = false;
  aiConversationTab.value = "auto";
  rightPanelTab.value = "ai";
  openWorkspaceSection("ai");
  autoParticipationUnreadCount.value = 0;
  void scrollAgentPanelToLatest();
}

function announceAutoParticipationReply(message: MeetingMessage) {
  const diagnostic = autoParticipationMessageMetadata(message);
  if (!diagnostic) return;
  const trigger = autoParticipationTriggerLabel(diagnostic.trigger_type);
  const confidence = autoParticipationConfidenceLabel(diagnostic.confidence);
  ElNotification({
    title: "会议Agent已公开参与",
    message: `${trigger} · 公开参与 · 诊断置信度 ${confidence}。点击查看。`,
    type: "warning",
    duration: 7000,
    showClose: true,
    onClick: openAutoParticipationPanel,
  });
}

function initializeAutoParticipationTracking(roomId: string) {
  knownAutoParticipationReplyIds = new Set(autoParticipationReplies.value.map((message) => message.id));
  autoParticipationUnreadCount.value = 0;
  autoParticipationTrackingRoomId.value = roomId;
}

async function loadActiveRoomData(newId: string) {
  if (!newId) {
    store.disconnectStream();
    closeMentionMenu();
    initializeAutoParticipationTracking("");
    await store.loadMembers();
    return;
  }

  closeMentionMenu();
  mainWasNearBottom.value = true;
  newMainMessageCount.value = 0;
  await store.loadMembers();
  const results = await Promise.allSettled([
    store.loadMessages(),
    store.loadMeetingContext(),
  ]);
  const failed = results.find((item) => item.status === "rejected");
  if (failed) {
    console.error("Failed to load meeting room data", failed.reason);
  }
  initializeAutoParticipationTracking(newId);
  store.connectStream();
  await scrollToBottom();
  await scrollToBottom("agent");
}

watch(() => store.activeRoomId, async (newId) => {
  closeMentionMenu();
  autoParticipationTrackingRoomId.value = "";
  knownAutoParticipationReplyIds = new Set<string>();
  autoParticipationUnreadCount.value = 0;
  try {
    await loadActiveRoomData(newId);
  } catch (error) {
    console.error("Failed to switch meeting room", error);
  }
});

watch(() => [
  store.activeRoomId,
  store.conversationMessages.reduce((latest, message) => Math.max(latest, message.seq_no), 0),
] as const, async ([roomId, latestSeq], [previousRoomId, previousLatestSeq]) => {
  if (!roomId || roomId !== previousRoomId || latestSeq <= previousLatestSeq) return;
  const addedCount = store.conversationMessages.filter((message) => message.seq_no > previousLatestSeq).length;
  if (!addedCount) return;
  if (mainWasNearBottom.value) {
    await scrollToBottom();
  } else {
    newMainMessageCount.value += addedCount;
  }
});

watch(() => agentConversationGroups.value.map((group) => {
  const questionKey = group.question ? `${group.question.id}:${group.question.content.length}` : "no-question";
  const replyKey = group.replies.map((item) => `${item.id}:${item.content.length}`).join(",");
  return `${group.id}:${questionKey}:${replyKey}`;
}).join("|"), async () => {
  if (isNearBottom(agentPanelListRef.value)) await scrollToBottom("agent");
});

watch(() => autoParticipationReplies.value.map((message) => message.id).join("|"), () => {
  if (!store.activeRoomId || autoParticipationTrackingRoomId.value !== store.activeRoomId) return;
  const newReplies = autoParticipationReplies.value.filter(
    (message) => !knownAutoParticipationReplyIds.has(message.id),
  );
  knownAutoParticipationReplyIds = new Set(autoParticipationReplies.value.map((message) => message.id));
  if (!newReplies.length) return;
  if (!agentPanelVisible.value || aiConversationTab.value !== "auto") {
    autoParticipationUnreadCount.value += newReplies.length;
  }
  announceAutoParticipationReply(newReplies[newReplies.length - 1]);
}, { flush: "post" });

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
  if (meetingLayoutMode.value === "workspace") {
    workspaceSection.value = tab === "context" ? "overview" : tab;
  }
  if (tab === "ai" && aiConversationTab.value === "auto" && agentPanelVisible.value) {
    autoParticipationUnreadCount.value = 0;
  }
  if (tab === "private") ensureActivePrivateMember();
  if (tab === "ai") await scrollAgentPanelToLatest();
});

watch(aiConversationTab, async (tab) => {
  if (tab === "auto" && agentPanelVisible.value) autoParticipationUnreadCount.value = 0;
  await scrollAgentPanelToLatest();
});

watch(workspaceSection, async (section) => {
  if (section !== "ai") return;
  if (aiConversationTab.value === "auto" && agentPanelVisible.value) {
    autoParticipationUnreadCount.value = 0;
  }
  await scrollAgentPanelToLatest();
});

watch(workspaceMemoryItems, (items) => {
  if (linkedMemoryId.value && items.some((memory) => memory.memory_id === linkedMemoryId.value)) {
    workspaceSelectedMemoryId.value = linkedMemoryId.value;
    linkedMemoryId.value = "";
    workspaceSection.value = "memory";
    return;
  }
  if (!items.some((memory) => memory.memory_id === workspaceSelectedMemoryId.value)) {
    workspaceSelectedMemoryId.value = items[0]?.memory_id || "";
  }
}, { immediate: true });

watch(() => store.activeRoomId, () => {
  workspaceSection.value = "live";
});

watch(rightPanelCollapsed, (collapsed) => {
  if (!collapsed && aiConversationTab.value === "auto" && agentPanelVisible.value) {
    autoParticipationUnreadCount.value = 0;
  }
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
  const linkedRoomId = new URLSearchParams(window.location.search).get("room_id")?.trim() || "";
  linkedMemoryId.value = new URLSearchParams(window.location.search).get("memory_id")?.trim() || "";
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
  } else if (linkedRoomId && store.rooms.some((room) => room.id === linkedRoomId)) {
    store.activeRoomId = linkedRoomId;
  }
  window.addEventListener("resize", clampPrivateWindowRect);
  document.addEventListener("pointerdown", closeMessageSelectionMenu);
});

onBeforeUnmount(() => {
  stopPanelResize();
  stopPrivateWindowInteraction();
  if (privateRecallTimer !== null) {
    window.clearInterval(privateRecallTimer);
    privateRecallTimer = null;
  }
  window.removeEventListener("resize", clampPrivateWindowRect);
  document.removeEventListener("pointerdown", closeMessageSelectionMenu);
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
      'is-workspace-layout': meetingLayoutMode === 'workspace',
      'is-workspace-focus': meetingLayoutMode === 'workspace',
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
            :class="['hub-mode-button', { 'hub-mode-active': hubMode === 'create' }]"
            role="tab"
            :aria-selected="hubMode === 'create'"
            @click="hubMode = 'create'"
          >
            <span class="hub-mode-check" aria-hidden="true">
              <Check v-if="hubMode === 'create'" />
            </span>
            <span class="hub-mode-label">创建会议</span>
          </button>
          <button
            type="button"
            :class="['hub-mode-button', { 'hub-mode-active': hubMode === 'join' }]"
            role="tab"
            :aria-selected="hubMode === 'join'"
            @click="hubMode = 'join'"
          >
            <span class="hub-mode-check" aria-hidden="true">
              <Check v-if="hubMode === 'join'" />
            </span>
            <span class="hub-mode-label">加入会议</span>
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
              aria-label="退出会议"
              title="退出会议"
              @click.stop="handleLeaveRoom(room)"
            >
              退出
            </el-button>
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

    <section class="meeting-room" :class="{ 'has-workspace-nav': meetingLayoutMode === 'workspace' }">
      <header class="room-header">
        <div class="room-title-block">
          <p class="section-kicker">实时会议</p>
          <h2>{{ store.activeRoom?.title || "实时会议协作" }}</h2>
          <div v-if="store.activeRoom" class="room-submeta">
            <span v-if="hostMember" class="host-pill">主持人{{ hostMember.username }}</span>
            <span class="status-pill" :class="`status-${store.activeRoom.status}`">{{ roomStatusLabel }}</span>
            <span class="auto-mode-pill" :class="`auto-mode-${autoParticipationMode}`">
              Agent {{ autoParticipationModeLabel(autoParticipationMode) }}
            </span>
            <button
              type="button"
              class="discussion-object-entry"
              :class="{ 'discussion-object-entry-ambiguous': visibleBusinessObjects.some((item) => item.status === 'candidate') }"
              @click="businessObjectDrawerVisible = true"
            >
              讨论对象 {{ visibleBusinessObjects.length }}
            </button>
          </div>
        </div>
        <div v-if="store.activeRoom" class="room-header-right">
          <div class="room-toolbar-main">
            <div class="meeting-layout-switch" role="radiogroup" aria-label="会议室布局">
              <button
                type="button"
                role="radio"
                :aria-checked="meetingLayoutMode === 'workspace'"
                :class="{ 'meeting-layout-option-active': meetingLayoutMode === 'workspace' }"
                @click="setMeetingLayoutMode('workspace')"
              >
                <Grid />
                <span>工作区</span>
              </button>
              <button
                type="button"
                role="radio"
                :aria-checked="meetingLayoutMode === 'classic'"
                :class="{ 'meeting-layout-option-active': meetingLayoutMode === 'classic' }"
                @click="setMeetingLayoutMode('classic')"
              >
                <Menu />
                <span>经典</span>
              </button>
            </div>
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
            <el-popover placement="bottom-end" :width="344" trigger="click">
              <template #reference>
                <el-button size="small" :icon="Setting">
                  Agent 主动参与
                </el-button>
              </template>
              <div class="auto-participation-settings">
                <div class="auto-participation-settings-head">
                  <strong>会议Agent主动参与</strong>
                  <span>{{ autoParticipationModeLabel(autoParticipationMode) }}</span>
                </div>
                <div class="auto-mode-control" role="radiogroup" aria-label="会议Agent主动参与模式">
                  <button
                    v-for="option in autoParticipationOptions"
                    :key="option.value"
                    type="button"
                    role="radio"
                    :aria-checked="autoParticipationMode === option.value"
                    :class="[
                      `auto-mode-option-${option.value}`,
                      { 'auto-mode-control-active': autoParticipationMode === option.value },
                    ]"
                    :disabled="autoParticipationSaving"
                    @click="updateAutoParticipationMode(option.value)"
                  >
                    <span class="auto-mode-icon-slot" aria-hidden="true">
                      <Check v-if="autoParticipationMode === option.value" />
                    </span>
                    <span>{{ option.label }}</span>
                  </button>
                </div>
                <p>{{ autoParticipationDescription }}</p>
              </div>
            </el-popover>
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

      <nav v-if="meetingLayoutMode === 'workspace' && store.activeRoom" class="meeting-workspace-nav" aria-label="会议工作区">
        <div class="meeting-workspace-label">
          <strong>会议工作区</strong>
          <small>切换任务，不离开当前会议室</small>
        </div>
        <div class="meeting-workspace-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'live'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'live' }"
            @click="openWorkspaceSection('live')"
          >
            <ChatDotRound />
            <span>会场</span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'ai'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'ai' }"
            @click="openWorkspaceSection('ai')"
          >
            <MagicStick />
            <span>AI</span>
            <strong v-if="agentQuestionCount || autoParticipationUnreadCount">
              {{ autoParticipationUnreadCount || agentQuestionCount }}
            </strong>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'private'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'private' }"
            @click="openWorkspaceSection('private')"
          >
            <User />
            <span>私聊</span>
            <strong v-if="privateConversationCount">{{ privateConversationCount }}</strong>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'overview'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'overview' }"
            @click="openWorkspaceSection('overview')"
          >
            <View />
            <span>概览</span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'memory'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'memory' }"
            @click="openWorkspaceSection('memory')"
          >
            <Grid />
            <span>记忆</span>
            <strong v-if="store.candidateMemories.length">{{ store.candidateMemories.length }}</strong>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'tasks'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'tasks' }"
            @click="openWorkspaceSection('tasks')"
          >
            <List />
            <span>待办</span>
            <strong v-if="store.openActionItems.length">{{ store.openActionItems.length }}</strong>
          </button>
          <button
            v-if="canReviewMemory"
            type="button"
            role="tab"
            :aria-selected="workspaceSection === 'audit'"
            :class="{ 'meeting-workspace-tab-active': workspaceSection === 'audit' }"
            @click="openWorkspaceSection('audit')"
          >
            <DataAnalysis />
            <span>审计</span>
            <strong v-if="store.agentQueryAudits.length">{{ store.agentQueryAudits.length }}</strong>
          </button>
        </div>
      </nav>

      <section
        v-if="meetingLayoutMode === 'workspace' && ['memory', 'tasks', 'audit'].includes(workspaceSection)"
        ref="workspaceStageRef"
        class="meeting-workspace-stage"
        v-loading="store.loadingContext"
      >
        <template v-if="workspaceSection === 'memory'">
          <header class="workspace-stage-head">
            <div>
              <p class="section-kicker">记忆与协作</p>
              <h2>会议记忆工作台</h2>
              <p>在宽视图中阅读完整内容与证据，再完成确认、共享或拒绝。</p>
            </div>
            <el-button
              v-if="canReviewMemory"
              type="primary"
              plain
              :icon="MagicStick"
              :loading="store.memoryExtracting"
              @click="extractCandidateMemories"
            >
              整理知识
            </el-button>
          </header>

          <div
            class="workspace-memory-extraction-state"
            :data-state="store.memoryExtractionStatus"
            role="status"
            aria-live="polite"
          >
            <span class="workspace-memory-extraction-indicator" aria-hidden="true"></span>
            <div>
              <strong>{{ memoryExtractionStatusLabel() }}</strong>
              <small v-if="store.memoryExtractionStatus === 'error'">{{ store.memoryExtractionError }}</small>
              <small v-else>QDL v2 · 仅处理公共发言</small>
            </div>
            <el-button
              v-if="store.memoryExtractionStatus === 'error'"
              size="small"
              text
              :icon="RefreshRight"
              @click="extractCandidateMemories"
            >
              重试
            </el-button>
          </div>

          <div class="workspace-memory-tabs" role="tablist" aria-label="记忆状态">
            <button
              type="button"
              role="tab"
              :aria-selected="workspaceMemoryTab === 'candidate'"
              :class="{ 'workspace-memory-tab-active': workspaceMemoryTab === 'candidate' }"
              @click="selectWorkspaceMemoryTab('candidate')"
            >
              待确认 <strong>{{ store.candidateMemories.length }}</strong>
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="workspaceMemoryTab === 'confirmed'"
              :class="{ 'workspace-memory-tab-active': workspaceMemoryTab === 'confirmed' }"
              @click="selectWorkspaceMemoryTab('confirmed')"
            >
              已沉淀 <strong>{{ store.confirmedMemories.length }}</strong>
            </button>
            <button
              v-if="canReviewMemory"
              type="button"
              role="tab"
              :aria-selected="workspaceMemoryTab === 'governance'"
              :class="{ 'workspace-memory-tab-active': workspaceMemoryTab === 'governance' }"
              @click="selectWorkspaceMemoryTab('governance')"
            >
              待处理 <strong>{{ workspaceGovernanceCount }}</strong>
            </button>
          </div>

          <div v-if="workspaceMemoryTab !== 'governance'" class="workspace-memory-layout">
            <aside class="workspace-memory-list" aria-label="记忆列表">
              <div v-if="!workspaceMemoryItems.length" class="workspace-empty-state">
                <Grid />
                <strong>{{ workspaceMemoryTab === "candidate" ? "暂无待确认知识" : "暂无已沉淀知识" }}</strong>
                <p>{{ workspaceMemoryTab === "candidate" ? "会议Agent会自动整理，也可点击“整理知识”立即生成。" : "确认后的共享知识会出现在这里。" }}</p>
              </div>
              <button
                v-for="memory in workspaceMemoryItems"
                :key="memory.memory_id"
                type="button"
                class="workspace-memory-list-item"
                :class="{ 'workspace-memory-list-item-active': workspaceSelectedMemory?.memory_id === memory.memory_id }"
                @click="workspaceSelectedMemoryId = memory.memory_id"
              >
                <span class="workspace-memory-list-head">
                  <strong>{{ memory.title }}</strong>
                  <b>{{ memory.status === "candidate" ? memoryConfidence(memory) || "待审" : memoryStatusLabel(memory.status) }}</b>
                </span>
                <span class="workspace-memory-list-meta">
                  {{ memoryCategoryLabel(memory.memory_category) }} · {{ memoryTypeLabel(memory.memory_type) }}
                </span>
                <p>{{ memoryPreview(memory, 110) }}</p>
              </button>
            </aside>

            <article v-if="workspaceSelectedMemory" class="workspace-memory-review">
              <header class="workspace-memory-review-head">
                <div>
                  <p class="section-kicker">{{ workspaceSelectedMemory.status === "candidate" ? "知识审核" : "知识详情" }}</p>
                  <h3>{{ workspaceSelectedMemory.title }}</h3>
                </div>
                <span>{{ memoryScopeLabel(workspaceSelectedMemory.scope || workspaceSelectedMemory.recommended_scope) }}</span>
              </header>

              <div class="workspace-memory-review-meta">
                <span :class="['memory-category-badge', `memory-category-${workspaceSelectedMemory.memory_category || 'meeting_memory'}`]">
                  {{ memoryCategoryLabel(workspaceSelectedMemory.memory_category) }}
                </span>
                <span>{{ memoryTypeLabel(workspaceSelectedMemory.memory_type) }}</span>
                <span>{{ memoryStatusLabel(workspaceSelectedMemory.status) }}</span>
                <span v-if="memoryConfidence(workspaceSelectedMemory)">{{ memoryConfidence(workspaceSelectedMemory) }}</span>
              </div>

              <section class="workspace-memory-content-section">
                <h4>完整内容</h4>
                <p>{{ workspaceSelectedMemory.content || workspaceSelectedMemory.summary }}</p>
              </section>

              <section
                v-if="workspaceSelectedMemory.qdl_json || workspaceSelectedMemory.qdl_validation_status === 'invalid'"
                class="workspace-memory-qdl-section"
              >
                <header class="workspace-memory-qdl-head">
                  <div>
                    <h4>QDL 知识单元</h4>
                    <p>{{ workspaceSelectedMemory.qdl_schema_version || workspaceSelectedMemory.qdl_json?.version || "未知版本" }}</p>
                  </div>
                  <span :class="['qdl-validation-badge', `qdl-validation-${workspaceSelectedMemory.qdl_validation_status || 'missing'}`]">
                    {{ qdlValidationLabel(workspaceSelectedMemory) }}
                  </span>
                </header>

                <div v-if="workspaceSelectedMemory.qdl_validation_errors?.length" class="qdl-validation-errors" role="alert">
                  <strong>校验错误</strong>
                  <span v-for="error in workspaceSelectedMemory.qdl_validation_errors" :key="error">{{ error }}</span>
                </div>

                <template v-if="workspaceSelectedMemory.qdl_json">
                  <dl class="qdl-summary-grid">
                    <div>
                      <dt>知识层级</dt>
                      <dd>{{ qdlKnowledgeLevelLabel(workspaceSelectedMemory) }}</dd>
                    </div>
                    <div>
                      <dt>提取方式</dt>
                      <dd>{{ qdlExtractionMethodLabel(workspaceSelectedMemory.extraction_method || workspaceSelectedMemory.qdl_json.provenance.extraction_method) }}</dd>
                    </div>
                    <div>
                      <dt>适用范围</dt>
                      <dd>{{ memoryScopeLabel(workspaceSelectedMemory.qdl_json.applicability.scope_type) }}</dd>
                    </div>
                    <div>
                      <dt>治理状态</dt>
                      <dd>{{ memoryStatusLabel(workspaceSelectedMemory.qdl_json.governance.status) }}</dd>
                    </div>
                  </dl>

                  <div class="qdl-subsection">
                    <h5>知识属性</h5>
                    <div class="qdl-property-grid">
                      <div
                        v-for="property in qdlPropertyRows(workspaceSelectedMemory)"
                        :key="property.key"
                        class="qdl-property-row"
                        :title="property.rationale || undefined"
                      >
                        <span>{{ property.label }}</span>
                        <strong :data-level="property.level">{{ property.levelLabel }}</strong>
                        <small>{{ property.confidence || "未标置信度" }}</small>
                      </div>
                    </div>
                  </div>

                  <div class="qdl-context-grid">
                    <div class="qdl-subsection">
                      <h5>实体</h5>
                      <div v-if="qdlEntityRows(workspaceSelectedMemory).length" class="qdl-entity-list">
                        <div v-for="entity in qdlEntityRows(workspaceSelectedMemory)" :key="entity.key">
                          <span>{{ entity.type }}</span>
                          <strong>{{ entity.value }}</strong>
                          <small>{{ entity.status }}{{ entity.confidence ? ` · ${entity.confidence}` : "" }}</small>
                        </div>
                      </div>
                      <p v-else class="qdl-empty-line">未绑定实体</p>
                    </div>
                    <div class="qdl-subsection">
                      <h5>适用条件与标签</h5>
                      <div class="qdl-tag-list">
                        <span v-for="condition in workspaceSelectedMemory.qdl_json.applicability.conditions" :key="condition">{{ condition }}</span>
                        <span v-for="tag in qdlBusinessTags(workspaceSelectedMemory)" :key="tag.key">{{ tag.label }}</span>
                      </div>
                      <p
                        v-if="!workspaceSelectedMemory.qdl_json.applicability.conditions.length && !qdlBusinessTags(workspaceSelectedMemory).length"
                        class="qdl-empty-line"
                      >
                        无额外适用条件
                      </p>
                    </div>
                  </div>

                  <div class="qdl-subsection">
                    <h5>来源证据</h5>
                    <div class="qdl-evidence-list">
                      <article v-for="evidence in qdlEvidenceRows(workspaceSelectedMemory)" :key="evidence.key">
                        <div>
                          <strong>{{ evidence.label }}</strong>
                          <p>{{ evidence.quote || "已记录来源定位信息" }}</p>
                        </div>
                        <el-button
                          v-if="evidence.messageId"
                          size="small"
                          text
                          :icon="View"
                          @click="openBusinessObjectSource(evidence.messageId)"
                        >
                          定位消息
                        </el-button>
                      </article>
                    </div>
                  </div>

                  <div v-if="qdlRelationRows(workspaceSelectedMemory).length" class="qdl-subsection">
                    <h5>知识关系</h5>
                    <div class="qdl-relation-list">
                      <div v-for="relation in qdlRelationRows(workspaceSelectedMemory)" :key="relation.key">
                        <span>{{ relation.label }}</span>
                        <strong>{{ relation.target }}</strong>
                        <small v-if="relation.note">{{ relation.note }}</small>
                      </div>
                    </div>
                  </div>

                  <dl class="qdl-provenance-grid">
                    <div>
                      <dt>生成时间</dt>
                      <dd>{{ formatTime(workspaceSelectedMemory.qdl_json.provenance.generated_at) }}</dd>
                    </div>
                    <div>
                      <dt>模型</dt>
                      <dd>{{ workspaceSelectedMemory.extraction_model_id || workspaceSelectedMemory.qdl_json.provenance.model_id || "规则兜底" }}</dd>
                    </div>
                    <div>
                      <dt>Trace</dt>
                      <dd>{{ workspaceSelectedMemory.qdl_json.provenance.trace_id || "未记录" }}</dd>
                    </div>
                    <div>
                      <dt>版本</dt>
                      <dd>第 {{ workspaceSelectedMemory.qdl_json.lifecycle.revision }} 版</dd>
                    </div>
                  </dl>
                </template>
              </section>

              <section v-if="workspaceSelectedMemory.status === 'candidate' && !workspaceSelectedMemory.qdl_json" class="workspace-memory-evidence-section">
                <h4>提取与来源依据</h4>
                <dl>
                  <template v-if="workspaceSelectedMemory.extraction_reason">
                    <dt>提取理由</dt>
                    <dd>{{ workspaceSelectedMemory.extraction_reason }}</dd>
                  </template>
                  <dt>来源消息</dt>
                  <dd>{{ sourceMessageLabel(workspaceSelectedMemory) }}</dd>
                  <template v-if="relatedMemorySummary(workspaceSelectedMemory)">
                    <dt>关联记忆</dt>
                    <dd>{{ relatedMemorySummary(workspaceSelectedMemory) }}</dd>
                  </template>
                </dl>
                <div v-if="memorySourceSpans(workspaceSelectedMemory).length" class="workspace-source-spans">
                  <article v-for="span in memorySourceSpans(workspaceSelectedMemory)" :key="span.key">
                    <strong>{{ span.label }}</strong>
                    <p>{{ span.text }}</p>
                  </article>
                </div>
              </section>

              <section v-if="workspaceSelectedMemory.memory_type === 'risk_insight'" class="workspace-memory-risk-section">
                <h4>风险判断</h4>
                <div class="risk-insight-strip">
                  <span>风险：{{ riskLevelLabel(workspaceSelectedMemory.risk_level) }}</span>
                  <span v-if="forecastWindowLabel(workspaceSelectedMemory)">关注：{{ forecastWindowLabel(workspaceSelectedMemory) }}</span>
                </div>
              </section>

              <div v-if="visibleMemoryWarnings(workspaceSelectedMemory).length" class="memory-warning-list">
                <span v-for="warning in visibleMemoryWarnings(workspaceSelectedMemory)" :key="warning">{{ warning }}</span>
              </div>

              <footer class="workspace-memory-review-actions">
                <el-button :icon="View" @click="openMemoryDetail(workspaceSelectedMemory)">详情抽屉</el-button>
                <template v-if="canReviewMemory && workspaceSelectedMemory.status === 'candidate'">
                  <el-button
                    type="danger"
                    plain
                    :icon="Close"
                    :loading="rejectingMemoryId === workspaceSelectedMemory.memory_id"
                    @click="rejectCandidateMemory(workspaceSelectedMemory)"
                  >
                    拒绝
                  </el-button>
                  <el-button type="primary" :icon="Check" @click="confirmCandidateMemory(workspaceSelectedMemory)">确认并发布</el-button>
                </template>
                <template v-else-if="canReviewMemory && workspaceSelectedMemory.status !== 'superseded'">
                  <el-button @click="disputeSharedMemory(workspaceSelectedMemory)">质疑</el-button>
                  <el-button type="primary" @click="confirmCandidateMemory(workspaceSelectedMemory)">发布/修订</el-button>
                </template>
              </footer>
            </article>
          </div>

          <div v-else class="workspace-governance-layout">
            <section class="workspace-governance-section">
              <header>
                <div>
                  <p class="section-kicker">共享审批</p>
                  <h3>待审批共享</h3>
                </div>
                <span>{{ store.pendingMemoryShares.length }}</span>
              </header>
              <div v-if="!store.pendingMemoryShares.length" class="workspace-empty-state compact">
                <strong>暂无待审批共享</strong>
              </div>
              <article v-for="share in store.pendingMemoryShares" :key="share.id" class="workspace-governance-row">
                <div>
                  <strong>{{ share.memory_title || share.memory_id }}</strong>
                  <p>{{ shareTargetLabel(share.from_scope_type, share.from_scope_id) }} → {{ shareTargetLabel(share.to_scope_type, share.to_scope_id) }}</p>
                  <small>{{ share.transfer_reason || "暂无说明" }}</small>
                </div>
                <div v-if="share.can_approve || share.can_cancel" class="workspace-row-actions">
                  <template v-if="share.can_approve">
                    <el-button size="small" type="primary" @click="approveMemoryShare(share.id)">批准</el-button>
                    <el-button size="small" @click="rejectMemoryShare(share.id)">拒绝</el-button>
                  </template>
                  <el-button v-if="share.can_cancel" size="small" type="warning" plain @click="cancelMemoryShare(share.id)">撤回申请</el-button>
                </div>
              </article>
            </section>

            <section class="workspace-governance-section">
              <header>
                <div>
                  <p class="section-kicker">冲突治理</p>
                  <h3>冲突处理</h3>
                </div>
                <span>{{ store.conflictEvents.length }}</span>
              </header>
              <div v-if="!store.conflictEvents.length" class="workspace-empty-state compact">
                <strong>暂无冲突事件</strong>
              </div>
              <article v-for="conflict in store.conflictEvents" :key="conflict.id" class="workspace-governance-row">
                <div>
                  <strong>{{ conflictTypeLabel(conflict.conflict_type) }}</strong>
                  <p>{{ conflict.resource_key }}</p>
                  <small>{{ formatTime(conflict.created_at) }} · {{ conflict.status }}</small>
                </div>
                <div v-if="conflict.status === 'pending'" class="workspace-row-actions">
                  <el-button size="small" type="primary" @click="resolveConflictCard(conflict.id, 'approve')">批准</el-button>
                  <el-button size="small" @click="resolveConflictCard(conflict.id, 'queue')">排队</el-button>
                  <el-button size="small" @click="resolveConflictCard(conflict.id, 'candidate_only')">转候选</el-button>
                  <el-button size="small" @click="resolveConflictCard(conflict.id, 'reject')">拒绝</el-button>
                </div>
              </article>
            </section>
          </div>
        </template>

        <template v-else-if="workspaceSection === 'tasks'">
          <header class="workspace-stage-head">
            <div>
              <p class="section-kicker">会议协作</p>
              <h2>会议待办</h2>
              <p>统一查看负责人、进度和补充说明。</p>
            </div>
            <span class="workspace-stage-count">进行中 {{ store.openActionItems.length }}</span>
          </header>
          <div class="workspace-action-create">
            <el-input v-model="actionTitle" placeholder="待办标题" @keydown.enter="createActionItem" />
            <el-input v-model="actionDescription" placeholder="补充说明（可选）" />
            <el-select v-model="actionOwnerId" clearable placeholder="负责人">
              <el-option v-for="member in store.members" :key="member.user_id" :label="member.username" :value="member.user_id" />
            </el-select>
            <el-button type="primary" :icon="Plus" :loading="store.actionItemSaving" @click="createActionItem">新增待办</el-button>
          </div>
          <div v-if="!store.actionItems.length" class="workspace-empty-state">
            <List />
            <strong>暂无会议待办</strong>
            <p>新增待办后可在这里持续跟进。</p>
          </div>
          <div v-else class="workspace-action-list">
            <article v-for="item in store.actionItems" :key="item.id" :class="{ 'workspace-action-row-done': item.status === 'done' }">
              <span class="workspace-action-status"><Check v-if="item.status === 'done'" /></span>
              <div>
                <strong>{{ item.title }}</strong>
                <p v-if="item.description">{{ item.description }}</p>
                <small>{{ item.owner_name || "未分配" }} · {{ item.status === "done" ? "已完成" : "进行中" }}</small>
              </div>
              <el-button v-if="item.status !== 'done'" type="primary" plain size="small" :icon="Check" @click="completeActionItem(item.id)">完成</el-button>
            </article>
          </div>
        </template>

        <template v-else-if="workspaceSection === 'audit'">
          <header class="workspace-stage-head">
            <div>
              <p class="section-kicker">Agent 审计</p>
              <h2>AI 使用记录</h2>
              <p>查看 Agent 是否发言、触发原因以及回答时实际读取的数据。</p>
            </div>
            <span class="workspace-stage-count">记录 {{ store.agentQueryAudits.length }}</span>
          </header>
          <div v-if="!store.agentQueryAudits.length" class="workspace-empty-state">
            <DataAnalysis />
            <strong>暂无 AI 使用记录</strong>
          </div>
          <div v-else class="workspace-audit-list">
            <button v-for="audit in store.agentQueryAudits" :key="audit.id" type="button" @click="openAuditDetail(audit)">
              <span :class="['audit-decision', auditDecisionClass(audit.decision)]">{{ auditDecisionLabel(audit) }}</span>
              <span class="workspace-audit-main">
                <strong>{{ audit.question }}</strong>
                <small>{{ auditDecisionDescription(audit) }}</small>
              </span>
              <span class="workspace-audit-meta">
                <b>{{ auditIntentLabel(audit.intent) }}</b>
                <time>{{ formatTime(audit.created_at) }}</time>
              </span>
            </button>
          </div>
        </template>
      </section>

      <div
        v-show="meetingLayoutMode === 'classic' || workspaceSection === 'live'"
        class="meeting-message-pane"
      >
        <div
          ref="messageListRef"
          v-loading="store.loadingMessages"
          class="message-list"
          @scroll.passive="onMainMessageScroll"
        >
        <button
          v-if="store.activeRoom && store.hasOlderMessages"
          type="button"
          class="load-older-messages"
          :disabled="store.loadingMessages"
          @click="loadOlderMessages"
        >
          加载更早消息
        </button>
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
          tabindex="-1"
          :class="{
            'message-row-own': message.user_id === currentUserId,
          }"
          @mouseup="handleMessageSelection(message, $event)"
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
                <ImageAttachmentCard
                  v-if="isImageAttachment(att)"
                  :src="att.url"
                  :name="attachmentDisplayName(att)"
                  @preview="openImagePreview(att)"
                />
                <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ attachmentDisplayName(att) }}</a>
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
          <div
            v-for="reply in anchoredAgentReplies(message.id)"
            :key="reply.id"
            :data-reply-id="reply.id"
            class="anchored-agent-reply"
            :class="{
              'anchored-agent-reply-pending': reply.message_type === 'agent_streaming',
              'anchored-agent-reply-invalid': messageMetadata(reply).source_recalled || messageMetadata(reply).source_revised,
            }"
            role="status"
          >
            <span class="anchored-agent-mark"><MagicStick /></span>
            <span class="anchored-agent-copy">
              <strong>{{ anchoredReplySummary(reply) }}</strong>
              <small>
                {{ anchoredReplyType(reply) }}
                <template v-if="anchoredReplySourceCount(reply)"> · {{ anchoredReplySourceCount(reply) }} 个来源</template>
              </small>
            </span>
            <button
              v-if="reply.message_type !== 'agent_streaming'"
              type="button"
              @click="openPublicAgentReply(reply)"
            >查看完整回复</button>
          </div>
        </article>
        <div
          v-if="messageSelectionMenu.visible"
          class="message-selection-menu"
          :class="{ 'message-selection-menu-below': messageSelectionMenu.below }"
          :style="{ left: `${messageSelectionMenu.x}px`, top: `${messageSelectionMenu.y}px` }"
          role="toolbar"
          aria-label="所选文字操作"
          @mousedown.stop.prevent
        >
          <button type="button" @click="copyToClipboard(messageSelectionMenu.text, '所选文字已复制'); closeMessageSelectionMenu()">
            <CopyDocument aria-hidden="true" />
            <span>复制</span>
          </button>
          <button type="button" @click="askAgentAboutSelection">
            <MagicStick aria-hidden="true" />
            <span>问会议Agent</span>
          </button>
          <button
            v-if="agentInput.trim() || agentQuestionSources.length"
            type="button"
            @click="addSelectionToAgentDraft"
          >
            <Plus aria-hidden="true" />
            <span>加入当前提问</span>
          </button>
        </div>
        </div>
        <button
          v-if="newMainMessageCount"
          type="button"
          class="new-message-jump"
          :aria-label="`有 ${newMainMessageCount} 条新消息，回到最新消息`"
          @click="jumpToLatestMessages"
        >
          有 {{ newMainMessageCount }} 条新消息
        </button>
      </div>

      <footer
        v-show="meetingLayoutMode === 'classic' || workspaceSection === 'live'"
        class="composer"
        @paste="handleComposerPaste($event, 'main')"
      >
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
          aria-label="公共消息"
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

    <aside
      v-show="meetingLayoutMode === 'classic' || ['ai', 'private', 'overview'].includes(workspaceSection)"
      class="meeting-context"
      :class="{ 'panel-collapsed': rightPanelCollapsed }"
      v-loading="store.loadingContext"
    >
      <button
        type="button"
        class="panel-toggle panel-toggle-right"
        :aria-label="rightPanelCollapsed ? '展开记忆与协作面板' : '收起记忆与协作面板'"
        :title="rightPanelCollapsed ? '展开记忆与协作面板' : '收起记忆与协作面板'"
        @click="rightPanelCollapsed = !rightPanelCollapsed"
      >
        <ArrowLeft v-if="rightPanelCollapsed" />
        <ArrowRight v-else />
        <span v-if="autoParticipationUnreadCount" class="panel-unread-count" aria-label="会议Agent主动介入未读">
          {{ autoParticipationUnreadCount > 9 ? "9+" : autoParticipationUnreadCount }}
        </span>
      </button>
      <div class="panel-collapsed-label">侧栏</div>
      <div class="panel-content context-panel-content">
        <div class="sidecar-tabs" role="tablist" aria-label="会议侧栏">
          <button
            type="button"
            class="sidecar-tab"
            :class="{ 'sidecar-tab-active': rightPanelTab === 'ai' }"
            :aria-selected="rightPanelTab === 'ai'"
            :aria-label="autoParticipationUnreadCount ? `AI，${autoParticipationUnreadCount} 条主动介入未读` : 'AI'"
            @click="rightPanelTab = 'ai'"
          >
            AI <strong v-if="agentQuestionCount">{{ agentQuestionCount }}</strong>
            <span v-if="autoParticipationUnreadCount" class="sidecar-unread-count">
              {{ autoParticipationUnreadCount > 9 ? "9+" : autoParticipationUnreadCount }}
            </span>
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
            <div>
              <h2>会议Agent</h2>
              <div class="agent-conversation-tabs" role="tablist" aria-label="会议Agent对话范围">
                <button
                  type="button"
                  role="tab"
                  :aria-selected="aiConversationTab === 'private'"
                  :class="{ 'agent-conversation-tab-active': aiConversationTab === 'private' }"
                  @click="aiConversationTab = 'private'"
                >我的对话</button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="aiConversationTab === 'public'"
                  :class="{ 'agent-conversation-tab-active': aiConversationTab === 'public' }"
                  @click="aiConversationTab = 'public'"
                >公开问答</button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="aiConversationTab === 'auto'"
                  :class="{ 'agent-conversation-tab-active': aiConversationTab === 'auto' }"
                  @click="aiConversationTab = 'auto'"
                >
                  主动介入
                  <span v-if="autoParticipationReplies.length" class="agent-conversation-count">
                    {{ autoParticipationReplies.length > 99 ? "99+" : autoParticipationReplies.length }}
                  </span>
                </button>
              </div>
            </div>
            <span class="agent-live-pill" :class="{ 'agent-live-pill-active': store.generalAgentRunning }">
              <span class="agent-live-dot" />{{ store.generalAgentRunning ? "思考中" : "在线" }}
            </span>
          </div>
          <div ref="agentPanelListRef" class="agent-thread-list">
            <div v-if="!store.activeRoom" class="agent-empty">未进入会议</div>
            <div v-else-if="!agentConversationGroups.length" class="agent-empty">{{ agentConversationEmptyText }}</div>
            <section
              v-for="group in store.activeRoom ? agentConversationGroups : []"
              :key="group.id"
              class="agent-qa-group"
              :class="{ 'agent-auto-group': group.kind === 'auto' }"
            >
              <div class="agent-qa-index" :class="{ 'agent-qa-index-auto': group.kind === 'auto' }">
                <template v-if="group.kind === 'auto'">
                  <Bell aria-hidden="true" />
                  <span>主动介入</span>
                  <strong>
                    {{ autoParticipationTriggerLabel(group.autoParticipation?.trigger_type) }}
                    · {{ autoParticipationConfidenceLabel(group.autoParticipation?.confidence) }}
                  </strong>
                </template>
                <template v-else>问 {{ group.questionNumber }}</template>
              </div>
              <div v-if="group.autoParticipation?.reason" class="agent-auto-reason">
                <strong>触发原因</strong>
                <span>{{ group.autoParticipation.reason }}</span>
              </div>
              <article
                v-if="group.question"
                :id="`agent-question-${group.question.id}`"
                class="agent-thread-item agent-thread-question"
              >
                <div class="agent-thread-meta">
                  <span>提问 · {{ group.question.username }}</span>
                  <time>{{ formatTime(group.question.created_at) }}</time>
                </div>
                <div v-if="agentEditingMessageId === group.question.id" class="agent-message-edit">
                  <el-input v-model="agentEditingContent" type="textarea" :rows="3" resize="vertical" />
                  <div class="agent-message-edit-actions">
                    <el-button size="small" @click.stop="cancelModifyAgentQuestion">取消</el-button>
                    <el-button size="small" type="primary" :loading="store.generalAgentRunning" @click.stop="saveModifiedAgentQuestion(group.question, group)">修改并重新问</el-button>
                  </div>
                </div>
                <div v-else class="agent-thread-body">
                  <span>{{ displayMessageContent(group.question) }}</span>
                </div>
                <div v-if="agentEditingMessageId !== group.question.id && messageAttachments(group.question).length" class="message-attachments agent-thread-attachments">
                  <template v-for="att in messageAttachments(group.question)" :key="att.id">
                    <ImageAttachmentCard v-if="isImageAttachment(att)" :src="att.url" :name="attachmentDisplayName(att)" @preview="openImagePreview(att)" />
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ attachmentDisplayName(att) }}</a>
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
                :id="`agent-reply-${reply.id}`"
                tabindex="-1"
                class="agent-thread-item agent-thread-reply"
                :class="{
                  'agent-thread-streaming': reply.message_type === 'agent_streaming',
                  'agent-thread-auto': group.kind === 'auto',
                }"
              >
                <div class="agent-thread-meta">
                  <span>{{ group.kind === "auto" ? "主动提醒 · 会议Agent" : "回复 · 会议Agent" }}</span>
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
                    <ImageAttachmentCard v-if="isImageAttachment(att)" :src="att.url" :name="attachmentDisplayName(att)" @preview="openImagePreview(att)" />
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ attachmentDisplayName(att) }}</a>
                  </template>
                </div>
                <MessageActionBar
                  v-if="reply.message_type !== 'agent_streaming'"
                  :reaction="store.messageReactions[reply.id] || ''"
                  show-feedback
                  :show-share="canQuoteAgentMessageToMain(reply)"
                  share-label="分享到会场"
                  @copy="copyToClipboard(copyMessageContent(reply), '消息已复制')"
                  @like="submitMeetingFeedback(reply, 'up')"
                  @dislike="submitMeetingFeedback(reply, 'down')"
                  @share="openAgentSharePreview(reply)"
                />
              </article>
              <div v-if="!group.replies.length" class="agent-awaiting-reply">等待会议Agent回复</div>
            </section>
          </div>
          <div v-if="store.activeRoom" class="agent-composer" @paste="handleComposerPaste($event, 'agent')">
            <div v-if="agentQuestionSources.length" class="agent-source-chips" aria-label="当前问题来源">
              <span v-for="source in agentQuestionSources" :key="`${source.message_id}:${source.selected_text || ''}`">
                消息 #{{ source.seq_no }} · {{ source.author }}
                <button type="button" aria-label="移除来源" @click="agentQuestionSources = agentQuestionSources.filter((item) => item !== source)">×</button>
              </span>
            </div>
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
                aria-label="询问会议Agent"
                placeholder="问会议Agent"
                @keydown="onAgentInputKeydown"
              />
              <el-button v-if="store.generalAgentRunning" type="danger" @click="stopGeneralAgent">停止生成</el-button>
              <el-button
                v-else
                type="primary"
                :icon="Promotion"
                :disabled="!store.canSend"
                aria-label="发送给会议Agent"
                @click="sendAgentQuestion"
              />
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
                  整理知识
                </el-button>
              </div>
            </article>
            <div v-else class="context-empty context-empty-compact">暂无会议总结</div>
          </section>

          <section class="context-card" :class="{ 'context-card-collapsed': !isContextExpanded('candidateMemory') }">
            <div class="context-head">
              <div>
                <p class="section-kicker">待确认</p>
                <h2>待确认知识</h2>
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
            <p v-if="store.candidateMemories.length" class="context-note">会议Agent根据公共内容自动整理；成员可确认、修改、拒绝或标记争议，并选择沉淀到本会议、其他会议或组织共享空间。</p>
            <div v-if="!store.candidateMemories.length" class="context-empty context-empty-compact">暂无待确认知识，会议Agent会随公共讨论自动整理。</div>
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
                <el-button size="small" text :icon="View" @click="openMemoryDetail(memory)">查看完整</el-button>
                <el-button size="small" type="primary" :icon="Check" @click="confirmCandidateMemory(memory)">确认并发布</el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :icon="Close"
                  :loading="rejectingMemoryId === memory.memory_id"
                  :disabled="Boolean(rejectingMemoryId && rejectingMemoryId !== memory.memory_id)"
                  @click="rejectCandidateMemory(memory)"
                >
                  拒绝
                </el-button>
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
            <p v-if="store.confirmedMemories.length" class="context-note">确认后仍保留来源和版本；共享范围仅由本会议、其他会议或组织共享空间决定。</p>
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
              <div v-if="pendingMemoryShare(memory)" class="memory-pending-share-state">
                <span>{{ pendingMemoryShareLabel(memory) }}；批准前目标范围不可召回。</span>
                <el-button size="small" text type="primary" @click="openMemoryShareInCollab(memory)">在协作中心查看</el-button>
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
                  <el-button size="small" text type="primary" @click="confirmCandidateMemory(memory)">发布/修订</el-button>
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
              <div v-if="share.can_approve || share.can_cancel" class="memory-actions">
                <template v-if="share.can_approve">
                  <el-button size="small" type="primary" @click="approveMemoryShare(share.id)">批准</el-button>
                  <el-button size="small" @click="rejectMemoryShare(share.id)">拒绝</el-button>
                </template>
                <el-button v-if="share.can_cancel" size="small" type="warning" plain @click="cancelMemoryShare(share.id)">撤回申请</el-button>
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
            <p class="context-note">
              这里记录 Agent 是否发言，以及回答时实际可用的数据。点击记录可查看触发原因和原文依据。
            </p>
            <div v-if="!store.agentQueryAudits.length" class="context-empty context-empty-compact">暂无 AI 使用记录</div>
            <button
              v-for="audit in store.agentQueryAudits.slice(0, 4)"
              :key="audit.id"
              type="button"
              class="audit-item audit-item-clickable"
              @click="openAuditDetail(audit)"
            >
              <div class="audit-item-head">
                <div class="audit-outcome">
                  <div class="audit-outcome-row">
                    <span :class="['audit-decision', auditDecisionClass(audit.decision)]">
                      {{ auditDecisionLabel(audit) }}
                    </span>
                    <small class="audit-record-type">{{ auditIntentLabel(audit.intent) }}</small>
                  </div>
                  <small>{{ auditDecisionDescription(audit) }}</small>
                </div>
                <time>{{ formatTime(audit.created_at) }}</time>
              </div>
              <p>{{ audit.question }}</p>
              <small v-if="autoAuditDecision(audit)" class="audit-auto-summary">
                {{ autoParticipationTriggerLabel(autoAuditDecision(audit)?.trigger_type) }}
                · 诊断置信度 {{ Math.round(Number(autoAuditDecision(audit)?.confidence || 0) * 100) }}%
              </small>
              <small
                v-if="audit.decision === 'silent' && autoAuditSuppressionSummary(audit)"
                class="audit-suppression-summary"
              >
                沉默原因：{{ autoAuditSuppressionSummary(audit) }}
              </small>
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
                    <ImageAttachmentCard v-if="isImageAttachment(att)" :src="att.url" :name="attachmentDisplayName(att)" @preview="openImagePreview(att)" />
                    <a v-else :href="att.url" target="_blank" rel="noreferrer" class="att-link">{{ attachmentDisplayName(att) }}</a>
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
      v-model="businessObjectDrawerVisible"
      class="business-object-drawer"
      title="讨论对象"
      size="440px"
      append-to-body
    >
      <div class="business-object-drawer-body">
        <p class="context-note">会议Agent从公共发言中识别任务、产品、批次和标准。候选线索不会自动成为正式结论。</p>
        <div v-if="!visibleBusinessObjects.length" class="context-empty">暂无已识别的讨论对象</div>
        <div v-else class="business-object-list">
          <article v-for="item in visibleBusinessObjects" :key="item.id" class="business-object-item">
            <div class="business-object-item-head">
              <span>{{ businessObjectTypeLabel(item.object_type) }}</span>
              <b :class="`business-object-status-${item.status}`">{{ businessObjectStatusLabel(item.status) }}</b>
            </div>
            <strong>{{ item.resolved_value || item.object_value }}</strong>
            <small v-if="item.resolved_value && item.resolved_value !== item.object_value">原识别值：{{ item.object_value }}</small>
            <div class="business-object-meta">
              <span>置信度 {{ Math.round(Number(item.confidence || 0) * 100) }}%</span>
              <span>来源 {{ item.source_message_ids.length }} 条</span>
            </div>
            <div class="business-object-sources">
              <button
                v-for="sourceId in item.source_message_ids"
                :key="sourceId"
                type="button"
                @click="openBusinessObjectSource(sourceId)"
              >查看来源消息</button>
              <el-button
                v-if="item.status !== 'rejected'"
                text
                type="danger"
                :loading="businessObjectRemovingId === item.id"
                @click="removeBusinessObject(item.id, item.resolved_value || item.object_value)"
              >移除</el-button>
            </div>
          </article>
        </div>
        <form class="business-object-correction" @submit.prevent="submitBusinessObjectCorrection">
          <label for="business-object-correction">纠正讨论对象</label>
          <el-input
            id="business-object-correction"
            v-model="businessObjectCorrection"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="例如：不是A17，是A18"
          />
          <el-button
            native-type="submit"
            type="primary"
            :loading="businessObjectCorrectionSaving"
            :disabled="!businessObjectCorrection.trim()"
          >提交纠正</el-button>
        </form>
      </div>
    </el-drawer>
    <el-dialog
      v-model="agentShareDialogVisible"
      class="agent-share-dialog"
      title="分享到会场"
      width="620px"
      destroy-on-close
      @closed="agentShareMessage = null"
    >
      <div v-if="agentShareMessage" class="agent-share-preview">
        <div class="agent-share-visibility">
          <Share aria-hidden="true" />
          <div>
            <strong>会场全体成员可见</strong>
            <p>将新增一条由你分享的会议Agent回答，不会公开你的其他私人问答。</p>
          </div>
        </div>
        <label for="agent-share-content">公开内容预览</label>
        <el-input
          id="agent-share-content"
          v-model="agentShareContent"
          type="textarea"
          :rows="8"
          maxlength="6000"
          show-word-limit
        />
        <div class="agent-share-source-summary">
          <span>来源</span>
          <strong>{{ anchoredReplySourceCount(agentShareMessage) || 1 }} 条关联内容</strong>
        </div>
      </div>
      <template #footer>
        <el-button @click="agentShareDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="agentShareSubmitting"
          :disabled="!agentShareContent.trim()"
          @click="confirmAgentShare"
        >确认公开</el-button>
      </template>
    </el-dialog>
    <el-drawer
      v-model="auditDetailVisible"
      title="AI 使用记录"
      size="420px"
      append-to-body
    >
      <div v-if="selectedAudit" class="detail-drawer-body">
        <section class="detail-section">
          <p class="context-note">
            这里记录 Agent 是否发言，以及回答时实际可用的数据。诊断置信度只表示对问题类型的判断把握。
          </p>
          <h3>问题</h3>
          <p class="detail-main-text">{{ selectedAudit.question }}</p>
          <div class="detail-meta-grid">
            <span>时间</span>
            <strong>{{ formatTime(selectedAudit.created_at) || "未知" }}</strong>
            <span>处理结果</span>
            <strong>{{ auditDecisionLabel(selectedAudit) }}</strong>
            <span>结果说明</span>
            <strong>{{ auditDecisionDescription(selectedAudit) }}</strong>
            <span>记录类型</span>
            <strong>{{ auditIntentLabel(selectedAudit.intent) }}</strong>
          </div>
        </section>
        <section v-if="autoAuditDecision(selectedAudit)" class="detail-section auto-diagnostic-section">
          <h3>主动参与诊断</h3>
          <div class="detail-meta-grid">
            <span>运行模式</span>
            <strong>{{ autoParticipationModeLabel(autoAuditDecision(selectedAudit)?.mode) }}</strong>
            <span>触发原因</span>
            <strong>{{ autoParticipationTriggerLabel(autoAuditDecision(selectedAudit)?.trigger_type) }}</strong>
            <span>动作</span>
            <strong>{{ autoParticipationActionLabel(autoAuditDecision(selectedAudit)?.action_type) }}</strong>
            <span>目标</span>
            <strong>{{ autoParticipationTargetLabel(autoAuditDecision(selectedAudit)?.target_role) }}</strong>
            <span>诊断置信度</span>
            <strong>{{ Math.round(Number(autoAuditDecision(selectedAudit)?.confidence || 0) * 100) }}%</strong>
          </div>
          <p v-if="autoAuditDecision(selectedAudit)?.reason" class="detail-main-text">
            {{ autoAuditDecision(selectedAudit)?.reason }}
          </p>
          <div v-if="autoAuditDecision(selectedAudit)?.suppression_reasons?.length" class="audit-suppression-list">
            <span v-for="reason in autoAuditDecision(selectedAudit)?.suppression_reasons" :key="reason">
              沉默原因：{{ autoParticipationSuppressionLabel(reason) }}
            </span>
          </div>
        </section>
        <section v-if="selectedAuditEvidenceViews.length" class="detail-section">
          <h3>{{ auditEvidenceSectionTitle(selectedAudit) }}</h3>
          <div class="audit-evidence-list">
            <article v-for="evidence in selectedAuditEvidenceViews" :key="evidence.key" class="audit-evidence-item">
              <div class="audit-evidence-head">
                <strong>{{ evidence.title }}</strong>
                <small>{{ evidence.meta }}</small>
              </div>
              <p>{{ evidence.content }}</p>
              <small class="audit-evidence-trace" :title="evidence.traceId">{{ evidence.traceLabel }}</small>
            </article>
          </div>
        </section>
        <section class="detail-section">
          <h3>读取记忆</h3>
          <div v-if="selectedAuditMemoryViews.length" class="audit-evidence-list">
            <article v-for="memory in selectedAuditMemoryViews" :key="memory.key" class="audit-evidence-item">
              <div class="audit-evidence-head">
                <strong>{{ memory.title }}</strong>
                <small>{{ memory.meta }}</small>
              </div>
              <p>{{ memory.content }}</p>
              <div class="audit-evidence-footer">
                <small class="audit-evidence-trace" :title="memory.traceId">{{ memory.traceLabel }}</small>
                <el-button v-if="memory.memoryAvailable" text size="small" @click="openAuditMemory(memory.ref)">查看记忆</el-button>
              </div>
            </article>
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
      class="memory-detail-drawer"
      :title="memoryDetailTitle"
      size="520px"
      append-to-body
      @closed="selectedSharedMemory = null"
    >
      <div v-if="selectedSharedMemory" class="detail-drawer-body">
        <section class="detail-section">
          <div class="memory-title-row">
            <strong>{{ selectedSharedMemory.title }}</strong>
            <span>{{ memoryScopeLabel(selectedSharedMemory.scope || selectedSharedMemory.scope_type) }}</span>
          </div>
          <p class="detail-main-text memory-detail-content">{{ selectedSharedMemory.content || selectedSharedMemory.summary }}</p>
          <div class="memory-meta-row">
            <span :class="['memory-category-badge', `memory-category-${selectedSharedMemory.memory_category || 'meeting_memory'}`]">
              {{ memoryCategoryLabel(selectedSharedMemory.memory_category) }}
            </span>
            <span>{{ memoryTypeLabel(selectedSharedMemory.memory_type) }}</span>
            <span>{{ memoryStatusLabel(selectedSharedMemory.status) }}</span>
            <span>{{ scopeObjectLabel(selectedSharedMemory) }}</span>
          </div>
        </section>
        <section v-if="selectedMemoryIsCandidate" class="detail-section">
          <h3>提取依据</h3>
          <div class="detail-meta-grid">
            <span>来源位置</span>
            <strong>本会议室</strong>
            <span>来源消息</span>
            <strong>{{ sourceMessageLabel(selectedSharedMemory) }}</strong>
            <span>提取理由</span>
            <strong>{{ selectedSharedMemory.extraction_reason || "暂无记录" }}</strong>
          </div>
          <div v-if="memorySourceSpans(selectedSharedMemory).length" class="memory-source-span-list">
            <article v-for="span in memorySourceSpans(selectedSharedMemory)" :key="span.key">
              <strong>{{ span.label }}</strong>
              <p>{{ span.text }}</p>
            </article>
          </div>
          <p v-else class="context-empty context-empty-compact">暂无来源片段记录</p>
        </section>
        <section v-else class="detail-section">
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
          <div v-if="pendingMemoryShare(selectedSharedMemory)" class="memory-pending-share-state">
            <span>{{ pendingMemoryShareLabel(selectedSharedMemory) }}；批准前目标范围不可召回。</span>
            <el-button size="small" text type="primary" @click="openMemoryShareInCollab(selectedSharedMemory)">在协作中心查看</el-button>
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
        <div v-if="canReviewMemory && selectedMemoryIsCandidate" class="detail-actions memory-detail-review-actions">
          <el-button size="small" :icon="CopyDocument" @click="copyMemoryDetail">复制完整内容</el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :icon="Close"
            :loading="rejectingMemoryId === selectedSharedMemory.memory_id"
            @click="rejectCandidateMemory(selectedSharedMemory)"
          >
            拒绝
          </el-button>
          <el-button size="small" type="primary" :icon="Check" @click="confirmCandidateMemory(selectedSharedMemory)">确认并发布</el-button>
        </div>
        <div v-else-if="canReviewMemory && selectedSharedMemory.status !== 'superseded'" class="detail-actions">
          <el-button size="small" @click="disputeSharedMemory(selectedSharedMemory)">质疑</el-button>
          <el-button size="small" type="primary" @click="confirmCandidateMemory(selectedSharedMemory)">发布/修订</el-button>
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

.meeting-page.is-workspace-focus {
  grid-template-columns: var(--left-panel-width, 260px) minmax(0, 1fr);
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  column-gap: 12px;
  row-gap: 0;
}

.meeting-page.is-workspace-focus .meeting-sidebar {
  grid-column: 1;
  grid-row: 1 / -1;
}

.meeting-page.is-workspace-focus .meeting-room {
  display: contents;
  grid-column: 2;
}

.meeting-page.is-workspace-focus .room-header,
.meeting-page.is-workspace-focus .meeting-workspace-nav,
.meeting-page.is-workspace-focus .meeting-workspace-stage,
.meeting-page.is-workspace-focus .meeting-message-pane,
.meeting-page.is-workspace-focus .composer,
.meeting-page.is-workspace-focus .meeting-context {
  grid-column: 2;
  min-width: 0;
}

.meeting-page.is-workspace-focus .room-header {
  grid-row: 1;
  border: 1px solid #e4e4e7;
  border-radius: 12px 12px 0 0;
  background: #fff;
}

.meeting-page.is-workspace-focus .meeting-workspace-nav {
  grid-row: 2;
  border-right: 1px solid #e4e4e7;
  border-left: 1px solid #e4e4e7;
}

.meeting-page.is-workspace-focus .meeting-workspace-stage,
.meeting-page.is-workspace-focus .meeting-message-pane {
  grid-row: 3;
  border-right: 1px solid #e4e4e7;
  border-left: 1px solid #e4e4e7;
  background: #fff;
}

.meeting-page.is-workspace-focus .composer {
  grid-row: 4;
  border: 1px solid #e4e4e7;
  border-top-color: #e4e4e7;
  border-radius: 0 0 12px 12px;
  background: #fff;
}

.meeting-page.is-workspace-focus .meeting-context {
  grid-row: 3 / 5;
  overflow: hidden;
  border-radius: 0 0 12px 12px;
  box-shadow: none;
}

.meeting-page.is-workspace-focus .meeting-context .panel-toggle,
.meeting-page.is-workspace-focus .meeting-context .panel-collapsed-label,
.meeting-page.is-workspace-focus .meeting-context .panel-resizer,
.meeting-page.is-workspace-focus .meeting-context .sidecar-tabs {
  display: none;
}

.meeting-page.is-workspace-focus .meeting-context.panel-collapsed {
  display: block;
}

.meeting-page.is-workspace-focus .meeting-context.panel-collapsed .panel-content {
  visibility: visible;
  opacity: 1;
  pointer-events: auto;
}

.meeting-page.is-workspace-focus .context-panel-content {
  gap: 0;
  padding: 0;
  overflow: hidden;
}

.meeting-page.is-workspace-focus .agent-sidecar,
.meeting-page.is-workspace-focus .private-sidecar,
.meeting-page.is-workspace-focus .context-pane {
  height: 100%;
  padding: 18px 20px;
  overflow-y: auto;
  border: 0;
  border-radius: 0;
}

.meeting-page.is-workspace-focus .agent-sidecar {
  background: #f8fbff;
}

.meeting-page.is-workspace-focus .private-sidecar {
  background: #fff;
}

.meeting-page.is-workspace-focus .private-sidecar-roster .private-launcher-list {
  max-height: none;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.meeting-page.is-workspace-focus .context-pane > .context-card:not(.boundary-card):not(.summary-card) {
  display: none;
}

.meeting-page.is-workspace-focus .context-pane {
  display: grid;
  align-content: start;
  gap: 0;
}

.meeting-page.is-workspace-focus .context-pane > .context-card {
  padding: 18px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.meeting-page.is-workspace-focus .context-pane > .context-card + .context-card {
  border-top: 1px solid #e4e4e7;
}

.meeting-page.is-workspace-focus .boundary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.meeting-layout-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px;
  min-width: 154px;
  padding: 3px;
  border: 1px solid #d4d4d8;
  border-radius: 8px;
  background: #f4f4f5;
}

.meeting-layout-switch button {
  display: inline-flex;
  min-width: 0;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 4px 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  cursor: pointer;
  transition: background 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.meeting-layout-switch button:hover {
  color: #18181b;
}

.meeting-layout-switch button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.meeting-layout-switch svg {
  width: 15px;
  height: 15px;
}

.meeting-layout-option-active {
  background: #18181b !important;
  color: #fff !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.2);
}

.meeting-workspace-nav {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 14px;
  border-bottom: 1px solid #e4e4e7;
  background: #fafafa;
}

.meeting-workspace-label {
  display: grid;
  flex: 0 0 auto;
  gap: 1px;
}

.meeting-workspace-label strong {
  color: #18181b;
  font-size: 12px;
}

.meeting-workspace-label small {
  color: #71717a;
  font-size: 10px;
}

.meeting-workspace-tabs {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.meeting-workspace-tabs button {
  display: inline-flex;
  min-width: 88px;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
}

.meeting-workspace-tabs button:hover {
  border-color: #d4d4d8;
  background: #fff;
  color: #18181b;
}

.meeting-workspace-tabs button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.meeting-workspace-tabs svg {
  width: 15px;
  height: 15px;
}

.meeting-workspace-tabs button > strong {
  display: inline-flex;
  min-width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: #e4e4e7;
  color: #3f3f46;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.meeting-workspace-tab-active {
  border-color: #18181b !important;
  background: #18181b !important;
  color: #fff !important;
}

.meeting-workspace-tab-active > strong {
  background: rgba(255, 255, 255, 0.18) !important;
  color: #fff !important;
}

.meeting-workspace-stage {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.workspace-stage-head {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #e4e4e7;
}

.workspace-stage-head > div {
  min-width: 0;
}

.workspace-stage-head h2 {
  margin: 4px 0 0;
  color: #18181b;
  font-size: 18px;
  letter-spacing: 0;
}

.workspace-stage-head p:last-child {
  margin: 6px 0 0;
  color: #71717a;
  font-size: 12px;
  line-height: 1.5;
}

.workspace-stage-count {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  padding: 3px 9px;
  border: 1px solid #d4d4d8;
  border-radius: 6px;
  background: #fafafa;
  color: #3f3f46;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.workspace-memory-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 20px 0;
  border-bottom: 1px solid #e4e4e7;
}

.workspace-memory-tabs button {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  gap: 7px;
  padding: 6px 12px 8px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #71717a;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  cursor: pointer;
}

.workspace-memory-tabs button:hover,
.workspace-memory-tab-active {
  color: #18181b !important;
}

.workspace-memory-tab-active {
  border-bottom-color: #18181b !important;
}

.workspace-memory-tabs button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: -2px;
}

.workspace-memory-tabs strong {
  display: inline-flex;
  min-width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.workspace-memory-layout {
  display: grid;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns: minmax(260px, 34%) minmax(0, 1fr);
}

.workspace-memory-list {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  border-right: 1px solid #e4e4e7;
  background: #fafafa;
}

.workspace-memory-list-item {
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 6px;
  padding: 14px 16px;
  border: 0;
  border-bottom: 1px solid #e4e4e7;
  background: transparent;
  color: #3f3f46;
  font: inherit;
  letter-spacing: 0;
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease, box-shadow 150ms ease;
}

.workspace-memory-list-item:hover {
  background: #fff;
}

.workspace-memory-list-item:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: -3px;
}

.workspace-memory-list-item-active {
  background: #fff;
  box-shadow: inset 3px 0 0 #18181b;
}

.workspace-memory-list-head {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.workspace-memory-list-head strong {
  min-width: 0;
  color: #18181b;
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.workspace-memory-list-head b {
  flex: 0 0 auto;
  color: #4f46e5;
  font-size: 11px;
}

.workspace-memory-list-meta {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.workspace-memory-list-item p {
  margin: 0;
  color: #52525b;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.workspace-memory-extraction-state {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 8px 18px;
  border-top: 1px solid #e4e4e7;
  border-bottom: 1px solid #e4e4e7;
  background: #fafafa;
}

.workspace-memory-extraction-state > div {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.workspace-memory-extraction-state strong {
  color: #27272a;
  font-size: 12px;
  letter-spacing: 0;
}

.workspace-memory-extraction-state small {
  color: #71717a;
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.workspace-memory-extraction-state .el-button {
  margin-left: auto;
}

.workspace-memory-extraction-indicator {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #71717a;
}

.workspace-memory-extraction-state[data-state="running"] .workspace-memory-extraction-indicator {
  background: #2563eb;
  box-shadow: 0 0 0 4px #dbeafe;
}

.workspace-memory-extraction-state[data-state="success"] .workspace-memory-extraction-indicator {
  background: #15803d;
}

.workspace-memory-extraction-state[data-state="empty"] .workspace-memory-extraction-indicator {
  background: #a16207;
}

.workspace-memory-extraction-state[data-state="error"] .workspace-memory-extraction-indicator {
  background: #b91c1c;
}

.workspace-memory-review {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  padding: 20px 22px 0;
}

.workspace-memory-review-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.workspace-memory-review-head h3 {
  margin: 5px 0 0;
  color: #18181b;
  font-size: 18px;
  line-height: 1.4;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.workspace-memory-review-head > span {
  flex: 0 0 auto;
  padding: 3px 8px;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 700;
}

.workspace-memory-review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.workspace-memory-content-section,
.workspace-memory-evidence-section,
.workspace-memory-risk-section,
.workspace-memory-qdl-section {
  display: grid;
  gap: 9px;
  padding-top: 14px;
  border-top: 1px solid #e4e4e7;
}

.workspace-memory-review h4 {
  margin: 0;
  color: #27272a;
  font-size: 12px;
  letter-spacing: 0;
}

.workspace-memory-content-section > p {
  margin: 0;
  color: #27272a;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.workspace-memory-qdl-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.workspace-memory-qdl-head p {
  margin: 4px 0 0;
  color: #71717a;
  font-size: 12px;
}

.qdl-validation-badge {
  flex: 0 0 auto;
  padding: 4px 8px;
  border: 1px solid #d4d4d8;
  border-radius: 5px;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.qdl-validation-valid {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #166534;
}

.qdl-validation-legacy_mapped {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.qdl-validation-invalid {
  border-color: #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

.qdl-validation-errors {
  display: grid;
  gap: 5px;
  padding: 10px 12px;
  border-left: 3px solid #dc2626;
  background: #fef2f2;
  color: #7f1d1d;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.qdl-summary-grid,
.qdl-provenance-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  border-top: 1px solid #e4e4e7;
  border-bottom: 1px solid #e4e4e7;
}

.qdl-summary-grid > div,
.qdl-provenance-grid > div {
  min-width: 0;
  padding: 10px 12px;
}

.qdl-summary-grid > div + div,
.qdl-provenance-grid > div + div {
  border-left: 1px solid #e4e4e7;
}

.qdl-summary-grid dt,
.qdl-provenance-grid dt {
  margin: 0 0 4px;
  color: #71717a;
  font-size: 12px;
  font-weight: 700;
}

.qdl-summary-grid dd,
.qdl-provenance-grid dd {
  margin: 0;
  color: #27272a;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.qdl-subsection {
  display: grid;
  gap: 8px;
}

.qdl-subsection h5 {
  margin: 0;
  color: #52525b;
  font-size: 12px;
  letter-spacing: 0;
}

.qdl-property-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid #e4e4e7;
  border-left: 1px solid #e4e4e7;
}

.qdl-property-row {
  display: grid;
  min-width: 0;
  min-height: 58px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-content: center;
  gap: 3px 8px;
  padding: 8px 10px;
  border-right: 1px solid #e4e4e7;
  border-bottom: 1px solid #e4e4e7;
}

.qdl-property-row span,
.qdl-property-row small {
  color: #71717a;
  font-size: 12px;
}

.qdl-property-row strong {
  color: #52525b;
  font-size: 12px;
}

.qdl-property-row strong[data-level="high"] {
  color: #166534;
}

.qdl-property-row strong[data-level="medium"] {
  color: #92400e;
}

.qdl-property-row small {
  grid-column: 1 / -1;
}

.qdl-context-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.qdl-entity-list,
.qdl-relation-list {
  display: grid;
  border-top: 1px solid #e4e4e7;
}

.qdl-entity-list > div,
.qdl-relation-list > div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 38px;
  border-bottom: 1px solid #e4e4e7;
  color: #52525b;
  font-size: 12px;
}

.qdl-entity-list strong,
.qdl-relation-list strong {
  min-width: 0;
  color: #27272a;
  overflow-wrap: anywhere;
}

.qdl-entity-list small,
.qdl-relation-list small {
  color: #71717a;
  overflow-wrap: anywhere;
}

.qdl-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.qdl-tag-list span {
  padding: 4px 7px;
  border: 1px solid #d4d4d8;
  border-radius: 5px;
  background: #fafafa;
  color: #3f3f46;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.qdl-empty-line {
  margin: 0;
  color: #71717a;
  font-size: 12px;
}

.qdl-evidence-list {
  display: grid;
  border-top: 1px solid #e4e4e7;
}

.qdl-evidence-list article {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #e4e4e7;
}

.qdl-evidence-list article > div {
  min-width: 0;
}

.qdl-evidence-list strong {
  color: #3f3f46;
  font-size: 12px;
}

.qdl-evidence-list p {
  margin: 4px 0 0;
  color: #52525b;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.workspace-memory-evidence-section dl {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 7px;
  background: #fafafa;
}

.workspace-memory-evidence-section dt {
  color: #71717a;
  font-size: 11px;
  font-weight: 700;
}

.workspace-memory-evidence-section dd {
  margin: 0;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.workspace-source-spans {
  display: grid;
  gap: 8px;
}

.workspace-source-spans article {
  padding: 12px;
  border-left: 3px solid #a1a1aa;
  background: #fafafa;
}

.workspace-source-spans strong {
  color: #52525b;
  font-size: 11px;
}

.workspace-source-spans p {
  margin: 6px 0 0;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.workspace-memory-review-actions {
  position: sticky;
  bottom: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin: auto -22px 0;
  padding: 12px 22px;
  border-top: 1px solid #e4e4e7;
  background: rgba(255, 255, 255, 0.97);
}

.workspace-governance-layout {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  overflow: hidden;
}

.workspace-governance-section {
  min-width: 0;
  overflow-y: auto;
  padding: 18px 20px;
}

.workspace-governance-section + .workspace-governance-section {
  border-left: 1px solid #e4e4e7;
}

.workspace-governance-section > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e4e7;
}

.workspace-governance-section h3 {
  margin: 4px 0 0;
  color: #18181b;
  font-size: 15px;
  letter-spacing: 0;
}

.workspace-governance-section > header > span {
  display: inline-flex;
  min-width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 11px;
  font-weight: 800;
}

.workspace-governance-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid #e4e4e7;
}

.workspace-governance-row > div:first-child {
  min-width: 0;
}

.workspace-governance-row strong {
  color: #27272a;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.workspace-governance-row p {
  margin: 5px 0 0;
  color: #52525b;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.workspace-governance-row small {
  display: block;
  margin-top: 5px;
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.workspace-row-actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.workspace-action-create {
  display: grid;
  grid-template-columns: minmax(180px, 1.2fr) minmax(180px, 1fr) minmax(150px, 0.7fr) auto;
  gap: 8px;
  padding: 14px 20px;
  border-bottom: 1px solid #e4e4e7;
  background: #fafafa;
}

.workspace-action-list {
  min-height: 0;
  overflow-y: auto;
  padding: 0 20px;
}

.workspace-action-list article {
  display: grid;
  min-width: 0;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 15px 0;
  border-bottom: 1px solid #e4e4e7;
}

.workspace-action-status {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid #d4d4d8;
  border-radius: 50%;
  color: #166534;
}

.workspace-action-status svg {
  width: 14px;
  height: 14px;
}

.workspace-action-list article > div {
  min-width: 0;
}

.workspace-action-list strong {
  color: #27272a;
  font-size: 13px;
}

.workspace-action-list p {
  margin: 4px 0 0;
  color: #52525b;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.workspace-action-list small {
  display: block;
  margin-top: 5px;
  color: #71717a;
  font-size: 11px;
}

.workspace-action-row-done {
  opacity: 0.6;
}

.workspace-audit-list {
  min-height: 0;
  overflow-y: auto;
  padding: 0 20px;
}

.workspace-audit-list > button {
  display: grid;
  width: 100%;
  min-width: 0;
  grid-template-columns: 130px minmax(0, 1fr) 130px;
  align-items: start;
  gap: 14px;
  padding: 15px 0;
  border: 0;
  border-bottom: 1px solid #e4e4e7;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: 0;
  text-align: left;
  cursor: pointer;
}

.workspace-audit-list > button:hover {
  background: #fafafa;
}

.workspace-audit-list > button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: -2px;
}

.workspace-audit-main {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.workspace-audit-main strong {
  color: #27272a;
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.workspace-audit-main small {
  color: #71717a;
  font-size: 11px;
  line-height: 1.5;
}

.workspace-audit-meta {
  display: grid;
  justify-items: end;
  gap: 5px;
  color: #71717a;
  font-size: 11px;
}

.workspace-audit-meta b {
  color: #52525b;
  font-size: 11px;
}

.workspace-empty-state {
  display: grid;
  min-height: 180px;
  place-items: center;
  align-content: center;
  gap: 8px;
  padding: 24px;
  color: #71717a;
  text-align: center;
}

.workspace-empty-state.compact {
  min-height: 110px;
}

.workspace-empty-state svg {
  width: 28px;
  height: 28px;
}

.workspace-empty-state strong {
  color: #3f3f46;
  font-size: 13px;
}

.workspace-empty-state p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
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
  min-height: 44px;
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

.sidecar-unread-count,
.panel-unread-count {
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: #b91c1c;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.panel-unread-count {
  position: absolute;
  top: -7px;
  right: -7px;
  border: 2px solid #fff;
  pointer-events: none;
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

.agent-auto-group::before {
  background: #f59e0b;
}

.agent-qa-index-auto {
  max-width: 100%;
  flex-wrap: wrap;
  gap: 5px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.agent-qa-index-auto svg {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
}

.agent-qa-index-auto strong {
  font-weight: 800;
}

.agent-auto-reason {
  display: grid;
  gap: 3px;
  padding: 8px 10px;
  border-left: 3px solid #f59e0b;
  background: #fffbeb;
  color: #78350f;
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.agent-auto-reason strong {
  color: #92400e;
  font-size: 11px;
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

.agent-thread-reply-targeted {
  border-color: #16a34a;
  background: #f0fdf4;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.16);
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

.agent-thread-auto {
  border-color: #fcd34d;
  background: #fffdf5;
}

.agent-thread-auto::before {
  background: #d97706;
  box-shadow: 0 0 0 2px #fde68a;
}

.agent-thread-auto .agent-thread-meta span {
  color: #92400e;
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

.agent-stale-replies {
  padding: 7px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
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
  grid-template-columns: 44px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
  min-width: 0;
}

.agent-composer textarea {
  width: 100%;
  min-height: 44px;
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

.agent-composer-row :deep(.el-button) {
  min-width: 44px;
  min-height: 44px;
  margin: 0;
  padding: 0 12px;
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
  border: 1px solid #d4d4d8;
  border-radius: 8px;
  background: #f4f4f5;
}

.hub-mode-button {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #52525b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: center;
  transition: background 150ms ease, border-color 150ms ease, color 150ms ease;
}

.hub-mode-button:hover:not(.hub-mode-active) {
  border-color: #d4d4d8;
  background: #fff;
  color: #18181b;
}

.hub-mode-button:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 2px #a1a1aa;
}

.hub-mode-label {
  white-space: nowrap;
}

.hub-mode-check {
  display: grid;
  width: 16px;
  height: 16px;
  place-items: center;
  flex: none;
}

.hub-mode-check :deep(.el-icon) {
  font-size: 14px;
}

.hub-mode-active {
  border-color: #18181b;
  background: #18181b;
  color: #fff;
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

.meeting-room.has-workspace-nav {
  grid-template-rows: auto auto minmax(0, 1fr) auto;
}

.room-header {
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
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
  margin-top: 5px;
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

.auto-mode-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid #d4d4d8;
  border-radius: 999px;
  background: #fafafa;
  color: #52525b;
  font-size: 12px;
  font-weight: 600;
}

.auto-mode-live {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #166534;
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
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
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

.auto-participation-settings {
  display: grid;
  gap: 12px;
}

.auto-participation-settings-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.auto-participation-settings-head strong {
  color: #111827;
  font-size: 14px;
}

.auto-participation-settings-head span {
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.auto-participation-settings p {
  margin: 0;
  color: #71717a;
  font-size: 12px;
  line-height: 1.6;
}

.auto-mode-control {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #f4f4f5;
}

.auto-mode-control button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 0;
  min-height: 44px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease;
}

.auto-mode-control button:hover:not(:disabled):not(.auto-mode-control-active) {
  border-color: #d4d4d8;
  background: #fff;
  color: #18181b;
}

.auto-mode-control-active {
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.16);
}

.auto-mode-control-active.auto-mode-option-off {
  border-color: #27272a;
  background: #27272a;
  color: #fff;
}

.auto-mode-control-active.auto-mode-option-live {
  border-color: #4ade80;
  background: #dcfce7;
  color: #166534;
}

.auto-mode-icon-slot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
}

.auto-mode-icon-slot svg {
  width: 14px;
  height: 14px;
  stroke-width: 2.5;
}

.auto-mode-control button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.auto-mode-control button:disabled {
  cursor: wait;
  opacity: 0.55;
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
.meeting-message-pane {
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.message-list {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
  overflow-anchor: none;
}

.load-older-messages,
.new-message-jump {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  padding: 0 16px;
  border: 1px solid #d4d4d8;
  border-radius: 8px;
  background: #fff;
  color: #3f3f46;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.load-older-messages:hover,
.new-message-jump:hover {
  border-color: #166534;
  color: #166534;
}

.load-older-messages:focus-visible,
.new-message-jump:focus-visible,
.discussion-object-entry:focus-visible,
.anchored-agent-reply > button:focus-visible,
.message-selection-menu button:focus-visible,
.business-object-sources button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.load-older-messages:disabled {
  cursor: wait;
  opacity: 0.55;
}

.new-message-jump {
  position: absolute;
  z-index: 8;
  left: 50%;
  bottom: 8px;
  margin: 0;
  transform: translateX(-50%);
  border-color: #86efac;
  background: #f0fdf4;
  color: #166534;
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
  content-visibility: auto;
  contain-intrinsic-size: auto 132px;
}

.message-row:focus {
  outline: none;
}

.message-row:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 4px;
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

.anchored-agent-reply {
  width: min(720px, 82%);
  min-height: 52px;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 3px;
  padding: 8px 10px;
  border: 1px solid #bbf7d0;
  border-left: 3px solid #15803d;
  border-radius: 6px;
  background: #f0fdf4;
  color: #14532d;
}

.message-row-own .anchored-agent-reply {
  align-self: flex-end;
}

.anchored-agent-reply-pending {
  border-color: #bfdbfe;
  border-left-color: #2563eb;
  background: #eff6ff;
  color: #1e3a8a;
}

.anchored-agent-reply-invalid {
  border-color: #d4d4d8;
  border-left-color: #71717a;
  background: #fafafa;
  color: #52525b;
}

.anchored-agent-mark {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: #dcfce7;
}

.anchored-agent-mark svg {
  width: 17px;
  height: 17px;
}

.anchored-agent-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.anchored-agent-copy strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.anchored-agent-copy small {
  color: #4d7c5c;
  font-size: 11px;
}

.anchored-agent-reply > button {
  min-height: 44px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.message-selection-menu {
  position: fixed;
  z-index: 4000;
  display: flex;
  gap: 2px;
  max-width: calc(100vw - 24px);
  padding: 4px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #18181b;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.24);
  transform: translate(-50%, -100%);
}

.message-selection-menu button {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #fff;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.message-selection-menu button:hover {
  background: #3f3f46;
}

.message-selection-menu svg {
  width: 16px;
  height: 16px;
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.audit-outcome {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.audit-outcome-row {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.audit-record-type {
  color: #71717a !important;
  font-weight: 700;
}

.audit-outcome > small {
  color: #52525b;
  font-weight: 600;
}

.audit-item-head time {
  color: #a1a1aa;
  font-size: 11px;
}

.audit-decision {
  justify-self: start;
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

.audit-silent {
  background: #f4f4f5;
  color: #52525b;
}

.audit-observe {
  background: #dbeafe;
  color: #1d4ed8;
}

.audit-participate {
  background: #dcfce7;
  color: #166534;
}

.audit-auto-summary {
  color: #1d4ed8 !important;
  font-weight: 700;
}

.audit-suppression-summary {
  display: block;
  color: #92400e !important;
  font-weight: 800;
  overflow-wrap: anywhere;
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

.memory-pending-share-state {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
  padding: 7px 10px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  color: #854d0e;
  font-size: 12px;
  line-height: 1.5;
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

.memory-detail-content {
  margin: 8px 0 0 !important;
  color: #27272a !important;
  font-size: 13px !important;
  line-height: 1.75 !important;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.memory-source-span-list {
  display: grid;
  gap: 8px;
}

.memory-source-span-list article {
  padding: 10px;
  border: 1px solid #e4e4e7;
  border-radius: 7px;
  background: #fafafa;
}

.memory-source-span-list strong {
  color: #3f3f46;
  font-size: 12px;
}

.memory-source-span-list p {
  margin: 6px 0 0;
  color: #3f3f46;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.memory-detail-review-actions {
  position: sticky;
  bottom: 0;
  z-index: 1;
  padding: 10px 0 2px;
  background: #fff;
}

:global(.memory-detail-drawer.el-drawer) {
  max-width: 94vw;
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

.audit-evidence-list {
  display: grid;
  border-top: 1px solid #e4e4e7;
}

.audit-evidence-item {
  min-width: 0;
  display: grid;
  gap: 5px;
  padding: 10px 0;
  border-bottom: 1px solid #e4e4e7;
}

.audit-evidence-head {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.audit-evidence-head strong {
  color: #111827;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.audit-evidence-head small {
  color: #52525b;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.45;
}

.audit-evidence-item p {
  margin: 0;
  color: #374151;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.audit-evidence-trace {
  color: #71717a;
  font-size: 10px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.audit-evidence-footer {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.auto-diagnostic-section {
  border-color: #dbeafe;
  background: #f8fbff;
}

.audit-suppression-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.audit-suppression-list span {
  padding: 4px 7px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  background: #fff;
  color: #52525b;
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
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

.discussion-object-entry {
  position: relative;
  min-height: 44px;
  padding: 0 10px;
  border: 1px solid #d4d4d8;
  border-radius: 6px;
  background: #fff;
  color: #3f3f46;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.discussion-object-entry:hover {
  border-color: #15803d;
  color: #166534;
}

.discussion-object-entry-ambiguous::after {
  content: "";
  position: absolute;
  top: -3px;
  right: -3px;
  width: 8px;
  height: 8px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #d97706;
}

.agent-conversation-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
  margin-top: 8px;
  padding: 3px;
  border: 1px solid #d4d4d8;
  border-radius: 8px;
  background: #f4f4f5;
}

.agent-conversation-tabs button {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #52525b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.agent-conversation-tabs button:hover:not(.agent-conversation-tab-active) {
  background: #fff;
  color: #18181b;
}

.agent-conversation-tabs button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 1px;
}

.agent-conversation-tab-active {
  border-color: #18181b !important;
  background: #18181b !important;
  color: #fff !important;
}

.agent-conversation-count {
  min-width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  padding: 0 4px;
  border-radius: 999px;
  background: #e4e4e7;
  color: #3f3f46;
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
}

.agent-conversation-tab-active .agent-conversation-count {
  background: #fff;
  color: #18181b;
}

.agent-qa-group {
  content-visibility: auto;
  contain-intrinsic-size: auto 220px;
}

.agent-source-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px 0;
}

.agent-source-chips > span {
  min-width: 0;
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  gap: 6px;
  padding-left: 9px;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  background: #eff6ff;
  color: #1e40af;
  font-size: 11px;
  font-weight: 700;
}

.agent-source-chips button {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  font-size: 18px;
  cursor: pointer;
}

.agent-source-chips button:hover {
  background: #dbeafe;
}

.business-object-drawer-body,
.business-object-list,
.business-object-correction,
.agent-share-preview {
  display: grid;
  gap: 14px;
}

.business-object-list {
  gap: 10px;
}

.business-object-item {
  display: grid;
  gap: 7px;
  padding: 12px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fff;
}

.business-object-item-head,
.business-object-meta,
.agent-share-source-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.business-object-item-head > span {
  color: #3f3f46;
  font-size: 12px;
  font-weight: 700;
}

.business-object-item-head b {
  padding: 3px 7px;
  border-radius: 4px;
  background: #f4f4f5;
  color: #52525b;
  font-size: 11px;
}

.business-object-item-head .business-object-status-candidate {
  background: #fffbeb;
  color: #92400e;
}

.business-object-item-head .business-object-status-verified,
.business-object-item-head .business-object-status-corrected {
  background: #f0fdf4;
  color: #166534;
}

.business-object-item > strong {
  color: #18181b;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.business-object-item > small,
.business-object-meta {
  color: #71717a;
  font-size: 11px;
}

.business-object-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.business-object-sources button {
  min-height: 36px;
  padding: 0 8px;
  border: 1px solid #d4d4d8;
  border-radius: 6px;
  background: #fff;
  color: #52525b;
  font: inherit;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.business-object-correction {
  padding-top: 14px;
  border-top: 1px solid #e4e4e7;
}

.business-object-correction > label,
.agent-share-preview > label {
  color: #27272a;
  font-size: 13px;
  font-weight: 700;
}

.business-object-correction > :deep(.el-button) {
  min-height: 44px;
  justify-self: end;
}

.agent-share-dialog,
.business-object-drawer {
  max-width: calc(100vw - 24px);
}

.agent-share-visibility {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  border: 1px solid #86efac;
  border-radius: 8px;
  background: #f0fdf4;
  color: #14532d;
}

.agent-share-visibility > svg {
  width: 22px;
  height: 22px;
}

.agent-share-visibility p {
  margin: 4px 0 0;
  color: #3f6b4d;
  font-size: 12px;
  line-height: 1.6;
}

.agent-share-source-summary {
  padding: 10px 12px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  background: #fafafa;
  color: #52525b;
  font-size: 12px;
}

.message-selection-menu-below {
  transform: translate(-50%, 0);
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

  .meeting-page.is-workspace-focus {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto minmax(560px, 1fr) auto;
    row-gap: 0;
  }

  .meeting-page.is-workspace-focus .meeting-sidebar {
    grid-column: 1;
    grid-row: 1;
    margin-bottom: 12px;
  }

  .meeting-page.is-workspace-focus .room-header,
  .meeting-page.is-workspace-focus .meeting-workspace-nav,
  .meeting-page.is-workspace-focus .meeting-workspace-stage,
  .meeting-page.is-workspace-focus .meeting-message-pane,
  .meeting-page.is-workspace-focus .composer,
  .meeting-page.is-workspace-focus .meeting-context {
    grid-column: 1;
  }

  .meeting-page.is-workspace-focus .room-header {
    grid-row: 2;
  }

  .meeting-page.is-workspace-focus .meeting-workspace-nav {
    grid-row: 3;
  }

  .meeting-page.is-workspace-focus .meeting-workspace-stage,
  .meeting-page.is-workspace-focus .meeting-message-pane {
    grid-row: 4;
  }

  .meeting-page.is-workspace-focus .composer {
    grid-row: 5;
  }

  .meeting-page.is-workspace-focus .meeting-context {
    grid-row: 4 / 6;
    min-height: 0;
  }

  .meeting-workspace-nav {
    gap: 8px;
    padding: 8px 10px;
    overflow: hidden;
  }

  .meeting-workspace-label {
    display: none;
  }

  .meeting-workspace-tabs {
    width: 100%;
  }

  .meeting-workspace-tabs button {
    min-width: 76px;
    flex: 0 0 auto;
  }

  .workspace-memory-layout {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(150px, 36%) minmax(0, 1fr);
  }

  .workspace-memory-list {
    border-right: 0;
    border-bottom: 1px solid #e4e4e7;
  }

  .workspace-memory-review {
    padding: 16px 18px 0;
  }

  .workspace-memory-review-actions {
    margin-right: -18px;
    margin-left: -18px;
    padding-right: 18px;
    padding-left: 18px;
  }

  .qdl-summary-grid,
  .qdl-provenance-grid,
  .qdl-property-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .qdl-summary-grid > div:nth-child(3),
  .qdl-provenance-grid > div:nth-child(3) {
    border-top: 1px solid #e4e4e7;
    border-left: 0;
  }

  .qdl-summary-grid > div:nth-child(4),
  .qdl-provenance-grid > div:nth-child(4) {
    border-top: 1px solid #e4e4e7;
  }

  .workspace-governance-layout {
    grid-template-columns: minmax(0, 1fr);
    overflow-y: auto;
  }

  .workspace-governance-section {
    overflow: visible;
  }

  .workspace-governance-section + .workspace-governance-section {
    border-top: 1px solid #e4e4e7;
    border-left: 0;
  }

  .workspace-action-create {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace-audit-list > button {
    grid-template-columns: 110px minmax(0, 1fr);
  }

  .workspace-audit-meta {
    grid-column: 2;
    justify-items: start;
  }

  .meeting-page.is-workspace-focus .boundary-grid {
    grid-template-columns: minmax(0, 1fr);
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

  .message-list {
    padding: 12px;
  }

  .message-bubble,
  .message-attachments,
  .quoted-message,
  .anchored-agent-reply {
    max-width: 94%;
    width: auto;
  }

  .anchored-agent-reply {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .anchored-agent-reply > button {
    grid-column: 2;
    justify-self: start;
    padding: 0;
  }

  .message-selection-menu {
    flex-wrap: wrap;
    justify-content: center;
  }

  .room-header-right,
  .room-toolbar-main,
  .room-toolbar-admin {
    width: 100%;
    align-items: stretch;
    justify-content: flex-start;
  }

  .meeting-layout-switch {
    flex: 1 1 150px;
  }

  .workspace-stage-head {
    gap: 10px;
    padding: 14px;
  }

  .workspace-stage-head p:last-child {
    display: none;
  }

  .workspace-memory-tabs {
    padding-right: 10px;
    padding-left: 10px;
    overflow-x: auto;
  }

  .workspace-memory-tabs button {
    flex: 0 0 auto;
  }

  .workspace-memory-layout {
    grid-template-rows: minmax(96px, 24%) minmax(0, 1fr);
  }

  .workspace-memory-list-item {
    gap: 4px;
    padding: 10px 14px;
  }

  .workspace-memory-list-item p {
    display: none;
  }

  .workspace-memory-review-actions {
    position: static;
    margin-top: 8px;
  }

  .workspace-memory-review-head,
  .workspace-governance-row,
  .workspace-action-list article {
    align-items: flex-start;
  }

  .workspace-memory-review-head {
    flex-direction: column;
    gap: 8px;
  }

  .workspace-memory-evidence-section dl {
    grid-template-columns: minmax(0, 1fr);
  }

  .workspace-memory-extraction-state {
    align-items: flex-start;
    flex-wrap: wrap;
    padding-right: 14px;
    padding-left: 14px;
  }

  .workspace-memory-extraction-state .el-button {
    margin-left: 18px;
  }

  .qdl-summary-grid,
  .qdl-provenance-grid,
  .qdl-property-grid,
  .qdl-context-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .qdl-summary-grid > div + div,
  .qdl-provenance-grid > div + div,
  .qdl-summary-grid > div:nth-child(3),
  .qdl-provenance-grid > div:nth-child(3) {
    border-top: 1px solid #e4e4e7;
    border-left: 0;
  }

  .qdl-evidence-list article {
    flex-direction: column;
  }

  .qdl-entity-list > div,
  .qdl-relation-list > div {
    grid-template-columns: 58px minmax(0, 1fr);
  }

  .qdl-entity-list small,
  .qdl-relation-list small {
    grid-column: 2;
  }

  .workspace-action-create {
    grid-template-columns: minmax(0, 1fr);
    padding: 12px 14px;
  }

  .workspace-action-list {
    padding: 0 14px;
  }

  .workspace-action-list article {
    grid-template-columns: 24px minmax(0, 1fr);
  }

  .workspace-action-list article > :deep(.el-button) {
    grid-column: 2;
    justify-self: start;
  }

  .workspace-audit-list {
    padding: 0 14px;
  }

  .workspace-audit-list > button {
    grid-template-columns: minmax(0, 1fr);
    gap: 7px;
  }

  .workspace-audit-meta {
    grid-column: 1;
  }

  .meeting-page.is-workspace-focus .agent-sidecar,
  .meeting-page.is-workspace-focus .private-sidecar,
  .meeting-page.is-workspace-focus .context-pane {
    padding: 14px;
  }

  .meeting-page.is-workspace-focus .private-sidecar-roster .private-launcher-list {
    grid-template-columns: minmax(0, 1fr);
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
