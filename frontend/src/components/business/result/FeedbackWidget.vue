4<script setup lang="ts">
import { computed, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useFeedbackStore } from "@/stores/feedback.store";

interface Props {
  resultId: string;
}

const props = defineProps<Props>();
const store = useFeedbackStore();

const form = reactive({
  feedback_type: "up" as "up" | "down",
  category: "" as string | null,
  rating: 5,
  comment: "",
});

const disabled = computed(() => !props.resultId || store.loading);

async function submit(type: "up" | "down") {
  form.feedback_type = type;
  await store.submit(props.resultId, {
    feedback_type: form.feedback_type,
    category: (form.category || null) as any,
    rating: form.rating,
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
      <el-input-number v-model="form.rating" :min="1" :max="5" />
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

