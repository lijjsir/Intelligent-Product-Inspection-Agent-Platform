<script setup lang="ts">
import { computed } from "vue";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useOnlineValidationStore } from "@/stores/onlineValidation.store";
import { buildOnlineValidationSummaryViewModel } from "@/utils/algoResultSummary";

const store = useOnlineValidationStore();
const current = computed(() => store.current);
const resultSummary = computed(() => current.value?.result_summary || { summary: {}, metrics: {}, replay_samples: [], artifacts: [], logs: [] });
const replaySamples = computed(() => resultSummary.value.replay_samples || []);
const summaryView = computed(() => buildOnlineValidationSummaryViewModel(current.value));
</script>

<template>
  <AlgoResourceDetail
    title="在线验证详情"
    :store="store"
    back-path="/ops/eval/online"
    :relation-sections="[
      { label: '部署记录', value: (item) => item?.deployment_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看在线验证任务的部署关联、执行状态和结果摘要。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  >
    <section v-if="summaryView.artifacts.length" class="card-surface p-4">
      <h3 class="mb-4">验证报告</h3>
      <div class="flex flex-wrap gap-3">
        <a
          v-for="artifact in summaryView.artifacts.filter((item) => item.link)"
          :key="artifact.title"
          class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-cyan-400 hover:text-cyan-700"
          :href="artifact.link || undefined"
          target="_blank"
          rel="noreferrer"
        >
          {{ artifact.title }}
        </a>
      </div>
    </section>
    <section class="card-surface p-4">
      <h3 class="mb-4">回放样本</h3>
      <el-empty v-if="!replaySamples.length" description="暂无回放样本" />
      <el-table v-else :data="replaySamples">
        <el-table-column prop="task_id" label="任务 ID" min-width="180" />
        <el-table-column prop="product_id" label="产品" min-width="140" />
        <el-table-column prop="spec_code" label="规格" min-width="140" />
        <el-table-column prop="verdict" label="结论" width="120" />
        <el-table-column prop="overall_score" label="得分" width="120" />
      </el-table>
    </section>
  </AlgoResourceDetail>
</template>
