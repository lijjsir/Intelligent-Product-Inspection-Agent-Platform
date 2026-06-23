<script setup lang="ts">
defineProps<{
  sampleId?: string;
  assessmentState?: string;
  abnormalProbability?: number;
  riskLevel?: string;
  dataCompleteness?: number;
  earlyWarning?: boolean;
  canMakeFinalVerdict?: boolean;
  abnormalIndicators?: Array<{
    item: string;
    value: number;
    normal_range: string;
    deviation_type: string;
  }>;
  nextTestPriority?: Array<{
    item: string;
    reason: string;
  }>;
  suggestedAction?: string;
  confidence?: number;
}>();
</script>

<template>
  <div class="lab-card">
    <div class="lab-card-header">
      <span class="lab-card-title">实验室检测分析</span>
      <span class="lab-card-sub">LabDetectionAgent</span>
    </div>
    <div class="lab-card-meta">
      <el-tag size="small" effect="plain" type="info">样品 {{ sampleId || "-" }}</el-tag>
      <el-tag v-if="dataCompleteness != null" size="small" effect="plain" :type="dataCompleteness < 0.5 ? 'warning' : 'info'">
        完成度 {{ (dataCompleteness * 100).toFixed(0) }}%
      </el-tag>
      <el-tag size="small" effect="dark" :type="riskLevel === 'high' ? 'danger' : riskLevel === 'medium' ? 'warning' : 'info'">
        风险 {{ riskLevel || "-" }}
      </el-tag>
      <el-tag v-if="earlyWarning" size="small" type="danger" effect="plain">⚠ 早期预警</el-tag>
      <el-tag v-if="canMakeFinalVerdict === false" size="small" type="warning" effect="plain">数据不足，不可下结论</el-tag>
    </div>
    <div v-if="abnormalIndicators?.length" class="lab-card-indicators">
      <span class="lab-card-section-label">异常指标</span>
      <div v-for="(ind, ii) in abnormalIndicators" :key="ii" class="lab-indicator">
        <div class="lab-indicator-header">
          <strong>{{ ind.item }}</strong>
          <el-tag size="small" effect="dark" type="danger">{{ ind.deviation_type }}</el-tag>
        </div>
        <div class="lab-indicator-detail">
          <span>测量值 {{ ind.value }}，正常范围 {{ ind.normal_range }}</span>
        </div>
      </div>
    </div>
    <div v-if="nextTestPriority?.length" class="lab-card-next">
      <span class="lab-card-section-label">优先检测建议</span>
      <div v-for="(nt, ni) in nextTestPriority" :key="ni" class="lab-next-item">
        <strong>{{ nt.item }}</strong>
        <span v-if="nt.reason"> — {{ nt.reason }}</span>
      </div>
    </div>
    <div v-if="suggestedAction" class="lab-card-action">
      <span class="lab-card-section-label">建议措施</span>
      <div class="lab-card-action-text">{{ suggestedAction }}</div>
    </div>
    <div v-if="abnormalProbability != null" class="lab-card-footer">
      <span>异常概率 {{ (abnormalProbability * 100).toFixed(0) }}%</span>
      <span v-if="confidence != null">置信度 {{ (confidence * 100).toFixed(0) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.lab-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #eff6ff;
}

.lab-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.lab-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}

.lab-card-sub {
  font-size: 11px;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.lab-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.lab-card-section-label {
  font-size: 11px;
  color: #6b7280;
  font-weight: 700;
  text-transform: uppercase;
}

.lab-card-indicators,
.lab-card-next {
  display: grid;
  gap: 6px;
}

.lab-indicator {
  display: grid;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #dbeafe;
}

.lab-indicator-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.lab-indicator-header strong {
  font-size: 13px;
  color: #374151;
}

.lab-indicator-detail {
  font-size: 12px;
  color: #6b7280;
}

.lab-next-item {
  font-size: 12px;
  color: #374151;
  padding: 4px 8px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #dbeafe;
}

.lab-next-item strong {
  font-weight: 600;
}

.lab-card-action-text {
  font-size: 12px;
  color: #374151;
  line-height: 1.5;
}

.lab-card-footer {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: #9ca3af;
}
</style>
