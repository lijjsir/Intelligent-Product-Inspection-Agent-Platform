<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import DefectImageViewer from "@/components/business/result/DefectImageViewer.vue";
import FeedbackWidget from "@/components/business/result/FeedbackWidget.vue";
import { useResultStore } from "@/stores/result.store";
import { useTaskStore } from "@/stores/task.store";

const route = useRoute();
const router = useRouter();
const store = useResultStore();
const taskStore = useTaskStore();

const loading = ref(true);
const taskId = route.params.id as string;

function resolveTaskImageUrl(value?: string | null) {
  const url = String(value || "").trim();
  if (!url) return "";
  if (url.startsWith("data:")) return url;
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/uploads/")) return url;
  if (url.startsWith("uploads/")) return `/${url}`;
  return url;
}

const taskImages = computed(() => {
  return (taskStore.current?.image_urls || []).map((item) => resolveTaskImageUrl(item)).filter(Boolean);
});

const getVerdictType = (verdict: string) => {
  const map: Record<string, "info"|"primary"|"success"|"danger"|"warning"> = {
    pass: "success",
    fail: "danger",
    uncertain: "warning",
    manual_required: "info",
  };
  return map[verdict] || "info";
};

onMounted(async () => {
  try {
    await Promise.all([
      store.fetchByTask(taskId),
      taskStore.fetchTask(taskId)
    ]);
  } catch (err: any) {
    if (err.response?.status === 404) {
      ElMessage.warning("该任务暂无检测结果或不存在");
    } else {
      ElMessage.error("获取检测结果失败");
    }
  } finally {
    loading.value = false;
  }
});

function goBack() {
  router.back();
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" class="mb-4">
        &larr; 返回
      </el-button>
      <div v-if="store.current" class="title-area">
        <h2 class="title">分析结果大盘</h2>
        <el-tag :type="getVerdictType(store.current.verdict)" size="large" class="ml-4">
          判定结论: {{ store.current.verdict.toUpperCase() }}
        </el-tag>
      </div>
    </div>

    <div v-if="store.current" class="content">
      <el-row :gutter="20">
        <!-- 侧边摘要面板 -->
        <el-col :span="8">
          <el-card shadow="never" class="info-card">
            <template #header>结论摘要</template>
            <el-descriptions :column="1" border size="large">
              <el-descriptions-item label="任务编号">{{ store.current.task_id }}</el-descriptions-item>
              <el-descriptions-item label="检出异常分数">
                <span class="text-xl font-bold">{{ (store.current.overall_score * 100).toFixed(1) }}</span> 分
              </el-descriptions-item>
              <el-descriptions-item label="模型引擎">{{ store.current.llm_model }}</el-descriptions-item>
              <el-descriptions-item label="Prompt">{{ store.current.prompt_version }}</el-descriptions-item>
              <el-descriptions-item label="检测耗费时间">{{ store.current.latency_ms || '-' }} ms</el-descriptions-item>
              <el-descriptions-item label="Tokens">消耗 {{ store.current.tokens_used || '-' }} Token</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
        
        <!-- 主体数据面板 -->
        <el-col :span="16">
          <!-- 缺陷图像可视化 -->
          <el-card v-if="taskImages.length > 0 && store.current.defects && store.current.defects.length > 0" shadow="never" class="mb-4">
            <template #header>缺陷可视化标注</template>
            <DefectImageViewer
              :image-url="taskImages[0]"
              :defects="store.current.defects"
              :loading="loading"
              :normalized="true"
            />
          </el-card>

          <el-card shadow="never" class="mb-4">
            <template #header>缺陷与推理明细</template>
            <el-tabs type="border-card">
              <el-tab-pane label="缺陷坐标清单 (Defects)">
                <el-empty v-if="!store.current.defects || store.current.defects.length === 0" description="未检出明确缺陷包裹" />
                <div v-else>
                  <el-table :data="store.current.defects" stripe style="width: 100%">
                    <el-table-column type="index" label="#" width="50" />
                    <el-table-column prop="type" label="缺陷类型" width="120" />
                    <el-table-column prop="confidence" label="置信度" width="100">
                      <template #default="{ row }">
                        <el-tag :type="row.confidence > 0.8 ? 'danger' : row.confidence > 0.5 ? 'warning' : 'info'">
                          {{ (row.confidence * 100).toFixed(1) }}%
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="bbox" label="坐标框 (x, y, w, h)" width="200">
                      <template #default="{ row }">
                        <code>[{{ row.bbox.map((v: number) => v.toFixed(3)).join(', ') }}]</code>
                      </template>
                    </el-table-column>
                    <el-table-column prop="description" label="描述" />
                  </el-table>
                </div>
              </el-tab-pane>
              <el-tab-pane label="推理还原链路 (Reasoning)">
                <el-empty v-if="!store.current.reasoning_chain" description="模型未输出推理链路" />
                <pre v-else class="json-viewer">{{ JSON.stringify(store.current.reasoning_chain, null, 2) }}</pre>
              </el-tab-pane>
              <el-tab-pane label="原文引证来源 (Citations)">
                <el-empty v-if="!store.current.citations" description="未使用知识库引证" />
                <pre v-else class="json-viewer">{{ JSON.stringify(store.current.citations, null, 2) }}</pre>
              </el-tab-pane>
            </el-tabs>
          </el-card>

          <!-- 人工复核 -->
          <el-card shadow="never">
            <template #header>人工复核记录</template>
            <div v-if="store.current.reviewed_by">
              <p>专家 ({{ store.current.reviewed_by }}) 于 {{ new Date(store.current.reviewed_at!).toLocaleString() }} 进行了覆写。</p>
              <p>批注: {{ store.current.review_note }}</p>
            </div>
            <el-empty v-else description="暂无人工专家覆写此结果记录" :image-size="60" />
          </el-card>

          <el-card shadow="never" class="mb-4">
            <template #header>用户反馈</template>
            <FeedbackWidget :result-id="store.current.id" />
          </el-card>
        </el-col>
      </el-row>
    </div>
    
    <div v-else-if="!loading" class="empty-state">
      <el-empty description="无法获取该任务的结果报告" />
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

.text-xl {
  font-size: 1.25rem;
  line-height: 1.75rem;
  color: #e6a23c;
}

.font-bold {
  font-weight: 700;
}

.json-viewer {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 8px;
  overflow: auto;
  max-height: 500px;
  font-family: Consolas, Monaco, monospace;
}
</style>
