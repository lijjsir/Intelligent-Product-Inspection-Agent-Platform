import { createApp, defineComponent, h, nextTick, type App, type Slots } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { taskApi } from "@/api/task.api";
import { ragSpaceApi } from "@/api/rag-space.api";
import { ROLE_ALGORITHM_ENGINEER, ROLE_EXPERT } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import TaskDetailView from "@/views/TaskDetailView.vue";

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
  back: vi.fn(),
  route: {
    path: "/app/tasks/task-1",
    params: { id: "task-1" },
  },
}));

vi.mock("vue-router", () => ({
  useRoute: () => routerMock.route,
  useRouter: () => ({
    push: routerMock.push,
    back: routerMock.back,
  }),
}));

vi.mock("element-plus", () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock("@/api/task.api", () => ({
  taskApi: {
    get: vi.fn(),
    events: vi.fn(),
    stream: vi.fn(),
    ingest: vi.fn(),
    run: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/api/rag-space.api", () => ({
  ragSpaceApi: {
    list: vi.fn(),
  },
}));

const doneTask = {
  id: "task-1",
  org_id: "org-1",
  product_id: "screw",
  spec_code: "SCREW-A-2026-V1",
  status: "done",
  priority: 5,
  image_urls: ["/uploads/apple.jpg"],
  image_items: [],
  has_result: true,
  has_stability: true,
  result_id: "result-1",
  stability_id: "stability-1",
  created_at: "2026-06-25T20:52:00Z",
  execution: { mode: "celery", job_id: "job-1" },
};

function flushPromises() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

function renderSlots(slots: Slots) {
  return Object.values(slots).flatMap((slot) => slot?.() ?? []);
}

const GenericElementStub = defineComponent({
  setup(_, { slots }) {
    return () => h("div", renderSlots(slots));
  },
});

const ButtonStub = defineComponent({
  props: {
    disabled: Boolean,
  },
  emits: ["click"],
  setup(props, { slots, emit }) {
    return () => h(
      "button",
      {
        disabled: props.disabled,
        onClick: (event: MouseEvent) => emit("click", event),
      },
      slots.default?.(),
    );
  },
});

const DialogStub = defineComponent({
  props: {
    modelValue: Boolean,
    title: String,
  },
  setup(props, { slots }) {
    return () => props.modelValue
      ? h("section", [
        props.title ? h("h3", props.title) : null,
        slots.default?.(),
        slots.footer?.(),
      ])
      : null;
  },
});

function installElementPlusStubs(app: App<Element>) {
  app.directive("loading", () => undefined);
  app.component("el-button", ButtonStub);
  app.component("el-dialog", DialogStub);
  for (const name of [
    "el-alert",
    "el-card",
    "el-descriptions",
    "el-descriptions-item",
    "el-empty",
    "el-form",
    "el-form-item",
    "el-input",
    "el-option",
    "el-radio-button",
    "el-radio-group",
    "el-select",
    "el-tag",
    "el-timeline",
    "el-timeline-item",
  ]) {
    app.component(name, GenericElementStub);
  }
}

function findClickable(root: HTMLElement, label: string): HTMLElement {
  const elements = Array.from(root.querySelectorAll<HTMLElement>("button"));
  const match = elements.find((element) => element.textContent?.includes(label));
  if (!match) {
    throw new Error(`Clickable control with label "${label}" was not found. Rendered text: ${root.textContent}`);
  }
  return match;
}

async function click(root: HTMLElement, label: string) {
  findClickable(root, label).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await flushPromises();
  await nextTick();
}

async function mountTaskDetail(role = ROLE_EXPERT): Promise<{ app: App<Element>; root: HTMLElement }> {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "token-1";
  auth.orgId = "org-1";
  auth.userId = "user-1";
  auth.username = "expect";
  auth.role = role;
  auth.roles = [role];
  auth.planTier = "basic";
  auth.capabilities = [];

  const root = document.createElement("div");
  document.body.appendChild(root);
  const app = createApp(TaskDetailView);
  app.use(pinia);
  installElementPlusStubs(app);
  app.mount(root);
  await flushPromises();
  await nextTick();
  return { app, root };
}

describe("TaskDetailView action buttons", () => {
  let mounted: App<Element> | null = null;

  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = "";
    routerMock.push.mockReset();
    routerMock.back.mockReset();
    vi.mocked(taskApi.get).mockResolvedValue({ data: { data: doneTask } } as any);
    vi.mocked(taskApi.events).mockResolvedValue({ data: { data: [] } } as any);
    vi.mocked(taskApi.stream).mockResolvedValue({ close: vi.fn() } as any);
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
    vi.mocked(ragSpaceApi.list).mockResolvedValue({
      data: {
        data: [{ id: "rag-1", name: "默认知识库" }],
      },
    } as any);
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
  });

  it("opens the analysis result and stability report routes for roles that can access them", async () => {
    const { app, root } = await mountTaskDetail(ROLE_EXPERT);
    mounted = app;

    await click(root, "查看分析结果");
    expect(routerMock.push).toHaveBeenCalledWith("/app/results/task-1");

    await click(root, "查看稳定性评估");
    expect(routerMock.push).toHaveBeenCalledWith("/app/stability/task-1");
  });

  it("opens the ingest dialog and submits the task result ingest request", async () => {
    const { app, root } = await mountTaskDetail(ROLE_EXPERT);
    mounted = app;

    await click(root, "导入检测结果");
    expect(root.textContent).toContain("确认导入");
    expect(ragSpaceApi.list).toHaveBeenCalledWith(200, { suppressErrorToast: true });

    await click(root, "确认导入");
    expect(taskApi.ingest).toHaveBeenCalledWith("task-1", expect.objectContaining({
      target: "rag",
      rag_space_id: "rag-1",
      mode: "candidate",
    }));
  });

  it("does not show result-only navigation buttons to roles blocked by the target routes", async () => {
    const { app, root } = await mountTaskDetail(ROLE_ALGORITHM_ENGINEER);
    mounted = app;

    expect(root.textContent).not.toContain("查看分析结果");
    expect(root.textContent).not.toContain("查看稳定性评估");
    expect(root.textContent).toContain("导入检测结果");
  });
});
