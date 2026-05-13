<script setup lang="ts">
import { computed } from "vue";
import { useQualityStore } from "@/stores/quality.store";

const store = useQualityStore();
const report = computed(() => store.report);
const loading = computed(() => store.loading);
</script>

<template>
  <div class="quality-panel" v-loading="loading">
    <div class="flex gap-4" v-if="report">
      <div class="flex-1">
        <el-card shadow="never">
          <div class="metric-title">总结果数</div>
          <div class="metric-value">{{ report.total_results }}</div>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
          <div class="metric-title">幻觉率</div>
          <div class="metric-value warning">{{ (report.hallucination_rate * 100).toFixed(1) }}%</div>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
          <div class="metric-title">点踩率</div>
          <div class="metric-value danger">{{ (report.thumbs_down_rate * 100).toFixed(1) }}%</div>
        </el-card>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>模型对比</template>
      <el-table :data="report?.model_metrics || []" v-loading="loading">
        <el-table-column prop="model_key" label="模型" min-width="180" />
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

    <div class="flex gap-4">
      <div class="flex-1">
        <el-card shadow="never">
          <template #header>幻觉率趋势</template>
          <el-table :data="report?.hallucination_trend || []" size="small">
            <el-table-column prop="bucket" label="日期" />
            <el-table-column label="值">
              <template #default="{ row }">{{ (row.value * 100).toFixed(1) }}%</template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
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
  </div>
</template>

<style scoped>
.quality-panel { display: grid; gap: 16px; }
.metric-title { color: #64748b; font-size: 13px; }
.metric-value { margin-top: 8px; font-size: 30px; font-weight: 700; color: #1b3a5c; }
.warning { color: #d97706; }
.danger { color: #dc2626; }
</style>
