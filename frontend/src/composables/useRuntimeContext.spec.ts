import { afterEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
vi.mock("@/api/http", () => ({ http: { get } }));
afterEach(() => { vi.resetModules(); get.mockReset(); });

describe("server-owned environment identity", () => {
  it("does not enable demo mode from a browser query", async () => {
    window.history.replaceState({}, "", "/?demo=1&execution_mode=demo");
    get.mockResolvedValue({ data: { data: { execution_mode: "business", label: "业务环境" } } });
    const { useRuntimeContext } = await import("./useRuntimeContext");
    const runtime = useRuntimeContext();
    await runtime.load();
    expect(runtime.context.value?.execution_mode).toBe("business");
    expect(get).toHaveBeenCalledWith("/v1/runtime-context", { suppressErrorToast: true });
  });
  it("shares the server result across login and workspace", async () => {
    get.mockResolvedValue({ data: { data: { execution_mode: "demo", label: "演示环境" } } });
    const { useRuntimeContext } = await import("./useRuntimeContext");
    await Promise.all([useRuntimeContext().load(), useRuntimeContext().load()]);
    expect(get).toHaveBeenCalledTimes(1);
    expect(useRuntimeContext().context.value?.execution_mode).toBe("demo");
  });
  it("reports missing environment information instead of guessing demo", async () => {
    get.mockRejectedValue(new Error("offline"));
    const { useRuntimeContext } = await import("./useRuntimeContext");
    const runtime = useRuntimeContext();
    await runtime.load();
    expect(runtime.context.value).toBeNull();
    expect(runtime.unavailable.value).toBe(true);
  });
});
