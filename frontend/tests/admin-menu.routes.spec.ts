import { describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";
import { ROLE_ADMIN } from "@/constants/roles";
import { appRoutes } from "@/router/routes/app.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";
import { opsRoutes } from "@/router/routes/ops.routes";

describe("admin menu routes", () => {
  it("maps every admin menu entry to a registered top-level route", () => {
    setActivePinia(createPinia());

    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    const { menu } = useMenu();
    const adminPaths = menu.value.flatMap((item) => ("items" in item ? item.items.map((child) => child.path) : [item.path]));

    const registeredPaths = new Set([
      ...appRoutes.map((route) => `/app/${route.path}`),
      ...opsRoutes.map((route) => `/ops/${route.path}`),
      ...governanceRoutes.map((route) => `/governance/${route.path}`),
    ]);

    for (const path of adminPaths) {
      expect(registeredPaths.has(path)).toBe(true);
    }
  });
});
