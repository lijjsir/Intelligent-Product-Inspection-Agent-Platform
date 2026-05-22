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
      <section v-if="current?.execution_mode === 'gpu_ssh'" class="card-surface p-4">
        <h3 class="mb-3">GPU 执行信息</h3>
        <p class="text-sm text-slate-600">当前离线评测运行在 GPU 节点上，分配节点、GPU 槽位和远端命令摘要已汇总到上方指标区。</p>
      </section>
      <section v-if="summaryView.artifacts.length" class="card-surface p-4">
        <h3 class="mb-4">评测报告</h3>
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
