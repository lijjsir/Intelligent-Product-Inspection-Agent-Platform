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
    path: "/app/results",
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

const getVerdictType = (verdict: string): "info" | "success" | "danger" | "warning" => {
  const map: Record<string, "info" | "success" | "danger" | "warning"> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "danger",
  };
  return map[verdict] || "info";
};

const quickFilters = [
  { label: "全部", verdict: "" as const, tag: "" },
  { label: "待人工审核", verdict: "manual_required" as const, tag: "danger" },
  { label: "通过", verdict: "pass" as const, tag: "success" },
  { label: "不通过", verdict: "fail" as const, tag: "danger" },
];

function applyQuickFilter(v: Verdict | "") {
  filters.value.verdict = v;
  resetPage();
  pushQuery();
}

const VERDICT_LABELS: Record<string, string> = {
  pass: "通过",
  fail: "不通过",
  uncertain: "待定",
  manual_required: "待人工审核",
};
</script>

<template>
  <div class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">检测结果列表</h2>
      <p class="mt-2 text-sm text-zinc-500">支持按产品线、模型和结论筛选。专家角色可在此进行人工复核裁定。</p>
    </div>

    <!-- 快捷筛选 -->
    <div class="flex items-center gap-3 flex-wrap">
      <el-button
        v-for="qf in quickFilters"
        :key="qf.verdict"
        :type="filters.verdict === qf.verdict ? 'primary' : 'default'"
        :plain="filters.verdict !== qf.verdict"
        size="default"
        @click="applyQuickFilter(qf.verdict)"
      >
        {{ qf.label }}
      </el-button>
    </div>

    <div class="card-surface p-4">
      <el-form :model="filters" inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
        <el-form-item label="结论">
          <el-select v-model="filters.verdict" clearable class="!w-[160px]" size="small">
            <el-option label="通过" value="pass" />
            <el-option label="不通过" value="fail" />
            <el-option label="待定" value="uncertain" />
            <el-option label="待人工审核" value="manual_required" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线">
          <el-input v-model="filters.product_id" placeholder="产品线 / 产品编号" clearable size="small" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="filters.model_key" placeholder="模型标识" clearable size="small" />
        </el-form-item>
        <el-form-item label="任务 ID">
          <el-input v-model="filters.task_id" placeholder="任务 ID" clearable size="small" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" @click="handleSearch">查询</el-button>
          <el-button size="small" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="card-surface">
      <el-table :data="store.items" v-loading="store.loading" size="small" class="list-table">
        <el-table-column prop="id" label="结果ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="task_id" label="任务ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="product_id" label="产品线" width="140" />
        <el-table-column prop="llm_model" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column prop="verdict" label="结论" width="120">
          <template #default="scope">
            <el-tag :type="getVerdictType(scope.row.verdict)" size="small">{{ VERDICT_LABELS[scope.row.verdict] || scope.row.verdict }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="overall_score" label="分数" width="100">
          <template #default="scope">{{ (scope.row.overall_score * 100).toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" min-width="180">
          <template #default="scope">{{ scope.row.created_at ? new Date(scope.row.created_at).toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="router.push(`/app/results/${scope.row.task_id}`)">详情</el-button>
            <el-button link type="primary" size="small" @click="router.push(`/app/results/${scope.row.task_id}/evidence`)">证据溯源</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end p-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          size="small"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.list-table :deep(.el-table__header th) {
  @apply text-zinc-500 font-medium text-[13px] bg-zinc-50;
}
.list-table :deep(.el-table__body tr:hover > td) {
  @apply bg-zinc-50;
}
</style>
