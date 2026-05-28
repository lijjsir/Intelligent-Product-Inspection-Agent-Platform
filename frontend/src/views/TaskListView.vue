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
import { useAuthStore } from "@/stores/auth.store";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";
import { sha256Hex } from "@/utils/browserCrypto";
import { formatServerDateTime } from "@/utils/date-time";
import type { InspectionTask, TaskStatus } from "@/types/task.types";

const router = useRouter();
const route = useRoute();
const taskStore = useTaskStore();
const chatStore = useChatStore();
const inspectionSpecStore = useInspectionSpecStore();
const auth = useAuthStore();
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
const MAX_IMAGE_COUNT = 5;
const createForm = ref({
  product_id: "",
  spec_code: "",
  rag_space_id: "",
  image_urls_input: "",
  priority: 5,
});

const activeSpecOptions = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const selectedTaskSpec = computed(
  () => activeSpecOptions.value.find((item) => item.spec_code === createForm.value.spec_code) || null,
);
const parsedUrlEntries = computed(() => parseImageUrlLines(createForm.value.image_urls_input));
const totalSelectedImageCount = computed(() => parsedUrlEntries.value.length + uploadFiles.value.length);
const isAdmin = computed(() => hasRole("admin"));
const canCreateTask = computed(() => hasRole(["user", "expert"]));
const isOpsView = computed(() => route.path.startsWith("/ops/"));
const listBasePath = computed(() => (isOpsView.value ? "/ops/tasks" : "/app/tasks"));
const pageTitle = computed(() => (isOpsView.value ? "任务查看" : "任务管理"));
const pageDescription = computed(() =>
  isOpsView.value
    ? "这里查看平台侧已经物化的任务和执行状态，筛选、排查和跳转都保持在运维入口。"
    : "这里展示用户侧创建和执行的检测任务，也可以继续新建任务。"
);

function parseImageUrlLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^#(\d+)\s+(.+)$/);
      if (!match) return { url: line };
      return { url: match[2].trim(), sample_number: Number.parseInt(match[1], 10) };
    });
}

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

function canDeleteTask(row: InspectionTask) {
  return canCreateTask.value && row.created_by === auth.userId;
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
    await inspectionSpecStore.fetchAll({ suppressErrorToast: true });
  } catch (error) {
    console.error(error);
    ElMessage.warning("检测标准列表加载失败，手动创建任务时可能无法直接选择标准。");
  }
}

function handleSearch() {
  resetPage();
  router.push({
    path: listBasePath.value,
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
  router.push({ path: listBasePath.value, query: { page: "1" } });
}

function handleOpenCreate() {
  if (!canCreateTask.value) return;
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
  if (!canCreateTask.value) return;
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
  return sha256Hex(buffer);
}

async function textToHash(value: string): Promise<string> {
  return sha256Hex(value);
}

function extractTaskCreateErrorMessage(error: any) {
  const message = error?.response?.data?.message;
  if (typeof message === "string" && message.trim()) return message;
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail.find((item) => typeof item?.msg === "string" && item.msg.trim());
    if (first?.msg) return String(first.msg);
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return "任务创建失败，请稍后重试。";
}

async function buildImageSubmissionPayload() {
  const uploadFilesRaw: File[] = uploadFiles.value
    .map((item) => item.raw)
    .filter((item): item is NonNullable<typeof item> => item != null) as File[];

  const urlEntries = parsedUrlEntries.value;
  const totalCount = urlEntries.length + uploadFilesRaw.length;
  if (totalCount === 0) {
    throw new Error("请至少提供一张图片 URL 或上传一张图片");
  }
  if (totalCount > MAX_IMAGE_COUNT) {
    throw new Error(`当前共选择 ${totalCount} 张图片，最多只能提交 ${MAX_IMAGE_COUNT} 张`);
  }

  const [dataUrls, uploadHashes, urlHashes] = await Promise.all([
    Promise.all(uploadFilesRaw.map((item) => fileToDataUrl(item))),
    Promise.all(uploadFilesRaw.map((item) => fileToHash(item))),
    Promise.all(urlEntries.map((item) => textToHash(item.url))),
  ]);

  const duplicateGroups = new Map<string, string[]>();
  urlEntries.forEach((item, index) => {
    const label = item.sample_number != null ? `样品${item.sample_number}` : `URL图片${index + 1}`;
    const hash = urlHashes[index];
    duplicateGroups.set(hash, [...(duplicateGroups.get(hash) || []), label]);
  });
  uploadFilesRaw.forEach((file, index) => {
    const label = file.name?.trim() || `图片${urlEntries.length + index + 1}`;
    const hash = uploadHashes[index];
    duplicateGroups.set(hash, [...(duplicateGroups.get(hash) || []), label]);
  });

  const duplicateDescriptions = Array.from(duplicateGroups.values())
    .filter((items) => items.length > 1)
    .map((items) => Array.from(new Set(items)).join("、"));
  if (duplicateDescriptions.length > 0) {
    throw new Error(`检测到重复图片：${duplicateDescriptions.join("；")}，请删除重复图片后重试`);
  }

  const imageItems = [
    ...urlEntries.map((item, index) => ({
      index,
      url: item.url,
      hash: urlHashes[index],
      sample_number: item.sample_number,
    })),
    ...dataUrls.map((url, index) => ({
      index: urlEntries.length + index,
      url,
      hash: uploadHashes[index],
    })),
  ];

  const requiredImageCount = selectedTaskSpec.value?.required_image_count || 1;
  if (imageItems.length < requiredImageCount) {
    throw new Error(
      `标准 ${createForm.value.spec_code.trim()} 至少需要 ${requiredImageCount} 张图片，当前仅提供 ${imageItems.length} 张`,
    );
  }

  return {
    imageUrls: [...urlEntries.map((item) => item.url), ...dataUrls],
    imageItems,
  };
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
    const { imageUrls, imageItems } = await buildImageSubmissionPayload();

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
      image_urls: imageUrls,
      image_items: imageItems,
      priority: createForm.value.priority,
      metadata,
    }, { suppressErrorToast: true });
    ElMessage.success("任务创建成功");
    showCreateDialog.value = false;
    await fetchData();
  } catch (error) {
    console.error(error);
    ElMessage.error(extractTaskCreateErrorMessage(error));
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
  const jobs = [fetchData()];
  if (canCreateTask.value) {
    jobs.push(fetchSpecOptions(), chatStore.fetchRagSpaces());
  }
  await Promise.all(jobs);
  if (canCreateTask.value && route.query.create === "1") {
    handleOpenCreateFromDraft();
  }
});

watch(
  () => route.query,
  async () => {
    syncFromRoute();
    await fetchData();
    if (canCreateTask.value && route.query.create === "1" && !showCreateDialog.value) {
      handleOpenCreateFromDraft();
    }
  },
);
</script>

<template>
  <div class="task-page">
    <section class="task-hero">
      <div>
        <p class="eyebrow">{{ isOpsView ? "Platform Task Desk" : "Inspection Task Desk" }}</p>
        <h2>{{ pageTitle }}</h2>
        <p>{{ pageDescription }}</p>
      </div>
      <el-button v-if="canCreateTask" class="hero-action" plain @click="handleOpenCreate">新建任务</el-button>
    </section>

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
            {{ formatServerDateTime(row.created_at) || "-" }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="router.push(`${listBasePath}/${row.id}`)">查看详情</el-button>
            <el-button
              v-if="canDeleteTask(row)"
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

    <el-dialog v-model="showCreateDialog" title="新建检测任务" width="620px">
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
          <div v-if="selectedTaskSpec" class="task-spec-preview">
            <div class="task-spec-preview-title">{{ selectedTaskSpec.spec_code }} · {{ selectedTaskSpec.name }}</div>
            <div class="task-spec-preview-grid">
              <span>产品线</span><strong>{{ selectedTaskSpec.product_family || selectedTaskSpec.product_id || "未设置" }}</strong>
              <span>至少图片</span><strong>{{ selectedTaskSpec.required_image_count }}</strong>
              <span>要求视角</span><strong>{{ selectedTaskSpec.required_views?.join("、") || "未设置" }}</strong>
              <span>自动放行</span><strong>{{ selectedTaskSpec.auto_pass_enabled ? "开启" : "关闭" }}</strong>
            </div>
          </div>
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
          <div class="task-form-hint">
            图片 URL 会直接参与检测，并和本地上传图片合并计算。当前 URL 数量：{{ parsedUrlEntries.length }}。
          </div>
        </el-form-item>
        <el-form-item label="上传图片">
          <el-upload
            v-model:file-list="uploadFiles"
            :auto-upload="false"
            accept="image/*"
            :limit="5"
            multiple
            list-type="text"
            @change="handleUploadChange"
            @remove="handleUploadRemove"
          >
            <el-button type="primary" plain size="small">选择本地图片</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 JPG/PNG/WebP，可一次多选；URL 与上传合计最多 5 张。</div>
            </template>
          </el-upload>
          <div class="task-selection-summary">
            <span>当前已选</span>
            <strong>{{ totalSelectedImageCount }}</strong>
            <span>/ 需要至少</span>
            <strong>{{ selectedTaskSpec?.required_image_count || 1 }}</strong>
            <span>张</span>
          </div>
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
.task-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(180, 83, 9, 0.18), transparent 24%),
    radial-gradient(circle at right top, rgba(245, 158, 11, 0.18), transparent 25%),
    linear-gradient(180deg, #fff7ed 0%, #f1f5f9 100%);
}

.task-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 88% 16%, rgba(251, 191, 36, 0.24), transparent 28%),
    linear-gradient(135deg, #2a1708 0%, #7c2d12 48%, #b45309 100%);
  color: #f8fafc;
  box-shadow: 0 24px 60px rgba(124, 45, 18, 0.18);
}

.task-hero .eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.76;
}

.task-hero h2 {
  margin: 0;
  font-size: 40px;
  line-height: 1.1;
}

.task-hero p:not(.eyebrow) {
  max-width: 840px;
  margin: 12px 0 0;
  color: rgba(248, 250, 252, 0.82);
  line-height: 1.7;
}

.hero-action {
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
  font-weight: 700;
}

.hero-action:hover,
.hero-action:focus {
  border-color: rgba(255, 255, 255, 0.44);
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

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

.task-spec-preview {
  margin-top: 12px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(180, 83, 9, 0.12);
  background: linear-gradient(135deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
}

.task-spec-preview-title {
  font-size: 14px;
  font-weight: 700;
  color: #9a3412;
}

.task-spec-preview-grid {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px 12px;
  margin-top: 10px;
  font-size: 13px;
  color: #6b7280;
}

.task-spec-preview-grid strong {
  color: #1f2937;
  font-weight: 600;
}

.task-form-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
}

.task-selection-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 999px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
}

.task-selection-summary strong {
  font-size: 14px;
}

@media (max-width: 780px) {
  .task-page {
    padding: 14px;
  }

  .task-hero {
    flex-direction: column;
  }

  .task-hero h2 {
    font-size: 34px;
  }
}
</style>
