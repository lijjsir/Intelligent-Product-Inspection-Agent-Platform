<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task.store'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const store = useTaskStore()

const loading = ref(true)
const taskId = route.params.id as string

const getStatusType = (status: string) => {
  const map: Record<string, "info"|"primary"|"success"|"danger"|"warning"> = {
    pending: "info",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
}

onMounted(async () => {
  try {
    await store.fetchTask(taskId)
  } catch (err) {
    ElMessage.error("获取任务详情失败")
  } finally {
    loading.value = false
  }
})

function goBack() {
  router.back()
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" class="mb-4">
        &larr; 返回列表
      </el-button>
      <div v-if="store.current" class="title-area">
        <h2 class="title">任务：{{ store.current.id }}</h2>
        <el-tag :type="getStatusType(store.current.status)" size="large" class="ml-4">
          {{ store.current.status.toUpperCase() }}
        </el-tag>
        <el-button 
          v-if="['done', 'failed', 'reviewing'].includes(store.current.status)" 
          type="success" 
          plain 
          class="ml-4" 
          @click="router.push(`/results/${store.current.id}`)"
        >
          查看分析结果报告
        </el-button>
        <el-button 
          v-if="['done', 'failed', 'reviewing'].includes(store.current.status)" 
          type="warning" 
          plain 
          class="ml-2" 
          @click="router.push(`/stability/${store.current.id}`)"
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
          <el-descriptions-item label="检测规格">{{ store.current.spec_id }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ store.current.priority }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ store.current.created_at ? new Date(store.current.created_at).toLocaleString() : '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Agent Log Stream or Results section can be added here later based on Phase 3 design -->
      <el-card shadow="never" class="info-card" style="margin-top: 20px;">
        <template #header>AI 检测 Agent 工作流记录预留区</template>
        <el-empty description="即将于下一阶段实现实时 SSE 流推送" />
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

.mb-4 {
  margin-bottom: 16px;
}
</style>
