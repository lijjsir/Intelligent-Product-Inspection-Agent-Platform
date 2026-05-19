import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { taskApi } from "@/api/task.api";
import { useTaskStore } from "@/stores/task.store";

vi.mock("@/api/task.api", () => ({
  taskApi: {
    get: vi.fn(),
    run: vi.fn(),
    events: vi.fn(),
  },
}));

describe("task store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(taskApi.get).mockReset();
    vi.mocked(taskApi.run).mockReset();
  });

  it("refreshes the current task after starting execution", async () => {
    vi.mocked(taskApi.run).mockResolvedValue({
      data: { data: { mode: "celery", job_id: "job-1", status: "queued" } },
    } as any);
    vi.mocked(taskApi.get).mockResolvedValue({
      data: {
        data: {
          id: "task-1",
          org_id: "org-1",
          product_id: "P-1",
          spec_code: "STD-1",
          status: "queued",
          priority: 5,
          image_urls: [],
        },
      },
    } as any);

    const store = useTaskStore();
    const result = await store.runTask("task-1");

    expect(result.status).toBe("queued");
    expect(taskApi.get).toHaveBeenCalledWith("task-1");
    expect(store.current?.status).toBe("queued");
  });
});
