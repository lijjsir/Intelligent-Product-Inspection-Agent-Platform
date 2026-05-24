<script setup lang="ts">
import { computed } from "vue"
import { ElMessage } from "element-plus"
import type { InspectionResult } from "@/types/result.types"

const props = defineProps<{
  result: InspectionResult
}>()

const traceInfo = computed(() => {
  const rc = props.result.reasoning_chain as any
  return {
    traceId: rc?.trace?.trace_id || rc?.trace_id || "-",
    observationId: rc?.trace?.observation_id || rc?.observation_id || "-",
    trustScore: rc?.trust_score ?? rc?.trace?.trust_score ?? null,
    hallucinationRisk: rc?.hallucination_risk ?? rc?.trace?.hallucination_risk ?? null,
    overconfidence: rc?.overconfidence ?? rc?.trace?.overconfidence ?? null,
    hasCitation: rc?.has_citation ?? rc?.trace?.has_citation ?? null,
    traceUrl: rc?.trace?.trace_url || rc?.trace_url || null,
    synced: rc?.trace?.synced ?? rc?.trace?.langfuse_synced ?? null,
  }
})

function trustLevel(score: number | null) {
  if (score === null) return "na"
  if (score >= 0.8) return "high"
  if (score >= 0.5) return "medium"
  return "low"
}

function trustLabel(score: number | null) {
  if (score === null) return "-"
  return (score * 100).toFixed(0) + "%"
}

function riskLevel(risk: string | null) {
  if (risk === null) return "na"
  const r = String(risk).toLowerCase()
  if (r === "high" || r === "critical") return "danger"
  if (r === "medium") return "warning"
  return "success"
}

function riskLabel(risk: string | null) {
  if (risk === null) return "-"
  return String(risk)
}

function boolLabel(v: boolean | null) {
  if (v === true) return "是"
  if (v === false) return "否"
  return "-"
}

function copyTraceId() {
  if (traceInfo.value.traceId === "-") return
  navigator.clipboard.writeText(traceInfo.value.traceId)
  ElMessage.success("已复制 Trace ID")
}

const metricItems = computed(() => [
  { label: "Trace ID", value: traceInfo.value.traceId, mono: true, clip: true },
  { label: "Observation ID", value: traceInfo.value.observationId, mono: true },
  { label: "可信度", value: trustLabel(traceInfo.value.trustScore), tag: trustLevel(traceInfo.value.trustScore) },
  { label: "幻觉风险", value: riskLabel(traceInfo.value.hallucinationRisk), tag: riskLevel(traceInfo.value.hallucinationRisk) },
  { label: "过度自信", value: riskLabel(traceInfo.value.overconfidence), tag: riskLevel(traceInfo.value.overconfidence) },
  { label: "引用证据", value: boolLabel(traceInfo.value.hasCitation), tag: traceInfo.value.hasCitation ? "success" : "info" },
  { label: "Token 消耗", value: props.result.tokens_used?.toLocaleString() ?? "-" },
  { label: "Langfuse 状态", value: traceInfo.value.synced ? "已同步" : "本地", tag: traceInfo.value.synced ? "success" : "info" },
])

function tagType(level: string): any {
  if (level === "high" || level === "success") return "success"
  if (level === "medium") return "warning"
  if (level === "low" || level === "danger") return "danger"
  return "info"
}
</script>

<template>
  <div class="trace-tab">
    <div class="trace-metrics">
      <div
        v-for="item in metricItems"
        :key="item.label"
        class="trace-metric"
      >
        <span class="metric-label">{{ item.label }}</span>
        <div class="metric-body">
          <code v-if="item.mono" class="metric-mono" :class="{ clip: item.clip }">
            {{ item.value }}
            <button v-if="item.clip && item.value !== '-'" class="clip-btn" @click="copyTraceId" title="复制">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
              </svg>
            </button>
          </code>
          <el-tag v-else-if="item.tag" :type="tagType(item.tag)" size="small">{{ item.value }}</el-tag>
          <span v-else class="metric-text">{{ item.value }}</span>
        </div>
      </div>
    </div>

    <div class="trace-actions">
      <a
        v-if="traceInfo.traceUrl"
        :href="traceInfo.traceUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="langfuse-link"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
        <span>打开 Langfuse</span>
      </a>
      <el-button size="small" @click="copyTraceId" :disabled="traceInfo.traceId === '-'">
        复制 Trace ID
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.trace-tab {
  padding: 24px;
  max-width: 800px;
}

.trace-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.trace-metric {
  padding: 14px 16px;
  background: oklch(0.985 0.003 260);
  border-radius: 8px;
  border: 1px solid oklch(0.92 0.005 260);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-label {
  font-size: 11px;
  font-weight: 500;
  color: oklch(0.45 0.01 260);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-body {
  display: flex;
  align-items: center;
}

.metric-mono {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 12px;
  color: oklch(0.35 0.01 260);
  background: oklch(0.97 0.003 260);
  padding: 3px 8px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-mono.clip {
  cursor: default;
}

.clip-btn {
  flex-shrink: 0;
  border: none;
  background: none;
  color: oklch(0.5 0.01 260);
  cursor: pointer;
  padding: 1px;
  display: flex;
  opacity: 0.5;
  transition: opacity 0.15s;
}

.clip-btn:hover {
  opacity: 1;
  color: oklch(0.5 0.14 250);
}

.metric-text {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
}

.trace-actions {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid oklch(0.92 0.005 260);
  display: flex;
  gap: 12px;
  align-items: center;
}

.langfuse-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid oklch(0.5 0.14 250 / 0.3);
  background: oklch(0.96 0.04 250 / 0.08);
  color: oklch(0.45 0.13 250);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s;
}

.langfuse-link:hover {
  background: oklch(0.95 0.05 250 / 0.15);
  border-color: oklch(0.5 0.14 250 / 0.5);
}
</style>
