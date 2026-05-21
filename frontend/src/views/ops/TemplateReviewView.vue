<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";

const analyticsStore = useAnalyticsStore();
const loading = ref(false);

const overview = computed(() => analyticsStore.overview);
const modelMetrics = computed(() => overview.value?.model_metrics ?? []);

onMounted(async () => {
  loading.value = true;
  try {
    await analyticsStore.fetchOverview();
  } finally {
    loading.value = false;
  }
});

function formatRate(v: number) { return `${(v * 100).toFixed(1)}%`; }
</script>

<template>
  <div class="review-shell">
    <section class="hero">
      <p class="eyebrow">Template Review</p>
      <h2>模板审核</h2>
      <p class="sub">审核和管理 Prompt 模板、Agent 配置的变更，确保上线质量。</p>
    </section>

    <!-- Status overview -->
    <section class="summary-row">
      <div class="sc">
        <span class="sl">活跃模型</span>
        <span class="sv">{{ modelMetrics.length }}</span>
      </div>
      <div class="sc">
        <span class="sl">平均通过率</span>
        <span class="sv">{{ modelMetrics.length ? formatRate(modelMetrics.reduce((s, m) => s + m.pass_rate, 0) / modelMetrics.length) : '-' }}</span>
      </div>
      <div class="sc">
        <span class="sl">待审核项</span>
        <span class="sv">-</span>
        <span class="sl-sub">需接入 Agent 发布流程</span>
      </div>
      <div class="sc">
        <span class="sl">已通过</span>
        <span class="sv">-</span>
        <span class="sl-sub">需接入 Agent 发布流程</span>
      </div>
    </section>

    <el-card shadow="never" class="info-card">
      <template #header><strong>审核队列</strong></template>
      <el-empty description="暂无待审核的模板变更" />
      <p class="info-note">
        模板审核功能需要与 Agent 发布管理系统对接。当前版本的 Agent 和 Prompt 由 app_developer 直接管理，后续版本将引入“发布 - 审核 - 上线”的流程，platform_operator 在此流程中负责审核环节。
      </p>
    </el-card>

    <el-card v-if="modelMetrics.length" shadow="never" class="info-card">
      <template #header><strong>当前线上模型表现（审核参考）</strong></template>
      <el-table :data="modelMetrics" size="small">
        <el-table-column prop="model_key" label="模型" min-width="200" show-overflow-tooltip />
        <el-table-column label="调用次数" width="110">
          <template #default="{ row }">{{ row.result_count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="通过率" width="100">
          <template #default="{ row }">{{ formatRate(row.pass_rate) }}</template>
        </el-table-column>
        <el-table-column label="幻觉率" width="100">
          <template #default="{ row }">{{ formatRate(row.hallucination_rate) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.review-shell { display: grid; gap: 18px; padding: 24px; }

.hero {
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #1e293b 0%, #0f766e 52%, #059669 100%);
  color: #f8fafc;
}
.eyebrow { margin: 0 0 8px; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .76; }
.hero h2 { margin: 0; font-size: 40px; }
.sub { margin: 12px 0 0; color: rgba(248,250,252,.82); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.sc {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 4px 16px rgba(15,23,42,.03);
}
.sl { display: block; font-size: 13px; color: #a1a1aa; }
.sv { display: block; margin-top: 8px; font-size: 28px; font-weight: 800; color: #18181b; }
.sl-sub { display: block; margin-top: 4px; font-size: 11px; color: #d4d4d8; }

.info-card {
  border-radius: 20px;
  border: 1px solid rgba(16,36,61,.08);
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
}
.info-card strong { font-size: 18px; color: #172033; }
.info-note {
  margin-top: 12px;
  padding: 16px;
  background: #f4f4f5;
  border-radius: 10px;
  font-size: 13px;
  color: #71717a;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .summary-row { grid-template-columns: 1fr 1fr; }
}
</style>

