<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import AlgoResourceDetail from "@/components/business/algo/AlgoResourceDetail.vue";
import { useDeploymentStore } from "@/stores/deployment.store";
import { buildDeploymentSummaryViewModel } from "@/utils/algoResultSummary";

const route = useRoute();
const store = useDeploymentStore();
const current = computed(() => store.current);
const runtimeRegistration = computed(() => current.value?.result_summary?.runtime_registration || {});
const summaryView = computed(() => buildDeploymentSummaryViewModel(current.value));

async function load() {
  const id = String(route.params.id || "");
  if (!id) return;
  await store.fetchOne(id);
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <AlgoResourceDetail
    title="部署详情"
    :store="store"
    back-path="/ops/deployments"
    :relation-sections="[
      { label: '来源类型', value: (item) => item?.source_type },
      { label: '来源资源', value: (item) => item?.source_id },
      { label: '实验', value: (item) => item?.experiment_id },
    ]"
    intro="查看部署运行时注册信息、推理配置和产出清单。"
    :highlights="summaryView.highlights"
    :metrics="summaryView.metrics"
    :artifacts="summaryView.artifacts"
    :logs="summaryView.logs"
  >
    <section class="card-surface p-4">
      <h3 class="mb-4">运行时注册</h3>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="text-sm text-slate-500">状态</div>
          <div class="mt-2 text-base font-semibold text-slate-900">{{ runtimeRegistration.status || "-" }}</div>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="text-sm text-slate-500">来源</div>
          <div class="mt-2 break-all text-sm font-semibold text-slate-900">{{ runtimeRegistration.source_type || "-" }} / {{ runtimeRegistration.source_id || "-" }}</div>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="text-sm text-slate-500">模型</div>
          <div class="mt-2 break-all text-sm font-semibold text-slate-900">{{ runtimeRegistration.model_key || "-" }}</div>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 md:col-span-2 xl:col-span-3">
          <div class="text-sm text-slate-500">入口</div>
          <div class="mt-2 break-all text-sm font-semibold text-slate-900">{{ runtimeRegistration.endpoint_placeholder || "-" }}</div>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 md:col-span-2 xl:col-span-3">
          <div class="text-sm text-slate-500">推理配置</div>
          <pre class="mt-2 overflow-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{{ JSON.stringify(runtimeRegistration.inference_config || {}, null, 2) }}</pre>
        </div>
      </div>
    </section>
  </AlgoResourceDetail>
</template>
