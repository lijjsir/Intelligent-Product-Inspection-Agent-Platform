<script setup lang="ts">
import { computed } from "vue";
import { useQualityStore } from "@/stores/quality.store";

const store = useQualityStore();
const report = computed(() => store.report);
const loading = computed(() => store.loading);
const traceMeta = computed(() => store.traceMeta);

const metricItems = computed(() => {
  const value = report.value;
  if (!value) return [];
  return [
    { label: "结果数", value: value.total_results, tone: "default" },
    { label: "幻觉率", value: `${(value.hallucination_rate * 100).toFixed(1)}%`, tone: "warning" },
    { label: "点踩率", value: `${(value.thumbs_down_rate * 100).toFixed(1)}%`, tone: "danger" },
    { label: "聊天评分", value: value.chat_score_count, tone: "default" },
    { label: "平均可信度", value: `${(value.chat_avg_trust_score * 100).toFixed(1)}%`, tone: "success" },
    { label: "聊天引用率", value: `${(value.chat_citation_rate * 100).toFixed(1)}%`, tone: "warning" },
  ];
});

function traceMetaText() {
  const meta = traceMeta.value;
  if (!meta) return "质量追踪尚未加载，质量报告以 Langfuse 远端 Trace 为准";
  if (meta.langfuse_status === "ok") {
    return meta.canonical_source === "langfuse"
      ? `质量报告以 Langfuse 远端 Trace 为准，当前 ${meta.item_count} 条远端 Trace`
      : "Langfuse 未作为当前质量口径，报表不会使用本地旧记录伪装为远端同步数据";
  }
  if (meta.langfuse_status === "error") return `Langfuse 连接异常：${meta.langfuse_error || "无法读取远端 Trace"}`;
  return "Langfuse 未启用或未加载，质量报告显示本地开发兜底数据";
}

function traceMetaType() {
  if (traceMeta.value?.langfuse_status === "ok") return "success";
  if (traceMeta.value?.langfuse_status === "error") return "warning";
  return "info";
}
</script>

<template>
  <div class="quality-panel" v-loading="loading">
    <el-alert :title="traceMetaText()" :type="traceMetaType()" :closable="false" show-icon />

    <div v-if="report" class="metric-strip">
      <div v-for="item in metricItems" :key="item.label" class="metric-cell">
        <div class="metric-title">{{ item.label }}</div>
        <div class="metric-value" :class="item.tone">{{ item.value }}</div>
      </div>
    </div>

    <el-card shadow="never" class="quality-card">
      <template #header>模型对比</template>
      <el-table :data="report?.model_metrics || []" v-loading="loading" size="small">
        <el-table-column prop="model_key" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column prop="result_count" label="结果数" width="100" />
        <el-table-column label="通过率" width="120">
          <template #default="{ row }">{{ (row.pass_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="幻觉率" width="120">
          <template #default="{ row }">{{ (row.hallucination_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="点踩率" width="120">
          <template #default="{ row }">{{ (row.thumbs_down_rate * 100).toFixed(1) }}%</template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="trend-grid">
      <el-card shadow="never" class="quality-card">
        <template #header>幻觉率趋势</template>
        <el-table :data="report?.hallucination_trend || []" size="small">
          <el-table-column prop="bucket" label="日期" />
          <el-table-column label="值">
            <template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="quality-card">
        <template #header>聊天可信度趋势</template>
        <el-table :data="report?.chat_trust_trend || []" size="small">
          <el-table-column prop="bucket" label="日期" />
          <el-table-column label="值">
            <template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="quality-card">
        <template #header>点踩率趋势</template>
        <el-table :data="report?.thumbs_down_trend || []" size="small">
          <el-table-column prop="bucket" label="日期" />
          <el-table-column label="值">
            <template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.quality-panel { display: grid; gap: 16px; }
.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #e5e7eb;
}
.metric-cell { min-width: 0; padding: 14px 16px; background: #f9fafb; }
.metric-title { color: #6b7280; font-size: 13px; }
.metric-value { margin-top: 6px; font-size: 24px; font-weight: 700; color: #1f2937; }
.metric-value.warning { color: #d97706; }
.metric-value.danger { color: #dc2626; }
.metric-value.success { color: #059669; }
.quality-card { border-radius: 8px; border-color: #e5e7eb; }
.trend-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }

@media (max-width: 1180px) {
  .metric-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .trend-grid { grid-template-columns: 1fr; }
}
</style>
