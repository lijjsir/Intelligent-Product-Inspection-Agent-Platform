<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useQualityStore } from "@/stores/quality.store";
import AnalyticsTabNav from "@/components/business/analytics/AnalyticsTabNav.vue";

const router = useRouter();
const store = useQualityStore();

onMounted(() => {
  store.fetchReport();
});

function goToLangfuseTraces() {
  router.push({ name: "ops-analytics-tracing" });
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="hero">
      <div>
        <h2>AI 质量报告</h2>
        <p>聚合幻觉率、点赞率、点踩率、风险分与模型表现。</p>
      </div>
      <el-button type="primary" @click="goToLangfuseTraces">跳转 Langfuse Trace</el-button>
    </div>

    <AnalyticsTabNav />

    <div class="flex gap-4" v-if="store.report">
      <div class="flex-1"><el-card shadow="never"><div class="metric-title">总结果数</div><div class="metric-value">{{ store.report.total_results }}</div></el-card></div>
      <div class="flex-1"><el-card shadow="never"><div class="metric-title">幻觉率</div><div class="metric-value warning">{{ (store.report.hallucination_rate * 100).toFixed(1) }}%</div></el-card></div>
      <div class="flex-1"><el-card shadow="never"><div class="metric-title">点赞率</div><div class="metric-value success">{{ (store.report.thumbs_up_rate * 100).toFixed(1) }}%</div></el-card></div>
      <div class="flex-1"><el-card shadow="never"><div class="metric-title">点踩率</div><div class="metric-value danger">{{ (store.report.thumbs_down_rate * 100).toFixed(1) }}%</div></el-card></div>
    </div>

    <el-card shadow="never">
      <template #header>模型对比</template>
      <el-table :data="store.report?.model_metrics || []" v-loading="store.loading">
        <el-table-column prop="model_key" label="模型" min-width="180" />
        <el-table-column prop="result_count" label="结果数" width="100" />
        <el-table-column label="通过率" width="120"><template #default="{ row }">{{ (row.pass_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="幻觉率" width="120"><template #default="{ row }">{{ (row.hallucination_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="点踩率" width="120"><template #default="{ row }">{{ (row.thumbs_down_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="点赞率" width="120"><template #default="{ row }">{{ (row.thumbs_up_rate * 100).toFixed(1) }}%</template></el-table-column>
      </el-table>
    </el-card>

    <div class="flex gap-4">
      <div class="flex-1">
        <el-card shadow="never">
          <template #header>幻觉率趋势</template>
          <el-table :data="store.report?.hallucination_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值"><template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
          <template #header>点赞率趋势</template>
          <el-table :data="store.report?.thumbs_up_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值"><template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
          <template #header>点踩率趋势</template>
          <el-table :data="store.report?.thumbs_down_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值"><template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </el-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
