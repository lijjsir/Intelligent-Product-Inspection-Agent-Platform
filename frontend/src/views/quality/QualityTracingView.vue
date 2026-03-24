<script setup lang="ts">
import { onMounted } from "vue";
import { useQualityStore } from "@/stores/quality.store";

const store = useQualityStore();

onMounted(() => {
  store.fetchTraces();
});
</script>

<template>
  <div class="page-container">
    <div class="hero">
      <h2>质量追踪</h2>
      <p>Langfuse Trace 列表代理入口。</p>
    </div>
    <el-card shadow="never">
      <el-table :data="store.traces" v-loading="store.loading" empty-text="暂无 Trace 数据">
        <el-table-column prop="trace_id" label="Trace ID" min-width="220" />
        <el-table-column prop="result_id" label="结果 ID" min-width="180" />
        <el-table-column prop="task_id" label="任务 ID" min-width="180" />
        <el-table-column prop="verdict" label="结论" width="100" />
        <el-table-column prop="model_key" label="模型" width="180" />
        <el-table-column prop="total_tokens" label="Token" width="100" />
        <el-table-column prop="feedback_count" label="反馈数" width="100" />
        <el-table-column prop="thumbs_down_count" label="点踩数" width="100" />
        <el-table-column label="最近分值" width="120">
          <template #default="{ row }">
            {{ row.last_score_value == null ? "-" : row.last_score_value.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="last_score_at" label="最近评分时间" width="180" />
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: grid; gap: 16px; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
</style>
