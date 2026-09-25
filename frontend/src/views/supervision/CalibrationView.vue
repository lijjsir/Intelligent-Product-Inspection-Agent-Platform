<script setup lang="ts">
import { ref } from "vue";
import { http } from "@/api/http";
import { ElMessage } from "element-plus";
const dataset = ref(""),
  predictions = ref(""),
  outcomes = ref(""),
  report = ref<any>(null),
  busy = ref(false);
async function evaluate() {
  busy.value = true;
  try {
    const values = predictions.value
      .split(/[,，\s]+/)
      .filter(Boolean)
      .map(Number);
    const labels = outcomes.value
      .split(/[,，\s]+/)
      .filter(Boolean)
      .map(Number);
    report.value = (
      await http.post<any>("/v1/quality-supervision/evaluations/calibration", {
        dataset_id: dataset.value,
        predictions: values,
        outcomes: labels,
      })
    ).data.data;
    ElMessage.success("校准评测完成");
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <main class="calibration-page">
    <h1>概率校准评测</h1>
    <p>使用独立真实结果评测集，检查模型预测概率与完整检测标签的一致程度。</p>
    <el-form label-position="top"
      ><el-form-item label="评测集编号"><el-input v-model="dataset" /></el-form-item
      ><el-form-item label="模型预测概率（0–1，逗号或换行分隔）"
        ><el-input v-model="predictions" type="textarea" :rows="4" /></el-form-item
      ><el-form-item label="完整检测标签（0正常、1异常，与预测逐项对应）"
        ><el-input v-model="outcomes" type="textarea" :rows="4" /></el-form-item
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="!dataset.trim() || !predictions.trim() || !outcomes.trim()"
        @click="evaluate"
        >运行评测</el-button
      ></el-form
    >
    <section v-if="report">
      <el-descriptions :column="3" border
        ><el-descriptions-item label="样本量">{{ report.sample_count }}</el-descriptions-item
        ><el-descriptions-item label="Brier误差">{{ report.brier.toFixed(4) }}</el-descriptions-item
        ><el-descriptions-item label="校准误差ECE">{{
          report.ece.toFixed(4)
        }}</el-descriptions-item></el-descriptions
      ><el-table :data="report.reliability_bins"
        ><el-table-column prop="lower" label="概率区间下限" /><el-table-column
          prop="upper"
          label="上限" /><el-table-column prop="count" label="样本量" /><el-table-column
          prop="predicted"
          label="平均预测" /><el-table-column prop="observed" label="实际异常比例" /></el-table
      ><el-alert type="info" :closable="false" :title="report.limitations.join('；')" />
    </section>
  </main>
</template>
<style scoped>
.calibration-page {
  padding: 24px;
  max-width: 1000px;
  margin: auto;
}
h1 {
  font-size: 24px;
}
p {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.el-form {
  max-width: 640px;
  padding: 20px 0;
}
section {
  margin-top: 20px;
}
.el-table {
  margin: 16px 0;
}
</style>
