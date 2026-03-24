<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useTaskStore } from "@/stores/task.store";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import type { UploadFile, UploadFiles, UploadUserFile } from "element-plus";

const router = useRouter();
const route = useRoute();
const store = useTaskStore();
const { hasRole } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const filters = ref({ status: "", product_id: "" });

// --- Create Task Dialog State ---
const showCreateDialog = ref(false);
const creating = ref(false);
const formRef = ref<FormInstance>();
const createForm = ref({
  product_id: "",
  spec_id: "",
  image_urls_input: "",
  priority: 5,
});
const uploadFiles = ref<UploadUserFile[]>([]);

const rules: FormRules = {
  product_id: [
    { required: true, message: "产品编号不能为空", trigger: "blur" },
    { max: 64, message: "产品编号不超过 64 个字符", trigger: "blur" },
  ],
  spec_id: [
    { required: true, message: "检测规格不能为空", trigger: "blur" },
  ],
  image_urls_input: [
    {
      validator: (_rule, value: string, callback) => {
        const hasUrl = Boolean(value?.trim());
        const hasUpload = uploadFiles.value.length > 0;
        if (!hasUrl && !hasUpload) {
          callback(new Error("至少提供一个图像 URL 或上传一张图片"));
          return;
        }
        callback();
      },
      trigger: "blur",
    },
  ],
};

onMounted(() => {
  syncFromRoute();
  fetchData();
});

watch(() => route.query, () => {
  syncFromRoute();
  fetchData();
});

async function fetchData() {
  await store.fetchTasks({
    page: page.value,
    size: pageSize.value,
    status: filters.value.status || undefined,
    product_id: filters.value.product_id || undefined,
  });
  total.value = store.total;
}

function syncFromRoute() {
  filters.value = {
    status: String(route.query.status || ""),
    product_id: String(route.query.product_id || ""),
  };
  page.value = Number(route.query.page || 1);
}

function handleSearch() {
  resetPage();
  router.push({
    path: "/tasks",
    query: {
      ...(filters.value.status ? { status: filters.value.status } : {}),
      ...(filters.value.product_id ? { product_id: filters.value.product_id } : {}),
      page: String(page.value),
    },
  });
}

function handleReset() {
  filters.value = { status: "", product_id: "" };
  resetPage();
  router.push({ path: "/tasks", query: { page: "1" } });
}

function handleOpenCreate() {
  createForm.value = { product_id: "", spec_id: "", image_urls_input: "", priority: 5 };
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
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    
    creating.value = true;
    try {
      const urlsFromText = createForm.value.image_urls_input
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0);

      const dataUrls = await Promise.all(
        uploadFiles.value
          .map((f) => f.raw)
          .filter((raw): raw is File => Boolean(raw))
          .map((raw) => fileToDataUrl(raw))
      );

      const imageUrls = [...urlsFromText, ...dataUrls];
      if (imageUrls.length === 0) {
        ElMessage.error("请提供图像 URL 或上传图片");
        return;
      }

      await store.createTask({
        product_id: createForm.value.product_id,
        spec_id: createForm.value.spec_id,
        image_urls: imageUrls,
        priority: createForm.value.priority,
      });

      ElMessage.success("任务创建成功");
      showCreateDialog.value = false;
      // List will auto-update because store unshifts it, but we can refetch:
      fetchData();
    } catch (e: any) {
      // error handled globally by interceptor, but we catch it here just in case
      console.error(e);
    } finally {
      creating.value = false;
    }
  });
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  router.push({
    path: "/tasks",
    query: {
      ...(filters.value.status ? { status: filters.value.status } : {}),
      ...(filters.value.product_id ? { product_id: filters.value.product_id } : {}),
      page: String(page.value),
    },
  });
}

function handleCurrentChange(val: number) {
  onPageChange(val);
  router.push({
    path: "/tasks",
    query: {
      ...(filters.value.status ? { status: filters.value.status } : {}),
      ...(filters.value.product_id ? { product_id: filters.value.product_id } : {}),
      page: String(val),
    },
  });
}

const getStatusType = (status: string) => {
  const map: Record<string, "info"|"primary"|"success"|"danger"|"warning"> = {
    pending: "info",
    running: "primary",
    done: "success",
    failed: "danger",
    reviewing: "warning",
  };
  return map[status] || "info";
};
</script>

<template>
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">质检任务管理</h2>
        <p class="subtitle">查看和管理所有的产品缺陷检测任务</p>
      </div>
      <el-button v-if="hasRole(['org_admin', 'inspector'])" type="primary" @click="handleOpenCreate">
        + 新增任务
      </el-button>
    </div>

    <!-- Filters -->
    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline class="filter-form">
        <el-form-item label="任务状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 160px">
            <el-option label="待处理 (Pending)" value="pending" />
            <el-option label="运行中 (Running)" value="running" />
            <el-option label="已完成 (Done)" value="done" />
            <el-option label="失败 (Failed)" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品编号">
          <el-input v-model="filters.product_id" placeholder="输入产品ID搜索" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Table -->
    <el-card shadow="never" class="table-card">
      <el-table :data="store.items" v-loading="store.loading" border stripe style="width: 100%">
        <el-table-column prop="id" label="任务ID" width="300" show-overflow-tooltip />
        <el-table-column prop="product_id" label="产品编号" width="180" />
        <el-table-column prop="spec_id" label="检测规格" width="180" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="100" align="center" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/tasks/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper mt-4">
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

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建检测任务" width="500px">
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="100px">
        <el-form-item label="产品编号" prop="product_id">
          <el-input v-model="createForm.product_id" placeholder="如: PROD-123456" />
        </el-form-item>
        <el-form-item label="检测规格" prop="spec_id">
          <el-input v-model="createForm.spec_id" placeholder="如: SPEC-V1" />
        </el-form-item>
        <el-form-item label="图像 URLs" prop="image_urls_input">
          <el-input 
            v-model="createForm.image_urls_input" 
            type="textarea" 
            rows="4" 
            placeholder="可选：输入图像 URL，多个之间用逗号或换行分隔" 
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
              <div class="el-upload__tip">支持 JPG/PNG/WebP，最多 5 张。上传后会直接参与 AI 分析。</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="createForm.priority" :min="1" :max="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate">确定创建</el-button>
        </span>
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
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
}

.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
}
</style>
