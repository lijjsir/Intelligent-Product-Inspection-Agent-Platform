<script setup lang="ts">
import type { InspectionResult } from "@/types/result.types"

defineProps<{
  result: InspectionResult
  task: any
}>()

const emit = defineEmits<{
  back: []
}>()

function getVerdictType(v: string) {
  const map: Record<string, any> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "info",
  }
  return map[v] || "info"
}

const VERDICT_LABELS: Record<string, string> = {
  pass: "通过",
  fail: "不通过",
  uncertain: "待定",
  manual_required: "待人工审核",
}
</script>

<template>
  <div class="evidence-header">
    <button class="back-btn" @click="emit('back')" title="返回">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 12H5M12 19l-7-7 7-7"/>
      </svg>
    </button>

    <div class="header-main">
      <div class="header-row">
        <span class="label">证据溯源</span>
        <span class="task-id">Task: {{ result.task_id }}</span>
        <el-tag :type="getVerdictType(result.verdict)" size="small" class="verdict-tag">
          {{ VERDICT_LABELS[result.verdict] || result.verdict }}
        </el-tag>
        <span class="score">{{ (result.overall_score * 100).toFixed(1) }}<small> 分</small></span>
      </div>
      <div class="header-meta">
        <span class="meta-item">模型: {{ result.llm_model }}</span>
        <span class="meta-sep">|</span>
        <span class="meta-item">Prompt: {{ result.prompt_version }}</span>
        <span class="meta-sep">|</span>
        <span class="meta-item">耗时: {{ result.latency_ms ?? '-' }} ms</span>
        <span class="meta-sep">|</span>
        <span class="meta-item">Tokens: {{ result.tokens_used ?? '-' }}</span>
        <span v-if="result.reviewed_by" class="meta-sep">|</span>
        <span v-if="result.reviewed_by" class="meta-item reviewed">已复核: {{ result.reviewed_by }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.evidence-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 24px;
  background: oklch(0.985 0.003 260);
  border-bottom: 1px solid oklch(0.92 0.005 260);
}

.back-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid oklch(0.9 0.005 260);
  border-radius: 6px;
  background: oklch(1 0 0);
  color: oklch(0.45 0.01 260);
  cursor: pointer;
  margin-top: 2px;
  transition: background 0.15s, color 0.15s;
}

.back-btn:hover {
  background: oklch(0.96 0.005 260);
  color: oklch(0.25 0.01 260);
}

.header-main {
  flex: 1;
  min-width: 0;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.label {
  font-size: 15px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
}

.task-id {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 13px;
  color: oklch(0.5 0.01 260);
  background: oklch(0.96 0.003 260);
  padding: 2px 8px;
  border-radius: 4px;
}

.verdict-tag {
  font-weight: 600;
}

.score {
  font-size: 18px;
  font-weight: 700;
  color: oklch(0.55 0.15 85);
}

.score small {
  font-size: 13px;
  font-weight: 500;
  color: oklch(0.5 0.01 260);
}

.header-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 12px;
  color: oklch(0.5 0.01 260);
}

.meta-sep {
  color: oklch(0.82 0.005 260);
  font-size: 12px;
  user-select: none;
}

.reviewed {
  color: oklch(0.45 0.13 175);
  font-weight: 500;
}
</style>
