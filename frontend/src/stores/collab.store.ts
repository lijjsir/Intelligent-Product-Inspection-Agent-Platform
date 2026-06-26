import { defineStore } from "pinia";
import { computed, ref, shallowRef } from "vue";
import { collabApi } from "@/api/collab.api";
import { useAuthStore } from "@/stores/auth.store";
import type {
  CollabActionStatus,
  CollabAttachmentPayload,
  CollabMessage,
  CollabMessageCreatePayload,
  CollabMessageReceipt,
  CollabMessageType,
  CollabStreamEvent,
  CollabTarget,
  CollabThread,
  CollabThreadCreatePayload,
} from "@/types/collab.types";

export const useCollabStore = defineStore("collab", () => {
  const auth = useAuthStore();
  const threads = ref<CollabThread[]>([]);
  const targets = ref<CollabTarget[]>([]);
  const messagesByThread = ref<Record<string, CollabMessage[]>>({});
  const pendingAttachments = ref<CollabAttachmentPayload[]>([]);
  const activeThreadId = ref("");
  const eventSource = shallowRef<EventSource | null>(null);
  const streamConnected = ref(false);
  const loadingThreads = ref(false);
  const loadingTargets = ref(false);
  const loadingMessages = ref(false);
  const sending = ref(false);
  const uploading = ref(false);
  let streamRequestId = 0;

  function unwrap<T>(payload: unknown): T {
    return ((payload as { data?: T }).data || payload) as T;
  }

  const activeThread = computed(() => threads.value.find((thread) => thread.id === activeThreadId.value) || null);
  const activeMessages = computed(() => messagesByThread.value[activeThreadId.value] || []);
  const totalUnread = computed(() => threads.value.reduce((sum, thread) => sum + Number(thread.unread_count || 0), 0));
  const canSend = computed(() => Boolean(activeThread.value && !sending.value && !uploading.value));

  function sortThreads(items: CollabThread[]) {
    return [...items].sort((a, b) => {
      const left = new Date(a.last_message_at || a.updated_at || a.created_at || 0).getTime();
      const right = new Date(b.last_message_at || b.updated_at || b.created_at || 0).getTime();
      return right - left;
    });
  }

  function upsertThread(thread: CollabThread) {
    const index = threads.value.findIndex((item) => item.id === thread.id);
    if (index >= 0) {
      threads.value = sortThreads(threads.value.map((item) => (item.id === thread.id ? { ...item, ...thread } : item)));
    } else {
      threads.value = sortThreads([thread, ...threads.value]);
    }
  }

  function setMessages(threadId: string, items: CollabMessage[]) {
    messagesByThread.value = {
      ...messagesByThread.value,
      [threadId]: [...items].sort((a, b) => {
        const left = new Date(a.created_at || 0).getTime();
        const right = new Date(b.created_at || 0).getTime();
        if (left !== right) return left - right;
        return a.id.localeCompare(b.id);
      }),
    };
  }

  function upsertMessage(message: CollabMessage) {
    const current = messagesByThread.value[message.thread_id] || [];
    const exists = current.some((item) => item.id === message.id);
    setMessages(
      message.thread_id,
      exists ? current.map((item) => (item.id === message.id ? { ...item, ...message } : item)) : [...current, message],
    );
  }

  function touchThreadFromMessage(message: CollabMessage, unread: boolean) {
    let found = false;
    threads.value = sortThreads(threads.value.map((thread) => {
      if (thread.id !== message.thread_id) return thread;
      found = true;
      return {
        ...thread,
        last_message_at: message.created_at || thread.last_message_at,
        unread_count: Number(thread.unread_count || 0) + (unread ? 1 : 0),
      };
    }));
    return found;
  }

  function upsertReceipt(receipt: CollabMessageReceipt) {
    const current = messagesByThread.value[receipt.thread_id] || [];
    let wasUnreadForMe = false;
    const next = current.map((message) => {
      if (message.id !== receipt.message_id) return message;
      const existing = message.receipts.find((item) => item.id === receipt.id);
      wasUnreadForMe = Boolean(
        existing
        && existing.recipient_type === "user"
        && existing.recipient_id === auth.userId
        && !existing.read_at
        && receipt.read_at,
      );
      const receipts = existing
        ? message.receipts.map((item) => (item.id === receipt.id ? { ...item, ...receipt } : item))
        : [...message.receipts, receipt];
      return { ...message, receipts };
    });
    if (next.length) {
      messagesByThread.value = { ...messagesByThread.value, [receipt.thread_id]: next };
    }
    return wasUnreadForMe;
  }

  function decrementThreadUnread(threadId: string) {
    threads.value = threads.value.map((thread) => (
      thread.id === threadId
        ? { ...thread, unread_count: Math.max(0, Number(thread.unread_count || 0) - 1) }
        : thread
    ));
  }

  async function loadThreads(selectFirst = false) {
    loadingThreads.value = true;
    let nextThreadId = "";
    try {
      const { data } = await collabApi.listThreads();
      const list = sortThreads(unwrap<CollabThread[]>(data));
      threads.value = list;
      if (selectFirst || !activeThreadId.value || !list.some((thread) => thread.id === activeThreadId.value)) {
        activeThreadId.value = list[0]?.id || "";
      }
      nextThreadId = activeThreadId.value;
      return list;
    } finally {
      loadingThreads.value = false;
      if (nextThreadId) {
        void loadMessages(nextThreadId).catch(() => {
          // 消息详情加载失败不应让左侧线程列表一直停留在 loading 状态。
        });
      }
    }
  }

  async function loadTargets() {
    loadingTargets.value = true;
    try {
      const { data } = await collabApi.listTargets();
      targets.value = unwrap<CollabTarget[]>(data);
      return targets.value;
    } finally {
      loadingTargets.value = false;
    }
  }

  async function createThread(payload: CollabThreadCreatePayload) {
    const { data } = await collabApi.createThread(payload);
    const thread = unwrap<CollabThread>(data);
    upsertThread(thread);
    activeThreadId.value = thread.id;
    await loadMessages(thread.id);
    return thread;
  }

  async function openThread(threadId: string) {
    activeThreadId.value = threadId;
    return loadMessages(threadId);
  }

  async function loadMessages(threadId = activeThreadId.value, limit = 200) {
    if (!threadId) return [];
    loadingMessages.value = true;
    let lastUnreadMessageId = "";
    try {
      const { data } = await collabApi.listMessages(threadId, limit);
      const items = unwrap<CollabMessage[]>(data);
      setMessages(threadId, items);
      const lastUnread = [...items].reverse().find((item) =>
        item.receipts.some((receipt) =>
          receipt.recipient_type === "user" && receipt.recipient_id === auth.userId && !receipt.read_at
        ),
      );
      if (lastUnread) {
        lastUnreadMessageId = lastUnread.id;
      }
      return items;
    } finally {
      loadingMessages.value = false;
      if (lastUnreadMessageId) {
        void markRead(lastUnreadMessageId).catch(() => {
          // A slow/read-failed receipt update should not hide loaded messages.
        });
      }
    }
  }

  async function uploadAttachments(files: File[]) {
    if (!files.length) return [];
    uploading.value = true;
    try {
      const { data } = await collabApi.uploadAttachments(files);
      const items = unwrap<{ items: CollabAttachmentPayload[] }>(data).items || [];
      pendingAttachments.value = [...pendingAttachments.value, ...items];
      return items;
    } finally {
      uploading.value = false;
    }
  }

  function removePendingAttachment(id: string) {
    pendingAttachments.value = pendingAttachments.value.filter((item) => item.id !== id);
  }

  function clearPendingAttachments() {
    pendingAttachments.value = [];
  }

  async function sendMessage(
    content: string,
    messageType: CollabMessageType = "text",
    metadata?: Record<string, unknown> | null,
  ) {
    if (!activeThreadId.value || !canSend.value) return null;
    sending.value = true;
    try {
      const payload: CollabMessageCreatePayload = {
        content,
        message_type: messageType,
        attachments: pendingAttachments.value,
        metadata_json: metadata || null,
      };
      const { data } = await collabApi.sendMessage(activeThreadId.value, payload);
      const message = unwrap<CollabMessage>(data);
      upsertMessage(message);
      clearPendingAttachments();
      await loadThreads(false);
      activeThreadId.value = message.thread_id;
      return message;
    } finally {
      sending.value = false;
    }
  }

  async function markRead(messageId: string) {
    const { data } = await collabApi.markRead(messageId);
    const receipt = unwrap<CollabMessageReceipt>(data);
    if (upsertReceipt(receipt)) {
      decrementThreadUnread(receipt.thread_id);
    }
    return receipt;
  }

  async function updateAction(messageId: string, actionStatus: Exclude<CollabActionStatus, "pending">) {
    const { data } = await collabApi.updateAction(messageId, { action_status: actionStatus });
    const receipt = unwrap<CollabMessageReceipt>(data);
    if (activeThreadId.value) {
      await loadMessages(activeThreadId.value);
    }
    return receipt;
  }

  async function archiveThread(threadId = activeThreadId.value) {
    if (!threadId) return null;
    const { data } = await collabApi.archiveThread(threadId);
    const thread = unwrap<CollabThread>(data);
    upsertThread(thread);
    return thread;
  }

  async function deleteThread(threadId = activeThreadId.value) {
    if (!threadId) return null;
    await collabApi.deleteThread(threadId);
    threads.value = threads.value.filter((thread) => thread.id !== threadId);
    const remainingMessages = { ...messagesByThread.value };
    delete remainingMessages[threadId];
    messagesByThread.value = remainingMessages;
    if (activeThreadId.value === threadId) {
      activeThreadId.value = threads.value[0]?.id || "";
      if (activeThreadId.value) {
        await loadMessages(activeThreadId.value);
      }
    }
    return { deleted: true, thread_id: threadId };
  }

  async function deleteMessage(messageId: string) {
    await collabApi.deleteMessage(messageId);
    const threadId = activeThreadId.value;
    if (threadId) {
      messagesByThread.value = {
        ...messagesByThread.value,
        [threadId]: (messagesByThread.value[threadId] || []).filter((message) => message.id !== messageId),
      };
    }
  }

  function handleStreamEvent(evt: CollabStreamEvent) {
    switch (evt.event) {
      case "collab_message_created": {
        upsertMessage(evt.message);
        const knownThread = touchThreadFromMessage(evt.message, Boolean(evt.unread));
        if (!knownThread) {
          void loadThreads(false);
        }
        if (evt.unread && activeThreadId.value === evt.thread_id) {
          void markRead(evt.message.id);
        }
        break;
      }
      case "collab_message_read": {
        if (upsertReceipt(evt.receipt)) {
          decrementThreadUnread(evt.thread_id);
        }
        break;
      }
      case "collab_message_action_updated": {
        upsertReceipt(evt.receipt);
        break;
      }
      case "collab_message_deleted": {
        messagesByThread.value = {
          ...messagesByThread.value,
          [evt.thread_id]: (messagesByThread.value[evt.thread_id] || []).filter((message) => message.id !== evt.message_id),
        };
        break;
      }
      case "collab_thread_deleted": {
        threads.value = threads.value.filter((thread) => thread.id !== evt.thread_id);
        const remainingMessages = { ...messagesByThread.value };
        delete remainingMessages[evt.thread_id];
        messagesByThread.value = remainingMessages;
        if (activeThreadId.value === evt.thread_id) {
          activeThreadId.value = threads.value[0]?.id || "";
          if (activeThreadId.value) {
            void loadMessages(activeThreadId.value);
          }
        }
        break;
      }
    }
  }

  function connectStream() {
    disconnectStream();
    const userId = String(auth.userId || "").trim();
    if (!userId) return;
    const requestId = ++streamRequestId;
    collabApi.stream(userId, handleStreamEvent, (status) => {
      if (requestId !== streamRequestId) return;
      streamConnected.value = status === "open";
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
  }

  return {
    threads,
    targets,
    messagesByThread,
    pendingAttachments,
    activeThreadId,
    eventSource,
    streamConnected,
    loadingThreads,
    loadingTargets,
    loadingMessages,
    sending,
    uploading,
    activeThread,
    activeMessages,
    totalUnread,
    canSend,
    loadThreads,
    loadTargets,
    createThread,
    openThread,
    loadMessages,
    uploadAttachments,
    removePendingAttachment,
    clearPendingAttachments,
    sendMessage,
    markRead,
    updateAction,
    archiveThread,
    deleteThread,
    deleteMessage,
    connectStream,
    disconnectStream,
    handleStreamEvent,
  };
});
