<script setup lang="ts">
import { onMounted, reactive } from "vue";
import { useBillingStore } from "@/stores/billing.store";

const store = useBillingStore();
const filters = reactive({
  granularity: "day" as "day" | "week" | "month",
  model_key: "",
  product_line: "",
});

async function reload() {
  await store.fetchSummary({
    granularity: filters.granularity,
    model_key: filters.model_key || undefined,
    product_line: filters.product_line || undefined,
  });
}

onMounted(() => {
  reload();
});
</script>

<template>
  <div class="page-container">
    <div class="hero">
      <div>
        <h2>Token 成本台账</h2>
        <p>按模型、产品线和时间粒度查看成本与 Token 消耗。</p>
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

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <div class="metric-title">总 Token</div>
          <div class="metric-value">{{ store.current?.total_tokens ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <div class="metric-title">总成本</div>
          <div class="metric-value">￥ {{ (store.current?.total_cost ?? 0).toFixed(4) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>聚合趋势</template>
      <el-table :data="store.current?.buckets || []" v-loading="store.loading">
        <el-table-column prop="bucket" label="时间桶" />
        <el-table-column prop="request_count" label="请求数" />
        <el-table-column prop="total_tokens" label="总 Token" />
        <el-table-column prop="total_cost" label="总成本" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>流水明细</template>
      <el-table :data="store.current?.ledger_items || []" size="small" v-loading="store.loading">
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="model_key" label="模型" min-width="180" />
        <el-table-column prop="product_line" label="产品线" width="140" />
        <el-table-column prop="total_tokens" label="Token" width="120" />
        <el-table-column prop="cost_amount" label="成本" width="120" />
        <el-table-column prop="trace_id" label="Trace ID" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: grid; gap: 16px; }
.hero h2 { margin: 0; color: #1b3a5c; }
.hero p { margin: 6px 0 0; color: #64748b; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.metric-title { color: #64748b; font-size: 13px; }
.metric-value { margin-top: 8px; font-size: 30px; font-weight: 700; color: #1b3a5c; }
</style>

