import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useChatStore } from "@/stores/chat.store";
import { chatApi } from "@/api/chat.api";
import { ragSpaceApi } from "@/api/rag-space.api";

vi.mock("@/api/chat.api", () => ({
  chatApi: {
    listSessions: vi.fn(),
    listMessages: vi.fn(),
    createSession: vi.fn(),
  },
}));

vi.mock("@/api/rag-space.api", () => ({
  ragSpaceApi: {
    list: vi.fn(),
  },
}));

describe("chat store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    sessionStorage.clear();
    vi.mocked(chatApi.listSessions).mockReset();
    vi.mocked(chatApi.listMessages).mockReset();
    vi.mocked(chatApi.createSession).mockReset();
    vi.mocked(ragSpaceApi.list).mockReset();
  });

  it("preserves the saved RAG space when initializing the chat page", async () => {
    sessionStorage.setItem("chat_current_session_id", "session-1");
    sessionStorage.setItem("chat_selected_rag_space_id", "rag-1");
    vi.mocked(chatApi.listSessions).mockResolvedValue({
      data: {
        data: [
          {
            id: "session-1",
            title: "Session",
            created_at: "",
            updated_at: "",
            last_message_at: "",
          },
        ],
      },
    } as any);
    vi.mocked(ragSpaceApi.list).mockResolvedValue({
      data: { data: [{ id: "rag-1", name: "RAG Space", description: null }] },
    } as any);
    vi.mocked(chatApi.listMessages).mockResolvedValue({ data: { data: [] } } as any);

    const store = useChatStore();

    await store.initForChatPage();

    expect(store.selectedRagSpaceId).toBe("rag-1");
    expect(sessionStorage.getItem("chat_selected_rag_space_id")).toBe("rag-1");
  });
});
