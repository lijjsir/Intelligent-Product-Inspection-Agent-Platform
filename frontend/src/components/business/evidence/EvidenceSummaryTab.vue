<script setup lang="ts">
import { computed } from "vue"
import type { InspectionResult } from "@/types/result.types"

const props = defineProps<{
  result: InspectionResult
}>()

const VERDICT_LABELS: Record<string, string> = {
  pass: "通过",
  fail: "不通过",
  uncertain: "待定",
  manual_required: "需人工复核",
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function getVerdictType(value: string) {
  const map: Record<string, string> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "info",
  }
  return map[value] || "info"
}

function scorePercent(value: number) {
  return (value * 100).toFixed(1)
}

function riskTone(value: number | null) {
  if (value === null) return "default"
  if (value >= 0.6) return "danger"
  if (value >= 0.3) return "warning"
  return "success"
}

function riskLabel(value: number | null) {
  if (value === null) return "-"
  return `${(value * 100).toFixed(0)}%`
}

function boolLabel(value: boolean | null) {
  if (value === true) return "有"
  if (value === false) return "无"
  return "-"
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toBool(value: unknown): boolean | null {
  if (value === null || value === undefined || value === "") return null
  if (typeof value === "boolean") return value
  if (typeof value === "number") return value > 0
  const normalized = String(value).trim().toLowerCase()
  if (["1", "true", "yes", "y"].includes(normalized)) return true
  if (["0", "false", "no", "n"].includes(normalized)) return false
  return null
}

function itemLabel(item: unknown, fallback: string) {
  if (typeof item === "string") return item
  if (!isRecord(item)) return fallback
  return String(item.rule_code || item.code || item.name || item.id || item.defect_type || fallback)
}

const reasoningChain = computed(() => (
  isRecord(props.result.reasoning_chain) ? props.result.reasoning_chain : {}
))

const standardEvaluation = computed(() => {
  const value = reasoningChain.value.standard_evaluation
  return isRecord(value) ? value : null
})

const trustScoring = computed(() => {
  const direct = reasoningChain.value.trust_scoring
  if (isRecord(direct)) return direct
  const trace = reasoningChain.value.trace
  if (isRecord(trace) && isRecord(trace.trust_scoring)) return trace.trust_scoring
  return null
})

const citationCount = computed(() => {
  const citations = props.result.citations
  if (Array.isArray(citations)) return citations.length
  if (isRecord(citations) && Array.isArray(citations.items)) return citations.items.length
  if (isRecord(citations)) return Object.keys(citations).length
  return 0
})

const matchedRules = computed(() => (
  Array.isArray(standardEvaluation.value?.matched_rules) ? standardEvaluation.value?.matched_rules : []
))

const unmatchedDefects = computed(() => (
  Array.isArray(standardEvaluation.value?.unmatched_defects) ? standardEvaluation.value?.unmatched_defects : []
))

const fallbackBusinessSummary = computed(() => {
  const score = scorePercent(props.result.overall_score)
  if (props.result.verdict === "pass") {
    return `本次质检判定为通过，综合得分 ${score} 分，当前未发现阻断通过的缺陷或规则风险。`
  }
  if (props.result.verdict === "fail") {
    return `本次质检判定为不通过，综合得分 ${score} 分，请结合缺陷、规则命中和引用证据继续复核。`
  }
  if (props.result.verdict === "manual_required") {
    return `本次质检需要人工复核，综合得分 ${score} 分，自动判定未达到直接放行条件。`
  }
  return `本次质检当前结论为 ${VERDICT_LABELS[props.result.verdict] || props.result.verdict}，综合得分 ${score} 分。`
})

const businessSummary = computed(() => (
  String(standardEvaluation.value?.summary || fallbackBusinessSummary.value)
))

const trustSummaryItems = computed(() => {
  const trust = trustScoring.value
  return [
    {
      label: "可信度",
      value: riskLabel(toNumber(trust?.trust_score)),
      tone: riskTone(toNumber(trust?.trust_score) === null ? null : 1 - Number(trust?.trust_score)),
    },
    {
      label: "幻觉风险",
      value: riskLabel(toNumber(trust?.hallucination_risk)),
      tone: riskTone(toNumber(trust?.hallucination_risk)),
    },
    {
      label: "过度肯定风险",
      value: riskLabel(toNumber(trust?.overconfidence)),
      tone: riskTone(toNumber(trust?.overconfidence)),
    },
    {
      label: "引用支持",
      value: boolLabel(toBool(trust?.has_citation)),
      tone: toBool(trust?.has_citation) ? "success" : "default",
    },
  ]
})

const overviewMetrics = computed(() => [
  { label: "检出缺陷", value: `${props.result.defects?.length ?? 0}` },
  { label: "引用证据", value: `${citationCount.value}` },
  { label: "命中规则", value: `${matchedRules.value.length}` },
  { label: "未映射缺陷", value: `${unmatchedDefects.value.length}` },
  { label: "Token 消耗", value: props.result.tokens_used?.toLocaleString() ?? "-", muted: props.result.tokens_used == null },
  { label: "推理耗时", value: props.result.latency_ms != null ? `${props.result.latency_ms}ms` : "-" },
  { label: "模型引擎", value: props.result.llm_model || "-" },
  { label: "Prompt 版本", value: props.result.prompt_version || "-" },
])
</script>

<template>
  <div class="summary-tab">
    <div class="summary-layout">
      <div class="verdict-zone">
        <div class="verdict-badge" :class="`verdict-${getVerdictType(result.verdict)}`">
          <span class="verdict-icon">
            <template v-if="result.verdict === 'pass'">&#10003;</template>
            <template v-else-if="result.verdict === 'fail'">&#10007;</template>
            <template v-else>&#63;</template>
          </span>
          <span class="verdict-label">{{ VERDICT_LABELS[result.verdict] || result.verdict }}</span>
        </div>

        <div class="score-ring">
          <svg viewBox="0 0 100 100" class="ring-svg">
            <circle cx="50" cy="50" r="42" fill="none" stroke="oklch(0.92 0.005 260)" stroke-width="6" />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              :stroke="result.overall_score >= 0.8 ? 'oklch(0.55 0.18 20)' : result.overall_score >= 0.5 ? 'oklch(0.65 0.16 75)' : 'oklch(0.48 0.14 165)'"
              stroke-width="6"
              stroke-linecap="round"
              :stroke-dasharray="2 * Math.PI * 42"
              :stroke-dashoffset="2 * Math.PI * 42 * (1 - result.overall_score)"
              transform="rotate(-90 50 50)"
              class="ring-fill"
            />
            <text x="50" y="42" text-anchor="middle" class="ring-value">{{ scorePercent(result.overall_score) }}</text>
            <text x="50" y="60" text-anchor="middle" class="ring-unit">分</text>
          </svg>
        </div>
      </div>

      <div class="metric-grid">
        <div v-for="metric in overviewMetrics" :key="metric.label" class="metric-item">
          <span class="metric-value" :class="{ muted: metric.muted }">{{ metric.value }}</span>
          <span class="metric-label">{{ metric.label }}</span>
        </div>
      </div>
    </div>

    <div class="insight-grid">
      <section class="insight-card">
        <div class="card-head">
          <h3>标准评估摘要</h3>
          <p>来自 `reasoning_chain.standard_evaluation.summary`，表示质检链路的业务判定摘要。</p>
        </div>
        <p class="summary-text">{{ businessSummary }}</p>

        <div v-if="matchedRules.length" class="detail-block">
          <span class="detail-title">命中规则</span>
          <div class="chip-list">
            <span v-for="(item, index) in matchedRules" :key="`rule-${index}`" class="chip">
              {{ itemLabel(item, `规则 ${index + 1}`) }}
            </span>
          </div>
        </div>

        <div v-if="unmatchedDefects.length" class="detail-block">
          <span class="detail-title">未映射缺陷</span>
          <div class="chip-list">
            <span v-for="(item, index) in unmatchedDefects" :key="`defect-${index}`" class="chip warning">
              {{ itemLabel(item, `缺陷 ${index + 1}`) }}
            </span>
          </div>
        </div>
      </section>

      <section class="insight-card">
        <div class="card-head">
          <h3>文本可信度评估</h3>
          <p>来自 `reasoning_chain.trust_scoring`，针对质检输出文本做可信度估计，不等于业务风险等级。</p>
        </div>

        <div v-if="trustScoring" class="trust-grid">
          <div
            v-for="item in trustSummaryItems"
            :key="item.label"
            class="trust-item"
            :class="item.tone"
          >
            <span class="trust-label">{{ item.label }}</span>
            <span class="trust-value">{{ item.value }}</span>
          </div>
        </div>
        <div v-else class="empty-note">
          当前结果暂无文本可信度评分。
        </div>

        <p class="trust-note">
          “幻觉风险”和“过度肯定风险”反映的是总结文本是否缺乏引用、是否用语过满，不直接表示质检业务本身的高低风险。
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.summary-tab {
  padding: 24px;
  max-width: 980px;
  display: grid;
  gap: 24px;
}

.summary-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 32px;
  align-items: start;
}

.verdict-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.verdict-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  border-radius: 12px;
  font-weight: 700;
  font-size: 17px;
}

.verdict-success {
  background: oklch(0.92 0.06 165 / 0.3);
  color: oklch(0.4 0.12 165);
}

.verdict-danger {
  background: oklch(0.92 0.08 20 / 0.3);
  color: oklch(0.45 0.16 20);
}

.verdict-warning {
  background: oklch(0.92 0.1 85 / 0.3);
  color: oklch(0.5 0.14 80);
}

.verdict-info {
  background: oklch(0.92 0.03 260 / 0.3);
  color: oklch(0.4 0.04 260);
}

.verdict-icon {
  font-size: 20px;
}

.score-ring {
  width: 140px;
  height: 140px;
}

.ring-svg {
  width: 100%;
  height: 100%;
}

.ring-fill {
  transition: stroke-dashoffset 0.8s ease;
}

.ring-value {
  font-size: 26px;
  font-weight: 700;
  fill: oklch(0.25 0.01 260);
}

.ring-unit {
  font-size: 12px;
  fill: oklch(0.5 0.01 260);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-item {
  padding: 14px 16px;
  background: oklch(0.985 0.003 260);
  border-radius: 8px;
  border: 1px solid oklch(0.92 0.005 260);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: oklch(0.25 0.01 260);
  font-family: "JetBrains Mono", "Cascadia Code", monospace;
  word-break: break-word;
}

.metric-value.muted {
  color: oklch(0.6 0.005 260);
}

.metric-label {
  font-size: 12px;
  color: oklch(0.5 0.01 260);
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.insight-card {
  padding: 18px;
  border-radius: 12px;
  border: 1px solid oklch(0.92 0.005 260);
  background: #fff;
  display: grid;
  gap: 16px;
}

.card-head h3 {
  margin: 0;
  font-size: 16px;
  color: oklch(0.22 0.01 260);
}

.card-head p {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: oklch(0.5 0.01 260);
}

.summary-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  color: oklch(0.32 0.01 260);
  white-space: pre-wrap;
}

.detail-block {
  display: grid;
  gap: 8px;
}

.detail-title {
  font-size: 12px;
  font-weight: 600;
  color: oklch(0.45 0.01 260);
}

.chip-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: oklch(0.97 0.005 260);
  color: oklch(0.32 0.01 260);
  font-size: 12px;
}

.chip.warning {
  background: oklch(0.96 0.05 85 / 0.25);
  color: oklch(0.45 0.12 80);
}

.trust-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.trust-item {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid oklch(0.92 0.005 260);
  background: oklch(0.985 0.003 260);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trust-item.success {
  border-color: oklch(0.75 0.08 165);
}

.trust-item.warning {
  border-color: oklch(0.8 0.1 85);
}

.trust-item.danger {
  border-color: oklch(0.75 0.12 20);
}

.trust-label {
  font-size: 12px;
  color: oklch(0.48 0.01 260);
}

.trust-value {
  font-size: 20px;
  font-weight: 700;
  color: oklch(0.22 0.01 260);
}

.empty-note,
.trust-note {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: oklch(0.45 0.01 260);
}

@media (max-width: 1080px) {
  .summary-layout {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .insight-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .metric-grid,
  .trust-grid {
    grid-template-columns: 1fr;
  }
}
</style>
