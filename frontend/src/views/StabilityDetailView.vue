<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useStabilityStore } from "@/stores/stability.store";

const route = useRoute();
const router = useRouter();
const store = useStabilityStore();
const loading = ref(true);
const taskId = String(route.params.id || "");

const riskLabels: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "严重风险",
};

const detail = computed(() => store.current?.dimension_detail || {});
const confidenceMeasured = computed(() => detail.value.confidence?.status === "calibrated");
const consistencyMeasured = computed(() => detail.value.consistency?.status === "measured");
const rag = computed(() => detail.value.rag || {});
const ragHitCount = computed(() => Number(rag.value.hit_count || rag.value.used_citation_count || 0));

function getRiskType(level: string): "info" | "success" | "danger" | "warning" {
  const types: Record<string, "info" | "success" | "danger" | "warning"> = {
    low: "success", medium: "warning", high: "danger", critical: "danger",
  };
  return types[level?.toLowerCase()] || "info";
}

function formatPercent(value: number | null | undefined) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}

onMounted(async () => {
  try {
    await store.fetchByTask(taskId);
  } catch (err: any) {
    if (err.response?.status === 404) ElMessage.warning("该任务暂无可信性风险评估");
    else ElMessage.error("获取可信性风险评估失败");
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => store.$reset());
</script>

<template>
  <div class="trust-page" v-loading="loading">
    <el-button @click="router.back()">← 返回</el-button>

    <template v-if="store.current">
      <header class="title-area">
        <div>
          <h2>结果可信性评估</h2>
          <p>用于判断这次检测结论能否被证据和规则支撑，以及是否需要人工复核。它不代表模型长期运行稳定性。</p>
        </div>
        <el-tag :type="getRiskType(store.current.risk_level)" size="large">
          {{ riskLabels[store.current.risk_level] || "风险待定" }}
        </el-tag>
      </header>

      <el-alert
        title="评估用途"
        :description="String(detail.purpose || '评估单次检测结论的证据充分性、规则可追溯性和异常风险，用于决定自动放行或人工复核。')"
        type="info"
        :closable="false"
        show-icon
      />

      <section class="summary-grid">
        <el-card shadow="never" class="risk-card">
          <div class="eyebrow">综合可信风险</div>
          <strong :class="`risk-${store.current.risk_level}`">{{ (store.current.risk_score * 10).toFixed(1) }} / 10.0</strong>
          <p>数值越高，越需要补充证据或转人工复核。</p>
        </el-card>

        <el-card shadow="never" class="rag-card">
          <div class="eyebrow">知识库检索</div>
          <strong>{{ ragHitCount > 0 ? `命中 ${ragHitCount} 条` : "未命中可用原文" }}</strong>
          <p>{{ ragHitCount > 0 ? "知识库原文已进入本次判定的证据链。" : "本次结论没有获得可核验的知识库原文支持。" }}</p>
        </el-card>
      </section>

      <el-card shadow="never">
        <template #header>评估维度</template>
        <div class="dimension-grid">
          <article>
            <span>引证充分性</span>
            <strong>{{ formatPercent(store.current.evidence_score) }}</strong>
            <p>衡量结论是否附有可核验的知识库原文。</p>
          </article>
          <article>
            <span>规则可追溯性</span>
            <strong>{{ formatPercent(store.current.traceability_score) }}</strong>
            <p>衡量判定能否追溯到标准、规则及证据来源。</p>
          </article>
          <article>
            <span>模型置信分</span>
            <strong>{{ confidenceMeasured ? formatPercent(store.current.confidence_score) : "未校准" }}</strong>
            <p>{{ detail.confidence?.reason || "未经业务样本校准，不能当作真实概率。" }}</p>
          </article>
          <article>
            <span>重复结果一致性</span>
            <strong>{{ consistencyMeasured ? formatPercent(store.current.consistency_score) : "未测量" }}</strong>
            <p>{{ detail.consistency?.reason || "需要同一输入多次运行或采样后才能计算。" }}</p>
          </article>
          <article>
            <span>异常风险</span>
            <strong>{{ formatPercent(store.current.anomaly_score) }}</strong>
            <p>衡量物理常识冲突、幻觉或异常输出的风险。</p>
          </article>
          <article>
            <span>生成时间</span>
            <strong class="time-value">{{ store.current.created_at ? new Date(store.current.created_at).toLocaleString() : "-" }}</strong>
            <p>对应当前任务本次检测产生的评估。</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>风险原因与处理建议</template>
        <p class="root-cause">{{ store.current.root_cause || "当前没有生成风险原因，请重新执行检测或补充证据。" }}</p>
      </el-card>
    </template>

    <el-empty v-else-if="!loading" description="该任务尚未生成可信性风险评估" />
  </div>
</template>

<style scoped>
.trust-page { display: flex; flex-direction: column; gap: 20px; }
.title-area { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.title-area h2 { color: #18181b; font-size: 26px; font-weight: 700; }
.title-area p { max-width: 720px; margin-top: 7px; color: #71717a; font-size: 14px; line-height: 1.7; }
.summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.eyebrow { margin-bottom: 12px; color: #71717a; font-size: 13px; font-weight: 600; }
.risk-card strong, .rag-card strong { color: #18181b; font-size: 26px; }
.risk-card p, .rag-card p { margin-top: 8px; color: #71717a; font-size: 13px; }
.risk-low { color: #16a34a !important; }
.risk-medium { color: #d97706 !important; }
.risk-high, .risk-critical { color: #dc2626 !important; }
.dimension-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.dimension-grid article { min-height: 126px; padding: 16px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fafafa; }
.dimension-grid span { display: block; color: #52525b; font-size: 13px; font-weight: 600; }
.dimension-grid strong { display: block; margin-top: 9px; color: #18181b; font-size: 22px; }
.dimension-grid p { margin-top: 8px; color: #71717a; font-size: 12px; line-height: 1.6; }
.dimension-grid .time-value { font-size: 15px; }
.root-cause { padding: 16px; border-left: 3px solid #f59e0b; background: #fffbeb; color: #78350f; line-height: 1.8; }
@media (max-width: 900px) {
  .summary-grid, .dimension-grid { grid-template-columns: 1fr; }
  .title-area { flex-direction: column; }
}
</style>
