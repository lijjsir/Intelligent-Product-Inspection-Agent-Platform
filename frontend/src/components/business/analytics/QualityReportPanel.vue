<script setup lang="ts">
import { computed } from "vue";
import { useQualityStore } from "@/stores/quality.store";
import ChatTrustTrendChart from "@/components/business/analytics/ChatTrustTrendChart.vue";
import ThumbsDownTrendChart from "@/components/business/analytics/ThumbsDownTrendChart.vue";
import ThumbsUpTrendChart from "@/components/business/analytics/ThumbsUpTrendChart.vue";

const store = useQualityStore();
const report = computed(() => store.report);
const loading = computed(() => store.loading);
const traceMeta = computed(() => store.traceMeta);

const summaryCards = computed(() => {
  const r = report.value;
  if (!r) return [];
  return [
    {
      label: "聊天评分数",
      value: r.chat_score_count,
      sub: "已有信任评估的记录数",
      tone: r.chat_score_count > 0 ? "success" : "default",
    },
    {
      label: "平均可信度",
      value: `${(r.chat_avg_trust_score * 100).toFixed(1)}%`,
      sub: "LLM 评审对回复的综合信任评分",
      tone: r.chat_avg_trust_score >= 0.8 ? "success" : r.chat_avg_trust_score >= 0.6 ? "warning" : "danger",
    },
    {
      label: "幻觉率",
      value: `${(r.chat_hallucination_rate * 100).toFixed(1)}%`,
      sub: "幻觉风险 ≥ 0.6 的聊天占比",
      tone: r.chat_hallucination_rate <= 0.05 ? "success" : "danger",
    },
    {
      label: "过度自信率",
      value: `${(r.chat_overconfidence_rate * 100).toFixed(1)}%`,
      sub: "过度自信 ≥ 0.6 的聊天占比",
      tone: r.chat_overconfidence_rate <= 0.1 ? "success" : "warning",
    },
    {
      label: "引用率",
      value: `${(r.chat_citation_rate * 100).toFixed(1)}%`,
      sub: "回复中包含引用依据的比例",
      tone: r.chat_citation_rate >= 0.8 ? "success" : r.chat_citation_rate >= 0.5 ? "warning" : "danger",
    },
    {
      label: "点赞率",
      value: `${(r.thumbs_up_rate * 100).toFixed(1)}%`,
      sub: "用户明确标记满意的比例",
      tone: r.thumbs_up_rate >= 0.8 ? "success" : r.thumbs_up_rate >= 0.5 ? "warning" : "danger",
    },
    {
      label: "点踩率",
      value: `${(r.thumbs_down_rate * 100).toFixed(1)}%`,
      sub: "用户明确标记不满意的比例",
      tone: r.thumbs_down_rate <= 0.05 ? "success" : "danger",
    },
  ];
});

function metaAlertTitle() {
  const meta = traceMeta.value;
  if (!meta) return "";
  if (meta.langfuse_status === "ok")
    return `Langfuse 已连接 · 远端 ${meta.item_count || 0} 条 Trace · 本地 ${report.value?.chat_score_count || 0} 条评分`;
  if (meta.langfuse_status === "error")
    return `Langfuse 连接异常：${meta.langfuse_error || "无法读取远端"}`;
  if (meta.langfuse_status === "disabled")
    return "Langfuse 未启用，仅展示本地聊天评分数据";
  return "正在确认 Langfuse 状态";
}

function metaType() {
  if (traceMeta.value?.langfuse_status === "ok") return "success";
  if (traceMeta.value?.langfuse_status === "error") return "warning";
  return "info";
}

// Model trust comparison sorted by trust score
const modelComparison = computed(() => {
  const models = report.value?.model_metrics ?? [];
  return [...models].sort((a, b) => (b.pass_rate || 0) - (a.pass_rate || 0));
});
</script>

<template>
  <div class="qr-panel" v-loading="loading">
    <el-alert
      v-if="traceMeta"
      :title="metaAlertTitle()"
      :type="metaType()"
      :closable="false"
      show-icon
    />

    <!-- 聊天质量评估卡片 -->
    <section>
      <h3 class="section-title">聊天质量评估</h3>
      <p class="section-desc">以下指标来自 AI 对话的信任评审，独立于检测任务的业务指标。</p>
      <div class="card-grid">
        <div v-for="card in summaryCards" :key="card.label" class="qr-card" :class="card.tone">
          <span class="qr-card-label">{{ card.label }}</span>
          <span class="qr-card-value">{{ card.value }}</span>
          <span class="qr-card-sub">{{ card.sub }}</span>
        </div>
      </div>
    </section>

    <!-- 趋势图表区 -->
    <section class="trends-section">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>聊天可信度趋势</strong>
            <span>LLM 评审对回复的综合信任评分变化</span>
          </div>
        </template>
        <ChatTrustTrendChart v-if="(report?.chat_trust_trend || []).length" :points="report?.chat_trust_trend || []" />
        <el-empty v-else description="暂无趋势数据" :image-size="48" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>模型可信度对比</strong>
            <span>按模型维度统计通过率和幻觉表现</span>
          </div>
        </template>
        <div v-if="modelComparison.length" class="model-list">
          <div v-for="m in modelComparison" :key="m.model_key" class="model-row">
            <div class="model-main">
              <span class="m-key">{{ m.model_key }}</span>
              <span class="m-stat">{{ m.result_count }} 条记录</span>
            </div>
            <div class="model-metrics">
              <span class="m-pass" :class="(m.pass_rate || 0) >= 0.8 ? 'text-green-600' : 'text-red-600'">
                通过 {{ ((m.pass_rate || 0) * 100).toFixed(0) }}%
              </span>
              <span class="m-hall" :class="(m.hallucination_rate || 0) <= 0.1 ? 'text-green-600' : 'text-red-600'">
                幻觉 {{ ((m.hallucination_rate || 0) * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无模型数据" :image-size="48" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>点赞率趋势</strong>
            <span>用户标记满意的比例变化</span>
          </div>
        </template>
        <ThumbsUpTrendChart v-if="(report?.thumbs_up_trend || []).length" :points="report?.thumbs_up_trend || []" />
        <el-empty v-else description="暂无点赞数据" :image-size="48" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <strong>点踩率趋势</strong>
            <span>用户标记不满意的比例变化</span>
          </div>
        </template>
        <ThumbsDownTrendChart v-if="(report?.thumbs_down_trend || []).length" :points="report?.thumbs_down_trend || []" />
        <el-empty v-else description="暂无点踩数据" :image-size="48" />
      </el-card>
    </section>

    <!-- 空状态 -->
    <el-empty
      v-if="!report?.chat_score_count && !report?.total_results"
      description="暂无质量评估数据。开启信任评分或执行质检后，质量报告将展示 AI 回复质量分析。"
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
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 12px rgba(15,23,42,.03);
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
.chart-card { border-radius: 20px; border: 1px solid rgba(16,36,61,.08); box-shadow: 0 18px 40px rgba(15,23,42,.05); }
.card-head strong { display: block; color: #172033; font-size: 18px; }
.card-head span { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }

.model-list { display: flex; flex-direction: column; gap: 8px; }
.model-row { display: flex; flex-direction: column; gap: 4px; padding: 10px; border-radius: 8px; background: #fafafa; }
.model-main { display: flex; justify-content: space-between; align-items: center; }
.m-key { font-weight: 600; font-size: 13px; color: #18181b; }
.m-stat { font-size: 12px; color: #a1a1aa; }
.model-metrics { display: flex; gap: 16px; font-size: 13px; font-weight: 600; }
.text-green-600 { color: #16a34a; }
.text-red-600 { color: #dc2626; }

@media (max-width: 1180px) {
  .card-grid { grid-template-columns: repeat(2, 1fr); }
  .trends-section { grid-template-columns: 1fr; }
}
</style>
