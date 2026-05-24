<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { usePagination } from "@/composables/usePagination";
import { useDatasetStore } from "@/stores/dataset.store";
import type { DatasetCreateRequest, DatasetModality } from "@/types/dataset.types";
import { datasetModalityLabel, normalizeDatasetModality } from "@/utils/dataset-modality";

const route = useRoute();
const router = useRouter();
const store = useDatasetStore();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = reactive({
  keyword: "",
  modality: "" as DatasetModality | "",
  status: "" as "active" | "archived" | "",
});

const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref("");
const createAndUpload = ref(true);
const form = reactive<DatasetCreateRequest>({
  name: "",
  description: "",
  modality: "image+text",
  tags: [],
});
const modalitySelection = ref<string[]>(["image", "text"]);
const tagsInput = ref("");

watch(modalitySelection, () => {
  syncFormModality();
});

const activeCount = computed(() => store.items.filter((item) => item.status === "active").length);
const totalSamples = computed(() => store.items.reduce((sum, item) => sum + item.sample_count, 0));
const totalBytes = computed(() => store.items.reduce((sum, item) => sum + item.uploaded_bytes, 0));

function syncFromRoute() {
  filters.keyword = String(route.query.keyword || "");
  filters.modality = String(route.query.modality || "") as DatasetModality | "";
  filters.status = String(route.query.status || "") as "active" | "archived" | "";
  page.value = Number(route.query.page || 1);
}

async function fetchData() {
  const result = await store.fetchDatasets({
    page: page.value,
    size: pageSize.value,
    keyword: filters.keyword || undefined,
    modality: filters.modality || undefined,
    status: filters.status || undefined,
  });
  total.value = result.total;
}

function pushQuery() {
  router.push({
    path: "/ops/data/import",
    query: {
      ...(filters.keyword ? { keyword: filters.keyword } : {}),
      ...(filters.modality ? { modality: filters.modality } : {}),
      ...(filters.status ? { status: filters.status } : {}),
      page: String(page.value),
    },
  });
}

function handleSearch() {
  resetPage();
  pushQuery();
}

function handleReset() {
  filters.keyword = "";
  filters.modality = "";
  filters.status = "";
  resetPage();
  pushQuery();
}

function handleSizeChange(size: number) {
  onSizeChange(size);
  pushQuery();
}

function handleCurrentChange(current: number) {
  onPageChange(current);
  pushQuery();
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function modalityLabel(value: DatasetModality) {
  return datasetModalityLabel(value);
}

function resetForm() {
  editingId.value = "";
  form.name = "";
  form.description = "";
  form.modality = "image+text";
  form.tags = [];
  modalitySelection.value = ["image", "text"];
  createAndUpload.value = true;
  tagsInput.value = "";
}

function openCreate() {
  resetForm();
  dialogVisible.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  form.name = row.name;
  form.description = row.description || "";
  form.modality = normalizeDatasetModality(row.modality || "image+text");
  modalitySelection.value = form.modality.split("+");
  form.tags = [...(row.tags || [])];
  tagsInput.value = form.tags.join(", ");
  dialogVisible.value = true;
}

function syncFormModality() {
  form.modality = normalizeDatasetModality(modalitySelection.value);
}

function parseTags() {
  form.tags = tagsInput.value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写数据集名称");
    return;
  }
  syncFormModality();
  if (!form.modality) {
    ElMessage.warning("至少选择一种数据模态");
    return;
  }
  parseTags();
  saving.value = true;
  try {
    if (editingId.value) {
      await store.updateDataset(editingId.value, {
        name: form.name.trim(),
        description: form.description?.trim() || null,
        modality: form.modality,
        tags: form.tags,
      });
      ElMessage.success("数据集已更新");
    } else {
      const created = await store.createDataset({
        name: form.name.trim(),
        description: form.description?.trim() || "",
        modality: form.modality,
        tags: form.tags,
      });
      ElMessage.success("数据集已创建");
      if (createAndUpload.value) {
        dialogVisible.value = false;
        router.push(`/ops/data/import/${created.id}?tab=samples`);
        return;
      }
    }
    dialogVisible.value = false;
    await fetchData();
  } finally {
    saving.value = false;
  }
}

async function remove(row: any) {
  await ElMessageBox.confirm(`删除数据集「${row.name}」后，其样本也会一起移除。是否继续？`, "删除数据集", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await store.removeDataset(row.id);
  ElMessage.success("数据集已删除");
  await fetchData();
}

function openDetail(id: string) {
  router.push(`/ops/data/import/${id}`);
}

onMounted(async () => {
  syncFromRoute();
  await fetchData();
});

watch(
  () => route.query,
  async () => {
    syncFromRoute();
    await fetchData();
  },
);
</script>

<template>
  <div class="dataset-page">
    <section class="dataset-hero">
      <div>
        <p class="eyebrow">Algorithm Workspace</p>
        <h2>数据接入</h2>
        <p>面向算法工程师管理训练前样本，先打通图片与文本的手动接入、浏览和预处理闭环。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建数据集</el-button>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span>数据集数</span>
        <strong>{{ total }}</strong>
      </article>
      <article class="metric-card">
        <span>活跃数据集</span>
        <strong>{{ activeCount }}</strong>
      </article>
      <article class="metric-card">
        <span>样本总量</span>
        <strong>{{ totalSamples }}</strong>
      </article>
      <article class="metric-card">
        <span>已上传容量</span>
        <strong>{{ formatBytes(totalBytes) }}</strong>
      </article>
    </section>

    <section class="card-surface p-4">
      <el-form inline class="dataset-filters">
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="数据集名称或描述" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="模态">
          <el-select v-model="filters.modality" clearable placeholder="全部模态" class="!w-[180px]">
            <el-option label="图片" value="image" />
            <el-option label="文本" value="text" />
            <el-option label="视频" value="video" />
            <el-option label="图片 + 视频" value="image+video" />
            <el-option label="图片 + 文本" value="image+text" />
            <el-option label="视频 + 文本" value="video+text" />
            <el-option label="图片 + 视频 + 文本" value="image+video+text" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" class="!w-[160px]">
            <el-option label="活跃" value="active" />
            <el-option label="归档" value="archived" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="card-surface">
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="name" label="数据集" min-width="220">
          <template #default="{ row }">
            <div class="dataset-name-cell">
              <button class="link-button" @click="openDetail(row.id)">{{ row.name }}</button>
              <span class="dataset-subline">{{ row.description || "暂无描述" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模态" width="130">
          <template #default="{ row }">
            <el-tag effect="plain">{{ modalityLabel(row.modality) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="样本统计" min-width="180">
          <template #default="{ row }">
            <div class="compact-stack">
              <span>总数 {{ row.sample_count }}</span>
              <span>图 {{ row.image_sample_count }} / 视 {{ row.video_sample_count }} / 文 {{ row.text_sample_count }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="容量" width="120">
          <template #default="{ row }">{{ formatBytes(row.uploaded_bytes) }}</template>
        </el-table-column>
        <el-table-column label="扩展状态" min-width="200">
          <template #default="{ row }">
            <div class="compact-stack">
              <span>图谱 {{ row.knowledge_graph_status }}</span>
              <span>对齐 {{ row.alignment_status }} / 增强 {{ row.augmentation_status }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="mt-4 flex justify-end">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑数据集' : '新建数据集'" width="560px">
      <el-form label-position="top">
        <el-form-item label="数据集名称" required>
          <el-input v-model="form.name" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="支持模态">
          <el-checkbox-group v-model="modalitySelection">
            <el-checkbox value="image">图片</el-checkbox>
            <el-checkbox value="video">视频</el-checkbox>
            <el-checkbox value="text">文本</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="tagsInput" placeholder="用逗号分隔，例如：缺陷, OLED, 训练集" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="创建后操作">
          <el-switch v-model="createAndUpload" active-text="创建后立即添加数据" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.dataset-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dataset-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 30px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(14, 116, 144, 0.16), transparent 28%),
    linear-gradient(135deg, #fffdf8 0%, #f0f9ff 100%);
  border: 1px solid rgba(14, 116, 144, 0.12);
}

.dataset-hero h2 {
  margin: 4px 0 8px;
  font-size: 28px;
  color: #0f172a;
}

.dataset-hero p {
  margin: 0;
  max-width: 760px;
  color: #475569;
  line-height: 1.7;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.metric-card {
  padding: 18px 20px;
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.metric-card span {
  display: block;
  color: #64748b;
  font-size: 13px;
  margin-bottom: 10px;
}

.metric-card strong {
  font-size: 28px;
  color: #0f172a;
}

.dataset-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: flex-end;
}

.dataset-name-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dataset-subline {
  font-size: 12px;
  color: #64748b;
}

.compact-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #334155;
  font-size: 13px;
}

.link-button {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  color: #0f766e;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
</style>
