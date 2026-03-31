<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { useTaskStore } from "@/stores/task.store";
import type { TaskStreamEvent } from "@/types/task.types";

const route = useRoute();
const router = useRouter();
const store = useTaskStore();

const loading = ref(true);
const running = ref(false);
const taskId = route.params.id as string;
const timeline = ref<TaskStreamEvent[]>([]);
let unsubscribe: (() => void) | null = null;

const getStatusType = (status: string) => {
  const map: Record<string, "info" | "primary" | "success" | "danger" | "warning"> = {
    pending: "info",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
};

function pushEvent(event: TaskStreamEvent) {
  timeline.value.unshift(event);
  if (timeline.value.length > 100) {
    timeline.value = timeline.value.slice(0, 100);
  }
  if (event.status === "done" || event.status === "failed") {
    running.value = false;
    store.fetchTask(taskId);
  }
}

async function startPipeline() {
  try {
    running.value = true;
    const result = await store.runTask(taskId);
    pushEvent({ type: "run", message: `任务已提交 (${result.mode})`, ts: new Date().toISOString() });
  } catch (err: any) {
    running.value = false;
    ElMessage.error(err?.response?.data?.message || "启动任务失败");
  }
}

onMounted(async () => {
  try {
    await store.fetchTask(taskId);
    unsubscribe = store.subscribeTaskStream(taskId, pushEvent);
  } catch {
    ElMessage.error("获取任务详情失败");
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  if (unsubscribe) {
    unsubscribe();
    unsubscribe = null;
  }
});

function goBack() {
  router.back();
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" class="mb-4">&larr; 返回列表</el-button>
      <div v-if="store.current" class="title-area">
        <h2 class="title">任务：{{ store.current.id }}</h2>
        <el-tag :type="getStatusType(store.current.status)" size="large" class="ml-4">
          {{ store.current.status.toUpperCase() }}
        </el-tag>
        <el-button
          v-if="['pending', 'failed'].includes(store.current.status)"
          type="primary"
          class="ml-4"
          :loading="running"
          @click="startPipeline"
        >
          启动 AI 推演
        </el-button>
        <el-button
          v-if="['done', 'failed', 'reviewing'].includes(store.current.status)"
          type="success"
          plain
          class="ml-4"
          @click="router.push(`/app/results/${store.current.id}`)"
        >
          查看分析结果报告
        </el-button>
        <el-button
          v-if="['done', 'failed', 'reviewing'].includes(store.current.status)"
          type="warning"
          plain
          class="ml-2"
          @click="router.push(`/app/stability/${store.current.id}`)"
        >
          查看稳定性雷达
        </el-button>
      </div>
    </div>

    <div v-if="store.current" class="content">
      <el-card shadow="never" class="info-card">
        <template #header>基本信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">{{ store.current.id }}</el-descriptions-item>
          <el-descriptions-item label="组织 ID">{{ store.current.org_id }}</el-descriptions-item>
          <el-descriptions-item label="产品编号">{{ store.current.product_id }}</el-descriptions-item>
          <el-descriptions-item label="检测标准">{{ store.current.spec_code }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ store.current.priority }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ store.current.created_at ? new Date(store.current.created_at).toLocaleString() : "-" }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="info-card timeline-card">
        <template #header>AI 检测 Agent 实时流</template>
        <el-empty v-if="timeline.length === 0" description="等待运行阶段事件..." />
        <el-timeline v-else>
          <el-timeline-item v-for="(item, idx) in timeline" :key="idx" :timestamp="item.ts || ''" placement="top">
            <div class="event-line">
              <strong>{{ item.type }}</strong>
              <span v-if="item.stage"> / {{ item.stage }}</span>
              <span v-if="item.message"> - {{ item.message }}</span>
              <span v-if="item.status"> ({{ item.status }})</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
  margin-bottom: 24px;
}

.title-area {
  display: flex;
  align-items: center;
}

.title {
  margin: 0;
  font-size: 24px;
  color: #111827;
}

.ml-4 {
  margin-left: 16px;
}

.ml-2 {
  margin-left: 8px;
}

.mb-4 {
  margin-bottom: 16px;
}

.timeline-card {
  margin-top: 20px;
}

.event-line {
  color: #111827;
}
</style>
