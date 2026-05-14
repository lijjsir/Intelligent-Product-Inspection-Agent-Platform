<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useQualityStore } from "@/stores/quality.store";
import type { QualityTraceItem } from "@/types/governance.types";

const store = useQualityStore();
const source = ref<"all" | "inspection" | "chat">("all");

onMounted(() => refreshTraces());
function refreshTraces() { return store.fetchTraces({ source: source.value }); }

function openLangfuseTrace(row: QualityTraceItem) {
  if (!canOpenLangfuse(row)) { ElMessage.warning("当前 Trace 暂无可跳转的 Langfuse 地址"); return; }
  window.open(row.trace_url, "_blank", "noopener,noreferrer");
}

function pct(value: number | null | undefined) { return value == null ? "-" : `${(value * 100).toFixed(0)}%`; }
function riskType(value: number | null | undefined) { if (value == null) return "info"; return value >= 0.6 ? "danger" : value >= 0.3 ? "warning" : "success"; }
function trustColor(value: number | null | undefined) { if (value == null) return "#9ca3af"; return value >= 0.85 ? "#059669" : value >= 0.6 ? "#d97706" : "#dc2626"; }
function fmtTs(ts: string | null | undefined) { if (!ts) return "-"; return new Date(ts).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function langfuseStatus(row: QualityTraceItem) { return row.langfuse_status || (row.langfuse_synced ? "synced" : "local_only"); }
function canOpenLangfuse(row: QualityTraceItem) { return langfuseStatus(row) === "synced" && !!row.trace_url; }
function langfuseStatusType(row: QualityTraceItem) {
  const status = langfuseStatus(row);
  if (status === "synced") return "success";
  if (status === "missing") return "danger";
  if (status === "unknown") return "info";
  return "warning";
}
function langfuseStatusLabel(row: QualityTraceItem) {
  const status = langfuseStatus(row);
  if (status === "synced") return "已同步";
  if (status === "missing") return "已删除";
  if (status === "unknown") return "未知";
  return "本地";
}
</script>

<template>
  <div class="qt-panel">
    <!-- Summary bar -->
    <div class="qt-summary">
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ store.traces.length }}</span>
        <span class="qt-summary-label">Trace 总数</span>
      </div>
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ store.traces.filter((t: QualityTraceItem) => langfuseStatus(t) === "synced").length }}</span>
        <span class="qt-summary-label">已同步</span>
      </div>
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ store.traces.filter((t: QualityTraceItem) => t.thumbs_down_count > 0).length }}</span>
        <span class="qt-summary-label">有点踩</span>
      </div>
      <div class="qt-spacer" />
      <el-segmented v-model="source" size="small" :options="[{ label:'全部',value:'all' },{ label:'检验',value:'inspection' },{ label:'聊天',value:'chat' }]" @change="refreshTraces" />
      <el-button size="small" @click="refreshTraces">刷新</el-button>
    </div>

    <!-- Table -->
    <el-table :data="store.traces" v-loading="store.loading" empty-text="暂无 Trace 数据，执行检测任务后会出现" size="small" class="qt-table" row-key="trace_id">
      <el-table-column label="时间" width="150" prop="created_at" :formatter="(_r:any,_c:any,val:string)=>fmtTs(val)" sortable />
      <el-table-column label="来源" width="70">
        <template #default="{ row }"><el-tag size="small" :type="row.source_type==='chat'?'success':'info'">{{ row.source_type==="chat"?"聊天":"检验" }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="verdict" label="结论" width="80">
        <template #default="{ row }"><el-tag v-if="row.verdict" size="small" :type="row.verdict==='pass'?'success':row.verdict==='fail'?'danger':'warning'">{{ row.verdict }}</el-tag><span v-else class="text-zinc-400 text-xs">-</span></template>
      </el-table-column>
      <el-table-column prop="model_key" label="模型" width="160" show-overflow-tooltip />
      <el-table-column label="可信度" width="100" sortable prop="trust_score">
        <template #default="{ row }">
          <span :style="{ color: trustColor(row.trust_score) }" class="font-semibold">{{ pct(row.trust_score) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="幻觉风险" width="100" prop="hallucination_risk">
        <template #default="{ row }"><el-tag size="small" :type="riskType(row.hallucination_risk)" effect="plain">{{ pct(row.hallucination_risk) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="过度自信" width="100" prop="overconfidence">
        <template #default="{ row }">{{ pct(row.overconfidence) }}</template>
      </el-table-column>
      <el-table-column prop="total_tokens" label="Token" width="80" />
      <el-table-column label="反馈" width="90">
        <template #default="{ row }">{{ row.feedback_count ?? 0 }} / {{ row.thumbs_down_count ?? 0 }}踩</template>
      </el-table-column>
      <el-table-column label="同步" width="80">
        <template #default="{ row }"><el-tag size="small" :type="langfuseStatusType(row)">{{ langfuseStatusLabel(row) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" :disabled="!canOpenLangfuse(row)" @click="openLangfuseTrace(row)">Langfuse</el-button>
        </template>
      </el-table-column>

      <!-- Expand row for detail IDs -->
      <el-table-column type="expand" width="40">
        <template #default="{ row }">
          <div class="qt-expand">
            <div class="qt-expand-item"><label>Trace ID</label><code>{{ row.trace_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Task ID</label><code>{{ row.task_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Result ID</label><code>{{ row.result_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Session</label><code>{{ row.session_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Message</label><code>{{ row.assistant_message_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Observation</label><code>{{ row.observation_id || "-" }}</code></div>
            <div class="qt-expand-item"><label>Review Model</label><code>{{ row.review_model || "-" }}</code></div>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.qt-panel { display: grid; gap: 12px; }

.qt-summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.qt-summary-item { display: flex; flex-direction: column; }
.qt-summary-num { font-size: 20px; font-weight: 700; color: #1f2937; line-height: 1.2; }
.qt-summary-label { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.qt-spacer { flex: 1; }

.qt-table :deep(.el-table__body-wrapper) { max-height: calc(100vh - 340px); overflow-y: auto; }

.qt-expand { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 16px; padding: 8px 0; }
.qt-expand-item label { display: block; font-size: 11px; font-weight: 600; color: #9ca3af; margin-bottom: 2px; }
.qt-expand-item code { font-size: 12px; color: #374151; word-break: break-all; }

@media (max-width: 768px) {
  .qt-expand { grid-template-columns: repeat(2, 1fr); }
}
</style>
