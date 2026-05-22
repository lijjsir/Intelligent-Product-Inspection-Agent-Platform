<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useOfflineEvaluationStore } from "@/stores/offlineEvaluation.store";
import { buildOfflineEvaluationSummaryViewModel } from "@/utils/algoResultSummary";

const route = useRoute();
const store = useOfflineEvaluationStore();
const current = computed(() => store.current);
const resultSummary = computed(() => current.value?.result_summary);
const metrics = computed(() => resultSummary.value?.metrics || {});
const errorCases = computed(() => resultSummary.value?.error_cases || []);
const summaryView = computed(() => buildOfflineEvaluationSummaryViewModel(current.value));

async function load() {
  const id = String(route.params.id || "");
  if (!id) return;
  await store.fetchOne(id);
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <div class="flex flex-col gap-5">
    <AlgoResourceDetail
      title="离线评测详情"
      :store="store"
      back-path="/ops/eval/offline"
      :relation-sections="[
        { label: '评测集', value: (item) => item?.eval_set_id },
        { label: '目标类型', value: (item) => item?.target_type },
        { label: '目标资源', value: (item) => item?.target_id },
        { label: '实验', value: (item) => item?.experiment_id },
      ]"
      intro="查看离线评测指标、错误案例和执行日志。"
      :highlights="summaryView.highlights"
      :metrics="summaryView.metrics"
      :artifacts="summaryView.artifacts"
      :logs="summaryView.logs"
    >
      <section class="card-surface p-4">
        <h3 class="mb-4">错误案例</h3>
        <el-empty v-if="!errorCases.length" description="暂无错误案例" />
        <el-table v-else :data="errorCases">
          <el-table-column prop="sample_ref" label="样本" min-width="220" />
          <el-table-column prop="reason" label="原因" min-width="220" />
          <el-table-column prop="predicted_label" label="预测" width="140" />
          <el-table-column prop="expected_label" label="期望" width="140" />
        </el-table>
      </section>
    </AlgoResourceDetail>
  </div>
</template>
