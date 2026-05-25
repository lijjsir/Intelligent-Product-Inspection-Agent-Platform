<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import DefectImageViewer from "@/components/business/result/DefectImageViewer.vue";
import FeedbackWidget from "@/components/business/result/FeedbackWidget.vue";
import { resultApi, type ReviewSubmit } from "@/api/result.api";
import { usePermission } from "@/composables/usePermission";
import { useResultStore } from "@/stores/result.store";
import { useTaskStore } from "@/stores/task.store";

const route = useRoute();
const router = useRouter();
const store = useResultStore();
const taskStore = useTaskStore();
const { hasRole } = usePermission();

const loading = ref(true);
const reviewing = ref(false);
const reviewForm = ref<ReviewSubmit>({ verdict: "", note: "" });
const canReview = computed(() => hasRole(["expert"]));
const currentTaskId = computed(() => String(route.params.id || ""));
const currentResult = computed(() => store.current?.task_id === currentTaskId.value ? store.current : null);
const currentTask = computed(() => taskStore.current?.id === currentTaskId.value ? taskStore.current : null);

const verdictOptions = [
  { label: "合格 (Pass)", value: "pass" },
  { label: "不合格 (Fail)", value: "fail" },
  { label: "需人工复核 (Manual Required)", value: "manual_required" },
];

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
  return (currentTask.value?.image_urls || []).map((item) => resolveTaskImageUrl(item)).filter(Boolean);
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

async function loadResultDetail(taskId: string) {
  loading.value = true;
  if (store.current?.task_id !== taskId) store.current = null;
  if (taskStore.current?.id !== taskId) taskStore.current = null;
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
}

watch(currentTaskId, (id) => {
  if (id) void loadResultDetail(id);
}, { immediate: true });

function goBack() {
  router.back();
}

const sampleLabels = computed(() => {
  const items = currentTask.value?.image_items;
  if (!items || !items.length) return {} as Record<number, string>;
  const map: Record<number, string> = {};
  for (const item of items) {
    if (item.sample_number != null && !(item.index in map)) {
      map[item.index] = `样品${item.sample_number}`;
    }
  }
  return map;
});

function sampleLabel(imageIndex?: number | null): string {
  if (imageIndex == null) return "";
  return sampleLabels.value[imageIndex] || "";
}

const selectedImageIndex = ref(0);
const defects = computed(() => currentResult.value?.defects || []);
const hasDefectImageIndex = computed(() => defects.value.some((item) => item.image_index != null));
const imageDefectGroups = computed(() => {
  return taskImages.value.map((url, index) => {
    const defectsForImage = defects.value.filter((item) => item.image_index === index);
    return {
      index,
      url,
      sample: sampleLabel(index),
      defects: defectsForImage,
      defectCount: defectsForImage.length,
      isError: defectsForImage.length > 0,
    };
  });
});
const erroredImageGroups = computed(() => imageDefectGroups.value.filter((item) => item.isError));
const selectedImageGroup = computed(
  () => imageDefectGroups.value.find((item) => item.index === selectedImageIndex.value) || imageDefectGroups.value[0] || null,
);
const viewerDefects = computed(() => {
  if (!hasDefectImageIndex.value) return defects.value;
  return selectedImageGroup.value?.defects || [];
});

watch(
  imageDefectGroups,
  (groups) => {
    if (!groups.length) {
      selectedImageIndex.value = 0;
      return;
    }
    const activeGroup = groups.find((item) => item.index === selectedImageIndex.value);
    if (activeGroup) return;
    selectedImageIndex.value = (groups.find((item) => item.isError) || groups[0]).index;
  },
  { immediate: true },
);

async function submitReview() {
  if (!currentResult.value || !reviewForm.value.verdict) return;
  reviewing.value = true;
  try {
    const { data } = await resultApi.review(currentResult.value.id, reviewForm.value);
    if (store.current) {
      store.current.verdict = data.data.verdict;
      store.current.reviewed_by = data.data.reviewed_by;
      store.current.reviewed_at = data.data.reviewed_at;
      store.current.review_note = data.data.review_note;
    }
    ElMessage.success("复核已提交");
  } catch (error) {
    ElMessage.error("复核提交失败");
    console.error(error);
  } finally {
    reviewing.value = false;
  }
}
</script>

<template>
  <div class="flex flex-col gap-5" v-loading="loading">
    <div>
      <el-button @click="goBack" class="mb-4">
        &larr; 返回
      </el-button>
      <div v-if="currentResult" class="title-area">
        <h2 class="text-2xl font-bold text-zinc-900">分析结果大盘</h2>
        <el-tag :type="getVerdictType(store.current.verdict)" size="large" class="ml-4">
          判定结论: {{ store.current.verdict.toUpperCase() }}
        </el-tag>
      </div>
    </div>

    <div v-if="currentResult" class="content">
      <div class="flex gap-5">
        <!-- 侧边摘要面板 -->
        <div>
          <el-card shadow="never" class="info-card">
            <template #header>结论摘要</template>
            <el-descriptions :column="1" size="large">
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
        </div>
        
        <!-- 主体数据面板 -->
        <div>
          <!-- 缺陷图像可视化 -->
          <el-card v-if="taskImages.length > 0 && defects.length > 0" shadow="never" class="mb-4">
            <template #header>
              <div class="viewer-header">
                <span>缺陷可视化标注</span>
                <span class="viewer-header-meta">共 {{ taskImages.length }} 张图，问题图 {{ erroredImageGroups.length }} 张</span>
              </div>
            </template>
            <div v-if="imageDefectGroups.length > 1" class="image-group-list">
              <button
                v-for="group in imageDefectGroups"
                :key="group.index"
                type="button"
                class="image-group-chip"
                :class="{ active: selectedImageGroup?.index === group.index, error: group.isError }"
                @click="selectedImageIndex = group.index"
              >
                <span>{{ group.sample || `图${group.index + 1}` }}</span>
                <strong>{{ group.isError ? `${group.defectCount} 处问题` : "未见异常" }}</strong>
              </button>
            </div>
            <el-alert
              v-if="taskImages.length > 1 && !hasDefectImageIndex"
              type="warning"
              :closable="false"
              class="mb-3"
              title="当前结果未返回按图片定位信息，暂时只能展示总体缺陷。"
            />
            <DefectImageViewer
              :image-url="selectedImageGroup?.url || taskImages[0]"
              :defects="viewerDefects"
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
                  <div v-if="erroredImageGroups.length > 0" class="error-image-summary">
                    <span class="error-image-summary-label">问题图片</span>
                    <el-tag
                      v-for="group in erroredImageGroups"
                      :key="group.index"
                      type="danger"
                      effect="plain"
                      round
                    >
                      {{ group.sample || `图${group.index + 1}` }} · {{ group.defectCount }} 处
                    </el-tag>
                  </div>
                  <el-table :data="store.current.defects" stripe style="width: 100%">
                    <el-table-column type="index" label="#" width="50" />
                    <el-table-column label="样品" width="80">
                      <template #default="{ row }">
                        <el-tag v-if="sampleLabel(row.image_index)" type="danger" size="small">{{ sampleLabel(row.image_index) }}</el-tag>
                        <span v-else class="text-gray-400">-</span>
                      </template>
                    </el-table-column>
                    <el-table-column prop="image_index" label="图片序号" width="90">
                      <template #default="{ row }">
                        <el-tag v-if="row.image_index != null" size="small">图{{ row.image_index + 1 }}</el-tag>
                        <span v-else class="text-gray-400">-</span>
                      </template>
                    </el-table-column>
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
              <p>判定: <el-tag :type="getVerdictType(store.current.verdict)" size="small">{{ store.current.verdict.toUpperCase() }}</el-tag></p>
              <p v-if="store.current.review_note">批注: {{ store.current.review_note }}</p>
            </div>
            <div v-else-if="canReview && store.current" class="review-form">
              <el-form label-position="top">
                <el-form-item label="复核判定">
                  <el-select v-model="reviewForm.verdict" placeholder="请选择复核结论" class="!w-full">
                    <el-option v-for="opt in verdictOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </el-form-item>
                <el-form-item label="复核备注">
                  <el-input v-model="reviewForm.note" type="textarea" :rows="2" placeholder="可选：说明复核理由" />
                </el-form-item>
                <el-button type="primary" :loading="reviewing" :disabled="!reviewForm.verdict" @click="submitReview">
                  提交复核
                </el-button>
              </el-form>
            </div>
            <el-empty v-else description="暂无人工专家覆写此结果记录" :image-size="60" />
          </el-card>

          <el-card shadow="never" class="mb-4">
            <template #header>用户反馈</template>
            <FeedbackWidget :result-id="store.current.id" />
          </el-card>
        </div>
      </div>
    </div>
    
    <div v-else-if="!loading" class="empty-state">
      <el-empty description="无法获取该任务的结果报告" />
    </div>
  </div>
</template>

<style scoped>


.title-area {
  display: flex;
  align-items: center;
}


.ml-4 {
  margin-left: 16px;
}


.text-xl {
  font-size: 1.25rem;
  line-height: 1.75rem;
  color: #e6a23c;
}

.font-bold {
  font-weight: 700;
}

.viewer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.viewer-header-meta {
  font-size: 12px;
  color: #6b7280;
}

.image-group-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.image-group-chip {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  text-align: left;
  transition: all 0.2s ease;
}

.image-group-chip strong {
  font-size: 12px;
}

.image-group-chip.error {
  border-color: rgba(220, 38, 38, 0.24);
  background: rgba(254, 242, 242, 0.88);
  color: #991b1b;
}

.image-group-chip.active {
  border-color: #ea580c;
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.12);
  transform: translateY(-1px);
}

.error-image-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.error-image-summary-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
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
