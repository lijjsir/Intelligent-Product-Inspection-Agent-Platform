<script setup lang="ts">
import { onMounted } from "vue";
import { useAnalyticsStore } from "@/stores/analytics.store";
import { useRouter } from "vue-router";

const store = useAnalyticsStore();
const router = useRouter();

onMounted(() => {
  store.fetchOverview();
});
</script>

<template>
  <div class="page-container">
    <div class="header">
      <h2 class="title">数据与统计看板</h2>
      <p class="subtitle">全盘把握智能化质检进度及安全水位</p>
    </div>

    <!-- 数据核心卡片群 -->
    <el-row :gutter="20" v-if="store.overview" class="mb-4">
      <el-col :span="6">
        <el-card shadow="never" class="metric-card cursor-pointer" @click="router.push('/tasks')">
          <div class="metric-title">系统累计流转任务</div>
          <div class="metric-value">{{ store.overview.total_tasks }}</div>
          <div class="metric-footer">包括各状态的历史质检任务</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">智能判定期望通过率</div>
          <div class="metric-value text-success">
            {{ (store.overview.pass_rate * 100).toFixed(1) }}%
          </div>
          <div class="metric-footer">Verdict 为 Pass 的占比</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-title">评估底盘置信告警率</div>
          <div class="metric-value text-warning">
            {{ (store.overview.risk_yellow_rate * 100).toFixed(1) }}%
          </div>
          <div class="metric-footer">处于中等波动水位的测算记录</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="never" class="metric-card cursor-pointer" @click="router.push('/alerts')">
          <div class="metric-title">当前未处理核心告警</div>
          <div class="metric-value text-danger">{{ store.overview.total_alerts }}</div>
          <div class="metric-footer">急需组织内专家复核并消除</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表预留空洞区 -->
    <el-card shadow="never">
      <template #header>近期检测与异常水位趋势（Demo）</template>
      <div class="echart-placeholder">
        <el-empty description="ECharts 后端聚合序列正在联调中，敬请期待下一迭代" />
      </div>
    </el-card>
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

.metric-card {
  text-align: center;
  transition: all 0.2s ease;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
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
  margin-bottom: 8px;
}

.metric-footer {
  font-size: 12px;
  color: #9ca3af;
}

.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }

.echart-placeholder {
  min-height: 350px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f9fafb;
  border-radius: 8px;
}
</style>
