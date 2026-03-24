<script setup lang="ts">
import type { ModelDrilldown, ProductLineDrilldown, TaskDrilldown } from "@/types/analytics.types";

interface Props {
  visible: boolean;
  title: string;
  loading: boolean;
  productLineDrilldown: ProductLineDrilldown | null;
  modelDrilldown: ModelDrilldown | null;
  taskDrilldown: TaskDrilldown | null;
}

interface Emits {
  (e: "update:visible", value: boolean): void;
  (e: "product-line-tasks"): void;
  (e: "product-line-results"): void;
  (e: "model-results"): void;
  (e: "task-detail", taskId: string): void;
  (e: "result-detail", taskId: string): void;
  (e: "task-drilldown", taskId: string): void;
  (e: "task-related-list", taskIds: string[]): void;
  (e: "task-product-list", productLine: string): void;
  (e: "task-result-list", taskId: string): void;
  (e: "task-stability-detail", taskId: string): void;
}

defineProps<Props>();
defineEmits<Emits>();
</script>

<template>
  <el-drawer :model-value="visible" size="420px" :title="title" @update:model-value="$emit('update:visible', $event)">
    <div class="drilldown-stack" v-loading="loading">
      <template v-if="taskDrilldown">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务 ID">{{ taskDrilldown.task_id }}</el-descriptions-item>
          <el-descriptions-item label="产品线">{{ taskDrilldown.product_line }}</el-descriptions-item>
          <el-descriptions-item label="规格">{{ taskDrilldown.spec_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ taskDrilldown.status }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ taskDrilldown.priority }}</el-descriptions-item>
          <el-descriptions-item label="图像数">{{ taskDrilldown.image_count }}</el-descriptions-item>
          <el-descriptions-item label="结论">{{ taskDrilldown.verdict || "暂无" }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ taskDrilldown.llm_model || "暂无" }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ taskDrilldown.latency_ms ?? "-" }} ms</el-descriptions-item>
          <el-descriptions-item label="Tokens">{{ taskDrilldown.tokens_used }}</el-descriptions-item>
          <el-descriptions-item label="累计成本">￥{{ taskDrilldown.total_cost.toFixed(4) }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">{{ taskDrilldown.risk_level || "暂无" }}</el-descriptions-item>
          <el-descriptions-item label="开启告警">{{ taskDrilldown.open_alert_count }}</el-descriptions-item>
        </el-descriptions>
        <div class="drawer-actions">
          <el-button type="primary" @click="$emit('task-detail', taskDrilldown.task_id)">任务详情</el-button>
          <el-button v-if="taskDrilldown.has_result" plain @click="$emit('task-result-list', taskDrilldown.task_id)">关联结果</el-button>
          <el-button v-if="taskDrilldown.risk_level" plain @click="$emit('task-stability-detail', taskDrilldown.task_id)">稳定性详情</el-button>
          <el-button plain @click="$emit('task-product-list', taskDrilldown.product_line)">同产品线任务</el-button>
          <el-button plain @click="$emit('task-related-list', taskDrilldown.related_task_ids)">相关任务列表</el-button>
        </div>
        <el-card shadow="never">
          <template #header>任务判断摘要</template>
          <div class="drawer-line"><span>是否产出结果</span><strong>{{ taskDrilldown.has_result ? "是" : "否" }}</strong></div>
          <div class="drawer-line"><span>总分</span><strong>{{ taskDrilldown.overall_score != null ? taskDrilldown.overall_score.toFixed(4) : "-" }}</strong></div>
          <div class="drawer-line"><span>幻觉标记</span><strong>{{ taskDrilldown.hallucination_flag ? "是" : "否" }}</strong></div>
          <div class="drawer-line"><span>风险分</span><strong>{{ taskDrilldown.risk_score != null ? taskDrilldown.risk_score.toFixed(2) : "-" }}</strong></div>
        </el-card>
        <el-card shadow="never">
          <template #header>最近告警</template>
          <div v-if="taskDrilldown.alert_summaries.length === 0" class="empty-copy">暂无告警</div>
          <div v-for="item in taskDrilldown.alert_summaries" :key="`${item.title}-${item.created_at}`" class="alert-summary">
            <strong>{{ item.severity.toUpperCase() }}</strong>
            <span>{{ item.title }}</span>
            <small>{{ item.status }} · {{ new Date(item.created_at).toLocaleString() }}</small>
          </div>
        </el-card>
      </template>
      <template v-else-if="productLineDrilldown">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="产品线">{{ productLineDrilldown.product_line }}</el-descriptions-item>
          <el-descriptions-item label="任务总量">{{ productLineDrilldown.total_tasks }}</el-descriptions-item>
          <el-descriptions-item label="结果总量">{{ productLineDrilldown.total_results }}</el-descriptions-item>
          <el-descriptions-item label="通过率">{{ (productLineDrilldown.pass_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="幻觉率">{{ (productLineDrilldown.hallucination_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="平均耗时">{{ productLineDrilldown.avg_latency_ms.toFixed(0) }} ms</el-descriptions-item>
          <el-descriptions-item label="累计成本">￥{{ productLineDrilldown.total_cost.toFixed(4) }}</el-descriptions-item>
        </el-descriptions>
        <div class="drawer-actions">
          <el-button type="primary" @click="$emit('product-line-tasks')">查看任务列表</el-button>
          <el-button plain @click="$emit('product-line-results')">查看结果列表</el-button>
        </div>
        <el-card shadow="never">
          <template #header>结论分布</template>
          <div v-for="item in productLineDrilldown.verdict_distribution" :key="item.name" class="drawer-line">
            <span>{{ item.name }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </el-card>
        <el-card shadow="never">
          <template #header>最近任务</template>
          <el-table :data="productLineDrilldown.recent_tasks" size="small" empty-text="暂无任务">
            <el-table-column prop="task_id" label="任务" min-width="180" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="spec_id" label="规格" width="120" />
              <el-table-column label="操作" width="90">
                <template #default="scope">
                  <el-button link type="primary" @click="$emit('task-drilldown', scope.row.task_id)">统计</el-button>
                </template>
              </el-table-column>
            </el-table>
        </el-card>
      </template>
      <template v-else-if="modelDrilldown">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="模型">{{ modelDrilldown.model_key }}</el-descriptions-item>
          <el-descriptions-item label="结果数">{{ modelDrilldown.result_count }}</el-descriptions-item>
          <el-descriptions-item label="通过率">{{ (modelDrilldown.pass_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="幻觉率">{{ (modelDrilldown.hallucination_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="平均 Tokens">{{ modelDrilldown.avg_tokens.toFixed(1) }}</el-descriptions-item>
          <el-descriptions-item label="平均耗时">{{ modelDrilldown.avg_latency_ms.toFixed(0) }} ms</el-descriptions-item>
          <el-descriptions-item label="累计成本">￥{{ modelDrilldown.total_cost.toFixed(4) }}</el-descriptions-item>
        </el-descriptions>
        <div class="drawer-actions">
          <el-button type="primary" @click="$emit('model-results')">查看结果列表</el-button>
        </div>
        <el-card shadow="never">
          <template #header>产品线分布</template>
          <div v-for="item in modelDrilldown.product_line_distribution" :key="item.name" class="drawer-line">
            <span>{{ item.name }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </el-card>
        <el-card shadow="never">
          <template #header>最近结果</template>
          <el-table :data="modelDrilldown.recent_results" size="small" empty-text="暂无结果">
            <el-table-column prop="result_id" label="结果" min-width="160" />
            <el-table-column prop="product_line" label="产品线" width="120" />
            <el-table-column prop="verdict" label="结论" width="90" />
            <el-table-column label="操作" width="90">
              <template #default="scope">
                <el-button link type="primary" @click="$emit('result-detail', scope.row.task_id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </template>
      <template v-else>
        <el-alert title="暂无钻取数据，请调整时间范围或先产生分析结果。" type="info" :closable="false" />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drilldown-stack { display: grid; gap: 12px; }
.drawer-actions { display: flex; gap: 12px; }
.drawer-line { display: flex; justify-content: space-between; padding: 6px 0; color: #334155; }
.empty-copy { color: #64748b; }
.alert-summary { display: grid; gap: 4px; padding: 8px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.18); }
.alert-summary:last-child { border-bottom: 0; }
</style>
