<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { infrastructureApi } from "@/api/infrastructure.api";
import type { InfrastructureComponent, InfrastructureStatus } from "@/types/governance.types";

const loading = ref(false);
const statusData = ref<InfrastructureStatus | null>(null);

const summaryCards = computed(() => {
  const data = statusData.value;
  const components = data?.components ?? [];
  return [
    { label: "组件总数", value: components.length },
    { label: "健康", value: components.filter((item) => item.status === "healthy").length },
    { label: "降级", value: components.filter((item) => item.status === "degraded").length },
    { label: "异常", value: components.filter((item) => item.status === "unhealthy").length },
  ];
});

onMounted(() => {
  fetchStatus();
});

async function fetchStatus() {
  loading.value = true;
  try {
    const { data } = await infrastructureApi.getStatus();
    statusData.value = data.data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "加载基础设施状态失败");
  } finally {
    loading.value = false;
  }
}

async function checkAll() {
  loading.value = true;
  try {
    const { data } = await infrastructureApi.checkAll();
    statusData.value = data.data;
    ElMessage.success("检测完成");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "基础设施检测失败");
  } finally {
    loading.value = false;
  }
}

function statusTagType(status: string) {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  if (status === "unhealthy") return "danger";
  return "info";
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function componentIcon(kind: InfrastructureComponent["kind"]) {
  if (kind === "database") return "MySQL";
  if (kind === "cache") return "Redis";
  if (kind === "vector_db") return "Qdrant";
  return "Storage";
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">存储/基础设施</h2>
        <p class="mt-2 text-sm text-zinc-500">实时检测数据库、缓存、向量库和对象存储的连通性与基础健康状态。</p>
      </div>
      <div class="flex gap-3">
        <el-button @click="fetchStatus" :loading="loading">刷新状态</el-button>
        <el-button type="primary" @click="checkAll" :loading="loading">全部检测</el-button>
      </div>
    </div>

    <section class="grid gap-4 md:grid-cols-4">
      <el-card v-for="item in summaryCards" :key="item.label" shadow="never">
        <div class="text-sm text-zinc-500">{{ item.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-zinc-900">{{ item.value }}</div>
      </el-card>
    </section>

    <el-card shadow="never">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div class="text-sm text-zinc-500">整体状态</div>
          <div class="mt-2 flex items-center gap-3">
            <el-tag :type="statusTagType(statusData?.overall_status || 'unknown')" effect="dark" size="large">
              {{ statusData?.overall_status || "unknown" }}
            </el-tag>
            <span class="text-sm text-zinc-500">检测时间：{{ formatDateTime(statusData?.checked_at) }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <el-card v-for="item in statusData?.components || []" :key="`${item.kind}-${item.name}`" shadow="never" class="infra-card">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.24em] text-zinc-400">{{ componentIcon(item.kind) }}</div>
            <div class="mt-2 text-lg font-semibold text-zinc-900">{{ item.name }}</div>
          </div>
          <el-tag :type="statusTagType(item.status)" effect="light">{{ item.status }}</el-tag>
        </div>
        <div class="mt-4 space-y-2 text-sm text-zinc-600">
          <div>延迟：{{ item.latency_ms ?? "-" }} ms</div>
          <div class="min-h-[40px]">{{ item.detail || "暂无详情" }}</div>
          <div class="text-xs text-zinc-400">最后检测：{{ formatDateTime(item.last_check_at) }}</div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.infra-card {
  min-height: 220px;
}
</style>
