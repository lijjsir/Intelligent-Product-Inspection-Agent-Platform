import { describe, expect, it, vi, beforeEach } from "vitest";

const postMock = vi.fn();

vi.mock("@/api/http", () => ({
  http: {
    post: postMock,
  },
}));

describe("chat api stream", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it("subscribes to named sse message events", async () => {
    const addEventListener = vi.fn();
    const source = {
      addEventListener,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    };
    const EventSourceMock = vi.fn(() => source);
    vi.stubGlobal("EventSource", EventSourceMock as unknown as typeof EventSource);
    postMock.mockResolvedValue({
      data: {
        data: {
          stream_token: "token-1",
          expires_at: "2026-05-25T00:00:00Z",
          resource: "chat",
          resource_id: "session-1",
        },
      },
    });

    const { chatApi } = await import("@/api/chat.api");
    await chatApi.stream("session-1", 0, vi.fn());

    expect(EventSourceMock).toHaveBeenCalledTimes(1);
    expect(addEventListener).toHaveBeenCalledWith("message", expect.any(Function));
    expect(addEventListener).toHaveBeenCalledWith("ready", expect.any(Function));
    expect(typeof source.onmessage).toBe("function");
  });
});
