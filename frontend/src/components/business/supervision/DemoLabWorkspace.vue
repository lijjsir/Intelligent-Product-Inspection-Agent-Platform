<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
import type { RiskCaseV4, RiskWorkspace } from "@/types/quality-risk.types";
import RiskLabPanel from "@/components/business/quality-risk/RiskLabPanel.vue";
const route = useRoute(),
  router = useRouter();
const cases = ref<RiskCaseV4[]>([]),
  workspace = ref<RiskWorkspace | null>(null),
  error = ref("");
let epoch = 0;
async function load() {
  const key = ++epoch;
  const id = typeof route.query.case_id === "string" ? route.query.case_id : null;
  error.value = "";
  workspace.value = null;
  try {
    const choices = (await qualityRiskApi.riskCases({ page: 1, size: 200 })).data.data.items;
    const w = id ? (await qualityRiskApi.riskWorkspace(id)).data.data : null;
    if (key === epoch) {
      cases.value = choices;
      if (w && !cases.value.some((c) => c.id === w.case.id)) cases.value.push(w.case);
      workspace.value = w;
    }
  } catch (e) {
    if (key === epoch) {
      workspace.value = null;
      error.value = extractApiErrorMessage(e, "事项加载失败");
    }
  }
}
watch(() => route.query.case_id, load);
onMounted(load);
onBeforeUnmount(() => {
  ++epoch;
});
</script>
<template>
  <main class="demo-lab-workspace">
    <h1>实验室检测 · 可选验证</h1>
    <p>
      检测任务承载具体检测工作；本入口记录风险事项为何需要验证、关联什么资料，以及资料如何返回原事项。演示环境不启动检测。
    </p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" /><label for="lab-case"
      >选择来源事项</label
    ><select
      id="lab-case"
      :value="route.query.case_id || ''"
      @change="router.replace({ query: { case_id: ($event.target as HTMLSelectElement).value } })"
    >
      <option value="">请选择</option>
      <option v-for="row in cases" :key="row.id" :value="row.id">
        {{ row.code }} · {{ row.title }}
      </option></select
    ><RiskLabPanel
      v-if="workspace"
      :case-id="workspace.case.id"
      :assessment="workspace.latest_assessment"
      :is-latest="true"
      :context="workspace.workflow_context"
      @changed="load"
    /><el-button
      v-if="workspace"
      @click="router.push({ path: '/app/risk-assessments', query: { case_id: workspace.case.id } })"
      >返回原研判事项</el-button
    >
  </main>
</template>
<style scoped>
.demo-lab-workspace {
  max-width: 1100px;
  margin: auto;
  padding: 28px;
  display: grid;
  gap: 18px;
}
.demo-lab-workspace p {
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
h1 {
  font-size: 25px;
  margin: 0;
}
select {
  max-width: 100%;
  min-height: 44px;
  border: 1px solid var(--el-border-color);
  border-radius: 5px;
  padding: 8px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
}
@media (max-width: 700px) {
  .demo-lab-workspace {
    padding: 16px;
  }
}
</style>
