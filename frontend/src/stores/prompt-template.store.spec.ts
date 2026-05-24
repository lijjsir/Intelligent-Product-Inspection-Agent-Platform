import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useAuthStore } from "@/stores/auth.store";
import { usePromptTemplateStore } from "@/stores/prompt-template.store";

function prepareAuth(orgId = "org-1", userId = "user-1") {
  const auth = useAuthStore();
  auth.orgId = orgId;
  auth.userId = userId;
  auth.role = "expert";
  auth.roles = ["expert"];
  return auth;
}

describe("prompt template store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    sessionStorage.clear();
  });

  it("persists custom templates per user and restores the active selection", () => {
    prepareAuth("org-1", "user-1");

    const store = usePromptTemplateStore();
    store.loadTemplates();

    const created = store.createTemplate({
      name: "专家复核模板",
      description: "用于人工复核",
      content: "请以质检专家视角给出结论。",
    });

    store.selectTemplate(created.id);

    expect(store.allTemplates.some((item) => item.id === "builtin-expert-review")).toBe(true);
    expect(store.customTemplates).toHaveLength(1);
    expect(store.activeTemplate?.id).toBe(created.id);
    expect(localStorage.getItem("piap_prompt_templates:org-1:user-1")).toContain("专家复核模板");
    expect(localStorage.getItem("piap_prompt_template_selected:org-1:user-1")).toBe(created.id);
  });

  it("keeps templates isolated across users", () => {
    prepareAuth("org-1", "user-1");

    const store = usePromptTemplateStore();
    store.loadTemplates();
    store.createTemplate({
      name: "我的模板",
      description: "",
      content: "请先核对证据。",
    });

    setActivePinia(createPinia());
    const anotherAuth = prepareAuth("org-1", "user-2");
    const anotherStore = usePromptTemplateStore();
    anotherStore.loadTemplates();

    expect(anotherStore.customTemplates).toHaveLength(0);
    expect(anotherStore.activeTemplate).toBeNull();
    expect(anotherAuth.userId).toBe("user-2");
  });
});
