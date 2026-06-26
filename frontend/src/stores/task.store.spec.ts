import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { taskApi } from "@/api/task.api";
import { useTaskStore } from "@/stores/task.store";

vi.mock("@/api/task.api", () => ({
  taskApi: {
    get: vi.fn(),
    run: vi.fn(),
    events: vi.fn(),
    ingest: vi.fn(),
    stream: vi.fn(),
  },
}));

describe("task store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(taskApi.get).mockReset();
    vi.mocked(taskApi.run).mockReset();
    vi.mocked(taskApi.ingest).mockReset();
    vi.mocked(taskApi.stream).mockReset();
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

  it("sends completed task result ingest requests through the task API", async () => {
    vi.mocked(taskApi.ingest).mockResolvedValue({
      data: {
        data: {
          task_id: "task-1",
          target: "rag",
          mode: "candidate",
          rag_space_id: "rag-1",
          dataset_id: null,
          dataset_name: null,
          created_document_count: 1,
          created_sample_count: 0,
          skipped_count: 0,
          warnings: [],
        },
      },
    } as any);

    const store = useTaskStore();
    const result = await store.ingestTaskResult("task-1", {
      target: "rag",
      rag_space_id: "rag-1",
      mode: "candidate",
    });

    expect(taskApi.ingest).toHaveBeenCalledWith("task-1", {
      target: "rag",
      rag_space_id: "rag-1",
      mode: "candidate",
    });
    expect(result.created_document_count).toBe(1);
  });

  it("passes stream lifecycle callbacks to the task API", async () => {
    const source = { close: vi.fn() };
    vi.mocked(taskApi.stream).mockResolvedValue(source as unknown as EventSource);

    const store = useTaskStore();
    const onMessage = vi.fn();
    const lifecycle = {
      onOpen: vi.fn(),
      onError: vi.fn(),
      onHeartbeat: vi.fn(),
    };
    const unsubscribe = store.subscribeTaskStream("task-1", onMessage, lifecycle);
    await Promise.resolve();

    expect(taskApi.stream).toHaveBeenCalledWith("task-1", onMessage, lifecycle);
    unsubscribe();
    expect(source.close).toHaveBeenCalledOnce();
  });
});
