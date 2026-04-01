import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useChatStore } from "@/stores/chat.store";

vi.mock("@/api/chat.api", () => ({
  chatApi: {
    listSessions: vi.fn(),
    createSession: vi.fn(),
    listMessages: vi.fn(),
    sendMessage: vi.fn(),
    appendTaskResult: vi.fn(),
    uploadAttachments: vi.fn(),
    deleteSession: vi.fn(),
    stream: vi.fn(),
  },
}));

vi.mock("@/api/rag-space.api", () => ({
  ragSpaceApi: {
    list: vi.fn().mockResolvedValue({ data: { data: [] } }),
    create: vi.fn(),
    uploadDocuments: vi.fn(),
  },
}));

describe("chat store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    sessionStorage.clear();
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-1" });
  });

  it("creates a local assistant placeholder after sending a message", async () => {
    const { chatApi } = await import("@/api/chat.api");
    chatApi.createSession = vi.fn().mockResolvedValue({
      data: {
        data: {
          id: "session-1",
          org_id: "org-1",
          user_id: "user-1",
          status: "active",
        },
      },
    });
    chatApi.listSessions = vi.fn().mockResolvedValue({ data: { data: [] } });
    chatApi.sendMessage = vi.fn().mockResolvedValue({
      data: {
        data: {
          session: {
            id: "session-1",
            org_id: "org-1",
            user_id: "user-1",
            status: "active",
          },
          user_message: {
            id: "msg-user",
            session_id: "session-1",
            seq_no: 1,
            role: "user",
            message_type: "text",
            content: "什么是毛刺？",
            payload: {},
          },
          assistant_message_id: "msg-assistant",
          workflow_run_id: "run-1",
        },
      },
    });

    const store = useChatStore();
    await store.createNewSession("新会话");
    const sendPromise = store.sendMessage({ message: "什么是毛刺？" });

    expect(store.messages).toHaveLength(2);
    expect(store.messages[0].role).toBe("user");
    expect(store.messages[1].role).toBe("assistant");

    await sendPromise;

    expect(store.messages).toHaveLength(2);
    expect(store.messages[1].id).toBe("msg-assistant");
    expect(store.messages[1].message_type).toBe("streaming");
    expect(store.messages[1].payload?.workflow_run_id).toBe("run-1");
  });

  it("keeps chat initialization available when rag spaces fail to load", async () => {
    const { chatApi } = await import("@/api/chat.api");
    const { ragSpaceApi } = await import("@/api/rag-space.api");

    chatApi.listSessions = vi.fn().mockResolvedValue({ data: { data: [] } });
    chatApi.createSession = vi.fn().mockResolvedValue({
      data: {
        data: {
          id: "session-1",
          org_id: "org-1",
          user_id: "user-1",
          status: "active",
        },
      },
    });
    chatApi.stream = vi.fn().mockResolvedValue({
      close: vi.fn(),
      onopen: null,
      onerror: null,
      readyState: 1,
    });
    ragSpaceApi.list = vi.fn().mockRejectedValue({
      response: {
        data: {
          message: "RAG 空间尚未初始化，请先完成数据库迁移。",
        },
      },
    });

    const store = useChatStore();
    await expect(store.initForChatPage()).resolves.toBeUndefined();

    expect(store.session?.id).toBe("session-1");
    expect(store.ragSpaces).toEqual([]);
    expect(store.ragSpacesError).toBe("RAG 空间尚未初始化，请先完成数据库迁移。");
  });
});
