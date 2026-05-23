<template>
  <div class="pipeline-node" :class="[`tone-${data.tone || 'slate'}`, { active: data.active, dim: data.dim }]">
    <div class="node-kicker">{{ data.kicker }}</div>
    <div class="node-title">{{ data.title }}</div>
    <div v-if="data.subtitle" class="node-subtitle">{{ data.subtitle }}</div>
    <div v-if="data.items?.length" class="node-items">
      <span v-for="item in data.items" :key="item" class="node-chip">{{ item }}</span>
    </div>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<script setup lang="ts">
import { Handle, Position } from "@vue-flow/core";

defineProps<{
  data: {
    kicker: string;
    title: string;
    subtitle?: string;
    items?: string[];
    tone?: "blue" | "violet" | "teal" | "amber" | "slate";
    active?: boolean;
    dim?: boolean;
  };
}>();
</script>

<style scoped>
.pipeline-node {
  width: 220px;
  min-height: 96px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #d4d4d8;
  border-left-width: 4px;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  transition: border-color 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
}
.pipeline-node.active {
  border-color: #2563eb;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.16);
}
.pipeline-node.dim {
  opacity: 0.42;
}
.tone-blue { border-left-color: #2563eb; }
.tone-violet { border-left-color: #7c3aed; }
.tone-teal { border-left-color: #0d9488; }
.tone-amber { border-left-color: #d97706; }
.tone-slate { border-left-color: #64748b; }
.node-kicker {
  color: #71717a;
  font-size: 11px;
  font-weight: 600;
}
.node-title {
  margin-top: 4px;
  color: #18181b;
  font-size: 14px;
  font-weight: 700;
}
.node-subtitle {
  margin-top: 4px;
  color: #52525b;
  font-size: 12px;
  line-height: 1.35;
}
.node-items {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.node-chip {
  max-width: 190px;
  overflow: hidden;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f4f4f5;
  color: #52525b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
