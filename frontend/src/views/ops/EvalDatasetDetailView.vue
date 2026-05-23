<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { useDatasetStore } from "@/stores/dataset.store";
import { useEvalDatasetStore } from "@/stores/evalDataset.store";
import type { DatasetSample, DatasetSampleType } from "@/types/dataset.types";

const route = useRoute();
const router = useRouter();
const evalStore = useEvalDatasetStore();
const datasetStore = useDatasetStore();

const resourceId = computed(() => String(route.params.id || ""));
const sampleQuery = reactive({
  page: 1,
  size: 12,
  sample_type: "" as DatasetSampleType | "",
});
const appendDrawerOpen = ref(false);
const appendLoading = ref(false);
const previewVisible = ref(false);
const previewPayload = ref<any>(null);
const sourceSampleQuery = reactive({
  page: 1,
  size: 12,
  sample_type: "" as DatasetSampleType | "",
});
const selectedSamples = ref<DatasetSample[]>([]);
const selectedSampleIds = computed(() => selectedSamples.value.map((item) => item.id));

async function loadDetail() {
  if (!resourceId.value) return;
  await evalStore.fetchOne(resourceId.value);
}

async function loadSamples() {
  if (!resourceId.value) return;
  await evalStore.fetchSamples(resourceId.value, {
    page: sampleQuery.page,
    size: sampleQuery.size,
    sample_type: sampleQuery.sample_type || undefined,
  });
}

async function loadSourceSamples() {
  if (!evalStore.current?.source_dataset_id) return;
  await datasetStore.fetchSamples(evalStore.current.source_dataset_id, {
    page: sourceSampleQuery.page,
    size: sourceSampleQuery.size,
    sample_type: sourceSampleQuery.sample_type || undefined,
  });
}

function handleBack() {
  router.push("/ops/data/eval-sets");
}

function previewSample(row: any) {
  previewPayload.value = row;
  previewVisible.value = true;
}

async function removeItem(row: any) {
  await ElMessageBox.confirm(`确定移除样本「${row.sample_name || row.id}」吗？`, "移除样本", {
    type: "warning",
    confirmButtonText: "移除",
    cancelButtonText: "取消",
  });
  await evalStore.removeSampleItem(resourceId.value, row.id);
  ElMessage.success("样本已移除");
  await Promise.all([loadDetail(), loadSamples()]);
}

function toggleAppendSample(sample: DatasetSample) {
  const exists = selectedSamples.value.some((item) => item.id === sample.id);
  if (exists) {
    selectedSamples.value = selectedSamples.value.filter((item) => item.id !== sample.id);
    return;
  }
  selectedSamples.value = [...selectedSamples.value, sample];
}

function openAppendDrawer() {
  selectedSamples.value = [];
  sourceSampleQuery.page = 1;
  appendDrawerOpen.value = true;
  loadSourceSamples();
}

async function submitAppend() {
  if (!selectedSampleIds.value.length) {
    ElMessage.warning("至少选择一个样本");
    return;
  }
  appendLoading.value = true;
  try {
    await evalStore.appendSamples(resourceId.value, { sample_ids: selectedSampleIds.value });
    ElMessage.success("样本已追加");
    appendDrawerOpen.value = false;
    await Promise.all([loadDetail(), loadSamples()]);
  } finally {
    appendLoading.value = false;
  }
}

onMounted(async () => {
  await loadDetail();
  await Promise.all([loadSamples(), loadSourceSamples()]);
});

watch(
  () => route.params.id,
  async () => {
    await loadDetail();
    await Promise.all([loadSamples(), loadSourceSamples()]);
  },
);
</script>

<template>
  <div class="detail-page">
    <section class="detail-topbar">
      <div class="flex flex-col gap-2">
        <el-button link type="primary" @click="handleBack">返回评测集列表</el-button>
        <h2>{{ evalStore.current?.name || "评测集详情" }}</h2>
        <p>{{ evalStore.current?.description || "查看评测集快照样本，并继续增删样本。" }}</p>
      </div>
      <div class="detail-tags">
        <el-tag>来源数据集：{{ evalStore.current?.source_dataset_id || "-" }}</el-tag>
        <el-tag type="success">样本数：{{ evalStore.current?.sample_count || 0 }}</el-tag>
      </div>
    </section>

    <section class="detail-grid">
      <article class="overview-card">
        <h3>评测集概览</h3>
        <div class="overview-metrics">
          <div>
            <span>总样本数</span>
            <strong>{{ evalStore.current?.sample_count || 0 }}</strong>
          </div>
          <div>
            <span>来源数据集</span>
            <strong class="break-all">{{ evalStore.current?.source_dataset_id || "-" }}</strong>
          </div>
          <div>
            <span>状态</span>
            <strong>{{ evalStore.current?.status || "draft" }}</strong>
          </div>
        </div>
        <el-alert
          class="mt-4"
          type="info"
          :closable="false"
          title="该评测集为固定快照，源样本后续删除不会影响这里的可预览内容。"
        />
      </article>

      <article class="overview-card">
        <div class="section-head">
          <h3>快照预览</h3>
          <el-button type="primary" @click="openAppendDrawer">追加样本</el-button>
        </div>
        <div class="preview-grid" v-if="(evalStore.current?.samples_preview || []).length">
          <div v-for="item in evalStore.current?.samples_preview || []" :key="item.id" class="preview-card">
            <img v-if="item.sample_type === 'image' && item.file_url" :src="item.file_url" :alt="item.sample_name || item.id" />
            <div v-else class="text-preview">{{ item.preview_text || item.text_content || "无预览内容" }}</div>
            <strong>{{ item.sample_name || item.dataset_sample_id || item.id }}</strong>
          </div>
        </div>
        <el-empty v-else description="暂无快照预览" />
      </article>
    </section>

    <section class="card-surface p-4">
      <div class="section-head">
        <h3>评测集样本</h3>
        <div class="flex gap-3">
          <el-select v-model="sampleQuery.sample_type" clearable placeholder="样本类型" class="!w-[160px]" @change="loadSamples">
            <el-option label="图片" value="image" />
            <el-option label="文本" value="text" />
          </el-select>
          <el-button @click="loadSamples">刷新</el-button>
        </div>
      </div>

      <el-table :data="evalStore.detailItems" v-loading="evalStore.detailLoading" class="mt-4">
        <el-table-column prop="sample_name" label="样本" min-width="220" />
        <el-table-column prop="sample_type" label="类型" width="90" />
        <el-table-column prop="preview_text" label="预览" min-width="260" />
        <el-table-column label="快照状态" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.snapshot_deleted_from_source" type="warning">源样本已删除</el-tag>
            <el-tag v-else type="success" effect="plain">引用有效</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="previewSample(row)">预览</el-button>
            <el-button link type="danger" @click="removeItem(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="mt-4 justify-end"
        background
        layout="prev, pager, next"
        :page-size="sampleQuery.size"
        :current-page="sampleQuery.page"
        :total="evalStore.detailTotal"
        @current-change="(page: number) => { sampleQuery.page = page; loadSamples(); }"
      />
    </section>

    <el-dialog v-model="previewVisible" title="样本预览" width="760px">
      <div v-if="previewPayload" class="preview-dialog">
        <el-alert
          v-if="previewPayload.snapshot_deleted_from_source"
          type="warning"
          :closable="false"
          title="源样本已删除，当前展示的是评测集内保存的快照内容。"
        />
        <img
          v-if="previewPayload.sample_type === 'image' && previewPayload.file_url"
          :src="previewPayload.file_url"
          :alt="previewPayload.sample_name || previewPayload.id"
          class="preview-image"
        />
        <pre v-else class="preview-text-block">{{ previewPayload.text_content || previewPayload.preview_text || "无文本内容" }}</pre>
        <pre v-if="previewPayload.annotation_data" class="preview-json">{{ JSON.stringify(previewPayload.annotation_data, null, 2) }}</pre>
      </div>
    </el-dialog>

    <el-drawer v-model="appendDrawerOpen" title="追加评测集样本" size="920px">
      <div class="append-grid">
        <section class="card-surface p-4">
          <div class="section-head">
            <h3>来源数据集样本</h3>
            <div class="flex gap-3">
              <el-select v-model="sourceSampleQuery.sample_type" clearable placeholder="样本类型" class="!w-[160px]" @change="loadSourceSamples">
                <el-option label="图片" value="image" />
                <el-option label="文本" value="text" />
              </el-select>
              <el-button @click="loadSourceSamples">刷新</el-button>
            </div>
          </div>
          <el-table :data="datasetStore.samples" v-loading="datasetStore.sampleLoading" height="420">
            <el-table-column label="选择" width="80">
              <template #default="{ row }">
                <el-checkbox :model-value="selectedSampleIds.includes(row.id)" @change="toggleAppendSample(row)" />
              </template>
            </el-table-column>
            <el-table-column prop="sample_name" label="样本" min-width="180" />
            <el-table-column prop="sample_type" label="类型" width="90" />
            <el-table-column prop="preview_text" label="预览" min-width="220" />
          </el-table>
        </section>

        <section class="card-surface p-4">
          <div class="section-head">
            <h3>待追加样本</h3>
            <span class="text-sm text-zinc-500">共 {{ selectedSamples.length }} 条</span>
          </div>
          <div v-if="selectedSamples.length" class="selected-list">
            <div v-for="sample in selectedSamples" :key="sample.id" class="selected-card">
              <div>
                <strong>{{ sample.sample_name || sample.id }}</strong>
                <p>{{ sample.preview_text || sample.text_content || "无预览" }}</p>
              </div>
              <el-button link type="danger" @click="toggleAppendSample(sample)">移除</el-button>
            </div>
          </div>
          <el-empty v-else description="请从左侧选择样本" />
        </section>
      </div>

      <template #footer>
        <div class="flex justify-end gap-3">
          <el-button @click="appendDrawerOpen = false">取消</el-button>
          <el-button type="primary" :loading="appendLoading" @click="submitAppend">追加</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-topbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 24px;
  border-radius: 24px;
  background: linear-gradient(135deg, #f4f8ef, #fff6e8);
}

.detail-topbar h2 {
  margin: 0;
  font-size: 28px;
  color: #17212c;
}

.detail-topbar p {
  margin: 0;
  color: #536171;
}

.detail-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.overview-card {
  padding: 20px;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}

.overview-card h3 {
  margin: 0 0 14px;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.overview-metrics span {
  display: block;
  color: #637083;
  font-size: 13px;
  margin-bottom: 6px;
}

.overview-metrics strong {
  color: #17212c;
  font-size: 18px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.preview-card {
  padding: 12px;
  border-radius: 16px;
  background: #f8fafc;
}

.preview-card img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 12px;
  margin-bottom: 8px;
}

.text-preview {
  min-height: 120px;
  padding: 12px;
  border-radius: 12px;
  background: #fff;
  color: #49566a;
  margin-bottom: 8px;
  white-space: pre-wrap;
}

.preview-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-image {
  width: 100%;
  max-height: 480px;
  object-fit: contain;
  border-radius: 16px;
  background: #f8fafc;
}

.preview-text-block,
.preview-json {
  max-height: 280px;
  overflow: auto;
  background: #101827;
  color: #e5edf7;
  padding: 16px;
  border-radius: 16px;
  white-space: pre-wrap;
  font-size: 12px;
}

.append-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.9fr);
  gap: 16px;
}

.selected-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.selected-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  background: #fffaf0;
  border: 1px solid #f2e5c9;
}

.selected-card p {
  margin: 6px 0 0;
  color: #5c6978;
  font-size: 13px;
}
</style>
