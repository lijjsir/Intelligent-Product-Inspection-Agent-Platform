<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
import type { RiskWorkspace } from "@/types/quality-risk.types";
import RiskLabPanel from "@/components/business/quality-risk/RiskLabPanel.vue";
import RiskCasePicker from "@/components/business/quality-risk/RiskCasePicker.vue";
const route = useRoute(),
  router = useRouter();
const workspace = ref<RiskWorkspace | null>(null),
  error = ref("");
let epoch = 0;
async function load() {
  const key = ++epoch;
  const id = typeof route.query.case_id === "string" ? route.query.case_id : null;
  error.value = "";
  workspace.value = null;
  try {
    const w = id ? (await qualityRiskApi.riskWorkspace(id, {suppressErrorToast:true})).data.data : null;
    if (key === epoch) {
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
      暂不验证或引用已有报告无需检测任务；组织平台检测时才创建或关联任务。资料和结果返回原事项后，再形成新版研判与独立复核。
    </p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <RiskCasePicker id="lab-case" label="选择来源事项" empty-label="请选择" :model-value="typeof route.query.case_id === 'string' ? route.query.case_id : undefined"
      :selected-case="workspace?.case" @update:model-value="router.replace({query:{case_id:$event}})" />
    <RiskLabPanel
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
