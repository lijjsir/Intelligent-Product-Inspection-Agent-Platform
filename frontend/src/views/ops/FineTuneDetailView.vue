<script setup lang="ts">
import { computed } from "vue";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useFineTuneStore } from "@/stores/fineTune.store";
import { buildTrainingSummaryViewModel } from "@/utils/algoResultSummary";

const store = useFineTuneStore();
const current = computed(() => store.current);
const summaryView = computed(() => buildTrainingSummaryViewModel(current.value));
</script>

<template>
  <AlgoResourceDetail
    title="微调详情"
    :store="store"
    back-path="/ops/training/fine-tune"
    :auto-refresh-when-running="true"
    :relation-sections="[
      { label: '源数据集', value: (item) => item?.source_dataset_id },
      { label: '验证评测集', value: (item) => item?.eval_set_id },
      { label: '基础模型', value: (item) => item?.model_config_ref?.display_name || item?.model_config_ref?.model_key || item?.model_config_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看微调任务的数据集绑定、LoRA 参数、有效超参数、产出物和执行日志。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  >
    <section v-if="current?.execution_mode === 'gpu_ssh'" class="card-surface p-4">
      <h3 class="mb-3">GPU 执行信息</h3>
      <p class="text-sm text-slate-600">当前微调任务已绑定 GPU 节点执行，具体分配与命令摘要已合并到结果摘要中。</p>
      <pre class="mt-4 overflow-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{{ JSON.stringify(current?.result_summary?.remote_execution || {}, null, 2) }}</pre>
    </section>
    <section v-if="summaryView.artifacts.length" class="card-surface p-4">
      <h3 class="mb-4">关键产物下载</h3>
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
  </AlgoResourceDetail>
</template>
