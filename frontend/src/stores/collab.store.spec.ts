import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { collabApi } from "@/api/collab.api";
import { useAuthStore } from "@/stores/auth.store";
import { useCollabStore } from "@/stores/collab.store";
import type { CollabMessage, CollabMessageReceipt, CollabThread } from "@/types/collab.types";

vi.mock("@/api/collab.api", () => ({
  collabApi: {
    listThreads: vi.fn(),
    listTargets: vi.fn(),
    createThread: vi.fn(),
    listMessages: vi.fn(),
    sendMessage: vi.fn(),
    markRead: vi.fn(),
    updateAction: vi.fn(),
    deleteThread: vi.fn(),
    uploadAttachments: vi.fn(),
    stream: vi.fn(),
  },
}));

function thread(overrides: Partial<CollabThread> = {}): CollabThread {
  return {
    id: "thread-1",
    org_id: "org-1",
    thread_type: "user_to_user",
    source_type: "user",
    source_id: "user-2",
    target_type: "user",
    target_id: "user-1",
    title: "协作线程",
    status: "active",
    created_by: "user-2",
    last_message_at: null,
    unread_count: 0,
    metadata_json: null,
    participants: [],
    created_at: "2026-06-22T10:00:00Z",
    updated_at: "2026-06-22T10:00:00Z",
    ...overrides,
  };
}

function receipt(overrides: Partial<CollabMessageReceipt> = {}): CollabMessageReceipt {
  return {
    id: "receipt-1",
    message_id: "message-1",
    thread_id: "thread-1",
    recipient_type: "user",
    recipient_id: "user-1",
    delivered_at: "2026-06-22T10:01:00Z",
    read_at: null,
    acted_at: null,
    action_status: "pending",
    ...overrides,
  };
}

function message(overrides: Partial<CollabMessage> = {}): CollabMessage {
  return {
    id: "message-1",
    org_id: "org-1",
    thread_id: "thread-1",
    sender_type: "user",
    sender_id: "user-2",
    message_type: "text",
    content: "请看一下这份数据",
    reply_to_message_id: null,
    metadata_json: null,
    attachments: [],
    receipts: [receipt()],
    created_at: "2026-06-22T10:01:00Z",
    updated_at: "2026-06-22T10:01:00Z",
    ...overrides,
  };
}

describe("collab store stream handling", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const auth = useAuthStore();
    auth.userId = "user-1";
    vi.mocked(collabApi.listThreads).mockReset();
    vi.mocked(collabApi.markRead).mockReset();
    vi.mocked(collabApi.listMessages).mockReset();
    vi.mocked(collabApi.listThreads).mockResolvedValue(
      { data: { code: 0, message: "ok", data: [] } } as unknown as Awaited<ReturnType<typeof collabApi.listThreads>>,
    );
    vi.mocked(collabApi.listMessages).mockResolvedValue(
      { data: { code: 0, message: "ok", data: [] } } as unknown as Awaited<ReturnType<typeof collabApi.listMessages>>,
    );
    vi.mocked(collabApi.stream).mockReset();
  });

  it("adds incoming messages and increments unread for inactive threads", () => {
    const store = useCollabStore();
    store.threads = [thread()];
    store.activeThreadId = "thread-other";

    store.handleStreamEvent({
      event: "collab_message_created",
      thread_id: "thread-1",
      message: message(),
      unread: true,
    });

    expect(store.messagesByThread["thread-1"]).toHaveLength(1);
    expect(store.threads[0]).toMatchObject({
      id: "thread-1",
      unread_count: 1,
      last_message_at: "2026-06-22T10:01:00Z",
    });
    expect(collabApi.markRead).not.toHaveBeenCalled();
  });

  it("applies read receipts without double decrementing unread counts", () => {
    const store = useCollabStore();
    const readReceipt = receipt({ read_at: "2026-06-22T10:02:00Z" });
    store.threads = [thread({ unread_count: 1 })];
    store.messagesByThread = { "thread-1": [message()] };

    store.handleStreamEvent({
      event: "collab_message_read",
      thread_id: "thread-1",
      message_id: "message-1",
      receipt: readReceipt,
    });
    store.handleStreamEvent({
      event: "collab_message_read",
      thread_id: "thread-1",
      message_id: "message-1",
      receipt: readReceipt,
    });

    expect(store.threads[0].unread_count).toBe(0);
    expect(store.messagesByThread["thread-1"][0].receipts[0].read_at).toBe("2026-06-22T10:02:00Z");
  });

  it("applies action receipts and moves the thread without adding unread by itself", () => {
    const store = useCollabStore();
    const actedReceipt = receipt({
      recipient_id: "user-2",
      action_status: "rejected",
      acted_at: "2026-06-22T10:05:00Z",
      read_at: "2026-06-22T10:05:00Z",
    });
    store.activeThreadId = "thread-other";
    store.threads = [thread({ unread_count: 0, last_message_at: "2026-06-22T10:01:00Z" })];
    store.messagesByThread = { "thread-1": [message({ sender_id: "user-1", receipts: [receipt({ recipient_id: "user-2" })] })] };

    store.handleStreamEvent({
      event: "collab_message_action_updated",
      thread_id: "thread-1",
      message_id: "message-1",
      receipt: actedReceipt,
    });

    expect(store.threads[0]).toMatchObject({
      id: "thread-1",
      unread_count: 0,
      last_message_at: "2026-06-22T10:05:00Z",
    });
    expect(store.messagesByThread["thread-1"][0].receipts[0]).toMatchObject({
      action_status: "rejected",
      acted_at: "2026-06-22T10:05:00Z",
    });
  });

  it("removes deleted collaboration records from the inbox", () => {
    const store = useCollabStore();
    store.activeThreadId = "thread-1";
    store.threads = [thread(), thread({ id: "thread-2", title: "另一条记录" })];
    store.messagesByThread = {
      "thread-1": [message()],
      "thread-2": [message({ id: "message-2", thread_id: "thread-2" })],
    };

    store.handleStreamEvent({
      event: "collab_thread_deleted",
      thread_id: "thread-1",
    });

    expect(store.threads.map((item) => item.id)).toEqual(["thread-2"]);
    expect(store.messagesByThread["thread-1"]).toBeUndefined();
    expect(store.activeThreadId).toBe("thread-2");
  });

  it("does not keep the thread list loading while messages are still loading", async () => {
    const store = useCollabStore();
    let resolveMessages!: (value: Awaited<ReturnType<typeof collabApi.listMessages>>) => void;
    vi.mocked(collabApi.listThreads).mockResolvedValueOnce(
      { data: { code: 0, message: "ok", data: [thread()] } } as unknown as Awaited<ReturnType<typeof collabApi.listThreads>>,
    );
    vi.mocked(collabApi.listMessages).mockImplementationOnce(() => new Promise((resolve) => {
      resolveMessages = resolve;
    }));

    const threads = await store.loadThreads(true);

    expect(threads).toHaveLength(1);
    expect(store.loadingThreads).toBe(false);
    expect(store.loadingMessages).toBe(true);

    resolveMessages(
      { data: { code: 0, message: "ok", data: [] } } as unknown as Awaited<ReturnType<typeof collabApi.listMessages>>,
    );
    await Promise.resolve();
    expect(store.loadingMessages).toBe(false);
  });

  it("does not keep messages loading while read receipts are still pending", async () => {
    const store = useCollabStore();
    let resolveRead!: (value: Awaited<ReturnType<typeof collabApi.markRead>>) => void;
    vi.mocked(collabApi.listMessages).mockResolvedValueOnce(
      { data: { code: 0, message: "ok", data: [message()] } } as unknown as Awaited<ReturnType<typeof collabApi.listMessages>>,
    );
    vi.mocked(collabApi.markRead).mockImplementationOnce(() => new Promise((resolve) => {
      resolveRead = resolve;
    }));

    const items = await store.loadMessages("thread-1");

    expect(items).toHaveLength(1);
    expect(store.loadingMessages).toBe(false);
    expect(collabApi.markRead).toHaveBeenCalledWith("message-1");

    resolveRead(
      { data: { code: 0, message: "ok", data: receipt({ read_at: "2026-06-22T10:02:00Z" }) } } as unknown as Awaited<ReturnType<typeof collabApi.markRead>>,
    );
    await Promise.resolve();
  });

  it("connects the collaboration stream for the current user", async () => {
    const store = useCollabStore();
    const source = { close: vi.fn() } as unknown as EventSource;
    vi.mocked(collabApi.stream).mockImplementation(async (_userId, _onEvent, onStatus) => {
      onStatus?.("open");
      return source;
    });

    store.connectStream();
    await Promise.resolve();

    expect(collabApi.stream).toHaveBeenCalledWith("user-1", expect.any(Function), expect.any(Function));
    expect(store.streamConnected).toBe(true);
    expect(store.eventSource).toBe(source);

    store.disconnectStream();
    expect(source.close).toHaveBeenCalled();
    expect(store.streamConnected).toBe(false);
  });
});
