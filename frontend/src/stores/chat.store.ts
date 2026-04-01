import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { chatApi } from "@/api/chat.api";
import { ragSpaceApi } from "@/api/rag-space.api";
import type {
  ChatAttachment,
  ChatCreatedTask,
  ChatMessage,
  ChatMessagePayload,
  ChatMessageSendRequest,
  ChatSession,
  ChatStreamEvent,
} from "@/types/chat.types";
import type { RagSpace } from "@/types/rag-space.types";

function resolveErrorMessage(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null) {
    const candidate = error as {
      response?: {
        data?: {
          message?: string;
        };
      };
      message?: string;
    };
    return candidate.response?.data?.message || candidate.message || fallback;
  }
  return fallback;
}

function orderNo(message: ChatMessage) {
  return message.seq_no > 0 ? message.seq_no : message.client_seq || 0;
}

function normalizeSelectedRagSpace(
  value: unknown,
): Pick<RagSpace, "id" | "name" | "description"> | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.id !== "string" || typeof candidate.name !== "string") {
    return null;
  }
  return {
    id: candidate.id,
    name: candidate.name,
    description: typeof candidate.description === "string" ? candidate.description : null,
  };
}

function normalizeAttachments(value: unknown): ChatAttachment[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      id: typeof item.id === "string" ? item.id : crypto.randomUUID(),
      name: typeof item.name === "string" ? item.name : "附件",
      url: typeof item.url === "string" ? item.url : "",
      content_type: typeof item.content_type === "string" ? item.content_type : null,
      size_bytes: typeof item.size_bytes === "number" ? item.size_bytes : 0,
      kind: typeof item.kind === "string" ? item.kind : "file",
    }))
    .filter((item) => Boolean(item.url));
}

function normalizeMessage(message: ChatMessage): ChatMessage {
  const payload = message.payload || {};
  const ext = (payload as Record<string, unknown>).ext as Record<string, unknown> | undefined;
  const payloadAttachments = normalizeAttachments(payload.attachment_echo);
  const selected = normalizeSelectedRagSpace(payload.selected_rag_space) ?? normalizeSelectedRagSpace(ext?.selected_rag_space);
  const attachments = payloadAttachments.length > 0 ? payloadAttachments : normalizeAttachments(ext?.attachments);
  return {
    ...message,
    payload: {
      ...payload,
      selected_rag_space: selected,
      attachment_echo: attachments,
    },
  };
}

export const useChatStore = defineStore("chat", () => {
  const loading = ref(false);
  const sessions = ref<ChatSession[]>([]);
  const session = ref<ChatSession | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const streamConnected = ref(false);
  const eventSource = ref<EventSource | null>(null);
  const reconnectFailTimer = ref<number | null>(null);
  const ragSpaces = ref<RagSpace[]>([]);
  const ragSpacesError = ref("");
  const selectedRagSpaceId = ref("");
  const pendingAttachments = ref<ChatAttachment[]>([]);
  const nextClientSeq = ref(1);
  const STORAGE_CURRENT_SESSION = "chat_current_session_id";

  function saveCurrentSession(sessionId: string) {
    sessionStorage.setItem(STORAGE_CURRENT_SESSION, sessionId);
  }

  function getSavedSession() {
    return sessionStorage.getItem(STORAGE_CURRENT_SESSION) || "";
  }

  function getSelectedRagSpaceSnapshot() {
    return ragSpaces.value.find((item) => item.id === selectedRagSpaceId.value) || null;
  }

  const selectedRagSpace = computed(() => getSelectedRagSpaceSnapshot());
  const lastSeq = computed(() => {
    if (messages.value.length === 0) return 0;
    return Math.max(...messages.value.map((x) => x.seq_no));
  });

  function sortMessages() {
    messages.value.sort((a, b) => {
      const ao = orderNo(a);
      const bo = orderNo(b);
      if (ao !== bo) return ao - bo;
      if (a.role !== b.role) return a.role === "user" ? -1 : 1;
      return 0;
    });
  }

  function upsertMessage(incoming: ChatMessage) {
    const index = messages.value.findIndex((x) => x.id === incoming.id);
    if (index === -1) {
      messages.value.push(incoming);
    } else {
      messages.value[index] = {
        ...messages.value[index],
        ...incoming,
        payload: {
          ...(messages.value[index].payload || {}),
          ...(incoming.payload || {}),
        },
      };
    }
  }

  function appendMessages(incoming: ChatMessage[]) {
    for (const item of incoming) {
      upsertMessage(normalizeMessage(item));
    }
    sortMessages();
  }

  function removeMessages(ids: string[]) {
    messages.value = messages.value.filter((item) => !ids.includes(item.id));
  }

  function allocateClientSeq(count = 1) {
    const current = Math.max(nextClientSeq.value, ...messages.value.map((item) => orderNo(item)), 0) + 1;
    nextClientSeq.value = current + count;
    return current;
  }

  async function fetchSessions() {
    const { data } = await chatApi.listSessions(200);
    sessions.value = data.data;
    return sessions.value;
  }

  async function fetchRagSpaces() {
    try {
      const { data } = await ragSpaceApi.list(200);
      ragSpaces.value = data.data;
      ragSpacesError.value = "";
      if (selectedRagSpaceId.value && !ragSpaces.value.some((item) => item.id === selectedRagSpaceId.value)) {
        selectedRagSpaceId.value = "";
      }
      return ragSpaces.value;
    } catch (error) {
      ragSpaces.value = [];
      selectedRagSpaceId.value = "";
      ragSpacesError.value = resolveErrorMessage(error, "RAG 空间尚未初始化，请先完成数据库迁移。");
      throw error;
    }
  }

  async function createRagSpace(payload: { name: string; description?: string }, files: File[]) {
    const { data } = await ragSpaceApi.create(payload);
    const created = data.data;
    if (files.length > 0) {
      await ragSpaceApi.uploadDocuments(created.id, files);
    }
    await fetchRagSpaces();
    return ragSpaces.value.find((item) => item.id === created.id) || created;
  }

  async function uploadPendingAttachments(files: File[]) {
    if (files.length === 0) return [];
    const { data } = await chatApi.uploadAttachments(files);
    pendingAttachments.value = [...pendingAttachments.value, ...data.data.items];
    return data.data.items;
  }

  function removePendingAttachment(id: string) {
    pendingAttachments.value = pendingAttachments.value.filter((item) => item.id !== id);
  }

  function clearPendingAttachments() {
    pendingAttachments.value = [];
  }

  function selectRagSpace(spaceId: string) {
    selectedRagSpaceId.value = spaceId;
  }

  function clearSelectedRagSpace() {
    selectedRagSpaceId.value = "";
  }

  async function createNewSession(title = "新会话") {
    const { data } = await chatApi.createSession(title);
    session.value = data.data;
    if (session.value?.id) saveCurrentSession(session.value.id);
    messages.value = [];
    await fetchSessions();
    reconnectStream();
    return session.value;
  }

  async function selectSession(sessionId: string) {
    const found = sessions.value.find((x) => x.id === sessionId);
    session.value = found || null;
    messages.value = [];
    if (!session.value) return null;
    saveCurrentSession(session.value.id);
    const rows = await chatApi.listMessages(session.value.id, 0, 500);
    messages.value = rows.data.data.map((item) => normalizeMessage({ ...item, client_seq: item.seq_no }));
    sortMessages();
    reconnectStream();
    return session.value;
  }

  async function initForChatPage() {
    await fetchSessions();
    try {
      await fetchRagSpaces();
    } catch {
      // RAG metadata initialization should not block ordinary chat usage.
    }
    const savedSessionId = getSavedSession();
    if (savedSessionId && sessions.value.some((x) => x.id === savedSessionId)) {
      await selectSession(savedSessionId);
      return;
    }
    if (sessions.value.length > 0) {
      await selectSession(sessions.value[0].id);
      return;
    }
    await createNewSession();
  }

  async function sendMessage(payload: ChatMessageSendRequest) {
    if (!session.value) await createNewSession();
    if (!session.value) return null;

    const clientSeqStart = allocateClientSeq(2);
    const selected = getSelectedRagSpaceSnapshot();
    const ext = {
      ...(payload.ext || {}),
      attachments: [...pendingAttachments.value],
      selected_rag_space_id: selected?.id || undefined,
      selected_rag_space_name: selected?.name || undefined,
      selected_rag_space_description: selected?.description || undefined,
      selected_rag_space: selected
        ? {
            id: selected.id,
            name: selected.name,
            description: selected.description,
          }
        : undefined,
    };
    const tempUserId = `temp-user-${crypto.randomUUID()}`;
    const tempAssistantId = `temp-assistant-${crypto.randomUUID()}`;

    appendMessages([
      {
        id: tempUserId,
        session_id: session.value.id,
        seq_no: 0,
        client_seq: clientSeqStart,
        optimistic: true,
        role: "user",
        message_type: "text",
        content: payload.message,
        payload: {
          attachment_echo: [...pendingAttachments.value],
          selected_rag_space: selected
            ? {
                id: selected.id,
                name: selected.name,
                description: selected.description,
              }
            : null,
        },
        created_at: new Date().toISOString(),
      },
      {
        id: tempAssistantId,
        session_id: session.value.id,
        seq_no: 0,
        client_seq: clientSeqStart + 1,
        optimistic: true,
        role: "assistant",
        message_type: "streaming",
        content: "",
        payload: {
          status: "running",
        },
        created_at: new Date().toISOString(),
      },
    ]);

    loading.value = true;
    try {
      const { data } = await chatApi.sendMessage(session.value.id, {
        ...payload,
        ext,
      });
      removeMessages([tempUserId, tempAssistantId]);
      appendMessages([
        {
          ...data.data.user_message,
          payload: {
            ...(data.data.user_message.payload || {}),
            selected_rag_space: selected
              ? {
                  id: selected.id,
                  name: selected.name,
                  description: selected.description,
                }
              : null,
            attachment_echo: [...pendingAttachments.value],
          },
          client_seq: clientSeqStart,
        },
        {
          id: data.data.assistant_message_id,
          session_id: session.value.id,
          seq_no: 0,
          client_seq: clientSeqStart + 1,
          role: "assistant",
          message_type: "streaming",
          content: "",
          payload: {
            status: "running",
            workflow_run_id: data.data.workflow_run_id,
          },
          created_at: new Date().toISOString(),
        },
      ]);
      clearPendingAttachments();
      await fetchSessions();
      return data.data;
    } catch (error) {
      removeMessages([tempUserId, tempAssistantId]);
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function appendTaskResult(task: ChatCreatedTask) {
    if (!session.value) return null;
    const { data } = await chatApi.appendTaskResult(session.value.id, {
      task_id: task.id,
      status: task.status,
      product_id: task.product_id,
      spec_code: task.spec_code,
      priority: task.priority,
      image_count: task.image_count,
    });
    appendMessages([{ ...data.data, client_seq: data.data.seq_no }]);
    await fetchSessions();
    return data.data;
  }

  async function deleteSession(sessionId: string) {
    await chatApi.deleteSession(sessionId);
    const deletingCurrent = session.value?.id === sessionId;
    await fetchSessions();
    if (deletingCurrent) {
      if (sessions.value.length > 0) {
        await selectSession(sessions.value[0].id);
      } else {
        await createNewSession();
      }
    }
  }

  function applyStreamEvent(event: ChatStreamEvent) {
    if (!session.value || event.session_id !== session.value.id || !event.message_id) return;
    const current = messages.value.find((item) => item.id === event.message_id);
    const basePayload: ChatMessagePayload = {
      ...(current?.payload || {}),
      ...(event.payload || {}),
    };
    if (event.quality) {
      basePayload.quality = event.quality;
    }
    if (event.event === "message_delta") {
      upsertMessage({
        id: event.message_id,
        session_id: event.session_id,
        seq_no: current?.seq_no || 0,
        client_seq: current?.client_seq || allocateClientSeq(),
        role: "assistant",
        message_type: "streaming",
        content: `${current?.content || ""}${event.delta || ""}`,
        payload: basePayload,
        created_at: current?.created_at || event.ts || new Date().toISOString(),
      });
      sortMessages();
      return;
    }
    if (event.event === "message_final" || event.event === "run_failed") {
      upsertMessage({
        id: event.message_id,
        session_id: event.session_id,
        seq_no: current?.seq_no || 0,
        client_seq: current?.client_seq || allocateClientSeq(),
        role: "assistant",
        message_type:
          event.event === "run_failed"
            ? "error"
            : String(basePayload.message_type || current?.message_type || "quality_answer"),
        content: event.content || current?.content || "",
        payload: basePayload,
        created_at: current?.created_at || event.ts || new Date().toISOString(),
      });
      sortMessages();
      return;
    }
    if (event.event === "quality_signal" && current) {
      upsertMessage({
        ...current,
        payload: basePayload,
      });
      sortMessages();
    }
  }

  async function ensureStream() {
    if (!session.value || eventSource.value) return;
    const sessionId = session.value.id;
    const source = await chatApi.stream(sessionId, lastSeq.value, (event) => {
      applyStreamEvent(event);
    });
    if (!session.value || session.value.id !== sessionId) {
      source.close();
      return;
    }
    if (reconnectFailTimer.value != null) {
      window.clearTimeout(reconnectFailTimer.value);
      reconnectFailTimer.value = null;
    }
    source.onopen = () => {
      if (reconnectFailTimer.value != null) {
        window.clearTimeout(reconnectFailTimer.value);
        reconnectFailTimer.value = null;
      }
      streamConnected.value = true;
    };
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        streamConnected.value = false;
        return;
      }
      if (reconnectFailTimer.value == null) {
        reconnectFailTimer.value = window.setTimeout(() => {
          streamConnected.value = false;
          reconnectFailTimer.value = null;
        }, 6000);
      }
    };
    eventSource.value = source;
  }

  function stopStream() {
    if (reconnectFailTimer.value != null) {
      window.clearTimeout(reconnectFailTimer.value);
      reconnectFailTimer.value = null;
    }
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    streamConnected.value = false;
  }

  function reconnectStream() {
    stopStream();
    ensureStream().catch(() => {
      streamConnected.value = false;
    });
  }

  return {
    loading,
    sessions,
    session,
    messages,
    streamConnected,
    ragSpaces,
    ragSpacesError,
    selectedRagSpaceId,
    selectedRagSpace,
    pendingAttachments,
    fetchSessions,
    fetchRagSpaces,
    createRagSpace,
    uploadPendingAttachments,
    removePendingAttachment,
    clearPendingAttachments,
    selectRagSpace,
    clearSelectedRagSpace,
    createNewSession,
    selectSession,
    initForChatPage,
    sendMessage,
    appendTaskResult,
    deleteSession,
    stopStream,
  };
});
