<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { useTaskStore } from "@/stores/task.store";
import type { TaskStreamEvent } from "@/types/task.types";

const route = useRoute();
const router = useRouter();
const taskStore = useTaskStore();

const loading = ref(true);
const running = ref(false);
const deleting = ref(false);
const deleteDialogVisible = ref(false);
const taskId = route.params.id as string;
const timeline = ref<TaskStreamEvent[]>([]);
let unsubscribe: (() => void) | null = null;

function getStatusType(status: string) {
  const map: Record<string, "info" | "primary" | "success" | "danger" | "warning"> = {
    pending: "info",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
}

function pushEvent(event: TaskStreamEvent) {
  timeline.value.unshift(event);
  if (timeline.value.length > 100) {
    timeline.value = timeline.value.slice(0, 100);
  }
  if (event.status === "done" || event.status === "failed") {
    running.value = false;
    void taskStore.fetchTask(taskId);
  }
}

async function startPipeline() {
  try {
    running.value = true;
    const result = await taskStore.runTask(taskId);
    pushEvent({
      type: "run",
      message: `任务已提交执行（${result.mode}）`,
      status: "running",
      ts: new Date().toISOString(),
    });
  } catch (error: any) {
    running.value = false;
    ElMessage.error(error?.response?.data?.message || "启动任务失败");
  }
}

function goBack() {
  router.back();
}

async function deleteTask() {
  deleteDialogVisible.value = true;
}

async function confirmDeleteTask() {
  deleting.value = true;
  try {
    await taskStore.deleteTask(taskId);
    ElMessage.success("任务已删除");
    deleteDialogVisible.value = false;
    router.push("/app/tasks");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "删除任务失败");
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  try {
    await taskStore.fetchTask(taskId);
    unsubscribe = taskStore.subscribeTaskStream(taskId, pushEvent);
  } catch (error) {
    console.error(error);
    ElMessage.error("获取任务详情失败");
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  unsubscribe?.();
  unsubscribe = null;
});
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" class="back-button">&larr; 返回列表</el-button>
      <div v-if="taskStore.current" class="title-area">
        <h2 class="title">任务：{{ taskStore.current.id }}</h2>
        <el-tag :type="getStatusType(taskStore.current.status)" size="large">
          {{ taskStore.current.status.toUpperCase() }}
        </el-tag>
        <el-button
          v-if="['pending', 'failed'].includes(taskStore.current.status)"
          type="primary"
          :loading="running"
          @click="startPipeline"
        >
          启动 AI 推演
        </el-button>
        <el-button
          v-if="['done', 'failed', 'reviewing'].includes(taskStore.current.status)"
          type="success"
          plain
          @click="router.push(`/app/results/${taskStore.current.id}`)"
        >
          查看分析结果
        </el-button>
        <el-button
          v-if="['done', 'failed', 'reviewing'].includes(taskStore.current.status)"
          type="warning"
          plain
          @click="router.push(`/app/stability/${taskStore.current.id}`)"
        >
          查看稳定性评估
        </el-button>
        <el-button
          v-if="taskStore.current.status !== 'running'"
          type="danger"
          plain
          :loading="deleting"
          @click="deleteTask"
        >
          删除任务
        </el-button>
      </div>
    </div>

    <div v-if="taskStore.current" class="content">
      <el-card shadow="never">
        <template #header>基本信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">{{ taskStore.current.id }}</el-descriptions-item>
          <el-descriptions-item label="组织 ID">{{ taskStore.current.org_id }}</el-descriptions-item>
          <el-descriptions-item label="产品编号">{{ taskStore.current.product_id }}</el-descriptions-item>
          <el-descriptions-item label="检测标准">{{ taskStore.current.spec_code }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ taskStore.current.priority }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ taskStore.current.created_at ? new Date(taskStore.current.created_at).toLocaleString("zh-CN", { hour12: false }) : "-" }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="timeline-card">
        <template #header>AI 检测 Agent 实时流</template>
        <el-empty v-if="timeline.length === 0" description="等待执行阶段事件..." />
        <el-timeline v-else>
          <el-timeline-item v-for="(item, index) in timeline" :key="index" :timestamp="item.ts || ''" placement="top">
            <div class="event-line">
              <strong>{{ item.type }}</strong>
              <span v-if="item.stage"> / {{ item.stage }}</span>
              <span v-if="item.message"> - {{ item.message }}</span>
              <span v-if="item.status">（{{ item.status }}）</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>

    <el-dialog
      v-model="deleteDialogVisible"
      title="删除任务"
      width="420px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <div class="delete-dialog-copy">删除后该任务将不再出现在任务列表中，是否继续？</div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="deleteDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="deleting" @click="confirmDeleteTask">删除</el-button>
        </div>
      </template>
    </el-dialog>
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

.back-button {
  margin-bottom: 16px;
}

.title-area {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 24px;
  color: #111827;
}

.content {
  display: grid;
  gap: 20px;
}

.timeline-card {
  margin-top: 0;
}

.event-line {
  color: #111827;
  line-height: 1.7;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.delete-dialog-copy {
  line-height: 1.8;
  color: #374151;
}
</style>
