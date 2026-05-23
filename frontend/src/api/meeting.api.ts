import { http } from "./http";
import { streamApi } from "./stream.api";
import type {
  MeetingAddAgentRequest,
  MeetingMessage,
  MeetingRoom,
  MeetingRoomAgent,
  MeetingRoomCreate,
  MeetingRoomDetail,
  MeetingRoomJoin,
  MeetingStreamEvent,
} from "@/types/meeting.types";

const VITE_API_BASE = import.meta.env.VITE_API_BASE || "";

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

  listMessages(roomId: string, afterSeq = 0, limit = 200) {
    return http.get<MeetingMessage[]>(`/v1/meetings/rooms/${roomId}/messages`, {
      params: { after_seq: afterSeq, limit },
    });
  },

  sendMessage(roomId: string, content: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages`, { content });
  },

  deleteRoom(roomId: string) {
    return http.delete(`/v1/meetings/rooms/${roomId}`);
  },

  // ── AI Assistant ────────────────────────────────────────────────

  aiChat(roomId: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/ai-chat`);
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

  async stream(roomId: string, onEvent: (event: MeetingStreamEvent) => void): Promise<EventSource> {
    const { data } = await streamApi.create("meeting", roomId);
    const resp = data as { data?: { stream_token?: string } };
    const token = resp?.data?.stream_token || "";
    const sep = VITE_API_BASE.endsWith("/") ? "" : "/";
    const url = `${VITE_API_BASE}${sep}v1/meetings/rooms/${roomId}/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onmessage = (evt: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(evt.data) as MeetingStreamEvent;
        onEvent(parsed);
      } catch {
        // ignore parse errors
      }
    };
    source.onerror = () => {
      // EventSource will auto-reconnect; no action needed
    };
    return source;
  },
};
