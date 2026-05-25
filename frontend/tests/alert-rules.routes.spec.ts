import { describe, expect, it } from "vitest";
import { governanceRoutes } from "@/router/routes/governance.routes";

describe("alert rule governance routes", () => {
  it("registers the admin alert rule route used by the admin menu", () => {
    const route = governanceRoutes.find((item) => item.path === "admin/alert-rules");

    expect(route).toBeTruthy();
    expect(route?.name).toBe("governance-admin-alert-rules");
    expect(route?.meta?.roles).toContain("admin");
  });
});
