import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useAuthStore } from "@/stores/auth.store";
import { useMenu } from "@/composables/useMenu";

describe("algorithm engineer workspace menu", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    sessionStorage.clear();
  });

  it("exposes clickable algorithm engineer workspace entries", () => {
    const auth = useAuthStore();
    auth.role = "algorithm_engineer" as any;
    auth.roles = ["algorithm_engineer"] as any;

    const { menu } = useMenu();
    const paths = [
      "/ops/data/import",
      "/ops/data/eval-sets",
      "/ops/training/jobs",
      "/ops/training/fine-tune",
      "/ops/eval/offline",
      "/ops/eval/online",
      "/ops/experiments",
      "/ops/deployments",
    ];

    for (const path of paths) {
      const item = menu.value.find((entry) => "path" in entry && entry.path === path);
      expect(item).toBeTruthy();
      expect("placeholder" in (item as Record<string, unknown>) ? (item as { placeholder?: boolean }).placeholder : undefined).toBeUndefined();
    }
  });
});
