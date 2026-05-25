import { defineStore } from "pinia";
import { computed, ref, shallowRef } from "vue";
import { meetingApi } from "@/api/meeting.api";
import type {
  MeetingMessage,
  MeetingRoom,
  MeetingRoomAgent,
  MeetingRoomMember,
  MeetingStreamEvent,
} from "@/types/meeting.types";

export const useMeetingStore = defineStore("meeting", () => {

  // ── State ──────────────────────────────────────────────────────

  const rooms = ref<MeetingRoom[]>([]);
  const messages = ref<MeetingMessage[]>([]);
  const agents = ref<MeetingRoomAgent[]>([]);
  const members = ref<MeetingRoomMember[]>([]);
  const activeRoomId = ref("");
  const eventSource = shallowRef<EventSource | null>(null);
  const streamConnected = ref(false);
  const streamingContent = ref<Record<string, string>>({});
  const loadingRooms = ref(false);
  const loadingMessages = ref(false);
  const sending = ref(false);
  const aiThinking = ref(false);
  const summarizing = ref(false);
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

  function upsertMessage(message: MeetingMessage) {
    const index = messages.value.findIndex((m) => m.id === message.id);
    if (index >= 0) {
      messages.value = messages.value.map((m, i) => (i === index ? { ...m, ...message } : m));
    } else {
      messages.value = [...messages.value, message];
    }
    messages.value = [...messages.value].sort((a, b) => {
      if (a.seq_no !== b.seq_no) return a.seq_no - b.seq_no;
      return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
    });
  }

  // ── Computed ───────────────────────────────────────────────────

  const activeRoom = computed(() => rooms.value.find((r) => r.id === activeRoomId.value) || null);
  const canSend = computed(() => Boolean(activeRoom.value && !sending.value));

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

  async function createRoom(title: string, password?: string | null) {
    const { data } = await meetingApi.createRoom({ title, password: password || null });
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
        messages.value = [...messages.value, ...list.filter((m) => !seen.has(m.id))];
      } else {
        messages.value = list;
      }
    } finally {
      loadingMessages.value = false;
    }
  }

  async function sendMessage(content: string) {
    if (!canSend.value || !activeRoom.value) return null;
    sending.value = true;
    try {
      const { data } = await meetingApi.sendMessage(activeRoom.value.id, content);
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

  async function deleteRoom() {
    if (!activeRoom.value) return;
    await meetingApi.deleteRoom(activeRoom.value.id);
    rooms.value = rooms.value.filter((r) => r.id !== activeRoomId.value);
    activeRoomId.value = rooms.value[0]?.id || "";
    messages.value = [];
    agents.value = [];
    members.value = [];
  }

  async function loadAvailableAgentDefs() {
    try {
      const { data } = await meetingApi.listAgentDefs();
      availableAgentDefs.value = unwrap<typeof availableAgentDefs.value>(data);
    } catch {
      availableAgentDefs.value = [];
    }
  }

  async function addAgentToRoom(agentDefId: string, role = "participant") {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.addAgent(activeRoom.value.id, { agent_id: agentDefId, role });
    const agent = unwrap<MeetingRoomAgent>(data);
    agents.value = [...agents.value, agent];
    return agent;
  }

  async function removeAgentFromRoom(agentId: string) {
    if (!activeRoom.value) return;
    await meetingApi.removeAgent(activeRoom.value.id, agentId);
    agents.value = agents.value.filter((a) => a.agent_id !== agentId);
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
        upsertMessage(evt.message);
        loadRooms();
        break;
      }
      case "agent_run_started": {
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: "" };
        break;
      }
      case "message_delta": {
        const current = streamingContent.value[evt.message_id] || "";
        streamingContent.value = { ...streamingContent.value, [evt.message_id]: current + evt.delta };
        break;
      }
      case "message_final": {
        const content = evt.content;
        const existing = messages.value.find((m) => m.message_type === "agent_streaming" && m.agent_id === evt.agent_id && m.content === "");
        if (existing) {
          existing.content = content;
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
            created_at: new Date().toISOString(),
          } as MeetingMessage);
        }
        const next = { ...streamingContent.value };
        delete next[evt.message_id];
        streamingContent.value = next;
        break;
      }
      case "agent_run_failed": {
        const next = { ...streamingContent.value };
        delete next[evt.message_id];
        streamingContent.value = next;
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
    // computed
    activeRoom, canSend, lastMessageSeq,
    // actions
    loadRooms, createRoom, joinRoom,
    loadMessages, sendMessage,
    requestAiReply, summarizeMeeting,
    loadAgents, loadMembers, deleteRoom,
    availableAgentDefs, loadAvailableAgentDefs, addAgentToRoom, removeAgentFromRoom,
    connectStream, disconnectStream, handleStreamEvent,
    setReaction,
  };
});
