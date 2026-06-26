import { http } from "./http";
import { streamApi } from "./stream.api";
import type {
  CollabMessage,
  CollabMessageActionPayload,
  CollabMessageCreatePayload,
  CollabMessageReceipt,
  CollabStreamEvent,
  CollabTarget,
  CollabThread,
  CollabThreadCreatePayload,
  CollabUploadResponse,
} from "@/types/collab.types";

const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim();

export const collabApi = {
  listThreads(limit = 100) {
    return http.get<CollabThread[]>("/v1/collab/threads", { params: { limit } });
  },

  listTargets(limit = 100) {
    return http.get<CollabTarget[]>("/v1/collab/targets", { params: { limit } });
  },

  createThread(payload: CollabThreadCreatePayload) {
    return http.post<CollabThread>("/v1/collab/threads", payload);
  },

  listMessages(threadId: string, limit = 200) {
    return http.get<CollabMessage[]>(`/v1/collab/threads/${threadId}/messages`, {
      params: { limit },
    });
  },

  sendMessage(threadId: string, payload: CollabMessageCreatePayload) {
    return http.post<CollabMessage>(`/v1/collab/threads/${threadId}/messages`, payload);
  },

  markRead(messageId: string) {
    return http.post<CollabMessageReceipt>(`/v1/collab/messages/${messageId}/read`);
  },

  updateAction(messageId: string, payload: CollabMessageActionPayload) {
    return http.post<CollabMessageReceipt>(`/v1/collab/messages/${messageId}/action`, payload);
  },

  archiveThread(threadId: string) {
    return http.post<CollabThread>(`/v1/collab/threads/${threadId}/archive`);
  },

  deleteThread(threadId: string) {
    return http.delete<{ deleted: boolean; thread_id: string }>(`/v1/collab/threads/${threadId}`);
  },

  deleteMessage(messageId: string) {
    return http.delete<{ deleted: boolean; message_id: string }>(`/v1/collab/messages/${messageId}`);
  },

  uploadAttachments(files: File[]) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return http.post<CollabUploadResponse>("/v1/collab/uploads", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 180000,
    });
  },

  async stream(
    userId: string,
    onEvent: (event: CollabStreamEvent) => void,
    onStatus?: (status: "open" | "error") => void,
  ): Promise<EventSource> {
    const { data } = await streamApi.create("collab", userId);
    const token = data.data.stream_token;
    const sep = apiBase.endsWith("/") ? "" : "/";
    const url = `${apiBase}${sep}v1/collab/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onmessage = (evt: MessageEvent<string>) => {
      try {
        onEvent(JSON.parse(evt.data) as CollabStreamEvent);
      } catch {
        // Ignore malformed stream events.
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
