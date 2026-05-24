<script setup lang="ts">
import { computed } from "vue";

import ChatTrustTrendChart from "@/components/business/analytics/ChatTrustTrendChart.vue";
import ThumbsDownTrendChart from "@/components/business/analytics/ThumbsDownTrendChart.vue";
import ThumbsUpTrendChart from "@/components/business/analytics/ThumbsUpTrendChart.vue";
import { useQualityStore } from "@/stores/quality.store";

const store = useQualityStore();
const report = computed(() => store.report);
const loading = computed(() => store.reportLoading);
const traceMeta = computed(() => store.traceMeta);

function formatRate(value: number | null | undefined) {
  return `${(((value ?? 0) as number) * 100).toFixed(1)}%`;
}

function feedbackSubtext(share: number, coverage: number, total: number) {
  if (!total) return "暂无有效反馈";
  return `占反馈 ${formatRate(share)} · 覆盖率 ${formatRate(coverage)}`;
}

const summaryCards = computed(() => {
  const r = report.value;
  if (!r) return [];
  return [
    {
      label: "可评估消息",
      value: r.chat_message_count ? `${r.chat_score_count} / ${r.chat_message_count}` : `${r.chat_score_count}`,
      sub: `可信度覆盖率 ${formatRate(r.chat_scored_rate)}`,
      tone: r.chat_scored_rate >= 0.6 ? "success" : r.chat_score_count > 0 ? "warning" : "default",
    },
    {
      label: "平均可信度",
      value: formatRate(r.chat_avg_trust_score),
      sub: "来自 LLM 评审或规则兜底的综合得分",
      tone: r.chat_avg_trust_score >= 0.8 ? "success" : r.chat_avg_trust_score >= 0.6 ? "warning" : "danger",
    },
    {
      label: "聊天幻觉风险",
      value: formatRate(r.chat_avg_hallucination_risk),
      sub: `高风险占比 ${formatRate(r.chat_hallucination_rate)}`,
      tone: r.chat_avg_hallucination_risk >= 0.6 ? "danger" : r.chat_avg_hallucination_risk >= 0.3 ? "warning" : "success",
    },
    {
      label: "过度自信风险",
      value: formatRate(r.chat_avg_overconfidence),
      sub: `高风险占比 ${formatRate(r.chat_overconfidence_rate)}`,
      tone: r.chat_avg_overconfidence >= 0.6 ? "danger" : r.chat_avg_overconfidence >= 0.3 ? "warning" : "success",
    },
    {
      label: "引用率",
      value: formatRate(r.chat_citation_rate),
      sub: "已评分回复中包含引用依据的占比",
      tone: r.chat_citation_rate >= 0.8 ? "success" : r.chat_citation_rate >= 0.5 ? "warning" : "danger",
    },
    {
      label: "点赞数",
      value: `${r.thumbs_up_count}`,
      sub: feedbackSubtext(r.thumbs_up_share, r.thumbs_up_rate, r.feedback_total_count),
      tone: r.feedback_total_count > 0 && r.thumbs_up_share >= 0.5 ? "success" : "default",
    },
    {
      label: "点踩数",
      value: `${r.thumbs_down_count}`,
      sub: feedbackSubtext(r.thumbs_down_share, r.thumbs_down_rate, r.feedback_total_count),
      tone: r.feedback_total_count > 0 && r.thumbs_down_share >= 0.3 ? "danger" : "default",
    },
  ];
});

const trustTrendEmptyDescription = computed(() => {
  const r = report.value;
  if (!r) return "暂无趋势数据";
  if (r.chat_message_count > 0 && r.chat_score_count === 0) {
    return `暂无趋势数据，当前 ${r.chat_message_count} 条聊天消息缺少可评估回复内容`;
  }
  if (r.chat_message_count > r.chat_score_count) {
    return `仅有 ${r.chat_score_count} / ${r.chat_message_count} 条聊天消息可计算可信度`;
  }
  return "暂无趋势数据";
});

const metaTitle = computed(() => {
  const meta = traceMeta.value;
  const r = report.value;
  if (!meta) return "";
  if (meta.langfuse_status === "ok") {
    if (meta.canonical_source === "local_fast") {
      return `Langfuse 已连接 · 当前先展示本地快速记录 · 可评估消息 ${r?.chat_score_count ?? 0}/${r?.chat_message_count ?? 0}`;
    }
    return `Langfuse 已连接 · 远端 ${meta.item_count || 0} 条 Trace · 可评估消息 ${r?.chat_score_count ?? 0}/${r?.chat_message_count ?? 0}`;
  }
  if (meta.langfuse_status === "error") {
    return `Langfuse 连接异常：${meta.langfuse_error || "无法读取远端 Trace"}`;
  }
  if (meta.langfuse_status === "disabled") {
    return "Langfuse 未启用，当前仅展示本地质量数据";
  }
  return "正在确认 Langfuse 连接状态";
});

const metaType = computed(() => {
  if (traceMeta.value?.langfuse_status === "ok") return "success";
  if (traceMeta.value?.langfuse_status === "error") return "warning";
  return "info";
});
</script>

<template>
  <div class="qr-panel" v-loading="loading">
    <el-alert
      v-if="traceMeta"
      :title="metaTitle"
      :type="metaType"
      :closable="false"
      show-icon
    />

    <section>
      <h3 class="section-title">聊天质量评估</h3>
      <p class="section-desc">这里同时展示平均风险和高风险占比，避免“明明有风险却看到 0%”的误读。</p>
      <div class="card-grid">
        <div v-for="card in summaryCards" :key="card.label" class="qr-card" :class="card.tone">
          <span class="qr-card-label">{{ card.label }}</span>
          <span class="qr-card-value">{{ card.value }}</span>
          <span class="qr-card-sub">{{ card.sub }}</span>
        </div>
      </div>
    </section>

    <section class="trends-section">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>聊天可信度趋势</strong>
            <span>统计 LLM 评审结果；评审不可用时使用本地规则兜底</span>
          </div>
        </template>
        <ChatTrustTrendChart v-if="(report?.chat_trust_trend || []).length" :points="report?.chat_trust_trend || []" />
        <el-empty v-else :description="trustTrendEmptyDescription" :image-size="48" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>点赞覆盖率趋势</strong>
            <span>按天统计被用户明确点赞的结果覆盖率</span>
          </div>
        </template>
        <ThumbsUpTrendChart v-if="(report?.thumbs_up_trend || []).length" :points="report?.thumbs_up_trend || []" />
        <el-empty v-else description="暂无点赞趋势数据" :image-size="48" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>点踩覆盖率趋势</strong>
            <span>按天统计被用户明确点踩的结果覆盖率</span>
          </div>
        </template>
        <ThumbsDownTrendChart v-if="(report?.thumbs_down_trend || []).length" :points="report?.thumbs_down_trend || []" />
        <el-empty v-else description="暂无点踩趋势数据" :image-size="48" />
      </el-card>
    </section>

    <el-empty
      v-if="!report?.chat_score_count && !report?.total_results"
      description="暂无质量评估数据。执行质检或产生聊天可信度评分后，这里会展示结果。"
    />
  </div>
</template>

<style scoped>
.qr-panel { display: grid; gap: 18px; }

.section-title { font-size: 20px; font-weight: 700; color: #18181b; margin: 0; }
.section-desc { font-size: 13px; color: #71717a; margin: 4px 0 0; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.qr-card {
  padding: 18px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(16, 36, 61, 0.08);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.qr-card-label { font-size: 13px; color: #71717a; }
.qr-card-value { font-size: 30px; font-weight: 800; color: #18181b; }
.qr-card-sub { font-size: 12px; color: #a1a1aa; margin-top: 2px; }
.qr-card.success .qr-card-value { color: #059669; }
.qr-card.warning .qr-card-value { color: #d97706; }
.qr-card.danger .qr-card-value { color: #dc2626; }

.trends-section { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.chart-card { border-radius: 20px; border: 1px solid rgba(16, 36, 61, 0.08); box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05); }
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }

@media (max-width: 1180px) {
  .card-grid { grid-template-columns: repeat(2, 1fr); }
  .trends-section { grid-template-columns: 1fr; }
}
</style>
