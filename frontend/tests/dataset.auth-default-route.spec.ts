import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useAuthStore } from "@/stores/auth.store";

describe("algorithm engineer default route", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    sessionStorage.clear();
  });

  it("redirects algorithm engineer to dataset import workspace", () => {
    const store = useAuthStore();
    store.role = "algorithm_engineer" as any;
    store.roles = ["algorithm_engineer"] as any;

    expect(store.resolveDefaultRoute()).toBe("/ops/data/import");
  });
});
