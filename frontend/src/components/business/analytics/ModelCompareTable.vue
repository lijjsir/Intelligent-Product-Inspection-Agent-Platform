<script setup lang="ts">
import type { ModelAnalyticsMetric } from "@/types/analytics.types";

interface Props {
  items: ModelAnalyticsMetric[];
}

interface Emits {
  (e: "select", row: ModelAnalyticsMetric): void;
}

defineProps<Props>();
defineEmits<Emits>();
</script>

<template>
  <el-table :data="items" size="small" empty-text="暂无模型对比数据" @row-click="$emit('select', $event)">
    <el-table-column prop="model_key" label="模型" min-width="220" />
    <el-table-column prop="result_count" label="结果数" width="90" />
    <el-table-column label="通过率" width="120"><template #default="scope">{{ (scope.row.pass_rate * 100).toFixed(1) }}%</template></el-table-column>
    <el-table-column label="幻觉率" width="120"><template #default="scope">{{ (scope.row.hallucination_rate * 100).toFixed(1) }}%</template></el-table-column>
  </el-table>
</template>
