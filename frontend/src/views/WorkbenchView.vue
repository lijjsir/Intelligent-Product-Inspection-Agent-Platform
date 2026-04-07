<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const WORKBENCH_TABS = [
  { label: "智能对话", name: "workbench-chat" as const },
  { label: "知识库", name: "workbench-rag-spaces" as const },
];

type WorkbenchTabName = (typeof WORKBENCH_TABS)[number]["name"];

const route = useRoute();
const router = useRouter();

const activeTabName = computed<WorkbenchTabName>(() => {
  const currentName = route.name;

  if (currentName === "workbench-rag-spaces") {
    return "workbench-rag-spaces";
  }

  return "workbench-chat";
});

const handleTabChange = (tabName: string | number) => {
  if (typeof tabName !== "string" || tabName === activeTabName.value) {
    return;
  }

  void router.push({ name: tabName as WorkbenchTabName });
};
</script>

<template>
  <div class="workbench-page">
    <el-tabs :model-value="activeTabName" @tab-change="handleTabChange" class="workbench-tabs">
      <el-tab-pane v-for="tab in WORKBENCH_TABS" :key="tab.name" :label="tab.label" :name="tab.name" />
    </el-tabs>
    <div class="workbench-content">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.workbench-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.workbench-tabs {
  flex-shrink: 0;
}

.workbench-content {
  flex: 1;
  min-height: 0;
}

.workbench-tabs :deep(.el-tabs__content) {
  display: none;
}
</style>
