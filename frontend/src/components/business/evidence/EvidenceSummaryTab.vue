<script setup lang="ts">
import type { InspectionResult } from "@/types/result.types"

defineProps<{
  result: InspectionResult
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

function scoreColor(s: number) {
  if (s >= 0.8) return "danger"
  if (s >= 0.5) return "warning"
  return "success"
}

function scorePercent(s: number) {
  return (s * 100).toFixed(1)
}
</script>

<template>
  <div class="summary-tab">
    <div class="summary-layout">
      <!-- Left: verdict and score -->
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
            <circle cx="50" cy="50" r="42" fill="none" stroke="oklch(0.92 0.005 260)" stroke-width="6"/>
            <circle
              cx="50" cy="50" r="42"
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

      <!-- Right: metric grid -->
      <div class="metric-grid">
        <div class="metric-item">
          <span class="metric-value">{{ result.defects?.length ?? 0 }}</span>
          <span class="metric-label">检出缺陷</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ result.citations ? (Array.isArray(result.citations) ? result.citations.length : Object.keys(result.citations).length) : 0 }}</span>
          <span class="metric-label">引用证据</span>
        </div>
        <div class="metric-item">
          <span class="metric-value" :class="`tokens-${result.tokens_used ? 'val' : 'na'}`">{{ result.tokens_used?.toLocaleString() ?? '-' }}</span>
          <span class="metric-label">Token 消耗</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ result.latency_ms ? `${result.latency_ms}ms` : '-' }}</span>
          <span class="metric-label">推理耗时</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ result.llm_model }}</span>
          <span class="metric-label">模型引擎</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ result.prompt_version }}</span>
          <span class="metric-label">Prompt 版本</span>
        </div>
      </div>
    </div>

    <!-- Explanation -->
    <div v-if="result.verdict" class="explanation">
      <p>
        <template v-if="result.verdict === 'pass'">
          该检测结果判定为<strong>通过</strong>，异常分数 {{ scorePercent(result.overall_score) }} 分，
          未发现显著缺陷或风险指标在可接受范围内。
        </template>
        <template v-else-if="result.verdict === 'fail'">
          该检测结果判定为<strong>不通过</strong>，异常分数 {{ scorePercent(result.overall_score) }} 分，
          检测到 {{ result.defects?.length ?? 0 }} 个缺陷，建议关注图像证据和引用依据。
        </template>
        <template v-else-if="result.verdict === 'manual_required'">
          该检测结果<strong>需人工复核</strong>，异常分数 {{ scorePercent(result.overall_score) }} 分，
          模型置信度不足，建议专家介入判定。
        </template>
        <template v-else>
          该检测结果{{ VERDICT_LABELS[result.verdict] }}，异常分数 {{ scorePercent(result.overall_score) }} 分。
        </template>
      </p>
    </div>
  </div>
</template>

<style scoped>
.summary-tab {
  padding: 24px;
  max-width: 900px;
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
  grid-template-columns: repeat(3, 1fr);
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
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
}

.metric-value.tokens-na {
  color: oklch(0.6 0.005 260);
}

.metric-label {
  font-size: 12px;
  color: oklch(0.5 0.01 260);
}

.explanation {
  margin-top: 24px;
  padding: 14px 18px;
  background: oklch(0.97 0.005 260);
  border-radius: 8px;
  border: 1px solid oklch(0.92 0.005 260);
}

.explanation p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: oklch(0.4 0.01 260);
}

.explanation strong {
  color: oklch(0.25 0.01 260);
}
</style>
