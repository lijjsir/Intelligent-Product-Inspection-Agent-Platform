<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { useTrainingJobStore } from "@/stores/trainingJob.store";

const route = useRoute();
const router = useRouter();
const store = useTrainingJobStore();
const actionLoading = ref("");

const resourceId = computed(() => String(route.params.id || ""));
const current = computed(() => store.current);
const resultSummary = computed(() => {
  const value = current.value?.result_summary;
  if (!value || typeof value !== "object") {
    return { artifacts: [], metrics: {}, logs: [] };
  }
  const summary = value as Record<string, unknown>;
  return {
    artifacts: Array.isArray(summary.artifacts) ? summary.artifacts : [],
    metrics: summary.metrics && typeof summary.metrics === "object" ? summary.metrics : {},
    logs: Array.isArray(summary.logs) ? summary.logs : [],
  };
});

function statusTagType(status?: string | null) {
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "info";
  return "primary";
}

async function load() {
  if (!resourceId.value) return;
  await store.fetchOne(resourceId.value);
}

async function handleLaunch() {
  if (!resourceId.value) return;
  actionLoading.value = "launch";
  try {
    await store.launchOne(resourceId.value);
    ElMessage.success("已启动");
    await load();
  } finally {
    actionLoading.value = "";
  }
}

async function handleCancel() {
  if (!resourceId.value) return;
  actionLoading.value = "cancel";
  try {
    await store.cancelOne(resourceId.value);
    ElMessage.success("已取消");
    await load();
  } finally {
    actionLoading.value = "";
  }
}

async function handleDelete() {
  if (!resourceId.value) return;
  await ElMessageBox.confirm("确定删除该训练任务吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  actionLoading.value = "delete";
  try {
    await store.removeOne(resourceId.value);
    ElMessage.success("已删除");
    await router.push("/ops/training/jobs");
  } finally {
    actionLoading.value = "";
  }
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <div class="detail-page">
    <section class="detail-topbar">
      <div class="flex flex-col gap-2">
        <el-button link type="primary" @click="router.push('/ops/training/jobs')">返回列表</el-button>
        <h2>{{ current?.name || '训练任务详情' }}</h2>
        <p>{{ current?.description || '查看训练任务配置、执行状态和结果占位信息。' }}</p>
      </div>
      <div class="detail-actions">
        <el-button v-if="['draft', 'failed'].includes(current?.status || '')" type="primary" :loading="actionLoading === 'launch'" @click="handleLaunch">启动</el-button>
        <el-button v-if="['queued', 'running'].includes(current?.status || '')" type="warning" :loading="actionLoading === 'cancel'" @click="handleCancel">取消</el-button>
        <el-button type="danger" :loading="actionLoading === 'delete'" @click="handleDelete">删除</el-button>
      </div>
    </section>

    <section class="grid-layout" v-loading="store.loading">
      <article class="overview-card">
        <h3>概览</h3>
        <div class="overview-list">
          <div><span>状态</span><strong><el-tag :type="statusTagType(current?.status)">{{ current?.status || '-' }}</el-tag></strong></div>
          <div><span>来源数据集</span><strong class="break-all">{{ current?.source_dataset_id || '-' }}</strong></div>
          <div><span>训练模型</span><strong class="break-all">{{ current?.model_config_ref?.display_name || current?.model_config_ref?.model_key || current?.model_config_id || '-' }}</strong></div>
          <div><span>评测集</span><strong class="break-all">{{ current?.eval_set_id || '-' }}</strong></div>
          <div><span>执行模式</span><strong>{{ current?.execution_mode || '-' }}</strong></div>
          <div><span>开始时间</span><strong>{{ current?.started_at || '-' }}</strong></div>
          <div><span>完成时间</span><strong>{{ current?.completed_at || '-' }}</strong></div>
        </div>
      </article>

      <article class="overview-card">
        <h3>配置 JSON</h3>
        <pre class="code-block">{{ JSON.stringify(current?.config_json || {}, null, 2) }}</pre>
      </article>
    </section>

    <section class="grid-layout">
      <article class="overview-card">
        <h3>结果摘要</h3>
        <div class="summary-grid">
          <div>
            <h4>Artifacts</h4>
            <el-empty v-if="!resultSummary.artifacts.length" description="暂无 artifacts" />
            <ul v-else>
              <li v-for="(item, index) in resultSummary.artifacts" :key="index">{{ JSON.stringify(item) }}</li>
            </ul>
          </div>
          <div>
            <h4>Metrics</h4>
            <el-empty v-if="!Object.keys(resultSummary.metrics).length" description="暂无 metrics" />
            <pre v-else class="code-block small">{{ JSON.stringify(resultSummary.metrics, null, 2) }}</pre>
          </div>
          <div>
            <h4>Logs</h4>
            <el-empty v-if="!resultSummary.logs.length" description="暂无 logs" />
            <ul v-else>
              <li v-for="(item, index) in resultSummary.logs" :key="index">{{ item }}</li>
            </ul>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-topbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 24px;
  border-radius: 24px;
  background: linear-gradient(135deg, #f4f8ef, #fff6e8);
}

.detail-topbar h2 {
  margin: 0;
  font-size: 28px;
  color: #17212c;
}

.detail-topbar p {
  margin: 0;
  color: #536171;
}

.detail-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.grid-layout {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}

.overview-card {
  padding: 20px;
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e5e7eb;
}

.overview-card h3,
.summary-grid h4 {
  margin: 0 0 16px;
}

.overview-list {
  display: grid;
  gap: 12px;
}

.overview-list > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.overview-list span {
  color: #64748b;
}

.code-block {
  margin: 0;
  padding: 16px;
  border-radius: 16px;
  background: #101827;
  color: #dbe7f3;
  overflow: auto;
}

.code-block.small {
  font-size: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
</style>
