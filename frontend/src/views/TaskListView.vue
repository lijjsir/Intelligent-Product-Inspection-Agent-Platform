<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ElMessage,
  type FormInstance,
  type FormRules,
  type UploadFile,
  type UploadFiles,
  type UploadUserFile,
} from "element-plus";

import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";

const router = useRouter();
const route = useRoute();
const taskStore = useTaskStore();
const inspectionSpecStore = useInspectionSpecStore();
const { hasRole } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref({ status: "", product_id: "", ids: "" });
const showCreateDialog = ref(false);
const creating = ref(false);
const deletingTaskId = ref("");
const deleteDialogVisible = ref(false);
const pendingDeleteTaskId = ref("");
const formRef = ref<FormInstance>();
const uploadFiles = ref<UploadUserFile[]>([]);
const createForm = ref({
  product_id: "",
  spec_code: "",
  image_urls_input: "",
  priority: 5,
});

const activeSpecOptions = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const isAdmin = computed(() => hasRole("admin"));
const canCreateTask = computed(() => hasRole(["user", "inspector"]));

const rules: FormRules = {
  product_id: [
    { required: true, message: "产品编号不能为空", trigger: "blur" },
    { max: 64, message: "产品编号不能超过 64 个字符", trigger: "blur" },
  ],
  spec_code: [{ required: true, message: "请选择检测标准", trigger: "change" }],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasUrl = Boolean(value?.trim());
        const hasUpload = uploadFiles.value.length > 0;
        if (!hasUrl && !hasUpload) {
          callback(new Error("请至少提供一张图片 URL 或上传一张图片"));
          return;
        }
        callback();
      },
      trigger: "blur",
    },
  ],
};

function getStatusType(status: string) {
  const map: Record<string, "info" | "primary" | "success" | "danger" | "warning"> = {
    pending: "info",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
}

function syncFromRoute() {
  filters.value = {
    status: String(route.query.status || ""),
    product_id: String(route.query.product_id || ""),
    ids: String(route.query.ids || ""),
  };
  page.value = Number(route.query.page || 1);
}

async function fetchData() {
  await taskStore.fetchTasks({
    page: page.value,
    size: pageSize.value,
    status: filters.value.status || undefined,
    product_id: filters.value.product_id || undefined,
    ids: filters.value.ids || undefined,
  });
  total.value = taskStore.total;
}

async function fetchSpecOptions() {
  try {
    await inspectionSpecStore.fetchAll();
  } catch (error) {
    console.error(error);
    ElMessage.warning("检测标准列表加载失败，手动创建任务时可能无法直接选择标准。");
  }
}

function handleSearch() {
  resetPage();
  router.push({
    path: "/app/tasks",
    query: {
      ...(filters.value.status ? { status: filters.value.status } : {}),
      ...(filters.value.product_id ? { product_id: filters.value.product_id } : {}),
      ...(filters.value.ids ? { ids: filters.value.ids } : {}),
      page: String(page.value),
    },
  });
}

function handleReset() {
  filters.value = { status: "", product_id: "", ids: "" };
  resetPage();
  router.push({ path: "/app/tasks", query: { page: "1" } });
}

function handleOpenCreate() {
  createForm.value = { product_id: "", spec_code: "", image_urls_input: "", priority: 5 };
  uploadFiles.value = [];
  showCreateDialog.value = true;
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

function handleUploadChange(_file: UploadFile, files: UploadFiles) {
  uploadFiles.value = files;
}

function handleUploadRemove(_file: UploadFile, files: UploadFiles) {
  uploadFiles.value = files;
}

async function handleSubmitCreate() {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
  } catch {
    return;
  }

  creating.value = true;
  try {
    const urlsFromText = createForm.value.image_urls_input
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const dataUrls = await Promise.all(
      uploadFiles.value
        .map((item) => item.raw)
        .filter((item): item is File => Boolean(item))
        .map((item) => fileToDataUrl(item)),
    );
    await taskStore.createTask({
      product_id: createForm.value.product_id.trim(),
      spec_code: createForm.value.spec_code.trim(),
      image_urls: [...urlsFromText, ...dataUrls],
      priority: createForm.value.priority,
      metadata: { source: "task_list" },
    });
    ElMessage.success("任务创建成功");
    showCreateDialog.value = false;
    await fetchData();
  } catch (error) {
    console.error(error);
    ElMessage.error("任务创建失败，请稍后重试。");
  } finally {
    creating.value = false;
  }
}

async function handleDeleteTask(taskId: string) {
  pendingDeleteTaskId.value = taskId;
  deleteDialogVisible.value = true;
}

function cancelDeleteTask() {
  deleteDialogVisible.value = false;
  pendingDeleteTaskId.value = "";
}

async function confirmDeleteTask() {
  if (!pendingDeleteTaskId.value) return;
  deletingTaskId.value = pendingDeleteTaskId.value;
  try {
    await taskStore.deleteTask(pendingDeleteTaskId.value);
    ElMessage.success("任务已删除");
    cancelDeleteTask();
    await fetchData();
  } catch (error: any) {
    console.error(error);
    ElMessage.error(error?.response?.data?.message || "删除任务失败，请稍后重试。");
  } finally {
    deletingTaskId.value = "";
  }
}

function handleSizeChange(size: number) {
  onSizeChange(size);
  handleSearch();
}

function handleCurrentChange(current: number) {
  onPageChange(current);
  handleSearch();
}

onMounted(async () => {
  syncFromRoute();
  await Promise.all([fetchData(), fetchSpecOptions()]);
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
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">任务管理</h2>
        <p class="subtitle">这里展示所有真实物化后的检测任务。聊天终态、聊天提交和手动创建都会进入同一任务主表。</p>
      </div>
      <el-button v-if="canCreateTask" type="primary" @click="handleOpenCreate">新建任务</el-button>
    </div>

    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline class="filter-form">
        <el-form-item label="任务状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 160px">
            <el-option label="待执行" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品编号">
          <el-input v-model="filters.product_id" placeholder="输入产品编号" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item v-if="filters.ids" label="任务集合">
          <el-input v-model="filters.ids" readonly />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="taskStore.items" v-loading="taskStore.loading" border stripe>
        <el-table-column prop="id" label="任务 ID" min-width="260" show-overflow-tooltip />
        <el-table-column v-if="isAdmin" prop="org_slug" label="组织" width="120" />
        <el-table-column prop="product_id" label="产品编号" width="150" />
        <el-table-column prop="spec_code" label="检测标准" width="180" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_kind" label="来源" width="160" />
        <el-table-column prop="source_graph" label="子图" width="150" />
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString("zh-CN", { hour12: false }) : "-" }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/app/tasks/${row.id}`)">查看详情</el-button>
            <el-button
              link
              type="danger"
              :loading="deletingTaskId === row.id"
              @click="handleDeleteTask(row.id)"
            >
              删除任务
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="新建检测任务" width="560px">
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="96px">
        <el-form-item label="产品编号" prop="product_id">
          <el-input v-model="createForm.product_id" placeholder="例如：P-1001" />
        </el-form-item>
        <el-form-item label="检测标准" prop="spec_code">
          <el-select v-model="createForm.spec_code" filterable clearable placeholder="选择检测标准" style="width: 100%">
            <el-option
              v-for="spec in activeSpecOptions"
              :key="spec.id"
              :label="`${spec.spec_code} · ${spec.name}`"
              :value="spec.spec_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="图片 URL" prop="image_urls_input">
          <el-input
            v-model="createForm.image_urls_input"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="每行一个 URL，也可以同时上传本地图片"
          />
        </el-form-item>
        <el-form-item label="上传图片">
          <el-upload
            v-model:file-list="uploadFiles"
            :auto-upload="false"
            accept="image/*"
            :limit="5"
            list-type="text"
            @change="handleUploadChange"
            @remove="handleUploadRemove"
          >
            <el-button type="primary" plain>选择本地图片</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG/WebP，最多 5 张。</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="createForm.priority" :min="1" :max="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate">确认创建</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteDialogVisible"
      title="删除任务"
      width="420px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <div class="delete-dialog-copy">删除后该任务不会再参与任务列表、仪表盘、稳定性和分析统计，是否继续？</div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="cancelDeleteTask">取消</el-button>
          <el-button type="danger" :loading="Boolean(deletingTaskId)" @click="confirmDeleteTask">删除</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.title {
  margin: 0 0 8px;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  font-size: 14px;
  color: #6b7280;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
}

.mb-4 {
  margin-bottom: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.delete-dialog-copy {
  line-height: 1.8;
  color: #374151;
}
</style>
