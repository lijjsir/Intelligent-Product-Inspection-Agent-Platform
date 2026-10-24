<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
import type { RiskWorkspace } from "@/types/quality-risk.types";
import RiskLabPanel from "@/components/business/quality-risk/RiskLabPanel.vue";
import RiskCasePicker from "@/components/business/quality-risk/RiskCasePicker.vue";
defineProps<{ embedded?: boolean }>();
const route = useRoute(),
  router = useRouter();
const workspace = ref<RiskWorkspace | null>(null),
  error = ref("");
const loading = ref(false);
let epoch = 0;
async function load() {
  const key = ++epoch;
  const id = typeof route.query.case_id === "string" ? route.query.case_id : null;
  error.value = "";
  workspace.value = null;
  loading.value = true;
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
  } finally {
    if (key === epoch) loading.value = false;
  }
}
watch(() => route.query.case_id, load);
onMounted(load);
onBeforeUnmount(() => {
  ++epoch;
});
</script>
<template>
  <section class="demo-lab-workspace" :class="{ embedded }" aria-label="风险事项验证与证据回流">
    <component :is="embedded ? 'h2' : 'h1'">验证与证据回流</component>
    <p>
      选择来源风险事项，再记录验证方式。已有报告直接关联；新的检测通过任务执行，证据回流后在原事项中继续研判。
    </p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <RiskCasePicker id="lab-case" label="选择来源事项" empty-label="请选择风险事项" :model-value="typeof route.query.case_id === 'string' ? route.query.case_id : undefined"
      :selected-case="workspace?.case" @update:model-value="router.replace({query:{...route.query,case_id:$event,view:'validation'}})" />
    <el-skeleton v-if="loading" :rows="3" animated />
    <RiskLabPanel
      v-else-if="workspace"
      :case-id="workspace.case.id"
      :assessment="workspace.latest_assessment"
      :is-latest="true"
      :context="workspace.workflow_context"
      @changed="load"
    />
    <div v-else-if="!error" class="validation-empty"><strong>先确定需要验证的风险事项</strong><p>验证安排将保留来源事项与研判版本；需要新检测时，再关联任务并登记样品、设备和项目。</p><el-button @click="router.push('/app/risk-assessments')">查看风险研判事项</el-button></div>
    <el-button
      v-if="workspace"
      @click="router.push({ path: '/app/risk-assessments', query: { case_id: workspace.case.id } })"
      >返回原研判事项</el-button
    >
  </section>
</template>
<style scoped>
.demo-lab-workspace {
  max-width: 1440px;
  margin: auto;
  padding: 28px;
  display: grid;
  gap: 18px;
}
.demo-lab-workspace.embedded { max-width: none; padding: 22px; border: 1px solid var(--piap-line); border-radius: 12px; background: #fff; }
.demo-lab-workspace h2 { margin: 0; font-size: 19px; }
.validation-empty { padding: 20px; border-radius: 8px; background: var(--el-fill-color-light); }
.validation-empty strong { font-size: 15px; }.validation-empty p { margin: 8px 0 16px; font-size: 13px; }
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
  .demo-lab-workspace.embedded { padding: 16px; }
}
</style>
