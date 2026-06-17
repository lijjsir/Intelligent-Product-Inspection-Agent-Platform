import { http } from "./http";
import { streamApi } from "./stream.api";
import type {
  MeetingActionItem,
  MeetingActionItemCreate,
  MeetingActionItemUpdate,
  MeetingAddAgentRequest,
  MeetingAgentQueryAudit,
  MeetingAgentRunRequest,
  MeetingAgentRunResponse,
  MeetingAttachment,
  MeetingBusinessContext,
  MeetingContextPreview,
  MeetingMemory,
  MeetingMemoryConfirmPayload,
  MeetingMemoryDisputePayload,
  MeetingMemberRoleUpdate,
  MeetingMessage,
  MeetingQuoteSnapshot,
  MeetingRoom,
  MeetingRoomAgent,
  MeetingRoomCreate,
  MeetingRoomDetail,
  MeetingRoomJoin,
  MeetingRoomUpdate,
  MeetingRoomMember,
  MeetingStreamEvent,
} from "@/types/meeting.types";

const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim();

export const meetingApi = {
  listRooms(limit = 100) {
    return http.get<MeetingRoom[]>("/v1/meetings/rooms", { params: { limit } });
  },

  createRoom(payload: MeetingRoomCreate) {
    return http.post<MeetingRoom>("/v1/meetings/rooms", payload);
  },

  joinRoom(payload: MeetingRoomJoin) {
    return http.post<MeetingRoom>("/v1/meetings/rooms/join", payload);
  },

  getRoomDetail(roomId: string) {
    return http.get<MeetingRoomDetail>(`/v1/meetings/rooms/${roomId}`);
  },

  updateRoom(roomId: string, payload: MeetingRoomUpdate) {
    return http.put<MeetingRoom>(`/v1/meetings/rooms/${roomId}`, payload);
  },

  updateBusinessContext(roomId: string, payload: Partial<MeetingBusinessContext>) {
    return http.put<MeetingBusinessContext>(`/v1/meetings/rooms/${roomId}/business-context`, payload);
  },

  closeRoom(roomId: string) {
    return http.post<MeetingRoom>(`/v1/meetings/rooms/${roomId}/close`);
  },

  archiveRoom(roomId: string) {
    return http.post<MeetingRoom>(`/v1/meetings/rooms/${roomId}/archive`);
  },

  listMessages(roomId: string, afterSeq = 0, limit = 200) {
    return http.get<MeetingMessage[]>(`/v1/meetings/rooms/${roomId}/messages`, {
      params: { after_seq: afterSeq, limit },
    });
  },

  sendMessage(
    roomId: string,
    content: string,
    quoteMessageId?: string | null,
    options?: { skipAgentTrigger?: boolean; attachments?: MeetingAttachment[]; privateRecipientUserId?: string | null; quoteSnapshot?: MeetingQuoteSnapshot | null },
  ) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages`, {
      content,
      quote_message_id: quoteMessageId || null,
      private_recipient_user_id: options?.privateRecipientUserId || null,
      skip_agent_trigger: Boolean(options?.skipAgentTrigger),
      attachments: options?.attachments || [],
      quote_snapshot: options?.quoteSnapshot || null,
    });
  },

  updateMessage(roomId: string, messageId: string, content: string) {
    return http.put<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages/${messageId}`, { content });
  },

  recallMessage(roomId: string, messageId: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages/${messageId}/recall`, undefined, {
      suppressErrorToast: true,
    });
  },

  async uploadAttachments(roomId: string, files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<{ items: MeetingAttachment[] }>(`/v1/meetings/rooms/${roomId}/uploads`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 180000,
    });
  },

  quoteMessage(roomId: string, messageId: string, content: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages/${messageId}/quote`, { content });
  },

  deleteRoom(roomId: string) {
    return http.delete(`/v1/meetings/rooms/${roomId}`);
  },

  leaveRoom(roomId: string) {
    return http.post<{ ok: boolean }>(`/v1/meetings/rooms/${roomId}/leave`);
  },

  // ── AI Assistant ────────────────────────────────────────────────

  aiChat(roomId: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/ai-chat`);
  },

  summarize(roomId: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/summary`);
  },

  runGeneralAgent(roomId: string, payload: MeetingAgentRunRequest, config?: { signal?: AbortSignal }) {
    return http.post<MeetingAgentRunResponse>(`/v1/meetings/rooms/${roomId}/agent/run`, payload, {
      ...config,
      suppressErrorToast: true,
    });
  },

  cancelGeneralAgent(roomId: string, workflowRunId: string) {
    return http.post<{ cancelled: boolean; workflow_run_id: string }>(
      `/v1/meetings/rooms/${roomId}/agent/runs/${workflowRunId}/cancel`,
      {},
      { suppressErrorToast: true }
    );
  },

  getContextPreview(roomId: string) {
    return http.get<MeetingContextPreview>(`/v1/meetings/rooms/${roomId}/context-preview`);
  },

  listAgentQueryAudits(roomId: string, limit = 50) {
    return http.get<MeetingAgentQueryAudit[]>(`/v1/meetings/rooms/${roomId}/agent-query-audits`, {
      params: { limit },
      suppressErrorToast: true,
    });
  },

  listMemories(roomId: string) {
    return http.get<MeetingMemory[]>(`/v1/meetings/rooms/${roomId}/memories`);
  },

  extractMemories(roomId: string, payload: { topic?: string | null; max_items?: number }, config?: { signal?: AbortSignal }) {
    return http.post<MeetingMemory[]>(`/v1/meetings/rooms/${roomId}/memories/extract`, payload, config);
  },

  confirmMemory(memoryId: string, payload?: MeetingMemoryConfirmPayload) {
    return http.post<MeetingMemory>(`/v1/meetings/memories/${memoryId}/confirm`, payload || {});
  },

  rejectMemory(memoryId: string, payload?: { content?: string | null }) {
    return http.post<MeetingMemory>(`/v1/meetings/memories/${memoryId}/reject`, payload || {});
  },

  disputeMemory(memoryId: string, payload: MeetingMemoryDisputePayload) {
    return http.post<MeetingMemory>(`/v1/meetings/memories/${memoryId}/dispute`, payload);
  },

  listActionItems(roomId: string) {
    return http.get<MeetingActionItem[]>(`/v1/meetings/rooms/${roomId}/action-items`);
  },

  createActionItem(roomId: string, payload: MeetingActionItemCreate) {
    return http.post<MeetingActionItem>(`/v1/meetings/rooms/${roomId}/action-items`, payload);
  },

  updateActionItem(actionItemId: string, payload: MeetingActionItemUpdate) {
    return http.put<MeetingActionItem>(`/v1/meetings/action-items/${actionItemId}`, payload);
  },

  completeActionItem(actionItemId: string) {
    return http.post<MeetingActionItem>(`/v1/meetings/action-items/${actionItemId}/complete`);
  },

  // ── Agent management ───────────────────────────────────────────

  listAgents(roomId: string) {
    return http.get<MeetingRoomAgent[]>(`/v1/meetings/rooms/${roomId}/agents`);
  },

  addAgent(roomId: string, payload: MeetingAddAgentRequest) {
    return http.post<MeetingRoomAgent>(`/v1/meetings/rooms/${roomId}/agents`, payload);
  },

  removeAgent(roomId: string, agentId: string) {
    return http.delete(`/v1/meetings/rooms/${roomId}/agents/${agentId}`);
  },

  listMembers(roomId: string) {
    return http.get<MeetingRoomMember[]>(`/v1/meetings/rooms/${roomId}/members`);
  },

  updateMemberRole(roomId: string, memberUserId: string, payload: MeetingMemberRoleUpdate) {
    return http.put<MeetingRoomMember>(`/v1/meetings/rooms/${roomId}/members/${memberUserId}/role`, payload);
  },

  // ── Agent Definitions ─────────────────────────────────────────

  listAgentDefs() {
    return http.get<Array<{
      id: string;
      name: string;
      system_prompt: string;
      model: string;
      adapter_type: string;
      participation_strategy: Record<string, unknown> | null;
      is_active: boolean;
    }>>("/v1/meetings/agent-defs");
  },

  // ── SSE Stream ─────────────────────────────────────────────────

  async stream(
    roomId: string,
    onEvent: (event: MeetingStreamEvent) => void,
    onStatus?: (status: "open" | "error") => void,
  ): Promise<EventSource> {
    const { data } = await streamApi.create("meeting", roomId);
    const resp = data as { data?: { stream_token?: string } };
    const token = resp?.data?.stream_token || "";
    const sep = apiBase.endsWith("/") ? "" : "/";
    const url = `${apiBase}${sep}v1/meetings/rooms/${roomId}/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onmessage = (evt: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(evt.data) as MeetingStreamEvent;
        onEvent(parsed);
      } catch {
        // ignore parse errors
      }
    };
    source.onopen = () => {
      onStatus?.("open");
    };
    source.onerror = () => {
      onStatus?.("error");
    };
    return source;
  },
};
