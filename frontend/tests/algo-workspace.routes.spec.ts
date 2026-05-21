import { describe, expect, it } from "vitest";

import { opsRoutes } from "@/router/routes/ops.routes";

describe("algorithm engineer workspace routes", () => {
  it("exposes real algorithm engineer routes instead of placeholders", () => {
    const routeNames = [
      "ops-data-processing",
      "ops-data-eval-sets",
      "ops-training-jobs",
      "ops-training-fine-tune",
      "ops-eval-offline",
      "ops-eval-online",
      "ops-experiments",
      "ops-deployments",
    ];

    for (const name of routeNames) {
      const route = opsRoutes.find((item) => item.name === name);
      expect(route).toBeTruthy();
      expect(route?.meta?.roles).toContain("algorithm_engineer");
      expect(route?.component).toBeTruthy();
    }
  });

  it("registers hidden detail routes for algorithm engineer resources", () => {
    const detailNames = [
      "ops-data-eval-sets-detail",
      "ops-training-jobs-detail",
      "ops-training-fine-tune-detail",
      "ops-eval-offline-detail",
      "ops-eval-online-detail",
      "ops-experiments-detail",
      "ops-deployments-detail",
    ];

    for (const name of detailNames) {
      const route = opsRoutes.find((item) => item.name === name);
      expect(route?.path).toContain(":id");
    }
  });
});
