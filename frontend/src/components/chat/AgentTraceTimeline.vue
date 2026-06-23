<script setup lang="ts">
import type { ChatRouteTrace } from "@/types/chat.types";

defineProps<{
  trace?: ChatRouteTrace | null;
  capabilitiesUsed?: string[];
}>();
</script>

<template>
  <div class="trace-card">
    <div class="trace-card-header">
      <span class="trace-card-title">Agent 执行链路</span>
      <span v-if="trace?.iterations != null" class="trace-card-meta">迭代 {{ trace.iterations }} 次</span>
    </div>
    <div class="trace-card-steps" v-if="trace?.steps?.length || capabilitiesUsed?.length">
      <div v-for="(cap, ci) in (capabilitiesUsed || [])" :key="ci" class="trace-step">
        <div class="trace-step-dot"></div>
        <div class="trace-step-content">
          <span class="trace-step-cap">{{ cap }}</span>
        </div>
      </div>
    </div>
    <div v-if="trace?.observations?.length" class="trace-card-obs">
      <div v-for="(obs, oi) in trace.observations" :key="oi" class="trace-obs">
        <el-tag size="small" effect="plain" :type="obs.status === 'success' ? 'success' : obs.status === 'failed' ? 'danger' : 'warning'">
          {{ obs.status || "unknown" }}
        </el-tag>
        <span class="trace-obs-summary">{{ obs.summary || obs.capability_key || "-" }}</span>
      </div>
    </div>
    <div v-if="trace?.errors?.length" class="trace-card-errors">
      <div v-for="(err, ei) in trace.errors" :key="ei" class="trace-error">
        {{ err.message || JSON.stringify(err) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-card {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}

.trace-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.trace-card-title {
  font-size: 12px;
  font-weight: 700;
  color: #6b7280;
  text-transform: uppercase;
}

.trace-card-meta {
  font-size: 11px;
  color: #9ca3af;
}

.trace-card-steps {
  display: grid;
  gap: 0;
}

.trace-step {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 4px 0;
}

.trace-step-dot {
  width: 8px;
  height: 8px;
  margin-top: 4px;
  border-radius: 50%;
  background: #3b82f6;
  flex-shrink: 0;
}

.trace-step-content {
  font-size: 12px;
  color: #374151;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.trace-card-obs {
  display: grid;
  gap: 4px;
}

.trace-obs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trace-obs-summary {
  font-size: 12px;
  color: #6b7280;
}

.trace-card-errors {
  display: grid;
  gap: 4px;
}

.trace-error {
  font-size: 11px;
  color: #dc2626;
  padding: 6px 8px;
  border-radius: 4px;
  background: #fef2f2;
}
</style>
