import { http, type ApiRequestConfig } from "./http";
import { streamApi } from "./stream.api";
import type {
  ChatAttachment,
  ChatInspectionContext,
  ChatMessage,
  ChatMessageSendRequest,
  ChatSendResponse,
  ChatSession,
  ChatStreamEvent,
} from "@/types/chat.types";

const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim();

export const chatApi = {
  listSessions(limit = 100) {
    return http.get<ChatSession[]>("/v1/chat/sessions", { params: { limit } });
  },

  createSession(title?: string) {
    return http.post<ChatSession>("/v1/chat/sessions", { title });
  },

  listMessages(sessionId: string, afterSeq = 0, limit = 200) {
    return http.get<ChatMessage[]>(`/v1/chat/sessions/${sessionId}/messages`, {
      params: { after_seq: afterSeq, limit },
    });
  },

  getInspectionContext(config?: ApiRequestConfig) {
    return http.get<ChatInspectionContext>("/v1/chat/inspection-context", config);
  },

  sendMessage(sessionId: string, payload: ChatMessageSendRequest) {
    return http.post<ChatSendResponse>(`/v1/chat/sessions/${sessionId}/messages`, payload, { timeout: 180000 });
  },

  cancelMessage(sessionId: string, messageId: string) {
    return http.post<ChatMessage>(`/v1/chat/sessions/${sessionId}/messages/${messageId}/cancel`);
  },

  appendTaskResult(
    sessionId: string,
    payload: {
      task_id: string;
      status: string;
      product_id: string;
      spec_code: string;
      priority: number;
      image_count: number;
    },
  ) {
    return http.post<ChatMessage>(`/v1/chat/sessions/${sessionId}/task-result`, payload);
  },

  submitTask(
    sessionId: string,
    payload: {
      source_message_id?: string | null;
      product_id: string;
      spec_code: string;
      image_urls: string[];
      priority: number;
      metadata?: Record<string, unknown>;
    },
  ) {
    return http.post<ChatMessage>(`/v1/chat/sessions/${sessionId}/tasks/submit`, payload);
  },

  async uploadAttachments(files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<{ items: ChatAttachment[] }>("/v1/chat/uploads", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  deleteSession(sessionId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/chat/sessions/${sessionId}`);
  },

  async stream(sessionId: string, _afterSeq: number, onMessage: (event: ChatStreamEvent) => void): Promise<EventSource> {
    const { data } = await streamApi.create("chat", sessionId);
    const token = data.data.stream_token;
    const sep = apiBase.endsWith("/") ? "" : "/";
    const url = `${apiBase}${sep}v1/chat/sessions/${sessionId}/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    const consume = (evt: MessageEvent<string>) => {
      try {
        const data = JSON.parse(evt.data) as ChatStreamEvent;
        onMessage(data);
      } catch {
        // no-op
      }
    };
    source.onmessage = consume;
    source.addEventListener("message", consume as EventListener);
    source.addEventListener("ready", consume as EventListener);
    return source;
  },
};
