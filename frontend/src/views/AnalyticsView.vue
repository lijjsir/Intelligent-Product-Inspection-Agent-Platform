<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useAlertStore } from "@/stores/alert.store";
import { useRouter } from "vue-router";

const store = useAnalyticsStore();
const alertStore = useAlertStore();
const router = useRouter();
const dateRange = ref<[Date, Date] | null>(null);

const redRate = computed(() => {
  if (!alertStore.items.length) return 0;
  const red = alertStore.items.filter((item) => String(item.severity).toLowerCase() === "critical").length;
  return red / alertStore.items.length;
});

const avgRiskScore = computed(() => {
  if (!store.overview) return 0;
  // 临时估算值：用于占位，待后端补充真实聚合字段。
  return Math.min(100, Math.max(0, store.overview.risk_yellow_rate * 100));
});

onMounted(async () => {
  await Promise.all([
    store.fetchOverview(),
    alertStore.fetchAlerts({ page: 1, page_size: 100 }),
  ]);
});
</script>

<template>
  <div class="page-container">
    <div class="header">
      <h2 class="title">分析中心</h2>
      <p class="subtitle">时间过滤、趋势分析与模型对比</p>
    </div>

    <el-alert
      v-if="store.error"
      :title="store.error"
      type="warning"
      :closable="false"
      class="mb-4"
    />

    <el-card shadow="never" class="mb-4">
      <div class="filter-row">
        <span class="filter-label">时间范围</span>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          unlink-panels
        />
        <el-button type="primary" plain disabled>应用筛选（后端联调中）</el-button>
      </div>
    </el-card>

    <el-row :gutter="20" v-if="store.overview" class="mb-4">
      <el-col :span="8">
        <el-card shadow="never" class="metric-card cursor-pointer" @click="router.push('/tasks')">
          <div class="metric-title">总任务</div>
          <div class="metric-value">{{ store.overview.total_tasks }}</div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">通过率</div>
          <div class="metric-value text-success">
            {{ (store.overview.pass_rate * 100).toFixed(1) }}%
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">幻觉率</div>
          <div class="metric-value text-warning">
            {{ (store.overview.hallucination_rate * 100).toFixed(1) }}%
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">平均风险分</div>
          <div class="metric-value text-warning">
            {{ avgRiskScore.toFixed(1) }}
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">RED 级率</div>
          <div class="metric-value text-danger">
            {{ (redRate * 100).toFixed(1) }}%
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">平均耗时</div>
          <div class="metric-value text-warning">
            --
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>通过率趋势</template>
          <div class="chart-placeholder">
            <el-empty description="支持按天/周聚合，多产品线叠加（联调中）" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>幻觉率趋势</template>
          <div class="chart-placeholder">
            <el-empty description="折线 + 异常点标注（联调中）" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>风险分布变化</template>
          <div class="chart-placeholder">
            <el-empty description="风险等级占比时序变化（联调中）" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <template #header>模型性能对比</template>
          <div class="chart-placeholder">
            <el-empty description="多模型精确率/召回率/幻觉率对比（联调中）" />
          </div>
        </el-card>
      </el-col>
    </el-row>
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

.title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.mb-4 {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-label {
  color: #475569;
  font-size: 14px;
}

.metric-card {
  text-align: center;
}

.cursor-pointer {
  cursor: pointer;
}

.metric-title {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 32px;
  font-weight: bold;
  color: #111827;
}

.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }

.chart-card {
  margin-bottom: 16px;
}

.chart-placeholder {
  min-height: 260px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f9fafb;
  border-radius: 8px;
}
</style>
