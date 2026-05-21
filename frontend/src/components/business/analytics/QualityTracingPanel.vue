<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useQualityStore } from "@/stores/quality.store";
import type { QualityTraceItem } from "@/types/governance.types";

const store = useQualityStore();
const source = ref<"all" | "inspection" | "chat">("all");
const deleting = ref<string | null>(null);

const sourceOptions = [
  { label: "全部", value: "all" },
  { label: "检验", value: "inspection" },
  { label: "聊天", value: "chat" },
];

const traceMeta = computed(() => store.traceMeta);
const syncedCount = computed(() => store.traces.filter((item) => langfuseStatus(item) === "synced").length);
const riskyCount = computed(
  () => store.traces.filter((item) => item.thumbs_down_count > 0 || (item.hallucination_risk ?? 0) >= 0.6).length,
);

onMounted(() => refreshTraces());

function refreshTraces() {
  return store.fetchTraces({ source: source.value });
}

function extractTraceId(traceUrl: string): string {
  const idx = traceUrl.lastIndexOf("/traces/");
  return idx >= 0 ? traceUrl.slice(idx + "/traces/".length) : "";
}

function openLangfuseTrace(row: QualityTraceItem) {
  if (!canOpenLangfuse(row) || !row.trace_url) {
    ElMessage.warning("当前 Trace 暂无可跳转的 Langfuse 地址");
    return;
  }
  const traceId = extractTraceId(row.trace_url);
  if (!traceId) {
    window.open(row.trace_url, "_blank", "noopener,noreferrer");
    return;
  }
  window.open(`/api/v1/langfuse/redirect?trace_id=${encodeURIComponent(traceId)}`, "_blank", "noopener,noreferrer");
}

async function handleDeleteTrace(row: QualityTraceItem) {
  try {
    await ElMessageBox.confirm(
      "确定要删除此 Trace 吗？会先删除 Langfuse 远端记录，成功后再清理本地关联数据。",
      "确认删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }

  deleting.value = row.trace_id;
  try {
    const result = await store.deleteTrace(row.trace_id);
    if (result?.deleted) {
      ElMessage.success(result.message || "Trace 已删除");
      return;
    }
    ElMessage.warning(result?.message || "Trace 未删除，请检查 Langfuse 连接状态");
  } catch (e: any) {
    const msg = e?.response?.data?.message || e?.message || "删除失败";
    ElMessage.error(msg);
  } finally {
    deleting.value = null;
  }
}

function pct(value: number | null | undefined) {
  return value == null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function riskType(value: number | null | undefined) {
  if (value == null) return "info";
  return value >= 0.6 ? "danger" : value >= 0.3 ? "warning" : "success";
}

function trustColor(value: number | null | undefined) {
  if (value == null) return "#9ca3af";
  return value >= 0.85 ? "#059669" : value >= 0.6 ? "#d97706" : "#dc2626";
}

function fmtTs(ts: string | null | undefined) {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function langfuseStatus(row: QualityTraceItem) {
  return row.langfuse_status || (row.langfuse_synced ? "synced" : "local_only");
}

function canOpenLangfuse(row: QualityTraceItem) {
  return langfuseStatus(row) === "synced" && !!row.trace_url;
}

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
  if (status === "missing") return "远端缺失";
  if (status === "unknown") return "待确认";
  return "本地";
}

function metaAlertType() {
  if (traceMeta.value?.langfuse_status === "ok") return "success";
  if (traceMeta.value?.langfuse_status === "error") return "warning";
  return "info";
}

function metaAlertTitle() {
  const meta = traceMeta.value;
  if (!meta) return "";
  if (meta.langfuse_status === "ok") {
    return meta.canonical_source === "langfuse"
      ? "Langfuse 已连接，列表以远端 Trace 为准"
      : "Langfuse 已连接，当前无远端 Trace，显示本地记录";
  }
  if (meta.langfuse_status === "error") {
    return `Langfuse 连接异常：${meta.langfuse_error || "无法读取远端 Trace"}`;
  }
  if (meta.langfuse_status === "disabled") return "Langfuse 未启用，当前仅显示本地记录";
  return "正在确认 Langfuse 同步状态";
}
</script>

<template>
  <div class="qt-panel">
    <el-alert
      v-if="traceMeta"
      :title="metaAlertTitle()"
      :type="metaAlertType()"
      :closable="false"
      show-icon
    />

    <div class="qt-summary">
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ store.traces.length }}</span>
        <span class="qt-summary-label">当前记录</span>
      </div>
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ syncedCount }}</span>
        <span class="qt-summary-label">远端同步</span>
      </div>
      <div class="qt-summary-item">
        <span class="qt-summary-num">{{ riskyCount }}</span>
        <span class="qt-summary-label">风险记录</span>
      </div>
      <div class="qt-spacer" />
      <el-segmented v-model="source" size="small" :options="sourceOptions" @change="refreshTraces" />
      <el-button size="small" @click="refreshTraces">刷新</el-button>
    </div>

    <el-table
      :data="store.traces"
      v-loading="store.loading"
      empty-text="暂无 Trace 数据，执行检测或聊天后会出现"
      size="small"
      class="qt-table"
      row-key="trace_id"
    >
      <el-table-column label="时间" width="150" prop="created_at" :formatter="(_r:any,_c:any,val:string)=>fmtTs(val)" sortable />
      <el-table-column label="来源" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source_type === 'chat' ? 'success' : 'info'">
            {{ row.source_type === "chat" ? "聊天" : "检验" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="verdict" label="结论" width="80">
        <template #default="{ row }">
          <el-tag
            v-if="row.verdict"
            size="small"
            :type="row.verdict === 'pass' ? 'success' : row.verdict === 'fail' ? 'danger' : 'warning'"
          >
            {{ row.verdict }}
          </el-tag>
          <span v-else class="text-zinc-400 text-xs">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="model_key" label="模型" min-width="160" show-overflow-tooltip />
      <el-table-column label="可信度" width="100" sortable prop="trust_score">
        <template #default="{ row }">
          <span :style="{ color: trustColor(row.trust_score) }" class="font-semibold">{{ pct(row.trust_score) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="幻觉风险" width="100" prop="hallucination_risk">
        <template #default="{ row }">
          <el-tag size="small" :type="riskType(row.hallucination_risk)" effect="plain">{{ pct(row.hallucination_risk) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="过度自信" width="100" prop="overconfidence">
        <template #default="{ row }">{{ pct(row.overconfidence) }}</template>
      </el-table-column>
      <el-table-column prop="total_tokens" label="Token" width="80" />
      <el-table-column label="反馈" width="90">
        <template #default="{ row }">{{ row.feedback_count ?? 0 }} / {{ row.thumbs_down_count ?? 0 }} 踩</template>
      </el-table-column>
      <el-table-column label="同步" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="langfuseStatusType(row)">{{ langfuseStatusLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" :disabled="!canOpenLangfuse(row)" @click="openLangfuseTrace(row)">
            Langfuse
          </el-button>
          <el-button size="small" link type="danger" :loading="deleting === row.trace_id" @click="handleDeleteTrace(row)">
            删除
          </el-button>
        </template>
      </el-table-column>

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
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.qt-summary-item { display: flex; flex-direction: column; min-width: 72px; }
.qt-summary-num { font-size: 20px; font-weight: 700; color: #1f2937; line-height: 1.2; }
.qt-summary-label { font-size: 11px; color: #6b7280; margin-top: 2px; }
.qt-spacer { flex: 1; }

.qt-table :deep(.el-table__body-wrapper) { max-height: calc(100vh - 340px); overflow-y: auto; }

.qt-expand { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 16px; padding: 8px 0; }
.qt-expand-item label { display: block; font-size: 11px; font-weight: 600; color: #6b7280; margin-bottom: 2px; }
.qt-expand-item code { font-size: 12px; color: #374151; word-break: break-all; }

@media (max-width: 768px) {
  .qt-expand { grid-template-columns: repeat(2, 1fr); }
}
</style>
