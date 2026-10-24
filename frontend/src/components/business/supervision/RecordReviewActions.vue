<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { supervisionApi } from "@/api/supervision.api";
import { extractApiErrorMessage } from "@/api/http";
import { OP_LABELS, type RecordReview, type SupervisionRecord } from "@/types/supervision.types";

const props = defineProps<{ record: SupervisionRecord }>();
const emit = defineEmits<{ changed: [] }>();
const reviews = ref<RecordReview[]>([]);
const loading = ref(false), error = ref(""), processing = ref(false);
const actionable = computed(() => reviews.value.filter(review => review.can_decide));
const awaitingOthers = computed(() => reviews.value.some(review => !review.can_decide && ["pending", "escalate"].includes(review.status)));
let epoch = 0;

async function load() {
  const key = ++epoch;
  const { kind, id } = props.record;
  reviews.value = []; error.value = ""; loading.value = true;
  try {
    const response = await supervisionApi.recordReviews(kind, id);
    if (key === epoch) reviews.value = response.data.data;
  } catch (e) {
    if (key === epoch) error.value = extractApiErrorMessage(e, "复核状态读取失败");
  } finally {
    if (key === epoch) loading.value = false;
  }
}

function acceptLabel(operation: string) {
  return { "risk.review": "通过风险复核", "sampling.approve": "批准抽查方案", "result.review": "通过结果复核", "result.signoff": "确认正式结果" }[operation] || "通过复核";
}

async function decide(review: RecordReview, decision: string) {
  if (processing.value) return;
  const recordId = props.record.id, version = props.record.version, key = epoch;
  processing.value = true;
  try {
    const prompt = await ElMessageBox.prompt(
      "请填写复核依据或需要补充的材料。",
      OP_LABELS[review.operation] || "记录复核",
      { inputType: "textarea", inputValidator: (value: string) => !!value?.trim() || "请填写处理意见" },
    );
    if (key !== epoch || props.record.id !== recordId || props.record.version !== version) return;
    await supervisionApi.decide(review.id, decision, prompt.value.trim());
    ElMessage.success("已记录处理结果");
    if (props.record.id === recordId) { await load(); emit("changed"); }
  } catch (e) {
    if (e !== "cancel" && e !== "close") ElMessage.error(extractApiErrorMessage(e, "处理未完成，请刷新后重试"));
  } finally {
    processing.value = false;
  }
}

watch(() => props.record, load, { immediate: true });
onBeforeUnmount(() => { ++epoch; });
</script>

<template>
  <span v-if="loading" class="review-notice">正在读取复核状态…</span>
  <span v-else-if="error" class="review-notice" role="alert">{{ error }} <el-button size="small" link @click="load">重试</el-button></span>
  <template v-else>
    <template v-for="review in actionable" :key="review.id">
      <el-button size="small" type="primary" :disabled="processing" @click="decide(review, 'accept')">{{ acceptLabel(review.operation) }}</el-button>
      <el-button size="small" :disabled="processing" @click="decide(review, 'request_evidence')">退回补证</el-button>
      <el-button size="small" :disabled="processing" @click="decide(review, 'escalate')">转人工会商</el-button>
    </template>
    <span v-if="awaitingOthers" class="review-notice">已提交，等待其他专家独立复核</span>
  </template>
</template>

<style scoped>
.review-notice { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.8; }
</style>
