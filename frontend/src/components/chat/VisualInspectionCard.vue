<script setup lang="ts">
defineProps<{
  imageCount?: number;
  defects?: Array<{
    defect_type: string;
    location: string;
    bbox?: unknown;
    severity: string;
    confidence: number;
    evidence: string;
  }>;
  imageQuality?: string;
  requiresRecheck?: boolean;
  confidence?: number;
}>();
</script>

<template>
  <div class="visual-card">
    <div class="visual-card-header">
      <span class="visual-card-title">视觉缺陷检查</span>
      <span class="visual-card-sub">VisionInspectionAgent</span>
    </div>
    <div class="visual-card-meta">
      <el-tag size="small" effect="plain" type="info">{{ imageCount ?? 0 }} 张图片</el-tag>
      <el-tag v-if="imageQuality" size="small" effect="plain" type="warning">{{ imageQuality }}</el-tag>
      <el-tag v-if="requiresRecheck" size="small" type="danger" effect="plain">需复核</el-tag>
      <el-tag v-if="confidence != null" size="small" effect="plain">置信度 {{ (confidence * 100).toFixed(0) }}%</el-tag>
    </div>
    <div v-if="defects?.length" class="visual-card-defects">
      <div v-for="(d, di) in defects" :key="di" class="visual-defect">
        <div class="visual-defect-header">
          <el-tag size="small" effect="dark" :type="d.severity === 'high' ? 'danger' : d.severity === 'medium' ? 'warning' : 'info'">
            {{ d.severity.toUpperCase() }}
          </el-tag>
          <strong>{{ d.defect_type }}</strong>
          <span class="visual-defect-conf">置信度 {{ (d.confidence * 100).toFixed(0) }}%</span>
        </div>
        <div class="visual-defect-body">
          <div v-if="d.location" class="visual-defect-loc">
            <span>位置</span>
            <strong>{{ d.location }}</strong>
          </div>
          <div v-if="d.evidence" class="visual-defect-evidence">{{ d.evidence }}</div>
        </div>
      </div>
    </div>
    <div v-else class="visual-card-empty">
      未发现明显缺陷。
    </div>
  </div>
</template>

<style scoped>
.visual-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fefce8;
}

.visual-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.visual-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}

.visual-card-sub {
  font-size: 11px;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.visual-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.visual-card-empty {
  font-size: 12px;
  color: #9ca3af;
  font-style: italic;
}

.visual-card-defects {
  display: grid;
  gap: 8px;
}

.visual-defect {
  display: grid;
  gap: 6px;
  padding: 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #fde68a;
}

.visual-defect-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.visual-defect-header strong {
  font-size: 13px;
  color: #374151;
}

.visual-defect-conf {
  font-size: 11px;
  color: #6b7280;
}

.visual-defect-body {
  display: grid;
  gap: 4px;
}

.visual-defect-loc {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.visual-defect-loc span {
  color: #6b7280;
  font-weight: 600;
}

.visual-defect-loc strong {
  color: #374151;
}

.visual-defect-evidence {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}
</style>
