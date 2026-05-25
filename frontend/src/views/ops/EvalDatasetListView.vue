<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import { useDatasetStore } from "@/stores/dataset.store";
import { useEvalDatasetStore } from "@/stores/evalDataset.store";
import type { AlgoResourceStatus } from "@/types/algo-workspace.types";
import type { DatasetSample, DatasetSampleType } from "@/types/dataset.types";

const router = useRouter();
const evalStore = useEvalDatasetStore();
const datasetStore = useDatasetStore();

const query = reactive({
  page: 1,
  size: 20,
  keyword: "",
  status: "" as AlgoResourceStatus | "",
});

const sourceSampleQuery = reactive({
  page: 1,
  size: 12,
  sample_type: "" as DatasetSampleType | "",
});

const drawerOpen = ref(false);
const saving = ref(false);
const editingId = ref("");
const sourceDatasetId = ref("");
const form = reactive({
  name: "",
  description: "",
  config_json: "{}",
});
const selectedSamples = ref<DatasetSample[]>([]);
const selectedSampleIds = computed(() => selectedSamples.value.map((item) => item.id));

function resetForm() {
  editingId.value = "";
  form.name = "";
  form.description = "";
  form.config_json = "{}";
  selectedSamples.value = [];
  sourceSampleQuery.page = 1;
}

async function loadList() {
  await evalStore.fetchList(query);
}

async function loadSourceDatasets() {
  await datasetStore.fetchDatasets({ page: 1, size: 100, keyword: "", modality: "", status: "" } as any);
  if (!sourceDatasetId.value && datasetStore.items.length) {
    sourceDatasetId.value = datasetStore.items[0].id;
  }
}

async function loadSourceSamples() {
  if (!sourceDatasetId.value) return;
  await datasetStore.fetchSamples(sourceDatasetId.value, {
    page: sourceSampleQuery.page,
    size: sourceSampleQuery.size,
    sample_type: sourceSampleQuery.sample_type || undefined,
  });
}

async function loadAllEvalItems(resourceId: string) {
  const size = 100;
  let page = 1;
  let allItems: any[] = [];
  let total = 0;
  do {
    const data = await evalStore.fetchSamples(resourceId, {
      page,
      size,
      sample_type: undefined,
    });
    allItems = allItems.concat(data.items);
    total = data.total;
    page += 1;
  } while (allItems.length < total);
  return allItems;
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

async function openEdit(row: any) {
  resetForm();
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  form.config_json = JSON.stringify(row.config_json || {}, null, 2);
  const detail = await evalStore.fetchOne(row.id);
  sourceDatasetId.value = detail.source_dataset_id;
  await loadSourceSamples();
  const allItems = await loadAllEvalItems(row.id);
  selectedSamples.value = allItems.map((item: any) => ({
    id: item.dataset_sample_id || item.id,
    org_id: item.org_id,
    dataset_id: item.source_dataset_id,
    sample_type: item.sample_type,
    sample_name: item.sample_name,
    text_content: item.text_content,
    content_type: item.sample_type === "image" ? "image/*" : "text/plain",
    size_bytes: 0,
    checksum_sha256: "",
    file_url: item.file_url,
    annotation_data: item.annotation_data,
    source_metadata: item.source_metadata,
    preview_text: item.preview_text,
    created_at: item.created_at,
    updated_at: item.updated_at,
  }));
  drawerOpen.value = true;
}

function toggleSample(sample: DatasetSample) {
  const exists = selectedSamples.value.some((item) => item.id === sample.id);
  if (exists) {
    selectedSamples.value = selectedSamples.value.filter((item) => item.id !== sample.id);
    return;
  }
  selectedSamples.value = [...selectedSamples.value, sample];
}

function removeSelectedSample(sampleId: string) {
  selectedSamples.value = selectedSamples.value.filter((item) => item.id !== sampleId);
}

async function submit() {
  if (!sourceDatasetId.value) {
    ElMessage.warning("请选择来源数据集");
    return;
  }
  if (!selectedSampleIds.value.length) {
    ElMessage.warning("至少选择一个样本");
    return;
  }
  saving.value = true;
  try {
    const basePayload = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      config_json: JSON.parse(form.config_json || "{}"),
      sample_ids: selectedSampleIds.value,
    };
    if (editingId.value) {
      await evalStore.updateOne(editingId.value, basePayload);
      ElMessage.success("评测集已更新");
    } else {
      await evalStore.createOne({
        ...basePayload,
        source_dataset_id: sourceDatasetId.value,
      });
      ElMessage.success("评测集已创建");
    }
    drawerOpen.value = false;
    await loadList();
  } catch (error: any) {
    if (error instanceof SyntaxError) {
      ElMessage.error("配置 JSON 格式不正确");
    } else {
      throw error;
    }
  } finally {
    saving.value = false;
  }
}

async function removeRow(id: string) {
  await ElMessageBox.confirm("确定删除该评测集吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await evalStore.removeOne(id);
  ElMessage.success("评测集已删除");
  await loadList();
}

function openDetail(id: string) {
  router.push(`/ops/data/eval-sets/${id}`);
}

function resolveSourceDatasetName(row: any) {
  return row?.source_dataset_name || row?.source_dataset_id || "-";
}

onMounted(async () => {
  await Promise.all([loadList(), loadSourceDatasets()]);
  await loadSourceSamples();
});

watch(sourceDatasetId, async (next, prev) => {
  if (!next || next === prev) return;
  sourceSampleQuery.page = 1;
  if (!editingId.value) {
    selectedSamples.value = [];
  }
  await loadSourceSamples();
});
</script>

<template>
  <div class="eval-page">
    <AlgoWorkspaceHero
      title="测试集管理"
      description="基于现有数据集创建私有评测集快照，支持后续追加和移除样本。"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate">新增评测集</el-button>
      </template>
    </AlgoWorkspaceHero>

    <section class="card-surface p-4">
      <div class="toolbar">
        <el-input v-model="query.keyword" placeholder="搜索评测集名称" class="!w-[240px]" clearable />
        <el-select v-model="query.status" clearable placeholder="状态" class="!w-[180px]">
          <el-option label="draft" value="draft" />
          <el-option label="failed" value="failed" />
          <el-option label="queued" value="queued" />
          <el-option label="running" value="running" />
          <el-option label="completed" value="completed" />
          <el-option label="cancelled" value="cancelled" />
        </el-select>
        <el-button @click="loadList">刷新</el-button>
      </div>

      <el-table :data="evalStore.items" v-loading="evalStore.loading" class="mt-4">
        <el-table-column prop="name" label="名称" min-width="220" />
        <el-table-column label="来源数据集" min-width="220">
          <template #default="{ row }">
            <span>{{ resolveSourceDatasetName(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sample_count" label="样本数" width="100" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="removeRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑评测集' : '新增评测集'" size="1080px">
      <div class="drawer-grid">
        <section class="pane">
          <el-form label-position="top">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="输入评测集名称" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="来源数据集" required>
              <el-select v-model="sourceDatasetId" placeholder="选择数据集" :disabled="Boolean(editingId)">
                <el-option v-for="item in datasetStore.items" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="配置 JSON">
              <el-input v-model="form.config_json" type="textarea" :rows="6" />
            </el-form-item>
          </el-form>

          <div class="source-toolbar">
            <strong>来源样本</strong>
            <div class="flex gap-3">
              <el-select v-model="sourceSampleQuery.sample_type" clearable placeholder="样本类型" class="!w-[160px]" @change="loadSourceSamples">
                <el-option label="图片" value="image" />
                <el-option label="文本" value="text" />
              </el-select>
              <el-button @click="loadSourceSamples">刷新样本</el-button>
            </div>
          </div>

          <el-table :data="datasetStore.samples" v-loading="datasetStore.sampleLoading" height="420">
            <el-table-column label="选择" width="80">
              <template #default="{ row }">
                <el-checkbox :model-value="selectedSampleIds.includes(row.id)" @change="toggleSample(row)" />
              </template>
            </el-table-column>
            <el-table-column prop="sample_name" label="样本" min-width="180" />
            <el-table-column prop="sample_type" label="类型" width="90" />
            <el-table-column prop="preview_text" label="预览" min-width="220" />
          </el-table>
          <el-pagination
            class="mt-4 justify-end"
            background
            layout="prev, pager, next"
            :page-size="sourceSampleQuery.size"
            :current-page="sourceSampleQuery.page"
            :total="datasetStore.sampleTotal"
            @current-change="(page: number) => { sourceSampleQuery.page = page; loadSourceSamples(); }"
          />
        </section>

        <section class="pane selected-pane">
          <div class="source-toolbar">
            <strong>已选样本</strong>
            <span class="text-sm text-zinc-500">共 {{ selectedSamples.length }} 条</span>
          </div>
          <div v-if="selectedSamples.length" class="selected-list">
            <div v-for="sample in selectedSamples" :key="sample.id" class="selected-card">
              <div>
                <strong>{{ sample.sample_name || sample.id }}</strong>
                <p>{{ sample.preview_text || sample.text_content || "无预览" }}</p>
              </div>
              <el-button link type="danger" @click="removeSelectedSample(sample.id)">移除</el-button>
            </div>
          </div>
          <el-empty v-else description="请从左侧勾选至少一个样本" />
        </section>
      </div>

      <template #footer>
        <div class="flex justify-end gap-3">
          <el-button @click="drawerOpen = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.eval-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.drawer-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
  gap: 16px;
  height: 100%;
}

.pane {
  padding: 16px;
  border-radius: 20px;
  background: #f8fafc;
}

.selected-pane {
  background: linear-gradient(180deg, #fffdf7, #fff7ed);
}

.source-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
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
  background: #ffffff;
  border: 1px solid #f0e6d3;
}

.selected-card p {
  margin: 6px 0 0;
  color: #5c6978;
  font-size: 13px;
}
</style>
