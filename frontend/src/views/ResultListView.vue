<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { usePagination } from "@/composables/usePagination";
import { useResultStore } from "@/stores/result.store";
import type { Verdict } from "@/types/result.types";

const route = useRoute();
const router = useRouter();
const store = useResultStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref<{ verdict: Verdict | ""; product_id: string; model_key: string; task_id: string }>({
  verdict: "",
  product_id: "",
  model_key: "",
  task_id: "",
});

onMounted(() => {
  syncFromRoute();
  fetchData();
});

watch(() => route.query, () => {
  syncFromRoute();
  fetchData();
});

function syncFromRoute() {
  filters.value = {
    verdict: (route.query.verdict as Verdict | "") || "",
    product_id: String(route.query.product_id || ""),
    model_key: String(route.query.model_key || ""),
    task_id: String(route.query.task_id || ""),
  };
  page.value = Number(route.query.page || 1);
}

async function fetchData() {
  const data = await store.fetchResults({
    page: page.value,
    size: pageSize.value,
    verdict: filters.value.verdict || undefined,
    product_id: filters.value.product_id || undefined,
    model_key: filters.value.model_key || undefined,
    task_id: filters.value.task_id || undefined,
  });
  total.value = data.total;
}

function pushQuery() {
  router.push({
    path: "/results",
    query: {
      ...(filters.value.verdict ? { verdict: filters.value.verdict } : {}),
      ...(filters.value.product_id ? { product_id: filters.value.product_id } : {}),
      ...(filters.value.model_key ? { model_key: filters.value.model_key } : {}),
      ...(filters.value.task_id ? { task_id: filters.value.task_id } : {}),
      page: String(page.value),
    },
  });
}

function handleSearch() {
  resetPage();
  pushQuery();
}

function handleReset() {
  filters.value = { verdict: "", product_id: "", model_key: "", task_id: "" };
  resetPage();
  pushQuery();
}

function handleCurrentChange(val: number) {
  onPageChange(val);
  pushQuery();
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  pushQuery();
}

const getVerdictType = (verdict: string) => {
  const map: Record<string, "info" | "success" | "danger" | "warning"> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "info",
  };
  return map[verdict] || "info";
};
</script>

<template>
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">检测结果列表</h2>
        <p class="subtitle">支持按产品线、模型和结论筛选，用于承接分析中心钻取。</p>
      </div>
    </div>

    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="结论">
          <el-select v-model="filters.verdict" clearable style="width: 160px">
            <el-option label="PASS" value="pass" />
            <el-option label="FAIL" value="fail" />
            <el-option label="UNCERTAIN" value="uncertain" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线">
          <el-input v-model="filters.product_id" placeholder="产品线 / 产品编号" clearable />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="filters.model_key" placeholder="模型标识" clearable />
        </el-form-item>
        <el-form-item label="任务 ID">
          <el-input v-model="filters.task_id" placeholder="任务 ID" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading" border stripe>
        <el-table-column prop="id" label="结果ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="task_id" label="任务ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="product_id" label="产品线" width="140" />
        <el-table-column prop="llm_model" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column prop="verdict" label="结论" width="120">
          <template #default="scope">
            <el-tag :type="getVerdictType(scope.row.verdict)">{{ scope.row.verdict.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="overall_score" label="分数" width="100">
          <template #default="scope">{{ (scope.row.overall_score * 100).toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" min-width="180">
          <template #default="scope">{{ scope.row.created_at ? new Date(scope.row.created_at).toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="router.push(`/results/${scope.row.task_id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper mt-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; background-color: #f3f4f6; min-height: 100vh; }
.header { margin-bottom: 24px; }
.title { margin: 0 0 8px 0; font-size: 24px; color: #111827; }
.subtitle { margin: 0; color: #6b7280; font-size: 14px; }
.mb-4 { margin-bottom: 16px; }
.pagination-wrapper { display: flex; justify-content: flex-end; }
</style>
