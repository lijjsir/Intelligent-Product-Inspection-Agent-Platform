<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ElMessage,
  type FormInstance,
  type FormRules,
  type UploadFile,
  type UploadFiles,
} from "element-plus";

import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { useTaskStore } from "@/stores/task.store";
import { useChatStore } from "@/stores/chat.store";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";
import type { TaskStatus } from "@/types/task.types";

const router = useRouter();
const route = useRoute();
const taskStore = useTaskStore();
const chatStore = useChatStore();
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
const uploadFiles = ref<UploadFile[]>([]);
const createForm = ref({
  product_id: "",
  spec_code: "",
  rag_space_id: "",
  image_urls_input: "",
  priority: 5,
});

const activeSpecOptions = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const isAdmin = computed(() => hasRole("admin"));
const canCreateTask = computed(() => hasRole(["user", "expert"]));

const rules: FormRules = {
  product_id: [
    { required: true, message: "请选择检测标准以自动填入产品线", trigger: "blur" },
    { max: 64, message: "产品线不能超过 64 个字符", trigger: "blur" },
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
    status: (filters.value.status || undefined) as TaskStatus | undefined,
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
  createForm.value = { product_id: "", spec_code: "", rag_space_id: "", image_urls_input: "", priority: 5 };
  uploadFiles.value = [];
  showCreateDialog.value = true;
}

function onSpecChange(specCode: string) {
  const spec = activeSpecOptions.value.find((s) => s.spec_code === specCode);
  if (spec) {
    createForm.value.product_id = spec.product_family || spec.product_id || "";
  }
}

function handleOpenCreateFromDraft() {
  const raw = sessionStorage.getItem("piap_quality_task_draft");
  sessionStorage.removeItem("piap_quality_task_draft");
  if (!raw) {
    handleOpenCreate();
    return;
  }
  try {
    const draft = JSON.parse(raw) as {
      product_id?: string;
      spec_code?: string;
      image_urls?: string[];
      priority?: number;
    };
    createForm.value = {
      product_id: String(draft.product_id || ""),
      spec_code: String(draft.spec_code || ""),
      rag_space_id: "",
      image_urls_input: Array.isArray(draft.image_urls) ? draft.image_urls.filter(Boolean).join("\n") : "",
      priority: Number(draft.priority || 5),
    };
    uploadFiles.value = [];
    showCreateDialog.value = true;
  } catch (error) {
    console.error(error);
    handleOpenCreate();
  }
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

async function fileToHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
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
    // Parse URL lines with optional #N prefix for sample number
    const urlLines = createForm.value.image_urls_input
      .split(/[\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const parsedUrls: { url: string; sample_number?: number }[] = [];
    for (const line of urlLines) {
      const match = line.match(/^#(\d+)\s+(.+)$/);
      if (match) {
        parsedUrls.push({ url: match[2].trim(), sample_number: parseInt(match[1]) });
      } else {
        parsedUrls.push({ url: line });
      }
    }
    const urlsFromText = parsedUrls.map((p) => p.url);
    const uploadFilesRaw: File[] = uploadFiles.value
      .map((item) => item.raw)
      .filter((item): item is NonNullable<typeof item> => item != null) as File[];
    const dataUrls = await Promise.all(uploadFilesRaw.map((item) => fileToDataUrl(item)));
    const allUrls = [...urlsFromText, ...dataUrls];

    // Build image_items with content hashes for uploaded files.
    const imageItems = await Promise.all(
      allUrls.map(async (url, i) => {
        const uploadFile = uploadFilesRaw[i - urlsFromText.length];
        if (uploadFile && i >= urlsFromText.length) {
          const sn = i < parsedUrls.length ? parsedUrls[i].sample_number : undefined;
          return { index: i, url, hash: await fileToHash(uploadFile), sample_number: sn };
        }
        // For URL-only entries, hash the URL string.
        const msgUint8 = new TextEncoder().encode(url);
        const urlHash = await crypto.subtle.digest("SHA-256", msgUint8);
        const urlHashHex = Array.from(new Uint8Array(urlHash))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        const sn = i < parsedUrls.length ? parsedUrls[i].sample_number : undefined;
        return { index: i, url, hash: urlHashHex, sample_number: sn };
      }),
    );

    const metadata: Record<string, unknown> = { source: "task_list" };
    const selectedSpace = createForm.value.rag_space_id
      ? chatStore.ragSpaces.find((s) => s.id === createForm.value.rag_space_id)
      : null;
    if (selectedSpace) {
      metadata.selected_rag_space_id = selectedSpace.id;
      metadata.selected_rag_space_name = selectedSpace.name;
      metadata.selected_rag_space = {
        id: selectedSpace.id,
        name: selectedSpace.name,
        description: selectedSpace.description,
      };
      metadata.selected_rag_scope_node_ids = [];
    }

    await taskStore.createTask({
      product_id: createForm.value.product_id.trim(),
      spec_code: createForm.value.spec_code.trim(),
      image_urls: allUrls,
      image_items: imageItems,
      priority: createForm.value.priority,
      metadata,
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
  await Promise.all([fetchData(), fetchSpecOptions(), chatStore.fetchRagSpaces()]);
  if (route.query.create === "1") {
    handleOpenCreateFromDraft();
  }
});

watch(
  () => route.query,
  async () => {
    syncFromRoute();
    await fetchData();
    if (route.query.create === "1" && !showCreateDialog.value) {
      handleOpenCreateFromDraft();
    }
  },
);
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">任务管理</h2>
        <p class="mt-2 text-sm text-zinc-500">这里展示所有真实物化后的检测任务。正式创建和执行只在质量检测任务页面完成。</p>
      </div>
      <el-button v-if="canCreateTask" type="primary" @click="handleOpenCreate">新建任务</el-button>
    </div>

    <div class="card-surface p-4">
      <el-form :model="filters" inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
        <el-form-item label="任务状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable class="!w-[160px]" size="small">
            <el-option label="待执行" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品编号">
          <el-input v-model="filters.product_id" placeholder="输入产品线" clearable size="small" @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item v-if="filters.ids" label="任务集合">
          <el-input v-model="filters.ids" readonly size="small" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" @click="handleSearch">查询</el-button>
          <el-button size="small" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="card-surface">
      <el-table :data="taskStore.items" v-loading="taskStore.loading" size="small" class="list-table">
        <el-table-column prop="id" label="任务 ID" min-width="260" show-overflow-tooltip />
        <el-table-column v-if="isAdmin" prop="org_slug" label="组织" width="120" />
        <el-table-column prop="product_id" label="产品线" width="150" />
        <el-table-column prop="spec_code" label="检测标准" width="180" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ row.status.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_kind" label="来源" width="160" />
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString("zh-CN", { hour12: false }) : "-" }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="router.push(`/app/tasks/${row.id}`)">查看详情</el-button>
            <el-button
              link
              type="danger"
              size="small"
              :loading="deletingTaskId === row.id"
              @click="handleDeleteTask(row.id)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end p-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          size="small"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <el-dialog v-model="showCreateDialog" title="新建检测任务" width="560px">
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="96px">
        <el-form-item label="检测标准" prop="spec_code">
          <el-select v-model="createForm.spec_code" filterable clearable placeholder="选择检测标准" class="!w-full" @change="onSpecChange">
            <el-option
              v-for="spec in activeSpecOptions"
              :key="spec.id"
              :label="`${spec.spec_code} · ${spec.name}`"
              :value="spec.spec_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线" prop="product_id">
          <div class="product-line-display">{{ createForm.product_id || '选择标准后自动填入' }}</div>
        </el-form-item>
        <el-form-item label="RAG空间">
          <el-select v-model="createForm.rag_space_id" filterable clearable placeholder="选择RAG空间" class="!w-full">
            <el-option
              v-for="space in chatStore.ragSpaces"
              :key="space.id"
              :label="space.name"
              :value="space.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="图片 URL" prop="image_urls_input">
          <el-input
            v-model="createForm.image_urls_input"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="每行一个URL；批量标号加 #N 前缀，如：#1 https://a.jpg"
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
            <el-button type="primary" plain size="small">选择本地图片</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG/WebP，最多 5 张。</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="createForm.priority" :min="1" :max="10" size="small" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-end gap-2">
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
      <p class="leading-relaxed text-zinc-700">删除后该任务不会再参与任务列表、仪表盘、稳定性和分析统计，是否继续？</p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="cancelDeleteTask">取消</el-button>
          <el-button type="danger" :loading="Boolean(deletingTaskId)" @click="confirmDeleteTask">删除</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.list-table :deep(.el-table__header th) {
  @apply text-zinc-500 font-medium text-[13px] bg-zinc-50;
}
.list-table :deep(.el-table__body tr:hover > td) {
  @apply bg-zinc-50;
}

.product-line-display {
  height: 32px;
  line-height: 32px;
  padding: 0 11px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #f3f4f6;
  color: #374151;
  font-size: 13px;
  font-weight: 600;
}
</style>
