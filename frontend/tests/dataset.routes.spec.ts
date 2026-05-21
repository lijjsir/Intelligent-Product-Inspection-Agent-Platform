import { describe, expect, it } from "vitest";

import { opsRoutes } from "@/router/routes/ops.routes";

describe("dataset import routes", () => {
  it("exposes list and detail routes for algorithm engineer", () => {
    const listRoute = opsRoutes.find((route) => route.name === "ops-data-import");
    const detailRoute = opsRoutes.find((route) => route.name === "ops-data-import-detail");

    expect(listRoute?.path).toBe("data/import");
    expect(detailRoute?.path).toBe("data/import/:id");
    expect(listRoute?.meta?.roles).toContain("algorithm_engineer");
    expect(detailRoute?.meta?.roles).toContain("algorithm_engineer");
  });
});
