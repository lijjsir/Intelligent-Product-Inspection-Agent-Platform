<script setup lang="ts">
defineProps<{
  finalVerdict?: string;
  overallScore?: number;
  riskLevel?: string;
  evidenceUsed?: string[];
  conflicts?: Array<Record<string, unknown>>;
  limitations?: string[];
  recommendedAction?: string[];
  answer?: string;
  confidence?: number;
}>();
</script>

<template>
  <div class="quality-card">
    <div class="quality-card-header">
      <span class="quality-card-title">质量综合评估</span>
      <span class="quality-card-sub">QualityAnalysisAgent</span>
    </div>
    <div class="quality-card-verdict">
      <el-tag size="large" effect="dark" :type="finalVerdict === 'pass' ? 'success' : finalVerdict === 'fail' ? 'danger' : 'warning'">
        {{ finalVerdict || "pending" }}
      </el-tag>
      <span v-if="overallScore != null" class="quality-card-score">综合评分 {{ (overallScore * 100).toFixed(1) }}%</span>
      <span v-if="riskLevel" class="quality-card-risk">风险 {{ riskLevel }}</span>
    </div>
    <div v-if="evidenceUsed?.length" class="quality-card-section">
      <span class="quality-card-section-label">使用的证据</span>
      <div class="quality-card-tags">
        <el-tag v-for="ev in evidenceUsed" :key="ev" size="small" type="success" effect="plain">{{ ev }}</el-tag>
      </div>
    </div>
    <div v-if="conflicts?.length" class="quality-card-section">
      <span class="quality-card-section-label">证据冲突</span>
      <div v-for="(c, ci) in conflicts" :key="ci" class="quality-conflict">
        {{ c.description || JSON.stringify(c) }}
      </div>
    </div>
    <div v-if="limitations?.length" class="quality-card-section">
      <span class="quality-card-section-label">局限</span>
      <div class="quality-card-tags">
        <el-tag v-for="lim in limitations" :key="lim" size="small" type="warning" effect="plain">{{ lim }}</el-tag>
      </div>
    </div>
    <div v-if="recommendedAction?.length" class="quality-card-section">
      <span class="quality-card-section-label">建议措施</span>
      <ul class="quality-card-actions-list">
        <li v-for="(act, ai) in recommendedAction" :key="ai">{{ act }}</li>
      </ul>
    </div>
    <div v-if="answer" class="quality-card-answer">{{ answer }}</div>
  </div>
</template>

<style scoped>
.quality-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f0fdf4;
}

.quality-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.quality-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}

.quality-card-sub {
  font-size: 11px;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.quality-card-verdict {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.quality-card-score {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.quality-card-risk {
  font-size: 12px;
  color: #6b7280;
}

.quality-card-section {
  display: grid;
  gap: 6px;
}

.quality-card-section-label {
  font-size: 11px;
  color: #6b7280;
  font-weight: 700;
  text-transform: uppercase;
}

.quality-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.quality-conflict {
  font-size: 12px;
  color: #991b1b;
  padding: 6px 8px;
  border-radius: 4px;
  background: #fee2e2;
}

.quality-card-actions-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #374151;
  line-height: 1.6;
}

.quality-card-answer {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #dcfce7;
}
</style>
