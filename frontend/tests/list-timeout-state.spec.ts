import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useResultStore } from "@/stores/result.store";
import { useTaskStore } from "@/stores/task.store";

vi.mock("@/api/result.api", () => ({
  resultApi: {
    list: vi.fn(),
    getByTask: vi.fn(),
    review: vi.fn(),
  },
}));

vi.mock("@/api/task.api", () => ({
  taskApi: {
    list: vi.fn(),
    get: vi.fn(),
    events: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    run: vi.fn(),
    ingest: vi.fn(),
    stream: vi.fn(),
  },
}));

describe("list timeout state", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("keeps previous result rows when list refresh times out", async () => {
    const { resultApi } = await import("@/api/result.api");
    const store = useResultStore();
    store.items = [{ id: "result-1", task_id: "task-1" } as never];
    store.total = 1;
    resultApi.list = vi.fn().mockRejectedValue({ code: "ECONNABORTED", message: "timeout" });

    const data = await store.fetchResults({ page: 1, size: 20 });

    expect(store.items).toEqual([{ id: "result-1", task_id: "task-1" }]);
    expect(store.total).toBe(1);
    expect(store.listError).toContain("后端暂不可用");
    expect(data.items).toEqual(store.items);
  });

  it("keeps previous task rows when list refresh times out", async () => {
    const { taskApi } = await import("@/api/task.api");
    const store = useTaskStore();
    store.items = [{ id: "task-1", status: "pending" } as never];
    store.total = 1;
    taskApi.list = vi.fn().mockRejectedValue({ code: "ECONNABORTED", message: "timeout" });

    await store.fetchTasks({ page: 1, size: 20 });

    expect(store.items).toEqual([{ id: "task-1", status: "pending" }]);
    expect(store.total).toBe(1);
    expect(store.listError).toContain("后端暂不可用");
  });
});
