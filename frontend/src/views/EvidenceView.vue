<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { useResultStore } from "@/stores/result.store"
import { useTaskStore } from "@/stores/task.store"
import EvidenceHeader from "@/components/business/evidence/EvidenceHeader.vue"
import EvidenceSummaryTab from "@/components/business/evidence/EvidenceSummaryTab.vue"
import EvidenceImageTab from "@/components/business/evidence/EvidenceImageTab.vue"
import EvidenceCitationTab from "@/components/business/evidence/EvidenceCitationTab.vue"
import EvidenceReasoningTab from "@/components/business/evidence/EvidenceReasoningTab.vue"
import EvidenceTraceTab from "@/components/business/evidence/EvidenceTraceTab.vue"
import EvidenceFeedbackTab from "@/components/business/evidence/EvidenceFeedbackTab.vue"

const route = useRoute()
const router = useRouter()
const resultStore = useResultStore()
const taskStore = useTaskStore()

const loading = ref(true)
const activeTab = ref("summary")
const currentTaskId = computed(() => String(route.params.task_id || ""))
const currentResult = computed(() => resultStore.current?.task_id === currentTaskId.value ? resultStore.current : null)
const currentTask = computed(() => taskStore.current?.id === currentTaskId.value ? taskStore.current : null)

function resolveTaskImageUrl(value?: string | null) {
  const url = String(value || "").trim()
  if (!url) return ""
  if (url.startsWith("data:")) return url
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith("/uploads/")) return url
  if (url.startsWith("uploads/")) return `/${url}`
  return url
}

const taskImages = computed(() => {
  return (currentTask.value?.image_urls || []).map((item) => resolveTaskImageUrl(item)).filter(Boolean)
})

const sampleLabels = computed(() => {
  const items = currentTask.value?.image_items
  if (!items || !items.length) return {} as Record<number, string>
  const map: Record<number, string> = {}
  for (const item of items) {
    if (item.sample_number != null && !(item.index in map)) {
      map[item.index] = `样品${item.sample_number}`
    }
  }
  return map
})

function sampleLabel(imageIndex?: number | null): string {
  if (imageIndex == null) return ""
  return sampleLabels.value[imageIndex] || ""
}

async function loadEvidence(taskId: string) {
  loading.value = true
  if (resultStore.current?.task_id !== taskId) resultStore.current = null
  if (taskStore.current?.id !== taskId) taskStore.current = null
  try {
    await Promise.all([
      resultStore.fetchByTask(taskId),
      taskStore.fetchTask(taskId),
    ])
    const qtab = route.query.tab as string
    if (qtab && ["summary", "image", "citation", "reasoning", "trace", "feedback"].includes(qtab)) {
      activeTab.value = qtab
    }
  } catch (err: any) {
    if (err.response?.status === 404) {
      ElMessage.warning("该任务暂无检测结果或不存在")
    } else {
      ElMessage.error("获取证据溯源数据失败")
    }
  } finally {
    loading.value = false
  }
}

watch(currentTaskId, (taskId) => {
  if (taskId) void loadEvidence(taskId)
}, { immediate: true })

function goBack() {
  router.back()
}
</script>

<template>
  <div class="evidence-page" v-loading="loading">
    <div v-if="currentResult" class="evidence-container">
      <EvidenceHeader
        :result="currentResult"
        :task="currentTask"
        @back="goBack"
      />

      <el-tabs
        v-model="activeTab"
        class="evidence-tabs"
        @tab-change="(tab: string) => router.replace({ query: { tab } })"
      >
        <el-tab-pane label="结论摘要" name="summary">
          <EvidenceSummaryTab :result="currentResult" />
        </el-tab-pane>

        <el-tab-pane label="图像证据" name="image">
          <EvidenceImageTab
            :images="taskImages"
            :defects="currentResult.defects"
            :loading="loading"
            :sample-label="sampleLabel"
          />
        </el-tab-pane>

        <el-tab-pane label="引用证据" name="citation">
          <EvidenceCitationTab :citations="currentResult.citations" />
        </el-tab-pane>

        <el-tab-pane label="推理链路" name="reasoning">
          <EvidenceReasoningTab :reasoning-chain="currentResult.reasoning_chain" />
        </el-tab-pane>

        <el-tab-pane label="Trace" name="trace">
          <EvidenceTraceTab :result="currentResult" />
        </el-tab-pane>

        <el-tab-pane label="复核反馈" name="feedback">
          <EvidenceFeedbackTab :result="currentResult" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <div v-else-if="!loading" class="empty-state">
      <el-empty description="无法获取该任务的证据溯源数据" />
      <div class="flex justify-center mt-4">
        <el-button @click="goBack">返回</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.evidence-page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.evidence-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.evidence-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.evidence-tabs :deep(.el-tabs__content) {
  flex: 1;
}

.evidence-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  padding: 0 24px;
  background: oklch(0.97 0.005 260);
  border-bottom: 1px solid oklch(0.9 0.005 260);
}

.evidence-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}
</style>
