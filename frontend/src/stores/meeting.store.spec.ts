import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { meetingApi } from "@/api/meeting.api";
import { useAuthStore } from "@/stores/auth.store";
import { useMeetingStore } from "@/stores/meeting.store";

vi.mock("@/api/meeting.api", () => ({
  meetingApi: {
    listRooms: vi.fn(),
    listAgentQueryAudits: vi.fn(),
    listActionItems: vi.fn(),
    listMemories: vi.fn(),
    listConflicts: vi.fn(),
    listPendingMemoryShares: vi.fn(),
    getContextPreview: vi.fn(),
    runGeneralAgent: vi.fn(),
    stream: vi.fn(),
  },
}));

describe("meeting store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const auth = useAuthStore();
    auth.userId = "user-1";
    vi.mocked(meetingApi.listRooms).mockReset();
    vi.mocked(meetingApi.listAgentQueryAudits).mockReset();
    vi.mocked(meetingApi.listActionItems).mockReset();
    vi.mocked(meetingApi.listMemories).mockReset();
    vi.mocked(meetingApi.listConflicts).mockReset();
    vi.mocked(meetingApi.listPendingMemoryShares).mockReset();
    vi.mocked(meetingApi.getContextPreview).mockReset();
    vi.mocked(meetingApi.runGeneralAgent).mockReset();
    vi.mocked(meetingApi.stream).mockReset();
    vi.mocked(meetingApi.listRooms).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.listAgentQueryAudits).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.listActionItems).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.listMemories).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.listConflicts).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.listPendingMemoryShares).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(meetingApi.getContextPreview).mockResolvedValue({ data: { data: null } } as any);
  });

  it("loads meeting rooms from the active list", async () => {
    const store = useMeetingStore();
    vi.mocked(meetingApi.listRooms).mockResolvedValueOnce({
      data: { data: [{ id: "room-1", status: "active" }] },
    } as any);

    await store.loadRooms();

    expect(meetingApi.listRooms).toHaveBeenLastCalledWith(100);
    expect(store.rooms).toHaveLength(1);
  });

  it("reuses the local agent placeholder when stream starts", async () => {
    const store = useMeetingStore();
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";
    vi.mocked(meetingApi.runGeneralAgent).mockImplementation(async () => {
      store.handleStreamEvent({
        event: "agent_run_started",
        room_id: "room-1",
        message_id: "stream-msg-1",
        agent_id: "general_agent",
        agent_name: "会议Agent",
        workflow_run_id: "run-1",
      });
      return {
        data: {
          data: {
            selected_subgraph: "auto",
            answer: "ok",
            memory_sources: [],
            candidate_memories: [],
            message: {
              id: "stream-msg-1",
              room_id: "room-1",
              user_id: "general_agent",
              username: "会议Agent",
              seq_no: 1,
              content: "ok",
              message_type: "agent",
              agent_id: "general_agent",
              metadata_json: { visibility: "room", audience_scope_type: "meeting_room", audience_scope_id: "room-1" },
              created_at: "2026-06-11T06:10:00Z",
            },
          },
        },
      } as any;
    });

    const promise = store.runGeneralAgent("auto", "report style");

    expect(store.messages.filter((message) => message.message_type === "agent_streaming")).toHaveLength(1);
    expect(store.messages[0].id).toBe("stream-msg-1");

    await promise;
    expect(store.messages).toHaveLength(1);
    expect(store.messages[0].message_type).toBe("agent");
    expect(store.messages[0].content).toBe("ok");
    expect(store.messages[0].metadata_json?.visibility).toBe("room");
  });

  it("passes sidecar attachments to general agent requests", async () => {
    const store = useMeetingStore();
    const attachment = {
      id: "att-1",
      name: "screenshot.png",
      url: "/api/v1/files/chat-attachments/screenshot.png",
      content_type: "image/png",
      size_bytes: 1234,
      kind: "image",
      bucket: "chat-attachments",
      object_key: "screenshot.png",
    };
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";
    vi.mocked(meetingApi.runGeneralAgent).mockResolvedValue({
      data: {
        data: {
          selected_subgraph: "auto",
          answer: "ok",
          memory_sources: [],
          candidate_memories: [],
          message: {
            id: "agent-msg-1",
            room_id: "room-1",
            user_id: "general_agent",
            username: "会议Agent",
            seq_no: 1,
            content: "ok",
            message_type: "agent",
            agent_id: "general_agent",
            metadata_json: { attachment_echo: [attachment], visibility: "room", audience_scope_type: "meeting_room", audience_scope_id: "room-1" },
            created_at: "2026-06-11T06:10:00Z",
          },
        },
      },
    } as any);

    const promise = store.runGeneralAgent("auto", "inspect this", { attachments: [attachment] as any });

    expect(meetingApi.runGeneralAgent).toHaveBeenCalledWith(
      "room-1",
      expect.objectContaining({
        attachments: [attachment],
        memory_scope: expect.objectContaining({
          include_meeting: true,
          include_confirmed: true,
          include_personal_authorized: false,
          include_user: false,
          include_agent: true,
          include_org_space: true,
        }),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(store.messages[0].metadata_json?.attachment_echo).toEqual([attachment]);

    await promise;
    expect(store.messages[0].metadata_json?.attachment_echo).toEqual([attachment]);
    expect(store.messages[0].metadata_json?.visibility).toBe("room");
  });

  it("updates the streaming message by stream id on final event", () => {
    const store = useMeetingStore();
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";

    store.handleStreamEvent({
      event: "agent_run_started",
      room_id: "room-1",
      message_id: "stream-msg-1",
      agent_id: "general_agent",
      agent_name: "会议Agent",
      workflow_run_id: "run-1",
    });
    store.handleStreamEvent({
      event: "message_final",
      room_id: "room-1",
      message_id: "stream-msg-1",
      agent_id: "general_agent",
      content: "final answer",
      workflow_run_id: "run-1",
    });

    expect(store.messages).toHaveLength(1);
    expect(store.messages[0]).toMatchObject({
      id: "stream-msg-1",
      message_type: "agent",
      content: "final answer",
      metadata_json: { visibility: "room", audience_scope_type: "meeting_room", audience_scope_id: "room-1" },
    });
  });

  it("splits member conversation from agent sidecar messages", () => {
    const store = useMeetingStore();
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";
    store.messages = [
      {
        id: "msg-1",
        room_id: "room-1",
        user_id: "user-1",
        username: "成员A",
        seq_no: 1,
        content: "大家看一下这个批次",
        message_type: "user",
      },
      {
        id: "msg-2",
        room_id: "room-1",
        user_id: "user-1",
        username: "成员A",
        seq_no: 2,
        content: "@会议Agent 总结一下",
        message_type: "user",
        mentions: [{ agent_id: "general_agent", agent_name: "会议Agent" }],
      },
      {
        id: "msg-3",
        room_id: "room-1",
        user_id: "general_agent",
        username: "会议Agent",
        seq_no: 3,
        content: "侧栏回复",
        message_type: "agent",
        agent_id: "general_agent",
      },
      {
        id: "msg-4",
        room_id: "room-1",
        user_id: "system",
        username: "系统",
        seq_no: 4,
        content: "会议待办已完成：质检任务讨论",
        message_type: "system",
      },
    ] as any;

    expect(store.conversationMessages.map((message) => message.id)).toEqual(["msg-1", "msg-2"]);
    expect(store.agentPanelMessages.map((message) => message.id)).toEqual(["msg-2", "msg-3"]);
    expect(store.systemPanelMessages.map((message) => message.id)).toEqual(["msg-4"]);
  });

  it("keeps meeting summaries in the system panel feed", () => {
    const store = useMeetingStore();
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";
    store.messages = [
      {
        id: "msg-user",
        room_id: "room-1",
        user_id: "user-1",
        username: "member",
        seq_no: 1,
        content: "hello",
        message_type: "user",
      },
      {
        id: "msg-summary",
        room_id: "room-1",
        user_id: "general_agent",
        username: "meeting summary",
        seq_no: 2,
        content: "latest summary",
        message_type: "summary",
      },
    ] as any;

    expect(store.conversationMessages.map((message) => message.id)).toEqual(["msg-user"]);
    expect(store.systemPanelMessages.map((message) => message.id)).toEqual(["msg-summary"]);
  });

  it("routes stream failure visibility from event audience", () => {
    const store = useMeetingStore();
    store.rooms = [{ id: "room-1", status: "active" }] as any;
    store.activeRoomId = "room-1";

    store.handleStreamEvent({
      event: "agent_run_failed",
      room_id: "room-1",
      message_id: "failed-msg-1",
      agent_id: "general_agent",
      agent_name: "浼氭Agent",
      workflow_run_id: "run-1",
      error: "boom",
    });
    store.handleStreamEvent({
      event: "agent_run_failed",
      room_id: "room-1",
      message_id: "failed-msg-2",
      agent_id: "general_agent",
      agent_name: "浼氭Agent",
      workflow_run_id: "run-2",
      error: "secret boom",
      private_user_ids: ["user-1"],
    });

    expect(store.messages[0]).toMatchObject({
      id: "failed-msg-1",
      message_type: "agent",
      metadata_json: { visibility: "room", audience_scope_type: "meeting_room", audience_scope_id: "room-1" },
    });
    expect(store.messages[1]).toMatchObject({
      id: "failed-msg-2",
      message_type: "agent",
      metadata_json: { private_recipient_user_id: "user-1" },
    });
  });
});
