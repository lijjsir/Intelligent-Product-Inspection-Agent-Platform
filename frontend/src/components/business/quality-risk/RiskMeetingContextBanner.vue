<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { riskCollaborationApi } from "@/api/risk-collaboration.api";
import { extractApiErrorMessage } from "@/api/http";
import type { RiskCollaboration } from "@/types/risk-collaboration.types";
const props = defineProps<{ collaborationId: string }>();
const router = useRouter(),
  item = ref<RiskCollaboration | null>(null);
const error = ref("");
let epoch = 0;
watch(
  () => props.collaborationId,
  async (id) => {
    const token = ++epoch;
    item.value = null;
    error.value = "";
    if (id) {
      try {
        const value = (await riskCollaborationApi.get(id)).data.data;
        if (token === epoch) item.value = value;
      } catch (e) {
        if (token === epoch)
          error.value = extractApiErrorMessage(e, "协同上下文未能加载，请刷新会议重试");
      }
    }
  },
  { immediate: true },
);
</script>
<template>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <div v-if="item" class="risk-meeting-context">
    <div>
      <el-tag type="warning">演示 · 同单位人工协同</el-tag
      ><strong>{{ item.case_code }} · 固定第 {{ item.assessment_version }} 版</strong
      ><span v-if="!item.basis_current">原版依据已变化，需在原事项中重评</span
      ><span>会议公开讨论可返回原事项，独立复核仍按指定版本执行。</span>
    </div>
    <el-button type="primary" plain @click="router.push(item.source_link)"
      >返回事项与本版协同意见</el-button
    >
  </div>
</template>
<style scoped>
.risk-meeting-context {
  flex-basis: 100%;
  width: 100%;
  padding: 14px 18px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-light);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}
.risk-meeting-context > div {
  display: flex;
  gap: 8px 12px;
  align-items: center;
  flex-wrap: wrap;
}
.risk-meeting-context strong {
  font-size: 14px;
}
.risk-meeting-context span {
  font-size: 12px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}
@media (max-width: 650px) {
  .risk-meeting-context {
    padding: 12px;
  }
  .risk-meeting-context .el-button {
    min-height: 44px;
  }
}
</style>
