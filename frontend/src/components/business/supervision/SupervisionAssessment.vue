<script setup lang="ts">
import { STATUS_LABELS } from "@/types/supervision.types";
defineProps<{ output: Record<string, any>; reviewStatus?: string }>();
const riskLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
  unknown: "未知",
};
const findingLabels: Record<string, string> = {
  instrument_suspected: "设备或数据质量异常",
  product_abnormal: "产品指标异常",
  baseline_deviation: "偏离正常响应",
  visual_abnormal: "图片可观察缺陷",
};
</script>
<template>
  <section class="assessment">
    <div class="assessment-head">
      <strong>评估结果</strong
      ><el-tag>{{
        STATUS_LABELS[reviewStatus || output.status] || reviewStatus || output.status
      }}</el-tag>
    </div>
    <p>{{ output.summary }}</p>
    <el-descriptions :column="2" border>
      <el-descriptions-item v-if="output.risk_level" label="风险等级">{{
        riskLabels[output.risk_level] || output.risk_level
      }}</el-descriptions-item>
      <el-descriptions-item label="风险概率">{{
        output.probability == null ? "未校准，不提供概率" : output.probability
      }}</el-descriptions-item>
      <el-descriptions-item v-if="output.data_completeness != null" label="数据完整度"
        >{{ Math.round(output.data_completeness * 100) }}%</el-descriptions-item
      >
      <el-descriptions-item v-if="output.early_warning != null" label="提前提示">{{
        output.early_warning ? "发现产品异常信号" : "未发现提前预警信号"
      }}</el-descriptions-item>
    </el-descriptions>
    <el-alert
      v-if="output.missing_inputs?.length"
      type="warning"
      :closable="false"
      title="需要补齐"
      :description="output.missing_inputs.join('；')"
    />
    <el-alert
      v-if="output.conflicts?.length"
      type="error"
      :closable="false"
      title="待处理冲突"
      :description="output.conflicts.join('；')"
    />
    <el-alert
      v-if="output.uncovered_categories?.length"
      type="warning"
      :closable="false"
      title="尚未覆盖类别"
      :description="output.uncovered_categories.join('、')"
    />
    <el-table v-if="output.findings?.length" :data="output.findings">
      <el-table-column prop="item" label="检测项目" /><el-table-column
        prop="event_id"
        label="测量来源"
      /><el-table-column prop="value" label="检测值" />
      <el-table-column label="异常类型"
        ><template #default="{ row }">{{
          findingLabels[row.type] || row.type
        }}</template></el-table-column
      >
      <el-table-column prop="standard_ref" label="标准依据" />
    </el-table>
    <el-table v-if="output.selected?.length" :data="output.selected"
      ><el-table-column prop="case_id" label="案件编号" /><el-table-column
        prop="category"
        label="类别" /><el-table-column prop="sample_count" label="样本数" /><el-table-column
        prop="reason"
        label="选择理由"
    /></el-table>
    <el-table v-if="output.rejected?.length" :data="output.rejected"
      ><el-table-column prop="case_id" label="未纳入对象" /><el-table-column
        prop="reason"
        label="原因"
    /></el-table>
    <div v-if="output.normalized_signals?.length" class="evidence-list">
      归一化风险线索：{{ output.normalized_signals.join("；") }}
    </div>
    <div v-if="output.evidence_ids?.length" class="evidence-list">
      引用证据：{{ output.evidence_ids.join("、") }}
    </div>
    <ul v-if="output.limitations?.length">
      <li v-for="(limit, index) in output.limitations" :key="index">{{ limit }}</li>
    </ul>
  </section>
</template>
<style scoped>
.assessment {
  border-left: 3px solid var(--el-color-primary);
  padding: 16px;
  background: var(--el-fill-color-light);
}
.assessment-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.assessment .el-alert {
  margin-top: 12px;
}
.assessment p {
  line-height: 1.7;
}
.evidence-list,
ul {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 12px;
}
ul {
  padding-left: 18px;
}
</style>
