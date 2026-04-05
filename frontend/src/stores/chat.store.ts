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
  ChatStreamPhase,
  ChatStreamEvent,
} from "@/types/chat.types";
import type { RagSpace } from "@/types/rag-space.types";

const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 25000;

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
  const streamPhase = ref<ChatStreamPhase>("idle");
  const streamConnected = ref(false);
  const eventSource = ref<EventSource | null>(null);
  const initPromise = ref<Promise<void> | null>(null);
  const streamPromise = ref<Promise<void> | null>(null);
  const activeAssistantMessageId = ref<string | null>(null);
  const pollTimer = ref<number | null>(null);
  const pollDeadline = ref<number>(0);
  const pollInFlight = ref(false);
  const ragSpaces = ref<RagSpace[]>([]);
  const ragSpacesError = ref("");
  const pendingAttachments = ref<ChatAttachment[]>([]);
  const nextClientSeq = ref(1);
  const STORAGE_CURRENT_SESSION = "chat_current_session_id";
  const STORAGE_SELECTED_RAG_SPACE = "chat_selected_rag_space_id";

  function saveCurrentSession(sessionId: string) {
    sessionStorage.setItem(STORAGE_CURRENT_SESSION, sessionId);
  }

  function saveSelectedRagSpace(spaceId: string) {
    sessionStorage.setItem(STORAGE_SELECTED_RAG_SPACE, spaceId);
  }

  function getSavedSession() {
    return sessionStorage.getItem(STORAGE_CURRENT_SESSION) || "";
  }

  function getSavedSelectedRagSpace() {
    return sessionStorage.getItem(STORAGE_SELECTED_RAG_SPACE) || "";
  }

  function clearSavedSelectedRagSpace() {
    sessionStorage.removeItem(STORAGE_SELECTED_RAG_SPACE);
  }

  const selectedRagSpaceId = ref(getSavedSelectedRagSpace());

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

  function isTerminalAssistantMessage(message: ChatMessage | undefined) {
    if (!message) return false;
    if (message.message_type && message.message_type !== "streaming") {
      return true;
    }
    const status = String(message.payload?.status || "").toLowerCase();
    return ["failed", "done", "finished", "completed", "success"].includes(status);
  }

  function stopPolling() {
    if (pollTimer.value != null) {
      window.clearTimeout(pollTimer.value);
      pollTimer.value = null;
    }
    pollDeadline.value = 0;
    pollInFlight.value = false;
  }

  function closeStreamConnection() {
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    streamConnected.value = false;
  }

  function finishActiveSend() {
    activeAssistantMessageId.value = null;
    loading.value = false;
    streamPhase.value = "idle";
  }

  function stopStreamForIdle() {
    streamPromise.value = null;
    stopPolling();
    closeStreamConnection();
    finishActiveSend();
  }

  function finalizeStreaming() {
    streamPhase.value = "closing";
    stopPolling();
    closeStreamConnection();
    finishActiveSend();
  }

  function checkAndFinalizeByMessage(messageId: string) {
    const target = messages.value.find((item) => item.id === messageId);
    if (!isTerminalAssistantMessage(target)) {
      return false;
    }
    finalizeStreaming();
    return true;
  }

  function startFallbackPolling(sessionId: string, messageId: string) {
    if (!messageId || pollTimer.value != null) return;
    pollDeadline.value = Date.now() + POLL_TIMEOUT_MS;
    streamPhase.value = "streaming";

    const tick = async () => {
      if (!session.value || session.value.id !== sessionId || activeAssistantMessageId.value !== messageId) {
        stopPolling();
        return;
      }
      if (Date.now() > pollDeadline.value) {
        stopPolling();
        finishActiveSend();
        return;
      }
      if (pollInFlight.value) {
        pollTimer.value = window.setTimeout(tick, POLL_INTERVAL_MS);
        return;
      }
      pollInFlight.value = true;
      try {
        const rows = await chatApi.listMessages(sessionId, 0, 500);
        messages.value = rows.data.data.map((item) => normalizeMessage({ ...item, client_seq: item.seq_no }));
        sortMessages();
        if (checkAndFinalizeByMessage(messageId)) {
          return;
        }
      } catch {
        // Ignore transient polling errors and continue until timeout.
      } finally {
        pollInFlight.value = false;
      }
      pollTimer.value = window.setTimeout(tick, POLL_INTERVAL_MS);
    };

    pollTimer.value = window.setTimeout(tick, POLL_INTERVAL_MS);
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
        clearSavedSelectedRagSpace();
      }
      return ragSpaces.value;
    } catch (error) {
      ragSpaces.value = [];
      selectedRagSpaceId.value = "";
      clearSavedSelectedRagSpace();
      ragSpacesError.value = resolveErrorMessage(error, "RAG 空间暂不可用，请稍后重试。");
      throw error;
    }
  }

  async function createRagSpace(payload: { name: string; description?: string }, files: File[]) {
    const { data } = await ragSpaceApi.create(payload);
    const created = data.data;
    const selectedFiles = files.slice(0, 1);
    if (selectedFiles.length > 0) {
      await ragSpaceApi.uploadDocuments(created.id, selectedFiles);
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
    saveSelectedRagSpace(spaceId);
  }

  function clearSelectedRagSpace() {
    selectedRagSpaceId.value = "";
    clearSavedSelectedRagSpace();
  }

  async function createNewSession(title = "新会话") {
    stopStreamForIdle();
    const { data } = await chatApi.createSession(title);
    session.value = data.data;
    if (session.value?.id) saveCurrentSession(session.value.id);
    messages.value = [];
    await fetchSessions();
    return session.value;
  }

  async function selectSession(sessionId: string) {
    if (session.value?.id === sessionId && messages.value.length > 0) {
      return session.value;
    }
    stopStreamForIdle();
    const found = sessions.value.find((x) => x.id === sessionId);
    session.value = found || null;
    messages.value = [];
    if (!session.value) return null;
    saveCurrentSession(session.value.id);
    const rows = await chatApi.listMessages(session.value.id, 0, 500);
    messages.value = rows.data.data.map((item) => normalizeMessage({ ...item, client_seq: item.seq_no }));
    sortMessages();
    return session.value;
  }

  async function reloadCurrentSessionMessages() {
    if (!session.value) return [];
    const rows = await chatApi.listMessages(session.value.id, 0, 500);
    messages.value = rows.data.data.map((item) => normalizeMessage({ ...item, client_seq: item.seq_no }));
    sortMessages();
    await fetchSessions();
    return messages.value;
  }

  async function initForChatPage() {
    if (initPromise.value) {
      await initPromise.value;
      return;
    }
    initPromise.value = (async () => {
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
    })();
    try {
      await initPromise.value;
    } finally {
      initPromise.value = null;
    }
  }

  async function sendMessage(payload: ChatMessageSendRequest) {
    if (!session.value) await createNewSession();
    if (!session.value) return null;
    const sessionId = session.value.id;
    stopStreamForIdle();

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
        session_id: sessionId,
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
        session_id: sessionId,
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
    streamPhase.value = "connecting";
    let streamStarted = false;
    try {
      await ensureStream(sessionId);
      streamStarted = !!eventSource.value;
    } catch {
      streamStarted = false;
    }

    try {
      const { data } = await chatApi.sendMessage(sessionId, {
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
          session_id: sessionId,
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
      activeAssistantMessageId.value = data.data.assistant_message_id;
      clearPendingAttachments();
      await fetchSessions();
      if (!streamStarted || !eventSource.value) {
        startFallbackPolling(sessionId, data.data.assistant_message_id);
      } else if (!checkAndFinalizeByMessage(data.data.assistant_message_id)) {
        streamPhase.value = streamConnected.value ? "streaming" : "connecting";
      }
      return data.data;
    } catch (error) {
      removeMessages([tempUserId, tempAssistantId]);
      stopStreamForIdle();
      throw error;
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

  async function submitTask(payload: {
    source_message_id?: string | null;
    product_id: string;
    spec_code: string;
    image_urls: string[];
    priority: number;
    metadata?: Record<string, unknown>;
  }) {
    if (!session.value) return null;
    const { data } = await chatApi.submitTask(session.value.id, payload);
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
      if (event.message_id && activeAssistantMessageId.value === event.message_id) {
        finalizeStreaming();
      }
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

  async function ensureStream(sessionId: string) {
    if (!session.value || eventSource.value) return;
    if (streamPromise.value) {
      await streamPromise.value;
      return;
    }
    streamPromise.value = (async () => {
      const source = await chatApi.stream(sessionId, lastSeq.value, (event) => {
        applyStreamEvent(event);
      });
      if (!session.value || session.value.id !== sessionId) {
        source.close();
        return;
      }
      source.onopen = () => {
        streamConnected.value = true;
        streamPhase.value = "streaming";
      };
      source.onerror = () => {
        streamConnected.value = false;
        closeStreamConnection();
        if (activeAssistantMessageId.value) {
          streamPhase.value = "streaming";
          startFallbackPolling(sessionId, activeAssistantMessageId.value);
          return;
        }
        streamPhase.value = "idle";
      };
      eventSource.value = source;
    })();
    try {
      await streamPromise.value;
    } finally {
      streamPromise.value = null;
    }
  }

  function stopStream() {
    stopStreamForIdle();
  }

  return {
    loading,
    streamPhase,
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
    reloadCurrentSessionMessages,
    appendTaskResult,
    submitTask,
    deleteSession,
    stopStream,
  };
});

