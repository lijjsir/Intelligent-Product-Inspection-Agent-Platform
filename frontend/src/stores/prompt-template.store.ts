import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { useAuthStore } from "@/stores/auth.store";
import { createUuid } from "@/utils/browserCrypto";

export interface PromptTemplate {
  id: string;
  name: string;
  description: string;
  content: string;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplateDraft {
  name: string;
  description: string;
  content: string;
}

const BUILTIN_TIMESTAMP = "2026-01-01T00:00:00.000Z";

const CURATED_BUILTIN_PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: "builtin-user-context",
    name: "用户：补充背景",
    description: "把问题、背景和期望输出说清楚",
    content: [
      "请结合 PIAP 平台里的质检任务、历史结果和当前会话上下文回答。",
      "",
      "我的问题：",
      "[请输入问题]",
      "",
      "补充背景：",
      "- 产品/任务：",
      "- 关注点：",
      "- 已知现象：",
      "",
      "希望输出：",
      "1. 先给结论",
      "2. 说明依据",
      "3. 标出还缺哪些信息",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
  {
    id: "builtin-user-result-explain",
    name: "用户：结果解读",
    description: "解释一次质检结果为什么这样判定",
    content: [
      "请解释这次质检结果。",
      "",
      "任务或结果：",
      "[粘贴任务 ID、结果摘要，或直接说“最近一次”]",
      "",
      "请按以下结构输出：",
      "1. 判定结论",
      "2. 关键证据",
      "3. 触发的标准或规则",
      "4. 风险等级",
      "5. 是否建议人工复检",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
  {
    id: "builtin-user-task-draft",
    name: "用户：任务草稿",
    description: "把零散信息整理成质检任务",
    content: [
      "请把下面零散信息整理成质检任务草稿。聊天页只整理草稿，不直接提交正式任务。",
      "",
      "零散信息：",
      "[粘贴产品、标准、图片、优先级、备注]",
      "",
      "请输出：",
      "- 产品编号",
      "- 检测标准",
      "- 图片或附件清单",
      "- 优先级",
      "- 缺失字段",
      "- 建议下一步",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
  {
    id: "builtin-expert-review",
    name: "专家：复核判定",
    description: "从质检专家角度复核结果",
    content: [
      "请以资深质检专家视角复核下面这条结果，不要泛泛而谈。",
      "",
      "已知信息：",
      "- 产品编号：",
      "- 检测标准：",
      "- 质检结果：",
      "- 证据/图片：",
      "",
      "请按以下结构回答：",
      "1. 复核结论",
      "2. 判定依据",
      "3. 主要风险点",
      "4. 是否建议人工复检",
      "5. 还缺哪些信息",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
  {
    id: "builtin-expert-standard-trace",
    name: "专家：标准追溯",
    description: "核对标准、证据和引用链路",
    content: [
      "请以检测标准审核专家视角，核对当前回答或结果是否有足够依据。",
      "",
      "重点检查：",
      "1. 是否引用了明确标准或规则",
      "2. 证据是否能支撑结论",
      "3. 是否存在标准缺失、错配或过度推断",
      "4. trace / RAG / 任务历史里哪些信息最关键",
      "",
      "输出：",
      "- 依据充分性",
      "- 可追溯链路",
      "- 不确定点",
      "- 建议修正",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
  {
    id: "builtin-expert-risk-diagnosis",
    name: "专家：风险诊断",
    description: "定位失败、高风险和复检原因",
    content: [
      "请以质量风险专家视角分析当前质检情形。",
      "",
      "请优先结合平台里的最近任务、历史质检结果、风险等级和失败记录。",
      "",
      "输出结构：",
      "1. 当前情形判断",
      "2. 可能失败原因",
      "3. 高风险信号",
      "4. 建议复检或补证动作",
      "5. 对后续任务的提醒",
    ].join("\n"),
    is_builtin: true,
    created_at: BUILTIN_TIMESTAMP,
    updated_at: BUILTIN_TIMESTAMP,
  },
];

function nowIso() {
  return new Date().toISOString();
}

function storageNamespace(auth: ReturnType<typeof useAuthStore>) {
  return `${auth.orgId || "global"}:${auth.userId || "anonymous"}`;
}

function templatesStorageKey(auth: ReturnType<typeof useAuthStore>) {
  return `piap_prompt_templates:${storageNamespace(auth)}`;
}

function selectedStorageKey(auth: ReturnType<typeof useAuthStore>) {
  return `piap_prompt_template_selected:${storageNamespace(auth)}`;
}

function readStoredTemplates(auth: ReturnType<typeof useAuthStore>): PromptTemplate[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(templatesStorageKey(auth));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((item) => ({
        id: typeof item.id === "string" && item.id.trim() ? item.id.trim() : createUuid(),
        name: typeof item.name === "string" ? item.name.trim() : "",
        description: typeof item.description === "string" ? item.description.trim() : "",
        content: typeof item.content === "string" ? item.content.trim() : "",
        is_builtin: false,
        created_at: typeof item.created_at === "string" && item.created_at.trim() ? item.created_at : nowIso(),
        updated_at: typeof item.updated_at === "string" && item.updated_at.trim() ? item.updated_at : nowIso(),
      }))
      .filter((item) => item.name && item.content);
  } catch {
    return [];
  }
}

function writeStoredTemplates(auth: ReturnType<typeof useAuthStore>, templates: PromptTemplate[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(templatesStorageKey(auth), JSON.stringify(templates));
}

function readStoredSelectedTemplateId(auth: ReturnType<typeof useAuthStore>) {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(selectedStorageKey(auth)) || "";
}

function writeStoredSelectedTemplateId(auth: ReturnType<typeof useAuthStore>, templateId: string) {
  if (typeof window === "undefined") return;
  if (templateId) {
    window.localStorage.setItem(selectedStorageKey(auth), templateId);
  } else {
    window.localStorage.removeItem(selectedStorageKey(auth));
  }
}

function normalizeTemplate(input: PromptTemplateDraft, existing?: PromptTemplate): PromptTemplate {
  const timestamp = nowIso();
  return {
    id: existing?.id || createUuid(),
    name: input.name.trim(),
    description: input.description.trim(),
    content: input.content.trim(),
    is_builtin: existing?.is_builtin ?? false,
    created_at: existing?.created_at || timestamp,
    updated_at: timestamp,
  };
}

export const usePromptTemplateStore = defineStore("promptTemplate", () => {
  const auth = useAuthStore();
  const customTemplates = ref<PromptTemplate[]>([]);
  const selectedTemplateId = ref("");
  const loaded = ref(false);

  const allTemplates = computed(() => [...CURATED_BUILTIN_PROMPT_TEMPLATES, ...customTemplates.value]);
  const activeTemplate = computed(() => allTemplates.value.find((item) => item.id === selectedTemplateId.value) || null);

  function loadTemplates() {
    customTemplates.value = readStoredTemplates(auth);
    selectedTemplateId.value = readStoredSelectedTemplateId(auth);
    if (!allTemplates.value.some((item) => item.id === selectedTemplateId.value)) {
      selectedTemplateId.value = "";
      writeStoredSelectedTemplateId(auth, "");
    }
    loaded.value = true;
  }

  function ensureLoaded() {
    if (!loaded.value) {
      loadTemplates();
    }
  }

  function persistTemplates() {
    writeStoredTemplates(auth, customTemplates.value);
  }

  function createTemplate(draft: PromptTemplateDraft) {
    const template = normalizeTemplate(draft);
    customTemplates.value = [template, ...customTemplates.value];
    persistTemplates();
    return template;
  }

  function updateTemplate(templateId: string, draft: PromptTemplateDraft) {
    const index = customTemplates.value.findIndex((item) => item.id === templateId && !item.is_builtin);
    if (index === -1) return null;
    const current = customTemplates.value[index];
    const next = normalizeTemplate(draft, current);
    customTemplates.value = [
      ...customTemplates.value.slice(0, index),
      next,
      ...customTemplates.value.slice(index + 1),
    ];
    persistTemplates();
    if (selectedTemplateId.value === templateId) {
      selectedTemplateId.value = next.id;
      writeStoredSelectedTemplateId(auth, next.id);
    }
    return next;
  }

  function deleteTemplate(templateId: string) {
    const before = customTemplates.value.length;
    customTemplates.value = customTemplates.value.filter((item) => item.id !== templateId);
    if (customTemplates.value.length !== before) {
      persistTemplates();
    }
    if (selectedTemplateId.value === templateId) {
      clearSelection();
    }
  }

  function selectTemplate(templateId: string) {
    selectedTemplateId.value = templateId;
    writeStoredSelectedTemplateId(auth, templateId);
  }

  function clearSelection() {
    selectedTemplateId.value = "";
    writeStoredSelectedTemplateId(auth, "");
  }

  function hasCustomTemplates() {
    return customTemplates.value.length > 0;
  }

  return {
    loaded,
    customTemplates,
    allTemplates,
    activeTemplate,
    selectedTemplateId,
    loadTemplates,
    ensureLoaded,
    createTemplate,
    updateTemplate,
    deleteTemplate,
    selectTemplate,
    clearSelection,
    hasCustomTemplates,
  };
});
