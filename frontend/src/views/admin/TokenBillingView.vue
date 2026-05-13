<script setup lang="ts">
import { computed, onMounted, reactive } from "vue";
import { useBillingStore } from "@/stores/billing.store";

const store = useBillingStore();
const filters = reactive({
  granularity: "day" as "day" | "week" | "month",
  model_key: "",
  product_line: "",
});

const userSummaries = computed(() => store.current?.user_summaries || []);

async function reload() {
  await store.fetchSummary({
    granularity: filters.granularity,
    model_key: filters.model_key || undefined,
    product_line: filters.product_line || undefined,
  });
}

function formatNumber(value: number | null | undefined) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatCurrency(value: number | null | undefined) {
  return `¥ ${Number(value || 0).toFixed(4)}`;
}

function formatTime(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

onMounted(() => {
  reload();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="hero">
      <div>
        <h2>Token 计费看板</h2>
        <p>查看模型调用成本、Token 流水，以及每个用户累计消耗的 Token 总量。</p>
      </div>
    </div>

    <el-card shadow="never" class="filters">
      <el-select v-model="filters.granularity" style="width: 140px">
        <el-option label="按日" value="day" />
        <el-option label="按周" value="week" />
        <el-option label="按月" value="month" />
      </el-select>
      <el-input v-model="filters.model_key" placeholder="模型标识" style="width: 220px" />
      <el-input v-model="filters.product_line" placeholder="产品线" style="width: 220px" />
      <el-button type="primary" @click="reload">查询</el-button>
    </el-card>

    <div class="flex gap-4">
      <div class="flex-1">
        <el-card shadow="never">
          <div class="metric-title">累计 Token</div>
          <div class="metric-value">{{ formatNumber(store.current?.total_tokens) }}</div>
        </el-card>
      </div>
      <div class="flex-1">
        <el-card shadow="never">
          <div class="metric-title">累计成本</div>
          <div class="metric-value">{{ formatCurrency(store.current?.total_cost) }}</div>
        </el-card>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>各用户累计 Token</template>
      <el-table :data="userSummaries" v-loading="store.loading">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="role" label="角色" width="120" />
        <el-table-column prop="org_id" label="组织 ID" min-width="240" />
        <el-table-column label="总 Token" min-width="140">
          <template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template>
        </el-table-column>
        <el-table-column label="请求次数" min-width="120">
          <template #default="{ row }">{{ formatNumber(row.request_count) }}</template>
        </el-table-column>
        <el-table-column label="累计成本" min-width="140">
          <template #default="{ row }">{{ formatCurrency(row.total_cost) }}</template>
        </el-table-column>
        <el-table-column label="最近一次使用" min-width="180">
          <template #default="{ row }">{{ formatTime(row.last_ledger_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>聚合趋势</template>
      <el-table :data="store.current?.buckets || []" v-loading="store.loading">
        <el-table-column prop="bucket" label="时间桶" min-width="160" />
        <el-table-column prop="request_count" label="请求数" width="120" />
        <el-table-column prop="total_tokens" label="总 Token" width="140" />
        <el-table-column prop="total_cost" label="总成本" width="140" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>流水明细</template>
      <el-table :data="store.current?.ledger_items || []" size="small" v-loading="store.loading">
        <el-table-column prop="created_at" label="时间" min-width="180" />
        <el-table-column prop="user_id" label="用户 ID" min-width="220" />
        <el-table-column prop="model_key" label="模型" min-width="180" />
        <el-table-column prop="product_line" label="产品线" width="140" />
        <el-table-column prop="total_tokens" label="Token" width="120" />
        <el-table-column prop="cost_amount" label="成本" width="120" />
        <el-table-column prop="trace_id" label="Trace ID" min-width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>

.hero h2 {
  margin: 0;
  color: #1b3a5c;
}

.hero p {
  margin: 6px 0 0;
  color: #64748b;
}

.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.metric-title {
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  margin-top: 8px;
  font-size: 30px;
  font-weight: 700;
  color: #1b3a5c;
}
</style>
