<script setup lang="ts">
import { onMounted } from "vue";
import { useQualityStore } from "@/stores/quality.store";

const store = useQualityStore();

onMounted(() => {
  store.fetchReport();
});
</script>

<template>
  <div class="page-container">
    <div class="hero">
      <h2>AI 质量报告</h2>
      <p>聚合幻觉率、点踩率、风险分与模型表现。</p>
    </div>

    <el-row :gutter="16" v-if="store.report">
      <el-col :span="8"><el-card shadow="never"><div class="metric-title">总结果数</div><div class="metric-value">{{ store.report.total_results }}</div></el-card></el-col>
      <el-col :span="8"><el-card shadow="never"><div class="metric-title">幻觉率</div><div class="metric-value warning">{{ (store.report.hallucination_rate * 100).toFixed(1) }}%</div></el-card></el-col>
      <el-col :span="8"><el-card shadow="never"><div class="metric-title">点踩率</div><div class="metric-value danger">{{ (store.report.thumbs_down_rate * 100).toFixed(1) }}%</div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>模型对比</template>
      <el-table :data="store.report?.model_metrics || []" v-loading="store.loading">
        <el-table-column prop="model_key" label="模型" min-width="180" />
        <el-table-column prop="result_count" label="结果数" width="100" />
        <el-table-column label="通过率" width="120"><template #default="{ row }">{{ (row.pass_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="幻觉率" width="120"><template #default="{ row }">{{ (row.hallucination_rate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="点踩率" width="120"><template #default="{ row }">{{ (row.thumbs_down_rate * 100).toFixed(1) }}%</template></el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>幻觉率趋势</template>
          <el-table :data="store.report?.hallucination_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值"><template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>点踩率趋势</template>
          <el-table :data="store.report?.thumbs_down_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值"><template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-container { display: grid; gap: 16px; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
.metric-title { color: #64748b; font-size: 13px; }
.metric-value { margin-top: 8px; font-size: 30px; font-weight: 700; color: #1b3a5c; }
.warning { color: #d97706; }
.danger { color: #dc2626; }
</style>

