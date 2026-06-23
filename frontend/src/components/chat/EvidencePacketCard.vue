<script setup lang="ts">
import type { ChatArtifact } from "@/types/chat.types";

defineProps<{
  artifacts?: ChatArtifact[];
  ragHitCount?: number;
  memoryCount?: number;
  kgPathCount?: number;
  sourceCount?: number;
}>();
</script>

<template>
  <div class="evidence-card">
    <div class="evidence-card-header">
      <span class="evidence-card-title">证据检索结果</span>
      <span class="evidence-card-sub">EvidenceArbitrationAgent</span>
    </div>
    <div class="evidence-card-grid">
      <div class="evidence-card-item">
        <span>RAG 标准文档</span>
        <strong>{{ ragHitCount ?? 0 }} 条命中</strong>
      </div>
      <div class="evidence-card-item">
        <span>共享记忆</span>
        <strong>{{ memoryCount ?? 0 }} 条命中</strong>
      </div>
      <div class="evidence-card-item">
        <span>知识图谱</span>
        <strong>{{ kgPathCount ?? 0 }} 条路径</strong>
      </div>
      <div class="evidence-card-item">
        <span>证据来源</span>
        <strong>{{ sourceCount ?? 0 }}</strong>
      </div>
    </div>
    <div v-if="(sourceCount ?? 0) === 0" class="evidence-card-empty">
      未检索到相关证据，回答可能不基于具体标准依据。
    </div>
  </div>
</template>

<style scoped>
.evidence-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f9fafb;
}

.evidence-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.evidence-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}

.evidence-card-sub {
  font-size: 11px;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.evidence-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.evidence-card-item {
  display: grid;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #f3f4f6;
}

.evidence-card-item span {
  font-size: 11px;
  color: #6b7280;
  font-weight: 600;
  text-transform: uppercase;
}

.evidence-card-item strong {
  font-size: 13px;
  color: #374151;
  font-weight: 600;
}

.evidence-card-empty {
  font-size: 12px;
  color: #9ca3af;
  font-style: italic;
  padding: 4px 0;
}

@media (max-width: 640px) {
  .evidence-card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
