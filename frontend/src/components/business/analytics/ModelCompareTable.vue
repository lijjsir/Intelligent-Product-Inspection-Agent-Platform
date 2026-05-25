<script setup lang="ts">
import { computed } from "vue";
import type { ModelAnalyticsMetric } from "@/types/analytics.types";

interface Props {
  items: ModelAnalyticsMetric[];
}

interface Emits {
  (e: "select", row: ModelAnalyticsMetric): void;
}

const props = defineProps<Props>();
defineEmits<Emits>();

const qualityItems = computed(() => props.items.filter((item) => (item.result_count ?? 0) > 0));
</script>

<template>
  <el-table :data="qualityItems" size="small" empty-text="暂无产生质检结果的模型" @row-click="$emit('select', $event)">
    <el-table-column prop="model_key" label="模型" min-width="220" />
    <el-table-column prop="result_count" label="质检结果数" width="110" />
    <el-table-column label="质检通过率" width="130"><template #default="scope">{{ (scope.row.pass_rate * 100).toFixed(1) }}%</template></el-table-column>
    <el-table-column label="质检幻觉率" width="130"><template #default="scope">{{ (scope.row.hallucination_rate * 100).toFixed(1) }}%</template></el-table-column>
  </el-table>
</template>
