import { defineStore } from "pinia";
import { computed, ref, shallowRef } from "vue";
import { meetingApi } from "@/api/meeting.api";
import type {
  MeetingActionItem,
  MeetingActionItemCreate,
  MeetingActionItemUpdate,
  MeetingAgentQueryAudit,
  MeetingAgentRunResponse,
  MeetingAgentRunRequest,
  MeetingAgentSubgraph,
  MeetingContextPreview,
  MeetingDataDomain,
  MeetingMemory,
  MeetingMessage,
  MeetingRoom,
  MeetingRoomCreate,
  MeetingRoomAgent,
  MeetingRoomMember,
  MeetingStreamEvent,
} from "@/types/meeting.types";
import { normalizeAiResponseText } from "@/utils/ai-response";

export const useMeetingStore = defineStore("meeting", () => {

  // ── State ──────────────────────────────────────────────────────

  const rooms = ref<MeetingRoom[]>([]);
  const messages = ref<MeetingMessage[]>([]);
  const agents = ref<MeetingRoomAgent[]>([]);
  const members = ref<MeetingRoomMember[]>([]);
  const memories = ref<MeetingMemory[]>([]);
  const actionItems = ref<MeetingActionItem[]>([]);
  const contextPreview = ref<MeetingContextPreview | null>(null);
  const agentQueryAudits = ref<MeetingAgentQueryAudit[]>([]);
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
  const memoryExtracting = ref(false);
  const loadingContext = ref(false);
  const actionItemSaving = ref(false);
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

  // ── Computed ───────────────────────────────────────────────────

  const activeRoom = computed(() => rooms.value.find((r) => r.id === activeRoomId.value) || null);
  const canSend = computed(() => Boolean(activeRoom.value && activeRoom.value.status === "active" && !sending.value));
  const candidateMemories = computed(() => memories.value.filter((item) => item.status === "candidate"));
  const confirmedMemories = computed(() => memories.value.filter((item) => item.status === "active"));
  const openActionItems = computed(() => actionItems.value.filter((item) => item.status !== "done" && item.status !== "cancelled"));

  // ── Room Actions ───────────────────────────────────────────────

  async function loadRooms(selectLatest = false) {
    loadingRooms.value = true;
    try {
      const { data } = await meetingApi.listRooms();
      const list = unwrap<MeetingRoom[]>(data);
      rooms.value = list;
      if (selectLatest && list.length > 0) {
        activeRoomId.value = list[0].id;
      } else if (!activeRoomId.value && list.length > 0) {
        activeRoomId.value = list[0].id;
      } else if (activeRoomId.value && !list.some((r) => r.id === activeRoomId.value)) {
        activeRoomId.value = list[0]?.id || "";
      }
    } finally {
      loadingRooms.value = false;
    }
  }

  async function createRoom(title: string, password?: string | null, options?: Partial<MeetingRoomCreate>) {
    const { data } = await meetingApi.createRoom({
      title,
      password: password || null,
      room_type: options?.room_type || "quality_business",
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

  async function closeRoom() {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.closeRoom(activeRoom.value.id);
    const room = unwrap<MeetingRoom>(data);
    rooms.value = rooms.value.map((item) => (item.id === room.id ? { ...item, ...room } : item));
    return room;
  }

  async function archiveRoom() {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.archiveRoom(activeRoom.value.id);
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

  async function sendMessage(content: string, quoteMessageId?: string | null, options?: { skipAgentTrigger?: boolean }) {
    if (!canSend.value || !activeRoom.value) return null;
    sending.value = true;
    try {
      const { data } = await meetingApi.sendMessage(activeRoom.value.id, content, quoteMessageId, options);
      const msg = unwrap<MeetingMessage>(data);
      upsertMessage(msg);
      return msg;
    } finally {
      sending.value = false;
    }
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

  async function runGeneralAgent(mode: "auto" | MeetingAgentSubgraph = "auto", query = "") {
    if (!activeRoom.value || generalAgentRunning.value) return null;
    generalAgentRunning.value = true;
    try {
      const payload: MeetingAgentRunRequest = {
        query: query || generalAgentQuery(mode),
        mode,
        memory_scope: {
          include_meeting: true,
          include_project_shared: true,
          include_personal_authorized: false,
        },
      };
      const { data } = await meetingApi.runGeneralAgent(activeRoom.value.id, payload);
      const result = unwrap<MeetingAgentRunResponse>(data);
      upsertMessage(result.message);
      await loadMeetingContext();
      return result;
    } finally {
      generalAgentRunning.value = false;
    }
  }

  function generalAgentQuery(mode: "auto" | MeetingAgentSubgraph) {
    const map: Record<string, string> = {
      auto: "请根据当前会议上下文判断需要调用的能力，并给出可追溯回答。",
      meeting_summary: "请总结本次会议，提取关键结论和可沉淀记忆。",
      memory_transfer: "请从本次会议中提取候选记忆，等待人工确认后再共享。",
      action_items: "请从本次会议中提取会议待办线索。",
      risk_forecast: "请基于会议上下文和已确认共享记忆，预测后续检测风险。",
      evidence_query: "请基于会议上下文查询或整理检测证据线索。",
      standard_explain: "请基于会议上下文解释相关标准和判定依据。",
    };
    return map[mode] || map.auto;
  }

  async function loadMeetingContext() {
    if (!activeRoom.value) {
      memories.value = [];
      actionItems.value = [];
      contextPreview.value = null;
      agentQueryAudits.value = [];
      return;
    }
    loadingContext.value = true;
    try {
      const [memoryResp, actionResp, previewResp] = await Promise.all([
        meetingApi.listMemories(activeRoom.value.id),
        meetingApi.listActionItems(activeRoom.value.id),
        meetingApi.getContextPreview(activeRoom.value.id).catch(() => null),
      ]);
      memories.value = unwrap<MeetingMemory[]>(memoryResp.data);
      actionItems.value = unwrap<MeetingActionItem[]>(actionResp.data);
      contextPreview.value = previewResp ? unwrap<MeetingContextPreview>(previewResp.data) : null;
      await loadAgentQueryAudits();
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
    if (!activeRoom.value) {
      agentQueryAudits.value = [];
      return [];
    }
    try {
      const { data } = await meetingApi.listAgentQueryAudits(activeRoom.value.id, limit);
      agentQueryAudits.value = unwrap<MeetingAgentQueryAudit[]>(data);
      return agentQueryAudits.value;
    } catch {
      agentQueryAudits.value = [];
      return [];
    }
  }

  async function extractMemories(topic = "") {
    if (!activeRoom.value || memoryExtracting.value) return [];
    memoryExtracting.value = true;
    try {
      const { data } = await meetingApi.extractMemories(activeRoom.value.id, { topic, max_items: 3 });
      const list = unwrap<MeetingMemory[]>(data);
      await loadMeetingContext();
      return list;
    } finally {
      memoryExtracting.value = false;
    }
  }

  async function confirmMemory(memoryId: string, payload?: { title?: string | null; content?: string | null }) {
    const { data } = await meetingApi.confirmMemory(memoryId, { ...(payload || {}), scope: "project_shared" });
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    if (!memories.value.some((item) => item.memory_id === memory.memory_id)) {
      memories.value = [memory, ...memories.value];
    }
    return memory;
  }

  async function rejectMemory(memoryId: string) {
    const { data } = await meetingApi.rejectMemory(memoryId);
    const memory = unwrap<MeetingMemory>(data);
    memories.value = memories.value.map((item) => (item.memory_id === memory.memory_id ? memory : item));
    return memory;
  }

  async function createActionItem(payload: MeetingActionItemCreate) {
    if (!activeRoom.value) return null;
    actionItemSaving.value = true;
    try {
      const { data } = await meetingApi.createActionItem(activeRoom.value.id, payload);
      const item = unwrap<MeetingActionItem>(data);
      actionItems.value = [item, ...actionItems.value.filter((row) => row.id !== item.id)];
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
    rooms.value = rooms.value.filter((r) => r.id !== roomId);
    if (deletedActiveRoom) {
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

    meetingApi.stream(activeRoom.value.id, handleStreamEvent).then((source) => {
      if (requestId !== streamRequestId) {
        source.close();
        return;
      }
      eventSource.value = source;
      streamConnected.value = true;
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
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: "" };
        upsertMessage({
          id: evt.message_id,
          room_id: activeRoomId.value,
          user_id: evt.agent_id,
          username: evt.agent_name,
          seq_no: messages.value.length + 1,
          content: "",
          message_type: "agent_streaming",
          agent_id: evt.agent_id,
          metadata_json: { workflow_run_id: evt.workflow_run_id },
          created_at: new Date().toISOString(),
        } as MeetingMessage);
        break;
      }
      case "message_delta": {
        const current = streamingContent.value[evt.message_id] || "";
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: current + evt.delta };
        break;
      }
      case "message_final": {
        const normalized = normalizeAiResponseText(evt.content);
        const content = normalized.content;
        const existing = messages.value.find((m) => m.message_type === "agent_streaming" && m.agent_id === evt.agent_id && m.content === "");
        if (existing) {
          existing.content = content;
          existing.metadata_json = {
            ...(existing.metadata_json || {}),
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
            metadata_json: normalized.summary ? { summary: normalized.summary } : null,
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
    const last = messages.value[messages.value.length - 1];
    return last?.seq_no || 0;
  });

  return {
    // state
    rooms, messages, agents, members, activeRoomId, eventSource, streamConnected,
    streamingContent, loadingRooms, loadingMessages, sending, messageReactions, aiThinking, summarizing,
    generalAgentRunning, memoryExtracting, loadingContext, actionItemSaving,
    memories, actionItems, contextPreview, agentQueryAudits,
    // computed
    activeRoom, canSend, lastMessageSeq, candidateMemories, confirmedMemories, openActionItems,
    // actions
    loadRooms, createRoom, joinRoom, updateRoomTitle, updateRoomSettings, closeRoom, archiveRoom,
    loadMessages, sendMessage,
    requestAiReply, summarizeMeeting, runGeneralAgent, loadMeetingContext, loadContextPreview, loadAgentQueryAudits, extractMemories,
    confirmMemory, rejectMemory,
    createActionItem, updateActionItem, completeActionItem,
    loadAgents, loadMembers, updateMemberRole, deleteRoom,
    availableAgentDefs, loadAvailableAgentDefs, addAgentToRoom, removeAgentFromRoom,
    connectStream, disconnectStream, handleStreamEvent,
    setReaction,
  };
});
