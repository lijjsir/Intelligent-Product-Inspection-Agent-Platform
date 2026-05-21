import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";

describe("algorithm engineer menu", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("exposes dataset import as a clickable menu item", () => {
    const auth = useAuthStore();
    auth.role = "algorithm_engineer";
    auth.roles = ["algorithm_engineer"];

    const { menu } = useMenu();
    const datasetImport = menu.value.find((item) => "path" in item && item.path === "/ops/data/import");

    expect(datasetImport).toBeTruthy();
    expect("placeholder" in (datasetImport as Record<string, unknown>) ? (datasetImport as { placeholder?: boolean }).placeholder : undefined).toBeUndefined();
  });
});
