import { defineStore } from "pinia";
import { computed, ref, shallowRef, watch } from "vue";
import axios from "axios";
import { meetingApi } from "@/api/meeting.api";
import { useAuthStore } from "@/stores/auth.store";
import type {
  MeetingActionItem,
  MeetingActionItemCreate,
  MeetingActionItemUpdate,
  MeetingAgentQueryAudit,
  MeetingAgentRunResponse,
  MeetingAgentRunRequest,
  MeetingAgentSubgraph,
  MeetingAttachment,
  MeetingBusinessContext,
  MeetingConflictEvent,
  MeetingContextPreview,
  MeetingDataDomain,
  MeetingMemory,
  MeetingMemoryConfirmPayload,
  MeetingMemoryDisputePayload,
  MeetingMemoryShareApproval,
  MeetingMemorySharePayload,
  MeetingMessage,
  MeetingQuoteSnapshot,
  MeetingRoom,
  MeetingRoomCreate,
  MeetingRoomAgent,
  MeetingRoomMember,
  MeetingStreamEvent,
} from "@/types/meeting.types";
import { normalizeAiResponseText } from "@/utils/ai-response";

export const useMeetingStore = defineStore("meeting", () => {
  const auth = useAuthStore();

  // ── State ──────────────────────────────────────────────────────

  const rooms = ref<MeetingRoom[]>([]);
  const messages = ref<MeetingMessage[]>([]);
  const agents = ref<MeetingRoomAgent[]>([]);
  const members = ref<MeetingRoomMember[]>([]);
  const memories = ref<MeetingMemory[]>([]);
  const actionItems = ref<MeetingActionItem[]>([]);
  const pendingAttachments = ref<MeetingAttachment[]>([]);
  const contextPreview = ref<MeetingContextPreview | null>(null);
  const agentQueryAudits = ref<MeetingAgentQueryAudit[]>([]);
  const conflictEvents = ref<MeetingConflictEvent[]>([]);
  const pendingMemoryShares = ref<MeetingMemoryShareApproval[]>([]);
  const activeRoomId = ref("");
  const eventSource = shallowRef<EventSource | null>(null);
  const streamConnected = ref(false);
  const streamingContent = ref<Record<string, string>>({});
  const loadingRooms = ref(false);
  const loadingMessages = ref(false);
  const sending = ref(false);
  const aiThinking = ref(false);
  const summarizing = ref(false);
  const generalAgentRunning = ref(false);
  const generalAgentWorkflowRunId = ref("");
  const generalAgentRunningQuery = ref("");
  const generalAgentRunningAttachments = ref<MeetingAttachment[]>([]);
  const cancelledGeneralAgentWorkflowIds = ref<Set<string>>(new Set());
  const memoryExtracting = ref(false);
  let memoryExtractionController: AbortController | null = null;
  let generalAgentController: AbortController | null = null;
  const loadingContext = ref(false);
  const actionItemSaving = ref(false);
  const attachmentUploading = ref(false);
  const availableAgentDefs = ref<Array<{
    id: string;
    name: string;
    system_prompt: string;
    model: string;
    adapter_type: string;
    participation_strategy: Record<string, unknown> | null;
    is_active: boolean;
  }>>([]);
  const messageReactions = ref<Record<string, "up" | "down">>({});
  let streamRequestId = 0;

  function unwrap<T>(payload: unknown): T {
    return ((payload as { data?: T }).data || payload) as T;
  }

  function normalizeMeetingMessage(message: MeetingMessage) {
    if (!["agent", "agent_streaming"].includes(message.message_type)) return message;
    const normalized = normalizeAiResponseText(message.content);
    if (normalized.content === message.content.trim() && !normalized.summary) return message;
    return {
      ...message,
      content: normalized.content,
      metadata_json: {
        ...(message.metadata_json || {}),
        ...(normalized.summary ? { summary: normalized.summary } : {}),
      },
    };
  }

  function upsertMessage(message: MeetingMessage) {
    const nextMessage = normalizeMeetingMessage(message);
    const index = messages.value.findIndex((m) => m.id === nextMessage.id);
    if (index >= 0) {
      messages.value = messages.value.map((m, i) => (i === index ? { ...m, ...nextMessage } : m));
    } else {
      messages.value = [...messages.value, nextMessage];
    }
    messages.value = [...messages.value].sort((a, b) => {
      if (a.seq_no !== b.seq_no) return a.seq_no - b.seq_no;
      return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
    });
  }

  function removePendingAgentMessage(agentId?: string | null, messageId?: string | null) {
    messages.value = messages.value.filter((message) => {
      if (message.message_type !== "agent_streaming") return true;
      if (messageId && message.id === messageId) return false;
      return agentId ? message.agent_id !== agentId : true;
    });
  }

  function removePendingAgentMessageByWorkflow(workflowRunId?: string | null) {
    const cleanId = String(workflowRunId || "").trim();
    if (!cleanId) return;
    messages.value = messages.value.filter((message) => {
      if (message.message_type !== "agent_streaming") return true;
      return String(message.metadata_json?.workflow_run_id || "") !== cleanId;
    });
  }

  function findLocalPendingAgentMessage(agentId?: string | null) {
    return messages.value.find((message) =>
      message.message_type === "agent_streaming"
      && message.agent_id === agentId
      && Boolean(message.metadata_json?.local_pending)
    );
  }

  function replaceMessageId(fromId: string, toId: string) {
    if (fromId === toId) return;
    messages.value = messages.value.map((message) => (
      message.id === fromId ? { ...message, id: toId } : message
    ));
  }

  function clearActiveRoomState() {
    pendingAttachments.value = [];
    messages.value = [];
    agents.value = [];
    members.value = [];
    memories.value = [];
    actionItems.value = [];
    contextPreview.value = null;
    agentQueryAudits.value = [];
    conflictEvents.value = [];
    pendingMemoryShares.value = [];
  }

  function isAgentReplyMessage(message: MeetingMessage) {
    return ["agent", "agent_streaming"].includes(message.message_type);
  }

  function hasAgentMention(message: MeetingMessage) {
    return Array.isArray(message.mentions)
      && message.mentions.some((mention) => Boolean(mention?.agent_id || mention?.agent_name));
  }

  function isAgentSideQuestion(message: MeetingMessage) {
    return message.message_type === "user"
      && hasAgentMention(message);
  }

  function privateRecipientUserId(message: MeetingMessage) {
    const directValue = message.private_recipient_user_id;
    if (typeof directValue === "string" && directValue.trim()) {
      return directValue.trim();
    }
    const metadataValue = message.metadata_json?.private_recipient_user_id;
    return typeof metadataValue === "string" && metadataValue.trim() ? metadataValue.trim() : "";
  }

  function isPublicConversationMessage(message: MeetingMessage) {
    return message.message_type === "user"
      && !privateRecipientUserId(message);
  }

  function isSystemPanelMessage(message: MeetingMessage) {
    return ["system", "summary", "action_item"].includes(message.message_type);
  }

  function currentUserId() {
    return String(auth.userId || "").trim();
  }

  function privateRecipientFromEvent(evt: MeetingStreamEvent) {
    const privateUserIds = "private_user_ids" in evt && Array.isArray(evt.private_user_ids) ? evt.private_user_ids : [];
    const selfId = currentUserId();
    if (selfId && privateUserIds.includes(selfId)) return selfId;
    return privateUserIds.length === 1 ? String(privateUserIds[0] || "").trim() : "";
  }

  function agentVisibilityMetadata(evt?: MeetingStreamEvent | null, fallback?: MeetingMessage | null) {
    const fallbackMetadata = fallback?.metadata_json || {};
    const eventVisibility = evt && "response_visibility" in evt ? String(evt.response_visibility || "") : "";
    const fallbackVisibility = typeof fallbackMetadata.visibility === "string" ? fallbackMetadata.visibility : "";
    const visibility = eventVisibility || fallbackVisibility || (evt && privateRecipientFromEvent(evt) ? "private" : "room");
    if (visibility === "private") {
      const privateRecipientId = (evt ? privateRecipientFromEvent(evt) : "") || (fallback ? privateRecipientUserId(fallback) : "") || currentUserId();
      return {
        visibility: "private",
        audience_scope_type: "user",
        audience_scope_id: privateRecipientId,
        private_recipient_user_id: privateRecipientId,
      };
    }
    return {
      visibility: "room",
      audience_scope_type: "meeting_room",
      audience_scope_id: activeRoomId.value,
    };
  }

  // ── Computed ───────────────────────────────────────────────────

  const activeRoom = computed(() => rooms.value.find((r) => r.id === activeRoomId.value) || null);
  const canSend = computed(() => Boolean(activeRoom.value && activeRoom.value.status === "active" && !sending.value && !attachmentUploading.value));
  const activeRoomMessages = computed(() => {
    const roomId = activeRoom.value?.id;
    if (!roomId) return [];
    return messages.value.filter((message) => message.room_id === roomId);
  });
  const conversationMessages = computed(() => activeRoomMessages.value.filter(isPublicConversationMessage));
  const agentPanelMessages = computed(() => activeRoomMessages.value.filter((message) => isAgentReplyMessage(message) || isAgentSideQuestion(message)));
  const systemPanelMessages = computed(() => activeRoomMessages.value.filter(isSystemPanelMessage));
  const candidateMemories = computed(() => memories.value.filter((item) => item.status === "candidate"));
  const confirmedMemories = computed(() => memories.value.filter((item) => ["confirmed", "active", "disputed", "superseded"].includes(item.status)));
  const openActionItems = computed(() => actionItems.value.filter((item) => item.status !== "done" && item.status !== "cancelled"));
  const canViewAgentQueryAudits = computed(() => {
    const room = activeRoom.value;
    const userId = currentUserId();
    if (!room || !userId) return false;
    if (room.created_by === userId) return true;
    return members.value.some((member) => member.user_id === userId && member.role === "host");
  });

  // ── Room Actions ───────────────────────────────────────────────

  async function loadRooms(selectLatest = false) {
    loadingRooms.value = true;
    try {
      const { data } = await meetingApi.listRooms(100);
      const list = unwrap<MeetingRoom[]>(data);
      rooms.value = list;
      if (selectLatest && list.length > 0) {
        activeRoomId.value = list[0].id;
      } else if (!activeRoomId.value && list.length > 0) {
        activeRoomId.value = list[0].id;
      } else if (activeRoomId.value && !list.some((r) => r.id === activeRoomId.value)) {
        activeRoomId.value = list[0]?.id || "";
      }
      if (!activeRoomId.value) {
        clearActiveRoomState();
      }
    } finally {
      loadingRooms.value = false;
    }
  }

  async function createRoom(title: string, password?: string | null, options?: Partial<MeetingRoomCreate>) {
    const { data } = await meetingApi.createRoom({
      title,
      password: password || null,
      visibility: options?.visibility || "private",
      allowed_data_domains: options?.allowed_data_domains || null,
    });
    const room = unwrap<MeetingRoom>(data);
    rooms.value = [room, ...rooms.value.filter((r) => r.id !== room.id)];
    activeRoomId.value = room.id;
    return room;
  }

  async function joinRoom(accessCode: string, password?: string | null) {
    const { data } = await meetingApi.joinRoom({ access_code: accessCode, password: password || null });
    const room = unwrap<MeetingRoom>(data);
    rooms.value = [room, ...rooms.value.filter((r) => r.id !== room.id)];
    activeRoomId.value = room.id;
    return room;
  }

  async function updateRoomTitle(title: string) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.updateRoom(activeRoom.value.id, { title });
    const room = unwrap<MeetingRoom>(data);
    rooms.value = rooms.value.map((item) => (item.id === room.id ? { ...item, ...room } : item));
    return room;
  }

  async function updateRoomSettings(payload: Partial<MeetingRoomCreate>) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.updateRoom(activeRoom.value.id, payload);
    const room = unwrap<MeetingRoom>(data);
    rooms.value = rooms.value.map((item) => (item.id === room.id ? { ...item, ...room } : item));
    await loadContextPreview();
    return room;
  }

  async function updateBusinessContext(payload: Partial<MeetingBusinessContext>) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.updateBusinessContext(activeRoom.value.id, payload);
    const context = unwrap<MeetingBusinessContext>(data);
    rooms.value = rooms.value.map((room) => (
      room.id === activeRoom.value?.id ? { ...room, business_context: context } : room
    ));
    if (contextPreview.value && contextPreview.value.room_id === activeRoom.value.id) {
      contextPreview.value = { ...contextPreview.value, business_context: context };
    }
    await loadContextPreview();
    return context;
  }

  async function closeRoom() {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.closeRoom(activeRoom.value.id);
    const room = unwrap<MeetingRoom>(data);
    rooms.value = rooms.value.map((item) => (item.id === room.id ? { ...item, ...room } : item));
    return room;
  }

  // ── Message Actions ────────────────────────────────────────────

  async function loadMessages(afterSeq = 0) {
    if (!activeRoom.value) {
      messages.value = [];
      return;
    }
    loadingMessages.value = afterSeq === 0;
    try {
      const { data } = await meetingApi.listMessages(activeRoom.value.id, afterSeq);
      const list = unwrap<MeetingMessage[]>(data);
      if (afterSeq > 0) {
        const seen = new Set(messages.value.map((m) => m.id));
        messages.value = [
          ...messages.value,
          ...list.filter((m) => !seen.has(m.id)).map((m) => normalizeMeetingMessage(m)),
        ];
      } else {
        messages.value = list.map((m) => normalizeMeetingMessage(m));
      }
    } finally {
      loadingMessages.value = false;
    }
  }

  watch(activeRoomId, () => {
    clearActiveRoomState();
  });

  async function uploadAttachments(files: File[]) {
    if (!activeRoom.value || files.length === 0) return [];
    attachmentUploading.value = true;
    try {
      const { data } = await meetingApi.uploadAttachments(activeRoom.value.id, files);
      const items = unwrap<{ items: MeetingAttachment[] }>(data).items || [];
      return items;
    } finally {
      attachmentUploading.value = false;
    }
  }

  async function uploadPendingAttachments(files: File[]) {
    const items = await uploadAttachments(files);
    pendingAttachments.value = [...pendingAttachments.value, ...items];
    return items;
  }

  function removePendingAttachment(id: string) {
    pendingAttachments.value = pendingAttachments.value.filter((item) => item.id !== id);
  }

  function clearPendingAttachments() {
    pendingAttachments.value = [];
  }

  async function sendMessage(
    content: string,
    quoteMessageId?: string | null,
    options?: { skipAgentTrigger?: boolean; attachments?: MeetingAttachment[]; privateRecipientUserId?: string | null; quoteSnapshot?: MeetingQuoteSnapshot | null },
  ) {
    if (!canSend.value || !activeRoom.value) return null;
    sending.value = true;
    try {
      const attachments = options?.attachments ?? pendingAttachments.value;
      const { data } = await meetingApi.sendMessage(activeRoom.value.id, content, quoteMessageId, {
        ...options,
        attachments,
      });
      const msg = unwrap<MeetingMessage>(data);
      upsertMessage(msg);
      if (attachments.length && !options?.privateRecipientUserId && !options?.skipAgentTrigger) {
        clearPendingAttachments();
      }
      return msg;
    } finally {
      sending.value = false;
    }
  }

  async function updateMessage(messageId: string, content: string) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.updateMessage(activeRoom.value.id, messageId, content);
    const msg = unwrap<MeetingMessage>(data);
    upsertMessage(msg);
    return msg;
  }

  async function recallMessage(messageId: string) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.recallMessage(activeRoom.value.id, messageId);
    const msg = unwrap<MeetingMessage>(data);
    upsertMessage(msg);
    return msg;
  }

  async function requestAiReply() {
    if (!activeRoom.value || aiThinking.value) return null;
    aiThinking.value = true;
    try {
      const { data } = await meetingApi.aiChat(activeRoom.value.id);
      const msg = unwrap<MeetingMessage>(data);
      upsertMessage(msg);
      return msg;
    } finally {
      aiThinking.value = false;
    }
  }

  async function summarizeMeeting() {
    if (!activeRoom.value || summarizing.value) return null;
    summarizing.value = true;
    try {
      const { data } = await meetingApi.summarize(activeRoom.value.id);
      const msg = unwrap<MeetingMessage>(data);
      upsertMessage(msg);
      return msg;
    } finally {
      summarizing.value = false;
    }
  }

  type GeneralAgentRunOptions = {
    attachments?: MeetingAttachment[];
    parentMessageId?: string;
    questionRevision?: string;
    replaceMessageId?: string;
  };

  function agentQuestionLinkMetadata(options?: GeneralAgentRunOptions) {
    const parentMessageId = String(options?.parentMessageId || "").trim();
    const questionRevision = String(options?.questionRevision || "").trim();
    return {
      ...(parentMessageId ? { question_message_id: parentMessageId } : {}),
      ...(questionRevision ? { question_revision: questionRevision } : {}),
    };
  }

  async function runGeneralAgent(mode: "auto" | MeetingAgentSubgraph = "auto", query = "", options?: GeneralAgentRunOptions) {
    const room = activeRoom.value;
    if (!room || generalAgentRunning.value) return null;
    const roomId = room.id;
    const workflowRunId = `general-agent-${roomId}-${Date.now()}`;
    const replaceMessageId = String(options?.replaceMessageId || "").trim();
    const pendingMessageId = replaceMessageId || `pending-${workflowRunId}`;
    const attachments = options?.attachments || [];
    const questionLinkMetadata = agentQuestionLinkMetadata(options);
    const controller = new AbortController();
    generalAgentController = controller;
    generalAgentWorkflowRunId.value = workflowRunId;
    generalAgentRunningQuery.value = query || generalAgentQuery(mode);
    generalAgentRunningAttachments.value = attachments;
    generalAgentRunning.value = true;
    try {
      const payload: MeetingAgentRunRequest = {
        query: generalAgentRunningQuery.value,
        mode,
        memory_scope: {
          include_meeting: true,
          include_confirmed: true,
          include_personal_authorized: false,
          include_user: false,
          include_agent: true,
          include_org_space: true,
        },
        attachments,
        workflow_run_id: workflowRunId,
        replace_message_id: replaceMessageId || undefined,
      };
      upsertMessage({
        id: pendingMessageId,
        room_id: roomId,
        user_id: "general_agent",
        username: "会议Agent",
        seq_no: messages.value.length + 1,
        content: "",
        message_type: "agent_streaming",
        agent_id: "general_agent",
        metadata_json: {
          local_pending: true,
          query: payload.query,
          workflow_run_id: workflowRunId,
          visibility: "room",
          audience_scope_type: "meeting_room",
          audience_scope_id: roomId,
          ...questionLinkMetadata,
          ...(attachments.length ? { attachment_echo: attachments } : {}),
        },
        created_at: new Date().toISOString(),
      } as MeetingMessage);
      const { data } = await meetingApi.runGeneralAgent(roomId, payload, { signal: controller.signal });
      const result = unwrap<MeetingAgentRunResponse>(data);
      if (cancelledGeneralAgentWorkflowIds.value.has(workflowRunId)) {
        if (activeRoomId.value === roomId) removePendingAgentMessage("general_agent", pendingMessageId);
        return null;
      }
      if (result.message?.metadata_json?.cancelled) {
        if (activeRoomId.value === roomId) removePendingAgentMessage("general_agent", pendingMessageId);
        return result;
      }
      if (activeRoomId.value === roomId) {
        removePendingAgentMessage("general_agent", pendingMessageId);
        upsertMessage({
          ...result.message,
          metadata_json: {
            ...(result.message?.metadata_json || {}),
            ...questionLinkMetadata,
          },
        });
        await loadMeetingContext();
      }
      return result;
    } catch (error) {
      if (activeRoomId.value === roomId) {
        removePendingAgentMessage("general_agent", pendingMessageId);
      }
      if (axios.isCancel(error) || (error as { name?: string })?.name === "CanceledError") {
        return null;
      }
      throw error;
    } finally {
      if (generalAgentWorkflowRunId.value === workflowRunId) {
        generalAgentRunning.value = false;
        generalAgentWorkflowRunId.value = "";
        generalAgentController = null;
        generalAgentRunningQuery.value = "";
        generalAgentRunningAttachments.value = [];
      }
    }
  }

  async function cancelGeneralAgentRun() {
    const room = activeRoom.value;
    const workflowRunId = generalAgentWorkflowRunId.value;
    if (!room || !workflowRunId) return false;
    const restore = {
      question: generalAgentRunningQuery.value,
      attachments: [...generalAgentRunningAttachments.value],
    };
    cancelledGeneralAgentWorkflowIds.value = new Set([...cancelledGeneralAgentWorkflowIds.value, workflowRunId]);
    removePendingAgentMessage("general_agent");
    removePendingAgentMessageByWorkflow(workflowRunId);
    generalAgentRunning.value = false;
    generalAgentWorkflowRunId.value = "";
    generalAgentRunningQuery.value = "";
    generalAgentRunningAttachments.value = [];
    try {
      await meetingApi.cancelGeneralAgent(room.id, workflowRunId);
    } catch {
      // The request may already be gone locally; the server cancel is best-effort.
    }
    generalAgentController?.abort();
    generalAgentController = null;
    return restore;
  }

  function generalAgentQuery(mode: "auto" | MeetingAgentSubgraph) {
    const map: Record<string, string> = {
      auto: "请根据当前会议上下文判断需要调用的能力，并给出可追溯回答。",
      meeting_summary: "请总结本次会议，提取关键结论和可沉淀记忆。",
      memory_transfer: "请从本次会议中提取候选记忆，等待人工确认后进入本会议的已确认记忆。",
      action_items: "请从本次会议中提取会议待办线索。",
      risk_forecast: "请基于会议上下文和已确认记忆，预测后续检测风险。",
      evidence_query: "请基于会议上下文查询或整理检测证据线索。",
      standard_explain: "请基于会议上下文解释相关标准和判定依据。",
    };
    return map[mode] || map.auto;
  }

  async function loadMeetingContext() {
    const room = activeRoom.value;
    if (!room) {
      memories.value = [];
      actionItems.value = [];
      contextPreview.value = null;
      agentQueryAudits.value = [];
      conflictEvents.value = [];
      pendingMemoryShares.value = [];
      return;
    }
    loadingContext.value = true;
    try {
      const [memoryResp, actionResp, previewResp, conflictsResp, sharesResp] = await Promise.all([
        meetingApi.listMemories(room.id),
        meetingApi.listActionItems(room.id),
        meetingApi.getContextPreview(room.id).catch(() => null),
        meetingApi.listConflicts(room.id).catch(() => null),
        meetingApi.listPendingMemoryShares(room.id).catch(() => null),
      ]);
      if (activeRoomId.value !== room.id) return;
      memories.value = unwrap<MeetingMemory[]>(memoryResp.data);
      actionItems.value = unwrap<MeetingActionItem[]>(actionResp.data);
      contextPreview.value = previewResp ? unwrap<MeetingContextPreview>(previewResp.data) : null;
      conflictEvents.value = conflictsResp ? unwrap<MeetingConflictEvent[]>(conflictsResp.data) : [];
      pendingMemoryShares.value = sharesResp ? unwrap<MeetingMemoryShareApproval[]>(sharesResp.data) : [];
      if (canViewAgentQueryAudits.value) {
        await loadAgentQueryAudits();
      } else {
        agentQueryAudits.value = [];
      }
    } finally {
      loadingContext.value = false;
    }
  }

  async function loadContextPreview() {
    if (!activeRoom.value) {
      contextPreview.value = null;
      return null;
    }
    try {
      const { data } = await meetingApi.getContextPreview(activeRoom.value.id);
      contextPreview.value = unwrap<MeetingContextPreview>(data);
      return contextPreview.value;
    } catch {
      contextPreview.value = null;
      return null;
    }
  }

  async function loadAgentQueryAudits(limit = 20) {
    const room = activeRoom.value;
    if (!room || !canViewAgentQueryAudits.value) {
      agentQueryAudits.value = [];
      return [];
    }
    try {
      const { data } = await meetingApi.listAgentQueryAudits(room.id, limit);
      const audits = unwrap<MeetingAgentQueryAudit[]>(data);
      if (activeRoomId.value !== room.id) return agentQueryAudits.value;
      agentQueryAudits.value = audits;
      return agentQueryAudits.value;
    } catch {
      agentQueryAudits.value = [];
      return [];
    }
  }

  async function loadConflicts(limit = 50) {
    if (!activeRoom.value) {
      conflictEvents.value = [];
      return [];
    }
    try {
      const { data } = await meetingApi.listConflicts(activeRoom.value.id, limit);
      conflictEvents.value = unwrap<MeetingConflictEvent[]>(data);
      return conflictEvents.value;
    } catch {
      conflictEvents.value = [];
      return [];
    }
  }

  async function resolveConflict(conflictId: string, selectedAction: "approve" | "queue" | "reject" | "candidate_only") {
    const { data } = await meetingApi.resolveConflict(conflictId, selectedAction);
    const conflict = unwrap<MeetingConflictEvent>(data);
    conflictEvents.value = conflictEvents.value.map((item) => (item.id === conflict.id ? conflict : item));
    if (!conflictEvents.value.some((item) => item.id === conflict.id)) {
      conflictEvents.value = [conflict, ...conflictEvents.value];
    }
    return conflict;
  }

  async function loadPendingMemoryShares() {
    if (!activeRoom.value) {
      pendingMemoryShares.value = [];
      return [];
    }
    try {
      const { data } = await meetingApi.listPendingMemoryShares(activeRoom.value.id);
      pendingMemoryShares.value = unwrap<MeetingMemoryShareApproval[]>(data);
      return pendingMemoryShares.value;
    } catch {
      pendingMemoryShares.value = [];
      return [];
    }
  }

  async function approveMemoryShare(transferId: string) {
    const { data } = await meetingApi.approveMemoryShare(transferId);
    const memory = unwrap<MeetingMemory>(data);
    pendingMemoryShares.value = pendingMemoryShares.value.filter((item) => item.id !== transferId);
    memories.value = [memory, ...memories.value.filter((item) => item.memory_id !== memory.memory_id)];
    if (activeRoom.value) {
      await Promise.all([loadMeetingContext(), loadMessages(0)]);
    }
    return memory;
  }

  async function rejectMemoryShare(transferId: string) {
    const { data } = await meetingApi.rejectMemoryShare(transferId);
    const share = unwrap<MeetingMemoryShareApproval>(data);
    pendingMemoryShares.value = pendingMemoryShares.value
      .map((item) => (item.id === share.id ? share : item))
      .filter((item) => item.status === "pending_approval");
    return share;
  }

  async function extractMemories(topic = "") {
    if (!activeRoom.value || memoryExtracting.value) return [];
    memoryExtractionController = new AbortController();
    memoryExtracting.value = true;
    try {
      const { data } = await meetingApi.extractMemories(
        activeRoom.value.id,
        { topic, max_items: 3 },
        { signal: memoryExtractionController.signal },
      );
      const list = unwrap<MeetingMemory[]>(data);
      await loadMeetingContext();
      return list;
    } catch (error) {
      if (axios.isCancel(error) || (error instanceof Error && error.name === "CanceledError")) {
        return [];
      }
      throw error;
    } finally {
      memoryExtractionController = null;
      memoryExtracting.value = false;
    }
  }

  function cancelMemoryExtraction() {
    memoryExtractionController?.abort();
    memoryExtractionController = null;
    memoryExtracting.value = false;
  }

  async function confirmMemory(memoryId: string, payload?: MeetingMemoryConfirmPayload) {
    const { data } = await meetingApi.confirmMemory(memoryId, payload || {});
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    if (!memories.value.some((item) => item.memory_id === memory.memory_id)) {
      memories.value = [memory, ...memories.value];
    }
    if (activeRoom.value) {
      await Promise.all([loadMeetingContext(), loadMessages(0)]);
    }
    return memory;
  }

  async function rejectMemory(memoryId: string, reason = "") {
    const { data } = await meetingApi.rejectMemory(memoryId, { content: reason || null });
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    if (activeRoom.value) {
      await Promise.all([loadMeetingContext(), loadMessages(0)]);
    }
    return memory;
  }

  async function disputeMemory(memoryId: string, payload: MeetingMemoryDisputePayload) {
    const { data } = await meetingApi.disputeMemory(memoryId, payload);
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    if (!memories.value.some((item) => item.memory_id === memory.memory_id)) {
      memories.value = [memory, ...memories.value];
    }
    if (activeRoom.value) {
      await Promise.all([loadMeetingContext(), loadMessages(0)]);
    }
    return memory;
  }

  async function shareMemory(memoryId: string, payload: MeetingMemorySharePayload) {
    const { data } = await meetingApi.shareMemory(memoryId, payload);
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    if (!memories.value.some((item) => item.memory_id === memory.memory_id)) {
      memories.value = [memory, ...memories.value];
    }
    if (activeRoom.value) {
      await Promise.all([loadMeetingContext(), loadMessages(0)]);
    }
    return memory;
  }

  async function createActionItem(payload: MeetingActionItemCreate) {
    if (!activeRoom.value) return null;
    actionItemSaving.value = true;
    try {
      const { data } = await meetingApi.createActionItem(activeRoom.value.id, payload);
      const item = unwrap<MeetingActionItem>(data);
      actionItems.value = [item, ...actionItems.value.filter((row) => row.id !== item.id)];
      await loadMessages(0);
      return item;
    } finally {
      actionItemSaving.value = false;
    }
  }

  async function updateActionItem(actionItemId: string, payload: MeetingActionItemUpdate) {
    const { data } = await meetingApi.updateActionItem(actionItemId, payload);
    const item = unwrap<MeetingActionItem>(data);
    actionItems.value = actionItems.value.map((row) => (row.id === item.id ? item : row));
    return item;
  }

  async function completeActionItem(actionItemId: string) {
    const { data } = await meetingApi.completeActionItem(actionItemId);
    const item = unwrap<MeetingActionItem>(data);
    actionItems.value = actionItems.value.map((row) => (row.id === item.id ? item : row));
    if (activeRoom.value) {
      await loadMessages(0);
    }
    return item;
  }

  // ── Agent Actions ──────────────────────────────────────────────

  async function loadAgents() {
    if (!activeRoom.value) {
      agents.value = [];
      return;
    }
    try {
      const { data } = await meetingApi.listAgents(activeRoom.value.id);
      agents.value = unwrap<MeetingRoomAgent[]>(data);
    } catch {
      agents.value = [];
    }
  }

  async function loadMembers() {
    if (!activeRoom.value) {
      members.value = [];
      return;
    }
    try {
      const { data } = await meetingApi.listMembers(activeRoom.value.id);
      members.value = unwrap<MeetingRoomMember[]>(data);
    } catch {
      members.value = [];
    }
  }

  async function updateMemberRole(memberUserId: string, role: "host" | "member") {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.updateMemberRole(activeRoom.value.id, memberUserId, { role });
    const member = unwrap<MeetingRoomMember>(data);
    members.value = members.value.map((item) => (item.user_id === member.user_id ? member : item));
    return member;
  }

  async function deleteRoom(roomId = activeRoom.value?.id || "") {
    if (!roomId) return;
    const deletedActiveRoom = roomId === activeRoomId.value;
    await meetingApi.deleteRoom(roomId);
    removeRoomLocally(roomId, deletedActiveRoom);
  }

  async function leaveRoom(roomId = activeRoom.value?.id || "") {
    if (!roomId) return;
    const leftActiveRoom = roomId === activeRoomId.value;
    await meetingApi.leaveRoom(roomId);
    removeRoomLocally(roomId, leftActiveRoom);
  }

  function removeRoomLocally(roomId: string, clearActiveRoom: boolean) {
    rooms.value = rooms.value.filter((r) => r.id !== roomId);
    if (clearActiveRoom) {
      activeRoomId.value = rooms.value[0]?.id || "";
      messages.value = [];
      agents.value = [];
      members.value = [];
      memories.value = [];
      actionItems.value = [];
      contextPreview.value = null;
      agentQueryAudits.value = [];
    }
  }

  async function loadAvailableAgentDefs() {
    try {
      const { data } = await meetingApi.listAgentDefs();
      availableAgentDefs.value = unwrap<typeof availableAgentDefs.value>(data);
    } catch {
      availableAgentDefs.value = [];
    }
  }

  async function addAgentToRoom(
    agentDefId: string,
    role = "participant",
    allowedDomains?: MeetingDataDomain[] | null,
    allowedTools?: string[] | null
  ) {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.addAgent(activeRoom.value.id, {
      agent_id: agentDefId,
      role,
      allowed_domains: allowedDomains || null,
      allowed_tools: allowedTools || null,
    });
    const agent = unwrap<MeetingRoomAgent>(data);
    agents.value = [...agents.value, agent];
    await loadContextPreview();
    return agent;
  }

  async function removeAgentFromRoom(agentId: string) {
    if (!activeRoom.value) return;
    await meetingApi.removeAgent(activeRoom.value.id, agentId);
    agents.value = agents.value.filter((a) => a.agent_id !== agentId);
    await loadContextPreview();
  }

  // ── SSE Stream ─────────────────────────────────────────────────

  function connectStream() {
    disconnectStream();
    if (!activeRoom.value) return;
    const requestId = ++streamRequestId;

    meetingApi.stream(activeRoom.value.id, handleStreamEvent, (status) => {
      if (requestId !== streamRequestId) return;
      streamConnected.value = status === "open";
      void loadMessages(lastMessageSeq.value);
    }).then((source) => {
      if (requestId !== streamRequestId) {
        source.close();
        return;
      }
      eventSource.value = source;
    }).catch(() => {
      if (requestId !== streamRequestId) return;
      streamConnected.value = false;
    });
  }

  function disconnectStream() {
    streamRequestId += 1;
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    streamConnected.value = false;
    streamingContent.value = {};
  }

  function handleStreamEvent(evt: MeetingStreamEvent) {
    switch (evt.event) {
      case "message_created": {
        const workflowRunId = String(evt.message.metadata_json?.workflow_run_id || "");
        if (workflowRunId && cancelledGeneralAgentWorkflowIds.value.has(workflowRunId)) break;
        if (evt.message.message_type === "agent" && evt.message.agent_id) {
          removePendingAgentMessage(evt.message.agent_id);
        }
        upsertMessage(evt.message);
        loadRooms();
        if (evt.message.agent_id === "general_agent" || evt.message.message_type === "system") {
          loadMeetingContext();
        }
        break;
      }
      case "agent_run_started": {
        if (cancelledGeneralAgentWorkflowIds.value.has(evt.workflow_run_id)) break;
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: "" };
        const localPending = findLocalPendingAgentMessage(evt.agent_id);
        if (localPending) {
          replaceMessageId(localPending.id, evt.message_id);
        }
        upsertMessage({
          id: evt.message_id,
          room_id: activeRoomId.value,
          user_id: evt.agent_id,
          username: evt.agent_name,
          seq_no: messages.value.length + 1,
          content: "",
          message_type: "agent_streaming",
          agent_id: evt.agent_id,
          metadata_json: {
            ...(localPending?.metadata_json || {}),
            local_pending: false,
            workflow_run_id: evt.workflow_run_id,
            query: evt.query || localPending?.metadata_json?.query,
            ...agentVisibilityMetadata(evt, localPending),
          },
          created_at: new Date().toISOString(),
        } as MeetingMessage);
        break;
      }
      case "message_delta": {
        if (cancelledGeneralAgentWorkflowIds.value.has(evt.workflow_run_id)) break;
        const current = streamingContent.value[evt.message_id] || "";
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: current + evt.delta };
        break;
      }
      case "message_final": {
        if (cancelledGeneralAgentWorkflowIds.value.has(evt.workflow_run_id)) {
          removePendingAgentMessage(null, evt.message_id);
          removePendingAgentMessageByWorkflow(evt.workflow_run_id);
          break;
        }
        const normalized = normalizeAiResponseText(evt.content);
        const content = normalized.content;
        const existing = messages.value.find((m) =>
          m.id === evt.message_id
          || (m.message_type === "agent_streaming" && m.agent_id === evt.agent_id && m.content === "")
        );
        if (existing) {
          existing.content = content;
          existing.metadata_json = {
            ...(existing.metadata_json || {}),
            ...agentVisibilityMetadata(evt, existing),
            ...(normalized.summary ? { summary: normalized.summary } : {}),
          };
          existing.message_type = "agent" as never;
        } else {
          upsertMessage({
            id: evt.message_id,
            room_id: activeRoomId.value,
            user_id: evt.agent_id,
            username: (evt as { agent_name?: string }).agent_name || evt.agent_id.slice(-8),
            seq_no: messages.value.length + 1,
            content,
            message_type: "agent",
            agent_id: evt.agent_id,
            metadata_json: {
              ...agentVisibilityMetadata(evt),
              ...(normalized.summary ? { summary: normalized.summary } : {}),
            },
            created_at: new Date().toISOString(),
          } as MeetingMessage);
        }
        const next = { ...streamingContent.value };
        delete next[evt.message_id];
        streamingContent.value = next;
        removePendingAgentMessage(null, evt.message_id);
        break;
      }
      case "agent_run_failed": {
        const next = { ...streamingContent.value };
        delete next[evt.message_id];
        streamingContent.value = next;
        removePendingAgentMessage(null, evt.message_id);
        removePendingAgentMessageByWorkflow(evt.workflow_run_id);
        if (evt.error === "会议Agent回复已停止") {
          if (generalAgentWorkflowRunId.value === evt.workflow_run_id) {
            generalAgentRunning.value = false;
            generalAgentWorkflowRunId.value = "";
            generalAgentController = null;
          }
          break;
        }
        const errMsg = `[${evt.agent_name}] 响应失败: ${evt.error}`;
        upsertMessage({
          id: evt.message_id,
          room_id: activeRoomId.value,
          user_id: evt.agent_id,
          username: evt.agent_name,
          seq_no: messages.value.length + 1,
          content: errMsg,
          message_type: "agent",
          agent_id: evt.agent_id,
          metadata_json: agentVisibilityMetadata(evt),
          created_at: new Date().toISOString(),
        } as MeetingMessage);
        break;
      }
    }
  }

  // ── Feedback (pass-through for MessageActionBar) ───────────────

  function setReaction(messageId: string, type: "up" | "down" | "") {
    if (type) {
      messageReactions.value = { ...messageReactions.value, [messageId]: type };
    } else {
      const next = { ...messageReactions.value };
      delete next[messageId];
      messageReactions.value = next;
    }
  }

  const lastMessageSeq = computed(() => {
    const last = activeRoomMessages.value[activeRoomMessages.value.length - 1];
    return last?.seq_no || 0;
  });

  return {
    // state
    rooms, messages, agents, members, activeRoomId, eventSource, streamConnected,
    streamingContent, loadingRooms, loadingMessages, sending, messageReactions, aiThinking, summarizing,
    generalAgentRunning, generalAgentWorkflowRunId, memoryExtracting, loadingContext, actionItemSaving, attachmentUploading,
    memories, actionItems, pendingAttachments, contextPreview, agentQueryAudits, conflictEvents, pendingMemoryShares,
    // computed
    activeRoom, canSend, activeRoomMessages, conversationMessages, agentPanelMessages, systemPanelMessages, lastMessageSeq, candidateMemories, confirmedMemories, openActionItems, canViewAgentQueryAudits,
    // actions
    loadRooms, createRoom, joinRoom, updateRoomTitle, updateRoomSettings, updateBusinessContext, closeRoom,
    loadMessages, sendMessage, updateMessage, recallMessage, uploadAttachments, uploadPendingAttachments, removePendingAttachment, clearPendingAttachments,
    requestAiReply, summarizeMeeting, runGeneralAgent, loadMeetingContext, loadContextPreview, loadAgentQueryAudits, extractMemories,
    loadConflicts, resolveConflict, loadPendingMemoryShares, approveMemoryShare, rejectMemoryShare,
    cancelMemoryExtraction, cancelGeneralAgentRun,
    confirmMemory, rejectMemory, disputeMemory, shareMemory,
    createActionItem, updateActionItem, completeActionItem,
    loadAgents, loadMembers, updateMemberRole, deleteRoom,
    leaveRoom,
    availableAgentDefs, loadAvailableAgentDefs, addAgentToRoom, removeAgentFromRoom,
    connectStream, disconnectStream, handleStreamEvent,
    setReaction,
  };
});
