<script setup lang="ts">
type TabKey = "overview" | "quality" | "tracing";

interface Props {
  activeTab: TabKey;
}
interface Emits {
  (e: "change", tab: TabKey): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const tabs: { label: string; key: TabKey }[] = [
  { label: "总览", key: "overview" },
  { label: "质量报告", key: "quality" },
  { label: "质量追踪", key: "tracing" },
];

function handleClick(key: TabKey) {
  emit("change", key);
}
</script>

<template>
  <nav class="analytics-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      :class="['tab-item', { active: props.activeTab === tab.key }]"
      @click="handleClick(tab.key)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<style scoped>
.analytics-tabs {
  display: flex;
  gap: 4px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 12px;
  padding: 4px;
  width: fit-content;
}
.tab-item {
  padding: 8px 20px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-item:hover {
  color: #1b3a5c;
  background: rgba(255, 255, 255, 0.6);
}
.tab-item.active {
  background: #fff;
  color: #0f766e;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
  font-weight: 600;
}
</style>
