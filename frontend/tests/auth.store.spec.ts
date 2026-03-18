import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useAuthStore } from "@/stores/auth.store";
import type { AuthSession } from "@/types/auth.types";

vi.mock("@/api/auth.api", () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
  },
}));

const session: AuthSession = {
  access_token: "access",
  refresh_token: "refresh",
  token_type: "bearer",
  expires_in: 900,
  user_id: "u1",
  org_id: "org1",
  role: "org_admin",
};

describe("auth store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
  });

  it("login sets session", async () => {
    const { authApi } = await import("@/api/auth.api");
    authApi.login = vi.fn().mockResolvedValue({ data: session });

    const store = useAuthStore();
    await store.login({ org_id: "org1", username: "a", password: "b" });

    expect(store.token).toBe("access");
    expect(localStorage.getItem("piap_token")).toBe("access");
    expect(localStorage.getItem("piap_org_id")).toBe("org1");
  });

  it("register sets session", async () => {
    const { authApi } = await import("@/api/auth.api");
    authApi.register = vi.fn().mockResolvedValue({ data: session });

    const store = useAuthStore();
    await store.register({
      org_name: "PIAP",
      org_slug: "piap",
      username: "admin",
      email: "a@a.com",
      password: "pw",
    });

    expect(store.userId).toBe("u1");
    expect(store.role).toBe("org_admin");
  });

  it("logout clears session", () => {
    const store = useAuthStore();
    store.logout();
    expect(store.token).toBe("");
    expect(localStorage.getItem("piap_token")).toBe(null);
  });
});
