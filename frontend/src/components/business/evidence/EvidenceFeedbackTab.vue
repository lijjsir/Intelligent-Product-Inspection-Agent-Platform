<script setup lang="ts">
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { usePermission } from "@/composables/usePermission"
import { resultApi, type ReviewSubmit } from "@/api/result.api"
import FeedbackWidget from "@/components/business/result/FeedbackWidget.vue"
import type { InspectionResult } from "@/types/result.types"

const props = defineProps<{
  result: InspectionResult
}>()

const emit = defineEmits<{
  updated: []
}>()

const { hasRole } = usePermission()
const canReview = ref(hasRole(["expert"]))
const reviewing = ref(false)
const reviewForm = ref<ReviewSubmit>({ verdict: "", note: "" })

const verdictOptions = [
  { label: "合格 (Pass)", value: "pass" },
  { label: "不合格 (Fail)", value: "fail" },
  { label: "需人工复核 (Manual Required)", value: "manual_required" },
]

function getVerdictType(v: string) {
  const map: Record<string, any> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "info",
  }
  return map[v] || "info"
}

async function submitReview() {
  if (!reviewForm.value.verdict) return
  reviewing.value = true
  try {
    await resultApi.review(props.result.id, reviewForm.value)
    ElMessage.success("复核已提交")
    emit("updated")
  } catch {
    ElMessage.error("复核提交失败")
  } finally {
    reviewing.value = false
  }
}
</script>

<template>
  <div class="feedback-tab">
    <div class="feedback-layout">
      <!-- Review section -->
      <section class="feedback-section">
        <h3 class="section-title">人工复核</h3>

        <div v-if="result.reviewed_by" class="review-done">
          <div class="review-record">
            <div class="review-head">
              <el-tag :type="getVerdictType(result.verdict)" size="small">
                {{ result.verdict }}
              </el-tag>
              <span class="review-meta">
                由 {{ result.reviewed_by }} 复核于 {{ result.reviewed_at ? new Date(result.reviewed_at).toLocaleString() : '-' }}
              </span>
            </div>
            <p v-if="result.review_note" class="review-note">{{ result.review_note }}</p>
          </div>
        </div>

        <div v-else-if="canReview" class="review-form">
          <el-form label-position="top" size="small">
            <el-form-item label="复核判定" class="!mb-3">
              <el-select v-model="reviewForm.verdict" placeholder="请选择复核结论" class="!w-full">
                <el-option v-for="opt in verdictOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="复核备注" class="!mb-3">
              <el-input v-model="reviewForm.note" type="textarea" :rows="2" placeholder="可选：说明复核理由" />
            </el-form-item>
            <el-button type="primary" size="small" :loading="reviewing" :disabled="!reviewForm.verdict" @click="submitReview">
              提交复核
            </el-button>
          </el-form>
        </div>

        <div v-else class="review-none">
          <span class="text-zinc-400 text-sm">暂无人工复核记录</span>
        </div>
      </section>

      <!-- Feedback section -->
      <section class="feedback-section">
        <h3 class="section-title">用户反馈</h3>
        <FeedbackWidget :result-id="result.id" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.feedback-tab {
  padding: 24px;
  max-width: 800px;
}

.feedback-layout {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.feedback-section {
  border: 1px solid oklch(0.92 0.005 260);
  border-radius: 10px;
  padding: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: oklch(0.25 0.01 260);
  margin: 0 0 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid oklch(0.94 0.003 260);
}

.review-record {
  padding: 14px;
  background: oklch(0.985 0.003 260);
  border-radius: 8px;
}

.review-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.review-meta {
  font-size: 12px;
  color: oklch(0.5 0.01 260);
}

.review-note {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: oklch(0.35 0.01 260);
}

.review-none {
  padding: 24px;
  text-align: center;
}

.review-form {
  max-width: 420px;
}
</style>
