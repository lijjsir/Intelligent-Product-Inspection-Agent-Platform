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

import { inspectionStandardApi } from "@/api/inspection-standard.api";
import { taskApi } from "@/api/task.api";
import { qualityRiskApi } from "@/api/quality-risk.api";
import type { QualityProductionBatch } from "@/types/quality-risk.types";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";
import { useTaskStore } from "@/stores/task.store";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import { formatCodeName, formatTaskEntityLabel } from "@/utils/master-data-labels";
import type { TaskCreationStandardChoice } from "@/types/task.types";
import type { TaskStatus } from "@/types/task.types";
import { formatServerDateTime } from "@/utils/date-time";
import { taskStatusLabel } from "@/utils/task-status";

const router = useRouter();
const route = useRoute();
const taskStore = useTaskStore();
const qualityRefs = useQualityReferenceStore();
const { hasRole, hasPermission } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref({ status: "", product_id: "", ids: "" });
const showCreateDialog = ref(false);
const creating = ref(false);
const loadingCreateOptions = ref(false);
const deletingTaskId = ref("");
const deleteDialogVisible = ref(false);
const pendingDeleteTaskId = ref("");
const formRef = ref<FormInstance>();
const uploadFiles = ref<UploadFile[]>([]);
const inspectionStandards = ref<TaskCreationStandardChoice[]>([]);
const availableBatches = ref<QualityProductionBatch[]>([]);
const batchesLoading = ref(false);
const createForm = ref({
  input_mode: "image" as "image" | "measurement" | "mixed" | "report",
  product_category_id: "",
  quality_product_id: "",
  quality_batch_id: "",
  inspection_standard_id: "",
  sample_ids: "",
  production_date: "",
  test_context: "",
  image_urls_input: "",
  priority: 5,
});

const isAdmin = computed(() => hasRole("admin"));
const isOrdinaryUser = computed(() => hasRole("user"));
const isExpert = computed(() => hasRole("expert"));
const canReadStandardDetails = computed(() => !isOrdinaryUser.value && hasPermission("inspection_standard_library_read"));
const canCreateTask = computed(() => hasRole(["user", "expert"]));
const isOpsView = computed(() => route.path.startsWith("/ops/"));
const listBasePath = computed(() => (isOpsView.value ? "/ops/tasks" : "/app/tasks"));
const pageTitle = computed(() => (isOpsView.value ? "任务查看" : isOrdinaryUser.value ? "我的任务" : isExpert.value ? "检测任务" : "任务管理"));
const pageDescription = computed(() =>
  isOpsView.value
    ? "这里查看平台侧已经物化的任务和执行状态，筛选、排查和跳转都保持在运维入口。"
    : isOrdinaryUser.value
      ? "创建检测任务，查看进度和结果，下载检测报告。"
      : isExpert.value ? "创建与跟踪检测任务，查看检测结果，并对待复核结果进行专家判定。"
        : "统一管理图片、测量和混合检测任务；任务完成后形成可追溯的正式检测结果。",
);

const availableProducts = computed(() =>
  qualityRefs.products.filter(
    (item) => !createForm.value.product_category_id || item.category_id === createForm.value.product_category_id,
  ),
);
const selectedCategory = computed(() => qualityRefs.categories.find((item) => item.id === createForm.value.product_category_id) || null);
const selectedProduct = computed(() => qualityRefs.products.find((item) => item.id === createForm.value.quality_product_id) || null);
const activeStandards = computed(() =>
  inspectionStandards.value.filter((item) => item.is_active),
);
const availableStandards = computed(() => {
  return activeStandards.value;
});
const selectedTaskStandard = computed(
  () =>
    activeStandards.value.find((item) => item.id === createForm.value.inspection_standard_id) ||
    null,
);
const parsedUrlEntries = computed(() => parseImageUrlLines(createForm.value.image_urls_input));
const inputModeLabel = computed(() => ({
  image: "图片观察",
  measurement: "实测数据",
  mixed: "图片 + 实测",
  report: "检测报告转录",
}[createForm.value.input_mode]));
const inputModeDescription = computed(() => ({
  image: "适合外观、裂纹、缺陷、颜色和形态等可从图像观察的项目。",
  measurement: "适合尺寸、质量、温度、比例等必须由设备或人工测量产生的项目。",
  mixed: "图片用于外观观察，实测记录用于数值条款；两类证据会分别留痕。",
  report: "适合已有实验室或抽检 PDF 报告，任务详情中逐项录入页码、项目、数值、方法和条件。",
}[createForm.value.input_mode]));
const totalSelectedImageCount = computed(
  () => parsedUrlEntries.value.length + uploadFiles.value.length,
);
const requiredImageCount = computed(() => selectedTaskStandard.value?.required_image_count || 1);

const rules: FormRules = {
  product_category_id: [{ required: true, message: "请选择产品类别", trigger: "change" }],
  inspection_standard_id: [{ required: true, message: "请选择检测标准", trigger: "change" }],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasUrl = Boolean(value?.trim());
        const hasUpload = uploadFiles.value.length > 0;
        if (createForm.value.input_mode === "measurement" || createForm.value.input_mode === "report") {
          callback();
          return;
        }
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

function requiresStructuredEvidence() {
  return ["measurement", "mixed", "report"].includes(createForm.value.input_mode);
}

function formatTaskTime(value?: string | null) {
  return formatServerDateTime(value, { includeSeconds: true }) || "-";
}

function formatStandardLabel(standard: TaskCreationStandardChoice) {
  return formatCodeName({ code: standard.spec_code, name: standard.name });
}

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

function getStatusType(status: string) {
  const map: Record<string, "info" | "primary" | "success" | "danger" | "warning"> = {
    pending: "info",
    queued: "warning",
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

async function fetchCreateOptions() {
  if (loadingCreateOptions.value) return;
  loadingCreateOptions.value = true;
  try {
    const [, standards] = await Promise.all([
      qualityRefs.loadProducts(),
      !canReadStandardDetails.value ? taskApi.creationOptions().then(({ data }) => data.data.standards)
        : inspectionStandardApi.list().then(({ data }) => data.data.items),
    ]);
    inspectionStandards.value = standards;
  } catch (error) {
    console.error(error);
    ElMessage.warning("产品类别、具体产品或检测标准加载失败，请稍后重试。");
  } finally {
    loadingCreateOptions.value = false;
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

function resetCreateForm() {
  createForm.value = {
    input_mode: "image",
    product_category_id: "",
    quality_product_id: "",
    quality_batch_id: "",
    inspection_standard_id: "",
    sample_ids: "",
    production_date: "",
    test_context: "",
    image_urls_input: "",
    priority: 5,
  };
  uploadFiles.value = [];
}

async function handleOpenCreate() {
  if (!canCreateTask.value) return;
  await fetchCreateOptions();
  resetCreateForm();
  showCreateDialog.value = true;
}

async function handleOpenCreateFromDraft() {
  if (!canCreateTask.value) return;
  await fetchCreateOptions();
  const raw = sessionStorage.getItem("piap_quality_task_draft");
  sessionStorage.removeItem("piap_quality_task_draft");
  if (!raw) {
    await handleOpenCreate();
    return;
  }
  try {
    const draft = JSON.parse(raw) as {
      product_id?: string;
      product_category_id?: string;
      quality_product_id?: string;
      spec_code?: string;
      inspection_standard_id?: string;
      image_urls?: string[];
      priority?: number;
    };
    resetCreateForm();
    const matchedStandard = activeStandards.value.find(
      (item) => item.id === draft.inspection_standard_id || item.spec_code === draft.spec_code,
    );
    const matchedProduct =
      qualityRefs.products.find((item) => item.id === draft.quality_product_id) ||
      qualityRefs.products.find((item) => item.name === draft.product_id || item.model === draft.product_id) ||
      null;
    createForm.value.product_category_id =
      draft.product_category_id || matchedProduct?.category_id || "";
    createForm.value.quality_product_id = matchedProduct?.id || "";
    createForm.value.inspection_standard_id = matchedStandard?.id || "";
    createForm.value.image_urls_input = Array.isArray(draft.image_urls)
      ? draft.image_urls.filter(Boolean).join("\n")
      : "";
    createForm.value.priority = Number(draft.priority || 5);
    showCreateDialog.value = true;
  } catch (error) {
    console.error(error);
    await handleOpenCreate();
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

async function textToHash(value: string): Promise<string> {
  const buffer = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
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
  if (totalCount === 0 && createForm.value.input_mode === "mixed") {
    throw new Error("请至少提供一张图片 URL 或上传一张图片");
  }
  if (totalCount === 0 && createForm.value.input_mode === "image") {
    throw new Error("图片观察任务至少需要一张图片");
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
    const sampleIds = createForm.value.sample_ids
      .split(/\r?\n|,|，/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (requiresStructuredEvidence() && !createForm.value.production_date) {
      throw new Error("实测、混合或报告任务必须填写产品生产日期");
    }
    if (requiresStructuredEvidence() && !sampleIds.length) {
      throw new Error("实测、混合或报告任务必须填写样品编号");
    }
    const metadata: Record<string, unknown> = {
      source: "task_list",
      input_mode: createForm.value.input_mode,
      sample_ids: sampleIds,
      production_date: createForm.value.production_date || null,
      test_context: createForm.value.test_context.trim() || null,
      product_category_name: selectedCategory.value?.name,
      quality_product_name: selectedProduct.value?.name,
      inspection_standard_name: selectedTaskStandard.value?.name,
    };

    const createdTask = await taskStore.createTask(
      {
        input_mode: createForm.value.input_mode,
        product_category_id: createForm.value.product_category_id,
        quality_product_id: createForm.value.quality_product_id || null,
        quality_batch_id: createForm.value.quality_batch_id || null,
        inspection_standard_id: createForm.value.inspection_standard_id,
        product_id: selectedProduct.value?.model || selectedProduct.value?.name || selectedCategory.value?.code,
        spec_code: selectedTaskStandard.value?.spec_code || undefined,
        image_urls: imageUrls,
        image_items: imageItems,
        priority: createForm.value.priority,
      metadata,
      },
      { suppressErrorToast: true },
    );
    showCreateDialog.value = false;
    ElMessage.success(
      createForm.value.input_mode === "image"
        ? "任务已创建并开始图片检测"
        : "任务已创建，等待补充实测或报告证据",
    );
    await router.push(`${listBasePath.value}/${createdTask.id}`);
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

watch(
  () => createForm.value.product_category_id,
  () => {
    if (!availableProducts.value.some((item) => item.id === createForm.value.quality_product_id)) {
      createForm.value.quality_product_id = "";
    }
  },
);

watch(() => createForm.value.quality_product_id, async (productId) => {
  createForm.value.quality_batch_id = "";
  availableBatches.value = [];
  batchesLoading.value = false;
  if (!productId) return;
  batchesLoading.value = true;
  try {
    const data = (await (isOrdinaryUser.value || !hasPermission("product_master_read") ? qualityRiskApi.productBatchOptions(productId) : qualityRiskApi.productBatches(productId))).data.data;
    if (createForm.value.quality_product_id === productId) availableBatches.value = data;
  } finally { if (createForm.value.quality_product_id === productId) batchesLoading.value = false; }
});

onMounted(async () => {
  syncFromRoute();
  const jobs = [fetchData()];
  if (canCreateTask.value) {
    jobs.push(fetchCreateOptions());
  }
  await Promise.all(jobs);
  if (canCreateTask.value && route.query.create === "1") {
    await handleOpenCreateFromDraft();
  }
});

watch(
  () => route.query,
  async () => {
    syncFromRoute();
    await fetchData();
    if (canCreateTask.value && route.query.create === "1" && !showCreateDialog.value) {
      await handleOpenCreateFromDraft();
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
      <div class="task-hero-actions">
      <el-button v-if="canCreateTask" class="hero-action" plain @click="handleOpenCreate"
        >新建任务</el-button
      >
      </div>
    </section>

    <div class="card-surface p-4">
      <el-form :model="filters" inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
        <el-form-item label="任务状态">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            class="!w-[160px]"
            size="small"
          >
            <el-option label="待执行" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品编号">
          <el-input
            v-model="filters.product_id"
            placeholder="输入 SKU 编码"
            clearable
            size="small"
            @keyup.enter="handleSearch"
          />
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
      <el-table
        :data="taskStore.items"
        v-loading="taskStore.loading"
        size="small"
        class="list-table"
      >
        <el-table-column prop="display_no" label="任务编号" min-width="260" show-overflow-tooltip />
        <el-table-column v-if="isAdmin" prop="org_slug" label="组织" width="120" />
        <el-table-column label="产品线" width="150">
          <template #default="{ row }">{{
            formatTaskEntityLabel(row.product_line_name, row.product_line_code || row.product_id)
          }}</template>
        </el-table-column>
        <el-table-column label="SKU" min-width="160">
          <template #default="{ row }">{{
            formatTaskEntityLabel(row.product_name, row.product_sku_code || row.product_id)
          }}</template>
        </el-table-column>
        <el-table-column label="批次" min-width="200">
          <template #default="{ row }">{{ row.batch_no || (row.quality_batch_display_no ? `原始批次号未知（${row.quality_batch_display_no}）` : "未提供") }}</template>
        </el-table-column>
        <el-table-column label="检测标准" min-width="180">
          <template #default="{ row }">{{ row.standard_name || row.spec_code || "-" }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{
              isOrdinaryUser ? taskStatusLabel(row.status) : row.status.toUpperCase()
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!isOrdinaryUser" prop="source_kind" label="来源" width="140" />
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">{{ formatTaskTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" :width="isOrdinaryUser ? 245 : 180" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="router.push(`${listBasePath}/${row.id}`)"
              >查看详情</el-button
            >
            <el-button v-if="row.has_result" link type="primary" size="small" @click="router.push(`/app/results/${row.id}`)">查看结果</el-button>
            <el-button
              v-if="row.status === 'awaiting_review' && row.source_kind === 'task_list' && !row.has_result"
              link
              type="warning"
              size="small"
              @click="router.push(`${listBasePath}/${row.id}`)"
            >
              重新检测
            </el-button>
            <el-button
              v-if="canCreateTask && !(row.supervision && row.status === 'done')"
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

    <el-dialog v-model="showCreateDialog" :title="isOrdinaryUser ? '新建检测任务' : '新建通用检测任务'" width="680px" top="3vh">
      <el-form
        ref="formRef"
        :model="createForm"
        :rules="rules"
        label-width="112px"
        v-loading="loadingCreateOptions"
      >
        <el-form-item label="产品类别" prop="product_category_id">
          <el-select
            v-model="createForm.product_category_id"
            filterable
            clearable
            placeholder="选择产品类别"
            class="!w-full"
          >
            <el-option
              v-for="category in qualityRefs.categories"
              :key="category.id"
              :label="formatCodeName(category)"
              :value="category.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="具体产品 / 型号">
          <el-select
            v-model="createForm.quality_product_id"
            filterable
            clearable
            placeholder="来源明确时选择，无法确认可留空"
            class="!w-full"
            :disabled="!createForm.product_category_id"
          >
            <el-option
              v-for="product in availableProducts"
              :key="product.id"
              :label="[product.brand, product.name, product.model].filter(Boolean).join(' · ')"
              :value="product.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.quality_product_id" label="产品批次（选填）">
          <el-select v-model="createForm.quality_batch_id" clearable filterable :loading="batchesLoading" placeholder="已知时选择批次，未知可留空" class="!w-full">
            <el-option v-for="batch in availableBatches" :key="batch.id" :value="batch.id" :label="batch.original_batch_no ? `${batch.original_batch_no} · ${batch.display_no || ''}` : `原始批次号未提供 · ${batch.display_no || ''}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="检测标准" prop="inspection_standard_id">
          <el-select
            v-model="createForm.inspection_standard_id"
            filterable
            clearable
            placeholder="选择适用检测标准"
            class="!w-full"
          >
            <el-option
              v-for="standard in availableStandards"
              :key="standard.id"
              :label="formatStandardLabel(standard)"
              :value="standard.id"
            />
          </el-select>
          <div
            v-if="createForm.product_category_id && availableStandards.length === 0"
            class="task-form-hint warning"
          >
            {{ isOrdinaryUser ? '暂无已发布的检测标准，请联系管理员配置后再创建任务。' : '当前暂无可用检测标准，请先到治理页配置标准和执行规则。' }}
          </div>
          <div v-if="selectedTaskStandard" class="task-spec-preview">
            <div class="task-spec-preview-title">
              {{ formatStandardLabel(selectedTaskStandard) }}
            </div>
            <div v-if="canReadStandardDetails" class="task-spec-preview-grid">
              <span>绑定规则</span
              ><strong>{{
                selectedTaskStandard.spec_name || selectedTaskStandard.spec_code
              }}</strong>
              <span>质检图片门槛</span><strong>{{ requiredImageCount }}</strong>
              <span>要求视角</span
              ><strong>{{ selectedTaskStandard.required_views?.join("、") || "未设置" }}</strong>
              <span>置信门槛</span
              ><strong>{{ selectedTaskStandard.ai_gate_confidence_threshold ?? "-" }}</strong>
              <span>证据门槛</span
              ><strong>{{ selectedTaskStandard.ai_gate_evidence_threshold ?? "-" }}</strong>
              <span>可追溯门槛</span
              ><strong>{{ selectedTaskStandard.ai_gate_traceability_threshold ?? "-" }}</strong>
              <span>自动放行</span
              ><strong>{{ selectedTaskStandard.auto_pass_enabled ? "开启" : "关闭" }}</strong>
            </div>
            <p v-else class="task-form-hint">请提供至少 {{ requiredImageCount }} 张图片{{ selectedTaskStandard.required_views?.length ? `，包含${selectedTaskStandard.required_views.join('、')}视角` : '' }}。标准已由管理员发布，无需配置。</p>
          </div>
        </el-form-item>
        <el-form-item label="检测输入" required>
          <el-radio-group v-model="createForm.input_mode" class="input-mode-grid">
            <el-radio-button value="image">图片观察</el-radio-button>
            <el-radio-button value="measurement">实测数据</el-radio-button>
            <el-radio-button value="mixed">图片 + 实测</el-radio-button>
            <el-radio-button value="report">报告转录</el-radio-button>
          </el-radio-group>
          <div class="task-form-hint input-mode-help"><strong>{{ inputModeLabel }}</strong>：{{ inputModeDescription }}</div>
        </el-form-item>
        <el-form-item v-if="requiresStructuredEvidence()" label="样品编号" required>
          <el-input v-model="createForm.sample_ids" type="textarea" :rows="2" placeholder="每行一个样品编号，例如 S-001、S-002" />
          <div class="task-form-hint">这些编号必须能在实测记录或检测报告中对应到具体样品。</div>
        </el-form-item>
        <el-form-item v-if="requiresStructuredEvidence()" label="产品生产日期" required>
          <el-date-picker v-model="createForm.production_date" type="date" value-format="YYYY-MM-DD" placeholder="选择产品生产日期" class="!w-full" />
        </el-form-item>
        <el-form-item v-if="requiresStructuredEvidence()" label="试验场景说明">
          <el-input v-model="createForm.test_context" type="textarea" :rows="2" placeholder="可填写温度、设备、方法、报告来源等背景；不要把未经核对的数值写在这里代替测量记录。" />
        </el-form-item>
        <el-form-item v-if="createForm.input_mode === 'image' || createForm.input_mode === 'mixed'" label="图片 URL" prop="image_urls_input">
          <el-input
            v-model="createForm.image_urls_input"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="每行一个 URL；批量标号加 #N 前缀，如：#1 https://a.jpg"
          />
          <div class="task-form-hint">
            图片 URL
            会直接参与检测，并和本地上传图片合并计算；证据不足或标准规则不完整时，结果会进入人工复核。当前
            URL 数量：{{ parsedUrlEntries.length }}。
          </div>
        </el-form-item>
        <el-form-item v-if="createForm.input_mode === 'image' || createForm.input_mode === 'mixed'" label="上传图片">
          <el-upload
            v-model:file-list="uploadFiles"
            :auto-upload="false"
            accept="image/*"
            multiple
            list-type="text"
            @change="handleUploadChange"
            @remove="handleUploadRemove"
          >
            <el-button type="primary" plain size="small">选择本地图片</el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 JPG/PNG/WebP，可一次多选；URL 与上传图片将合并参与质检。
              </div>
            </template>
          </el-upload>
          <div class="task-selection-summary">
            <span>当前已选</span>
            <strong>{{ totalSelectedImageCount }}</strong>
            <span>/ 当前标准参考</span>
            <strong>{{ requiredImageCount }}</strong>
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
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate"
            >确认创建</el-button
          >
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
      <p class="leading-relaxed text-zinc-700">
        删除后该任务不会再参与任务列表、仪表盘、稳定性和分析统计，是否继续？
      </p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="cancelDeleteTask">取消</el-button>
          <el-button type="danger" :loading="Boolean(deletingTaskId)" @click="confirmDeleteTask"
            >删除</el-button
          >
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

.task-form-hint.warning {
  color: #b45309;
}

.input-mode-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
}

.input-mode-grid :deep(.el-radio-button),
.input-mode-grid :deep(.el-radio-button__inner) {
  width: 100%;
}

.input-mode-help {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.input-mode-help strong {
  color: #1f2937;
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

  .input-mode-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
<style scoped>
.task-hero-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.task-hero-actions .el-button+.el-button { margin-left:0; }
</style>
