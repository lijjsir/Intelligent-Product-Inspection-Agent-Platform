<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { useDatasetStore } from "@/stores/dataset.store";
import { useEvalDatasetStore } from "@/stores/evalDataset.store";
import { useModelConfigStore } from "@/stores/model_config.store";
import { useTrainingJobStore } from "@/stores/trainingJob.store";
import type { AlgoListQuery, TrainingJob } from "@/types/algo-workspace.types";

const router = useRouter();
const store = useTrainingJobStore();
const datasetStore = useDatasetStore();
const evalStore = useEvalDatasetStore();
const modelConfigStore = useModelConfigStore();
const drawerOpen = ref(false);
const saving = ref(false);
const actionLoadingId = ref("");
const editingId = ref("");
const query = reactive<AlgoListQuery>({
  page: 1,
  size: 20,
  keyword: "",
  status: "",
});
const form = reactive({
  name: "",
  description: "",
  config_json: "{}",
});
const refs = reactive({
  source_dataset_id: "",
  model_config_id: "",
  eval_set_id: "",
});

const datasetNameMap = computed(() => new Map(datasetStore.items.map((item) => [item.id, item.name])));
const evalNameMap = computed(() => new Map(evalStore.items.map((item) => [item.id, item.name])));

function resetForm() {
  editingId.value = "";
  form.name = "";
  form.description = "";
  form.config_json = "{}";
  refs.source_dataset_id = datasetStore.items[0]?.id || "";
  refs.model_config_id = modelConfigStore.items.find((item) => item.is_active && ["chat", "multimodal"].includes(item.model_type))?.id || "";
  refs.eval_set_id = "";
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(row: TrainingJob) {
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  form.config_json = JSON.stringify(row.config_json || {}, null, 2);
  refs.source_dataset_id = row.source_dataset_id;
  refs.model_config_id = row.model_config_id || "";
  refs.eval_set_id = row.eval_set_id || "";
  drawerOpen.value = true;
}

async function loadRefs() {
  await Promise.all([
    datasetStore.fetchDatasets({ page: 1, size: 100, keyword: "", modality: "", status: "" }),
    evalStore.fetchList({ page: 1, size: 100, keyword: "", status: "" }),
    modelConfigStore.fetchAll(),
  ]);
  if (!refs.source_dataset_id) {
    refs.source_dataset_id = datasetStore.items[0]?.id || "";
  }
  if (!refs.model_config_id) {
    refs.model_config_id = modelConfigStore.items.find((item) => item.is_active && ["chat", "multimodal"].includes(item.model_type))?.id || "";
  }
}

async function loadList() {
  await store.fetchList(query);
}

async function loadPage() {
  await Promise.all([loadRefs(), loadList()]);
}

async function submit() {
  if (!refs.source_dataset_id) {
    ElMessage.warning("请选择来源数据集");
    return;
  }
  if (!refs.model_config_id) {
    ElMessage.warning("请选择训练模型");
    return;
  }
  saving.value = true;
  try {
    const basePayload = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      config_json: JSON.parse(form.config_json || "{}"),
    };
    if (editingId.value) {
      await store.updateOne(editingId.value, {
        ...basePayload,
        model_config_id: refs.model_config_id,
        eval_set_id: refs.eval_set_id || null,
      });
      ElMessage.success("训练任务已更新");
    } else {
      await store.createOne({
        ...basePayload,
        source_dataset_id: refs.source_dataset_id,
        model_config_id: refs.model_config_id,
        eval_set_id: refs.eval_set_id || null,
      });
      ElMessage.success("训练任务已创建");
    }
    drawerOpen.value = false;
    await loadList();
  } catch (error) {
    if (error instanceof SyntaxError) {
      ElMessage.error("配置 JSON 格式不正确");
      return;
    }
    throw error;
  } finally {
    saving.value = false;
  }
}

async function openDetail(id: string) {
  await router.push(`/ops/training/jobs/${id}`);
}

async function launch(id: string) {
  actionLoadingId.value = id;
  try {
    await store.launchOne(id);
    ElMessage.success("已启动");
    await loadList();
  } finally {
    actionLoadingId.value = "";
  }
}

async function cancel(id: string) {
  actionLoadingId.value = id;
  try {
    await store.cancelOne(id);
    ElMessage.success("已取消");
    await loadList();
  } finally {
    actionLoadingId.value = "";
  }
}

async function remove(id: string) {
  await ElMessageBox.confirm("确定删除该训练任务吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  actionLoadingId.value = id;
  try {
    await store.removeOne(id);
    ElMessage.success("已删除");
    await loadList();
  } finally {
    actionLoadingId.value = "";
  }
}

function statusTagType(status?: string | null) {
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "info";
  return "primary";
}

onMounted(loadPage);
</script>

<template>
  <div class="training-page">
    <section class="hero">
      <div>
        <h2>训练任务</h2>
        <p>管理训练任务骨架，支持创建、编辑、启动、取消和查看执行结果占位信息。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建训练任务</el-button>
    </section>

    <section class="card-surface p-4">
      <div class="toolbar">
        <el-input v-model="query.keyword" placeholder="搜索任务名称" class="!w-[240px]" clearable />
        <el-select v-model="query.status" clearable placeholder="状态" class="!w-[180px]">
          <el-option label="draft" value="draft" />
          <el-option label="queued" value="queued" />
          <el-option label="running" value="running" />
          <el-option label="completed" value="completed" />
          <el-option label="failed" value="failed" />
          <el-option label="cancelled" value="cancelled" />
        </el-select>
        <el-button @click="loadList">刷新</el-button>
      </div>

      <el-table :data="store.items" v-loading="store.loading" class="mt-4">
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column label="来源数据集" min-width="180">
          <template #default="{ row }">{{ datasetNameMap.get(row.source_dataset_id) || row.source_dataset_id || "-" }}</template>
        </el-table-column>
        <el-table-column label="评测集" min-width="180">
          <template #default="{ row }">{{ row.eval_set_id ? (evalNameMap.get(row.eval_set_id) || row.eval_set_id) : "-" }}</template>
        </el-table-column>
        <el-table-column label="训练模型" min-width="220">
          <template #default="{ row }">{{ row.model_config_ref?.display_name || row.model_config_ref?.model_key || row.model_config_id || "-" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="execution_mode" label="执行模式" width="140" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
            <el-button v-if="['draft', 'failed'].includes(row.status)" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="['draft', 'failed'].includes(row.status)" link type="success" :loading="actionLoadingId === row.id" @click="launch(row.id)">启动</el-button>
            <el-button v-if="['queued', 'running'].includes(row.status)" link type="warning" :loading="actionLoadingId === row.id" @click="cancel(row.id)">取消</el-button>
            <el-button link type="danger" :loading="actionLoadingId === row.id" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑训练任务' : '新建训练任务'" size="720px">
      <el-form label-position="top">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="输入任务名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="来源数据集" required>
          <el-select v-model="refs.source_dataset_id" placeholder="选择数据集" :disabled="Boolean(editingId)">
            <el-option v-for="item in datasetStore.items" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="训练模型" required>
          <el-select v-model="refs.model_config_id" placeholder="选择模型配置">
            <el-option
              v-for="item in modelConfigStore.items.filter((config) => config.is_active && ['chat', 'multimodal'].includes(config.model_type))"
              :key="item.id"
              :label="`${item.display_name} (${item.model_key})`"
              :value="item.id"
            />
          </el-select>
          <div v-if="!modelConfigStore.items.some((config) => config.is_active && ['chat', 'multimodal'].includes(config.model_type))" class="mt-2 text-xs text-zinc-500">
            暂无可用模型配置，请先在模型配置中创建并启用 chat 或 multimodal 模型。
          </div>
        </el-form-item>
        <el-form-item label="评测集">
          <el-select v-model="refs.eval_set_id" clearable placeholder="选择评测集">
            <el-option v-for="item in evalStore.items" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置 JSON">
          <el-input v-model="form.config_json" type="textarea" :rows="10" />
        </el-form-item>
      </el-form>
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
.training-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero,
.card-surface {
  border-radius: 24px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 24px;
  background: linear-gradient(135deg, #f3f7f0, #fff6e8);
}

.hero h2 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  color: #17212c;
}

.hero p {
  margin: 0;
  color: #526071;
}

.toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
