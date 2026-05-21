import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { promptAdminApi } from "@/api/prompt-admin.api";
import type {
  PromptDefinitionSummary,
  PromptDefinitionDetail,
  PromptOverview,
  DiffResponse,
} from "@/types/prompt-admin.types";

export const usePromptAdminStore = defineStore("promptAdmin", () => {
  const overview = ref<PromptOverview | null>(null);
  const definitions = ref<PromptDefinitionSummary[]>([]);
  const detail = ref<PromptDefinitionDetail | null>(null);
  const diff = ref<DiffResponse | null>(null);
  const loading = ref(false);

  const selectedPromptKey = ref("");

  // Group by agent_key
  const agentGroups = computed(() => {
    const map = new Map<string, PromptDefinitionSummary[]>();
    for (const d of definitions.value) {
      const key = d.agent_name || "未分类";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(d);
    }
    return Array.from(map.entries()).map(([name, items]) => ({ name, items }));
  });

  async function fetchOverview() {
    const { data } = await promptAdminApi.getOverview();
    overview.value = data.data;
  }

  async function fetchDefinitions(params?: {
    agent_key?: string;
    stage_key?: string;
    keyword?: string;
    sync_status?: string;
  }) {
    loading.value = true;
    try {
      const { data } = await promptAdminApi.listDefinitions(params);
      definitions.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchDetail(promptKey: string) {
    loading.value = true;
    try {
      const { data } = await promptAdminApi.getDefinition(promptKey);
      detail.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createVersion(promptKey: string, content: string, changeSummary?: string, baseHash?: string) {
    const { data } = await promptAdminApi.createVersion(promptKey, {
      content,
      change_summary: changeSummary,
      base_hash: baseHash,
    });
    // Refresh detail
    if (selectedPromptKey.value === promptKey) {
      await fetchDetail(promptKey);
    }
    return data.data;
  }

  async function publishVersion(versionId: string) {
    const { data } = await promptAdminApi.publishVersion(versionId);
    if (detail.value) {
      await fetchDetail(detail.value.prompt_key);
    }
    await fetchDefinitions();
    return data.data;
  }

  async function rollback(promptKey: string, targetVersionId: string) {
    const { data } = await promptAdminApi.rollbackDefinition(promptKey, targetVersionId);
    if (detail.value) {
      await fetchDetail(promptKey);
    }
    return data.data;
  }

  async function fetchDiff(promptKey: string, left = "code_default", right = "active") {
    const { data } = await promptAdminApi.getDiff(promptKey, left, right);
    diff.value = data.data;
    return data.data;
  }

  async function scanCodePrompts() {
    const { data } = await promptAdminApi.scanCodePrompts();
    await fetchDefinitions();
    await fetchOverview();
    return data.data;
  }

  function selectPrompt(key: string) {
    selectedPromptKey.value = key;
  }

  function $reset() {
    overview.value = null;
    definitions.value = [];
    detail.value = null;
    diff.value = null;
    selectedPromptKey.value = "";
    loading.value = false;
  }

  return {
    overview,
    definitions,
    detail,
    diff,
    loading,
    selectedPromptKey,
    agentGroups,
    fetchOverview,
    fetchDefinitions,
    fetchDetail,
    createVersion,
    publishVersion,
    rollback,
    fetchDiff,
    scanCodePrompts,
    selectPrompt,
    $reset,
  };
});
