import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth.store";
import { useMenu } from "@/composables/useMenu";
import { userApi } from "@/api/user.api";

vi.mock("@/api/user.api", () => ({ userApi: { getMe: vi.fn() } }));

describe("effective permissions in navigation", () => {
  it("keeps result and report destinations inside ordinary-user tasks even with a stale standard-read snapshot", () => {
    const auth = useAuthStore();
    auth.token = "token";
    auth.role = "user";
    auth.roles = ["user"];
    auth.effectivePermissions = [
      "chat",
      "task",
      "result",
      "feedback",
      "product_master_read",
      "inspection_spec_read",
      "inspection_standard_library_read",
    ];
    expect(paths()).toEqual(["/app/chat", "/app/tasks", "/app/results", "/app/profile"]);
    expect(useMenu().menu.value.some((item) => item.title === "已授权功能")).toBe(false);
  });
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  function paths() {
    return useMenu().menu.value.flatMap((item) =>
      "items" in item ? item.items.map((child) => child.path) : [item.path],
    );
  }

  it("filters role menus without adding cross-role features from extra grants", () => {
    const auth = useAuthStore();
    auth.token = "token";
    auth.role = "algorithm_engineer";
    auth.roles = ["algorithm_engineer"];
    auth.effectivePermissions = ["chat", "model_config_read"];
    expect(paths()).not.toContain("/ops/data/import");
    expect(paths()).not.toContain("/app/chat");
    expect(paths()).toContain("/governance/admin/models");
    expect(auth.hasPermission("model_config")).toBe(false);
    expect(auth.resolveDefaultRoute()).toBe("/governance/admin/models");
  });

  it("falls back to the profile when all mapped permissions are revoked", () => {
    const auth = useAuthStore();
    auth.token = "token";
    auth.role = "user";
    auth.roles = ["user"];
    auth.effectivePermissions = [];
    expect(paths()).not.toContain("/app/chat");
    expect(auth.resolveDefaultRoute()).toBe("/app/profile");
    expect(auth.hasPermission("chat")).toBe(false);
  });

  it("refreshes effective permissions and role from the current server profile", async () => {
    const auth = useAuthStore();
    auth.token = "old-token";
    auth.role = "algorithm_engineer";
    vi.mocked(userApi.getMe).mockResolvedValue({
      data: {
        data: {
          role: "user",
          effective_permissions: ["chat"],
        },
      },
    } as Awaited<ReturnType<typeof userApi.getMe>>);
    expect(await auth.refreshPermissions()).toBe(true);
    expect(auth.role).toBe("user");
    expect(auth.hasPermission("chat")).toBe(true);
    expect(auth.hasPermission("dataset")).toBe(false);
    expect(sessionStorage.getItem("piap_role")).toBe("user");
  });

  it("discards an in-flight profile refresh when the session has logged out", async () => {
    const auth = useAuthStore();
    auth.token = "old-token";
    let resolve!: (value: Awaited<ReturnType<typeof userApi.getMe>>) => void;
    vi.mocked(userApi.getMe).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const pending = auth.refreshPermissions();
    auth.logout();
    resolve({ data: { data: { role: "admin", effective_permissions: ["user"] } } } as Awaited<
      ReturnType<typeof userApi.getMe>
    >);
    expect(await pending).toBe(false);
    expect(auth.role).toBe("");
    expect(auth.effectivePermissions).toBeNull();
    expect(auth.hasPermission("user")).toBe(false);
  });
});
