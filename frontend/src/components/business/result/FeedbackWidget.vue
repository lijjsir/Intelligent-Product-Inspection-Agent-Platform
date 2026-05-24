<script setup lang="ts">
import { computed, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useFeedbackStore } from "@/stores/feedback.store";
import type { FeedbackSeverity } from "@/types/governance.types";

interface Props {
  resultId: string;
}

const props = defineProps<Props>();
const store = useFeedbackStore();

const form = reactive({
  feedback_type: "up" as "up" | "down",
  category: "" as string | null,
  severity: "" as FeedbackSeverity | "",
  comment: "",
});

const disabled = computed(() => !props.resultId || store.loading);

const severityOptions: Array<{ label: string; value: FeedbackSeverity; rating: number }> = [
  { label: "无风险", value: "info", rating: 5 },
  { label: "低危", value: "low", rating: 4 },
  { label: "中危", value: "medium", rating: 3 },
  { label: "高危", value: "high", rating: 2 },
  { label: "致命", value: "critical", rating: 1 },
];

function severityRating(value: FeedbackSeverity | "") {
  return severityOptions.find((item) => item.value === value)?.rating ?? null;
}

async function submit(type: "up" | "down") {
  if (!form.severity) {
    ElMessage.warning("请选择严重程度");
    return;
  }
  form.feedback_type = type;
  await store.submit(props.resultId, {
    feedback_type: form.feedback_type,
    category: (form.category || null) as any,
    rating: severityRating(form.severity),
    severity: form.severity,
    comment: form.comment || null,
  });
  ElMessage.success("反馈已提交");
}
</script>

<template>
  <div class="feedback-widget">
    <div class="headline">
      <h3>结果反馈</h3>
      <p>将本次判定质量回灌至治理层</p>
    </div>
    <div class="controls">
      <el-select v-model="form.category" placeholder="反馈类型" clearable>
        <el-option label="真实可靠" value="reliable" />
        <el-option label="判定错误" value="wrong_verdict" />
        <el-option label="证据不足" value="weak_evidence" />
        <el-option label="定位不准" value="bad_bbox" />
        <el-option label="描述模糊" value="unclear_reasoning" />
      </el-select>
      <el-select v-model="form.severity" placeholder="严重程度" clearable>
        <el-option
          v-for="item in severityOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-input v-model="form.comment" type="textarea" :rows="3" placeholder="补充说明（可选）" />
      <div class="actions">
        <el-button type="success" :disabled="disabled" @click="submit('up')">点赞</el-button>
        <el-button type="danger" :disabled="disabled" @click="submit('down')">点踩</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feedback-widget {
  display: grid;
  gap: 16px;
}

.headline h3 {
  margin: 0;
  color: #1b3a5c;
}

.headline p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.controls {
  display: grid;
  gap: 12px;
}

.actions {
  display: flex;
  gap: 12px;
}
</style>
