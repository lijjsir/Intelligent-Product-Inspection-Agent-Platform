<script setup lang="ts">
import { ref, computed } from "vue"
import EvidenceJsonDialog from "./EvidenceJsonDialog.vue"

const props = defineProps<{
  reasoningChain: Record<string, any> | null
}>()

const expandedStep = ref<number | null>(null)
const jsonDialogRef = ref<InstanceType<typeof EvidenceJsonDialog>>()

interface ReasoningStep {
  name: string
  status: string
  input: string
  output: string
  durationMs?: number
  evidence?: string
  risk?: string
}

const steps = computed<ReasoningStep[]>(() => {
  if (!props.reasoningChain) return []

  const chain = props.reasoningChain
  // Try known patterns: steps array, or parse top-level keys
  if (chain.steps && Array.isArray(chain.steps)) {
    return chain.steps.map((s: any) => ({
      name: s.name || s.step || s.label || "",
      status: s.status || "success",
      input: truncate(s.input || s.input_summary || ""),
      output: truncate(s.output || s.output_summary || ""),
      durationMs: s.duration_ms || s.duration,
      evidence: s.evidence || s.related_evidence,
      risk: s.risk || s.risk_warning,
    }))
  }

  // Fallback: create steps from top-level structure
  const stepMap: Record<string, string> = {
    input_parsing: "输入解析",
    image_recognition: "图像识别",
    evidence_retrieval: "证据检索",
    standard_matching: "标准匹配",
    model_judgment: "模型判断",
    conclusion: "结论生成",
    risk_scoring: "风险评分",
  }

  const entries = Object.entries(chain)
  if (entries.length === 0) return []

  // If it has recognizable step keys
  const hasKnownKeys = entries.some(([k]) => stepMap[k])
  if (hasKnownKeys) {
    return entries
      .filter(([k]) => stepMap[k])
      .map(([k, v]: [string, any]) => ({
        name: stepMap[k] || k,
        status: "success",
        input: "",
        output: truncate(typeof v === "string" ? v : JSON.stringify(v)),
      }))
  }

  // Last resort: single-step view
  return [{
    name: "推理过程",
    status: "success",
    input: "",
    output: truncate(JSON.stringify(chain)),
  }]
})

function truncate(s: string, max = 120) {
  return s.length > max ? s.slice(0, max) + "…" : s
}

function toggleStep(idx: number) {
  expandedStep.value = expandedStep.value === idx ? null : idx
}

function statusIcon(s: string) {
  if (s === "success") return "check"
  if (s === "failed" || s === "error") return "close"
  if (s === "skipped") return "minus"
  return "more"
}

function statusColor(s: string) {
  if (s === "success") return "oklch(0.48 0.14 165)"
  if (s === "failed" || s === "error") return "oklch(0.55 0.18 20)"
  if (s === "skipped") return "oklch(0.5 0.01 260)"
  return "oklch(0.5 0.14 250)"
}

function openRawJson() {
  jsonDialogRef.value?.open()
}
</script>

<template>
  <div class="reasoning-tab">
    <div v-if="!steps.length" class="empty-full">
      <el-empty description="模型未输出推理链路" :image-size="80" />
    </div>

    <div v-else class="reasoning-layout">
      <div class="timeline">
        <div
          v-for="(step, idx) in steps"
          :key="idx"
          class="timeline-node"
          :class="{ expanded: expandedStep === idx }"
        >
          <div class="node-indicator" @click="toggleStep(idx)">
            <svg width="16" height="16" viewBox="0 0 24 24" :fill="statusColor(step.status)">
              <circle v-if="step.status === 'success'" cx="12" cy="12" r="8"/>
              <rect v-else cx="12" cy="12" rx="2" width="16" height="16" x="4" y="4"/>
            </svg>
            <div v-if="idx < steps.length - 1" class="node-line" />
          </div>

          <div class="node-content">
            <button class="node-header" @click="toggleStep(idx)">
              <span class="node-name">{{ step.name }}</span>
              <span class="node-status" :style="{ color: statusColor(step.status) }">
                {{ step.status === 'success' ? '完成' : step.status === 'failed' ? '失败' : step.status === 'skipped' ? '跳过' : step.status }}
              </span>
              <span v-if="step.durationMs" class="node-duration">{{ step.durationMs }}ms</span>
              <svg
                class="node-chevron"
                :class="{ rotated: expandedStep === idx }"
                width="14" height="14" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" stroke-width="2"
              >
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </button>

            <div v-if="step.risk" class="node-risk">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="oklch(0.55 0.16 75)" stroke-width="2">
                <path d="M12 2L2 22h20L12 2zM12 10v4M12 18h.01"/>
              </svg>
              {{ step.risk }}
            </div>

            <div v-if="expandedStep === idx" class="node-detail">
              <div v-if="step.input" class="detail-block">
                <span class="detail-label">输入</span>
                <p class="detail-text">{{ step.input }}</p>
              </div>
              <div class="detail-block">
                <span class="detail-label">输出</span>
                <p class="detail-text">{{ step.output }}</p>
              </div>
              <div v-if="step.evidence" class="detail-block">
                <span class="detail-label">关联证据</span>
                <p class="detail-text">{{ step.evidence }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="reasoning-actions">
        <el-button size="small" @click="openRawJson">查看原始 reasoning_chain JSON</el-button>
      </div>
    </div>

    <EvidenceJsonDialog
      ref="jsonDialogRef"
      title="推理链路原始 JSON"
      :data="reasoningChain"
    />
  </div>
</template>

<style scoped>
.reasoning-tab {
  padding: 24px;
  max-width: 800px;
}

.empty-full {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-node {
  display: flex;
  gap: 16px;
}

.node-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 16px;
  flex-shrink: 0;
  cursor: pointer;
}

.node-line {
  width: 2px;
  flex: 1;
  min-height: 24px;
  background: oklch(0.9 0.005 260);
  margin-top: 8px;
}

.timeline-node:last-child .node-line {
  display: none;
}

.node-content {
  flex: 1;
  padding: 14px 0;
  min-width: 0;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  background: none;
  padding: 10px 14px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}

.node-header:hover {
  background: oklch(0.97 0.005 260);
}

.timeline-node.expanded .node-header {
  background: oklch(0.96 0.01 260);
}

.node-name {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
}

.node-status {
  font-size: 11px;
  font-weight: 500;
}

.node-duration {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: oklch(0.5 0.01 260);
  margin-left: auto;
}

.node-chevron {
  flex-shrink: 0;
  color: oklch(0.5 0.01 260);
  transition: transform 0.2s;
}

.node-chevron.rotated {
  transform: rotate(180deg);
}

.node-risk {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 14px;
  margin-top: 4px;
  font-size: 12px;
  color: oklch(0.55 0.16 75);
}

.node-detail {
  margin-top: 8px;
  padding: 14px;
  background: oklch(0.985 0.003 260);
  border-radius: 8px;
  border: 1px solid oklch(0.94 0.003 260);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: oklch(0.45 0.01 260);
}

.detail-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: oklch(0.35 0.01 260);
}

.reasoning-actions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid oklch(0.92 0.005 260);
}
</style>
